import 'dart:async';
import 'dart:typed_data';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'audio_writer.dart';

const String kTargetMac = 'FD:04:D0:EB:84:88';
const Duration kSilenceTimeout = Duration(minutes: 5);

// Known Limitless Pendant audio service/characteristic UUIDs
// The pendant typically uses a custom audio characteristic
const String kAudioServiceUuid = '19b10000-e8f2-537e-4f6c-d104768a1214';
const String kAudioCharUuid    = '19b10001-e8f2-537e-4f6c-d104768a1214';

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
            sUuid == kAudioServiceUuid.toLowerCase() ||
            (char.properties.notify && cUuid.contains('19b1'))) {
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

    _log('Subscribing to audio char: ${audioChar.uuid.str}');
    _audioWriter = AudioWriter();
    await _audioWriter!.open();
    _packetCount = 0;

    await audioChar.setNotifyValue(true);
    _dataSub?.cancel();
    _dataSub = audioChar.onValueReceived.listen(_onAudioPacket);

    _resetSilenceTimer();
  }

  void _onAudioPacket(List<int> data) {
    if (data.isEmpty) return;
    _packetCount++;
    _audioWriter?.write(Uint8List.fromList(data));
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

  Future<void> disconnect() async {
    await _device?.disconnect();
    _cleanupSession();
    _scanSub?.cancel();
    _stateSub?.cancel();
    _setState(DeviceState.idle);
  }
}
