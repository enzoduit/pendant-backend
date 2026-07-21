import 'dart:async';
import 'package:flutter/material.dart';
import 'main.dart';
import 'ble_service.dart';

class StatusScreen extends StatefulWidget {
  const StatusScreen({super.key});

  @override
  State<StatusScreen> createState() => _StatusScreenState();
}

class _StatusScreenState extends State<StatusScreen> {
  BleState _bleState = BleState.idle;
  final List<String> _logs = [];
  StreamSubscription? _stateSub;
  StreamSubscription? _logSub;
  bool _initialized = false;
  int _pendingUploaded = 0;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    // Request permissions
    final ok = await requestPermissions();
    _addLog(ok ? 'Permissions granted' : 'Some permissions denied');

    // Listen to BLE state
    _stateSub = bleService.stateStream.stream.listen((s) {
      setState(() => _bleState = s);
    });

    _logSub = bleService.logStream.stream.listen(_addLog);

    // Wire up file-ready callback
    bleService.onFileReady = (path) async {
      _addLog('Uploading: ${path.split('/').last}');
      final ok = await uploader.queueAndUpload(path).then((_) => true).catchError((_) => false);
      _addLog(ok ? '✓ Upload done' : '✗ Upload failed');
      if (mounted) setState(() {});
    };

    // Upload pending files
    _addLog('Checking for pending files...');
    _pendingUploaded = await uploader.uploadPending();
    if (_pendingUploaded > 0) {
      _addLog('Uploaded $_pendingUploaded pending file(s)');
    } else {
      _addLog('No pending files');
    }

    // Auto-connect BLE
    if (!_initialized) {
      _initialized = true;
      await bleService.startAutoConnect();
    }
  }

  void _addLog(String msg) {
    final time = TimeOfDay.now().format(context);
    setState(() {
      _logs.insert(0, '[$time] $msg');
      if (_logs.length > 50) _logs.removeLast();
    });
  }

  @override
  void dispose() {
    _stateSub?.cancel();
    _logSub?.cancel();
    super.dispose();
  }

  String get _statusText {
    switch (_bleState) {
      case BleState.idle:        return 'Idle';
      case BleState.scanning:    return 'Scanning...';
      case BleState.connecting:  return 'Connecting...';
      case BleState.connected:   return 'Connected';
      case BleState.disconnected:return 'Disconnected';
    }
  }

  Color get _statusColor {
    switch (_bleState) {
      case BleState.connected:   return Colors.greenAccent;
      case BleState.scanning:
      case BleState.connecting:  return Colors.amberAccent;
      case BleState.disconnected:
      case BleState.idle:        return Colors.redAccent;
    }
  }

  @override
  Widget build(BuildContext context) {
    final last = uploader.lastUploadTime;
    final lastStr = last != null
        ? '${last.hour.toString().padLeft(2,'0')}:${last.minute.toString().padLeft(2,'0')}'
        : 'Never';

    return Scaffold(
      appBar: AppBar(
        title: const Text('Pendant Sync'),
        backgroundColor: const Color(0xFF1E1E2E),
        elevation: 0,
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Status card
            Card(
              color: const Color(0xFF2D2D44),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    Container(
                      width: 14,
                      height: 14,
                      decoration: BoxDecoration(
                        color: _statusColor,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            _statusText,
                            style: TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.bold,
                              color: _statusColor,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            'Pendant FD:04:D0:EB:84:88',
                            style: TextStyle(
                              fontSize: 12,
                              color: Colors.white54,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            // Upload stats
            Row(
              children: [
                Expanded(
                  child: _StatCard(
                    label: 'Uploads',
                    value: uploader.uploadCount.toString(),
                    icon: Icons.cloud_upload_outlined,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _StatCard(
                    label: 'Last Upload',
                    value: lastStr,
                    icon: Icons.access_time,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            // Log
            const Text(
              'Log',
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.bold,
                color: Colors.white70,
              ),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: Container(
                decoration: BoxDecoration(
                  color: const Color(0xFF2D2D44),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: ListView.builder(
                  padding: const EdgeInsets.all(8),
                  itemCount: _logs.length,
                  itemBuilder: (ctx, i) => Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: Text(
                      _logs[i],
                      style: const TextStyle(
                        fontSize: 11,
                        fontFamily: 'monospace',
                        color: Colors.white70,
                      ),
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 12),
            // Reconnect button
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                icon: const Icon(Icons.bluetooth_searching),
                label: const Text('Reconnect'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF6C63FF),
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                ),
                onPressed: () {
                  bleService.startAutoConnect();
                  _addLog('Manual reconnect triggered');
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;

  const _StatCard({required this.label, required this.value, required this.icon});

  @override
  Widget build(BuildContext context) {
    return Card(
      color: const Color(0xFF2D2D44),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Icon(icon, color: const Color(0xFF6C63FF), size: 20),
            const SizedBox(width: 8),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label, style: const TextStyle(fontSize: 11, color: Colors.white54)),
                Text(value, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
