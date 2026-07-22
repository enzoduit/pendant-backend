import 'dart:async';
import 'dart:typed_data';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'audio_writer.dart';

const String kTargetMac = 'FD:04:D0:EB:84:88';
const Duration kSilenceTimeout = Duration(minutes: 5);

// Known Limitless Pendant audio service/characteristic UUIDs
// The pendant typically uses a custom audio characteristic
// Limitless Pendant BLE UUIDs (verified from Omi source)
const String kAudioServiceUuid = '632de001-604c-446b-a80f-7963e950f3fb';
const String kAudioCharUuid    = '632de003-604c-446b-a80f-7963e950f3fb';
const String kTxCharUuid       = '632de002-604c-446b-a80f-7963e950f3fb';

enum DeviceState { idle, scanning, connecting, connected, disconnected }

class BleService {
  DeviceState state = DeviceState.idle;
  BluetoothDevice? _device;
  StreamSubscription? _scanSub;
  StreamSubscription? _dataSub;
  StreamSubscription? _stateSub;
  Timer? _silenceTimer;
  AudioWriter? _audioWriter;
  int _packetCount = 0;

  final StreamController<DeviceState> _stateController = StreamController.broadcast();
  final StreamController<String> _logController = StreamController.broadcast();
  Stream<DeviceState> get stateStream => _stateController.stream;
  Stream<String> get logStream => _logController.stream;

  void _setState(DeviceState s) {
    state = s;
    _stateController.add(s);
  }

  void _log(String msg) {
    _logController.add(msg);
  }

  Future<void> startAutoConnect() async {
    _log('Auto-connect starting...');
    await _startScan();
  }

  Future<void> _startScan() async {
    if (state == DeviceState.scanning || state == DeviceState.connecting || state == DeviceState.connected) return;
    _setState(DeviceState.scanning);
    _log('Scanning for Pendant...');

    await FlutterBluePlus.stopScan();

    _scanSub?.cancel();
    _scanSub = FlutterBluePlus.scanResults.listen((results) async {
      for (final r in results) {
        final name = r.device.platformName.toLowerCase();
        final mac  = r.device.remoteId.str.toUpperCase();
        if (mac == kTargetMac || name.contains('limitless') || name.contains('pendant')) {
          _log('Found: ${r.device.platformName} ($mac)');
          await FlutterBluePlus.stopScan();
          await _connect(r.device);
          break;
        }
      }
    });

    await FlutterBluePlus.startScan(
      timeout: const Duration(seconds: 30),
      androidUsesFineLocation: true,
    );

    // Retry scan if not found
    Future.delayed(const Duration(seconds: 32), () {
      if (state == DeviceState.scanning || state == DeviceState.idle) {
        _log('Retry scan...');
        _startScan();
      }
    });
  }

  Future<void> _connect(BluetoothDevice device) async {
    _setState(DeviceState.connecting);
    _log('Connecting to ${device.platformName}...');
    _device = device;

    try {
      await device.connect(timeout: const Duration(seconds: 20), autoConnect: false);
      _setState(DeviceState.connected);
      _log('Connected!');

      _stateSub?.cancel();
      _stateSub = device.connectionState.listen((cs) {
        if (cs == BluetoothConnectionState.disconnected) {
          _log('Disconnected. Retrying...');
          _setState(DeviceState.disconnected);
          _cleanupSession();
          Future.delayed(const Duration(seconds: 5), _startScan);
        }
      });

      await _discoverAndSubscribe(device);
    } catch (e) {
      _log('Connect error: $e');
      _setState(DeviceState.disconnected);
      Future.delayed(const Duration(seconds: 5), _startScan);
    }
  }

  Future<void> _discoverAndSubscribe(BluetoothDevice device) async {
    _log('Discovering services...');
    final services = await device.discoverServices();
    _log('Found ${services.length} services');

    BluetoothCharacteristic? audioChar;

    for (final svc in services) {
      for (final char in svc.characteristics) {
        final cUuid = char.uuid.str.toLowerCase();
        final sUuid = svc.uuid.str.toLowerCase();
        _log('  Service: $sUuid  Char: $cUuid  Props: ${char.properties}');

        // Match known audio char or any notify/indicate characteristic with large data
        if (cUuid == kAudioCharUuid.toLowerCase() ||
            (sUuid == kAudioServiceUuid.toLowerCase() && char.properties.notify)) {
          audioChar = char;
        }
      }
    }

    // Fallback: use first notifiable characteristic
    if (audioChar == null) {
      for (final svc in services) {
        for (final char in svc.characteristics) {
          if (char.properties.notify || char.properties.indicate) {
            audioChar = char;
            _log('Using fallback char: ${char.uuid.str}');
            break;
          }
        }
        if (audioChar != null) break;
      }
    }

    if (audioChar == null) {
      _log('No audio characteristic found!');
      return;
    }

    await _initializePendant(device, services);
    _log('Subscribing to audio char: ${audioChar.uuid.str}');
    _audioWriter = AudioWriter();
    await _audioWriter!.open();
    _packetCount = 0;

    await audioChar.setNotifyValue(true);
    _dataSub?.cancel();
    _dataSub = audioChar.onValueReceived.listen(_onAudioPacket);

    _resetSilenceTimer();
  }

  // ── Limitless Pendant Protobuf Helpers ─────────────────────────────────
  int _messageIndex = 0;
  int _requestId = 0;

  List<int> _encodeVarint(int value) {
    final result = <int>[];
    while (value > 0x7f) {
      result.add((value & 0x7f) | 0x80);
      value >>= 7;
    }
    result.add(value & 0x7f);
    return result.isNotEmpty ? result : [0];
  }

  List<int> _encodeField(int fieldNum, int wireType, List<int> value) {
    final tag = (fieldNum << 3) | wireType;
    return [..._encodeVarint(tag), ...value];
  }

  List<int> _encodeBytesField(int fieldNum, List<int> data) {
    final length = _encodeVarint(data.length);
    return _encodeField(fieldNum, 2, [...length, ...data]);
  }

  List<int> _encodeMessage(int fieldNum, List<int> msgBytes) {
    return _encodeBytesField(fieldNum, msgBytes);
  }

  List<int> _encodeInt32Field(int fieldNum, int value) {
    return _encodeField(fieldNum, 0, _encodeVarint(value));
  }

  List<int> _encodeInt64Field(int fieldNum, int value) {
    return _encodeField(fieldNum, 0, _encodeVarint(value));
  }

  List<int> _encodeRequestData() {
    _requestId++;
    final msg = <int>[];
    msg.addAll(_encodeInt64Field(1, _requestId));
    msg.addAll(_encodeField(2, 0, [0x00]));
    return _encodeMessage(30, msg);
  }

  List<int> _encodeBleWrapper(List<int> payload) {
    final msg = <int>[];
    msg.addAll(_encodeInt32Field(1, _messageIndex));
    msg.addAll(_encodeInt32Field(2, 0));
    msg.addAll(_encodeInt32Field(3, 1));
    msg.addAll(_encodeBytesField(4, payload));
    _messageIndex++;
    return msg;
  }

  List<int> _buildSetCurrentTime(int timestampMs) {
    final timeMsg = _encodeInt64Field(1, timestampMs);
    final cmd = [..._encodeMessage(6, timeMsg), ..._encodeRequestData()];
    return _encodeBleWrapper(cmd);
  }

  List<int> _buildEnableDataStream({bool enable = true}) {
    final msg = <int>[];
    msg.addAll(_encodeField(1, 0, [0x00]));
    msg.addAll(_encodeField(2, 0, [enable ? 0x01 : 0x00]));
    final cmd = [..._encodeMessage(8, msg), ..._encodeRequestData()];
    return _encodeBleWrapper(cmd);
  }

  Future<void> _initializePendant(BluetoothDevice device, List<BluetoothService> services) async {
    // Find TX char from already-discovered services
    BluetoothCharacteristic? txChar;
    for (final svc in services) {
      if (svc.uuid.str.toLowerCase() == kAudioServiceUuid.toLowerCase()) {
        for (final c in svc.characteristics) {
          if (c.uuid.str.toLowerCase() == kTxCharUuid.toLowerCase()) {
            txChar = c;
            break;
          }
        }
      }
    }

    if (txChar == null) {
      _log('TX char not found — cannot initialize');
      return;
    }

    // Step 1: Wait for pendant to settle
    await Future.delayed(const Duration(seconds: 1));

    // Step 2: Time sync (required before enable data stream)
    try {
      final timeCmd = _buildSetCurrentTime(DateTime.now().millisecondsSinceEpoch);
      await txChar.write(timeCmd, withoutResponse: true);
      _log('✓ Time sync sent');
    } catch (e) {
      _log('Time sync error: $e');
    }

    // Step 3: Wait
    await Future.delayed(const Duration(seconds: 1));

    // Step 4: Enable data stream
    try {
      final enableCmd = _buildEnableDataStream();
      await txChar.write(enableCmd, withoutResponse: true);
      _log('✓ Enable data stream sent');
    } catch (e) {
      _log('Enable data stream error: $e');
    }
  }

  void _onAudioPacket(List<int> data) {
    if (data.isEmpty) return;
    _packetCount++;
    _audioWriter?.write(Uint8List.fromList(data));
    onBytesReceived?.call(data.length);
    _resetSilenceTimer();
  }

  void _resetSilenceTimer() {
    _silenceTimer?.cancel();
    _silenceTimer = Timer(kSilenceTimeout, () {
      _log('Silence timeout — flushing audio file');
      _flushCurrentFile();
    });
  }

  Future<void> _flushCurrentFile() async {
    if (_audioWriter == null) return;
    final path = await _audioWriter!.close();
    _audioWriter = null;
    if (path != null) {
      _log('Audio file ready: $path ($_packetCount packets)');
      // Notify uploader
      onFileReady?.call(path);
    }
    // Start new writer
    _audioWriter = AudioWriter();
    await _audioWriter!.open();
    _packetCount = 0;
  }

  void _cleanupSession() {
    _silenceTimer?.cancel();
    _dataSub?.cancel();
    _audioWriter?.close();
    _audioWriter = null;
    _packetCount = 0;
  }

  // Callback when a file is complete
  void Function(String path)? onFileReady;
  void Function(int bytes)? onBytesReceived;

  Future<void> disconnect() async {
    await _device?.disconnect();
    _cleanupSession();
    _scanSub?.cancel();
    _stateSub?.cancel();
    _setState(DeviceState.idle);
  }
}
