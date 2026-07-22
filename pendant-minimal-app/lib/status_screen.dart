import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:path/path.dart' as p;
import 'main.dart';
import 'ble_service.dart';
import 'uploader.dart';

class StatusScreen extends StatefulWidget {
  const StatusScreen({super.key});
  @override
  State<StatusScreen> createState() => _StatusScreenState();
}

class _StatusScreenState extends State<StatusScreen> with SingleTickerProviderStateMixin {
  DeviceState _bleState = DeviceState.idle;
  final List<String> _logs = [];
  StreamSubscription? _stateSub;
  StreamSubscription? _logSub;
  bool _initialized = false;
  int _liveBytes = 0;
  late TabController _tabController;
  List<_LocalFile> _localFiles = [];
  bool _uploading = false;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
    _init();
  }

  Future<void> _init() async {
    await uploader.loadHistory();
    final ok = await requestPermissions();
    _addLog(ok ? 'Permissions granted' : 'Some permissions denied');

    _stateSub = bleService.stateStream.listen((s) {
      setState(() => _bleState = s);
    });

    _logSub = bleService.logStream.listen(_addLog);

    bleService.onBytesReceived = (bytes) {
      setState(() => _liveBytes += bytes);
    };

    bleService.onFileReady = (path) async {
      _addLog('Uploading: ${p.basename(path)}');
      setState(() => _uploading = true);
      final ok = await uploader.queueAndUpload(path).then((_) => true).catchError((_) => false);
      _addLog(ok ? '✓ Upload done' : '✗ Upload failed');
      setState(() {
        _uploading = false;
        _liveBytes = 0;
      });
      await _refreshFiles();
    };

    _addLog('Checking for pending files...');
    final count = await uploader.uploadPending();
    if (count > 0) _addLog('Uploaded $count pending file(s)');
    else _addLog('No pending files');

    await _refreshFiles();

    if (!_initialized) {
      _initialized = true;
      await bleService.startAutoConnect();
    }
  }

  Future<void> _refreshFiles() async {
    final dir = await getApplicationDocumentsDirectory();
    final files = dir.listSync()
        .whereType<File>()
        .where((f) => f.path.endsWith('.bin') && p.basename(f.path).startsWith('audio_omibatch'))
        .map((f) => _LocalFile(
              name: p.basename(f.path),
              path: f.path,
              sizeKb: f.lengthSync() ~/ 1024,
              modified: f.lastModifiedSync(),
            ))
        .toList()
      ..sort((a, b) => b.modified.compareTo(a.modified));
    if (mounted) setState(() => _localFiles = files);
  }

  void _addLog(String msg) {
    if (!mounted) return;
    final now = DateTime.now();
    final time = '${now.hour.toString().padLeft(2,'0')}:${now.minute.toString().padLeft(2,'0')}:${now.second.toString().padLeft(2,'0')}';
    setState(() {
      _logs.insert(0, '[$time] $msg');
      if (_logs.length > 100) _logs.removeLast();
    });
  }

  @override
  void dispose() {
    _tabController.dispose();
    _stateSub?.cancel();
    _logSub?.cancel();
    super.dispose();
  }

  Color get _statusColor {
    switch (_bleState) {
      case DeviceState.connected:   return Colors.greenAccent;
      case DeviceState.scanning:
      case DeviceState.connecting:  return Colors.amberAccent;
      case DeviceState.disconnected:
      case DeviceState.idle:        return Colors.redAccent;
    }
  }

  String get _statusText {
    switch (_bleState) {
      case DeviceState.idle:        return 'Idle';
      case DeviceState.scanning:    return 'Scanning...';
      case DeviceState.connecting:  return 'Connecting...';
      case DeviceState.connected:   return 'Connected ●';
      case DeviceState.disconnected:return 'Disconnected';
    }
  }

  @override
  Widget build(BuildContext context) {
    final last = uploader.lastUploadTime;
    final lastStr = last != null
        ? '${last.hour.toString().padLeft(2,'0')}:${last.minute.toString().padLeft(2,'0')}'
        : '—';

    return Scaffold(
      backgroundColor: const Color(0xFF0A0A0F),
      appBar: AppBar(
        title: const Text('Listen', style: TextStyle(fontWeight: FontWeight.bold, letterSpacing: 2)),
        backgroundColor: const Color(0xFF0A0A0F),
        elevation: 0,
        bottom: TabBar(
          controller: _tabController,
          indicatorColor: const Color(0xFF6C63FF),
          labelColor: Colors.white,
          unselectedLabelColor: Colors.white38,
          tabs: const [
            Tab(text: 'Status', icon: Icon(Icons.bluetooth, size: 16)),
            Tab(text: 'History', icon: Icon(Icons.history, size: 16)),
          ],
        ),
      ),
      body: SafeArea(
        child: TabBarView(
          controller: _tabController,
          children: [
            _buildStatusTab(lastStr),
            _buildFilesTab(),
          ],
        ),
      ),
    );
  }

  Widget _buildStatusTab(String lastStr) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Status card
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: const Color(0xFF161622),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: _statusColor.withOpacity(0.3), width: 1),
            ),
            child: Row(
              children: [
                Container(
                  width: 12, height: 12,
                  decoration: BoxDecoration(color: _statusColor, shape: BoxShape.circle),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(_statusText, style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: _statusColor)),
                      const SizedBox(height: 2),
                      const Text('Pendant FD:04:D0:EB:84:88', style: TextStyle(fontSize: 11, color: Colors.white38)),
                    ],
                  ),
                ),
                if (_liveBytes > 0)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: Colors.greenAccent.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      '${(_liveBytes / 1024).toStringAsFixed(1)} KB',
                      style: const TextStyle(fontSize: 11, color: Colors.greenAccent),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          // Stats row
          Row(
            children: [
              Expanded(child: _StatCard(label: 'Uploads', value: uploader.uploadCount.toString(), icon: Icons.cloud_upload_outlined, color: const Color(0xFF6C63FF))),
              const SizedBox(width: 8),
              Expanded(child: _StatCard(label: 'Last Upload', value: lastStr, icon: Icons.access_time, color: Colors.white54)),
              const SizedBox(width: 8),
              Expanded(child: _StatCard(label: 'Local Files', value: _localFiles.length.toString(), icon: Icons.folder_outlined, color: Colors.amberAccent)),
            ],
          ),
          const SizedBox(height: 16),
          // Log header
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('Log', style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: Colors.white54)),
              if (_uploading)
                const Row(
                  children: [
                    SizedBox(width: 10, height: 10, child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF6C63FF))),
                    SizedBox(width: 6),
                    Text('Uploading...', style: TextStyle(fontSize: 11, color: Color(0xFF6C63FF))),
                  ],
                ),
            ],
          ),
          const SizedBox(height: 6),
          // Log list
          Expanded(
            child: Container(
              decoration: BoxDecoration(
                color: const Color(0xFF0D0D1A),
                borderRadius: BorderRadius.circular(8),
              ),
              child: ListView.builder(
                padding: const EdgeInsets.all(8),
                itemCount: _logs.length,
                itemBuilder: (ctx, i) => Text(
                  _logs[i],
                  style: TextStyle(
                    fontSize: 10.5,
                    fontFamily: 'monospace',
                    color: _logs[i].contains('✓') ? Colors.greenAccent
                        : _logs[i].contains('✗') ? Colors.redAccent
                        : Colors.white60,
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 10),
          // Buttons row
          Row(
            children: [
              Expanded(
                child: ElevatedButton.icon(
                  icon: const Icon(Icons.bluetooth_searching, size: 16),
                  label: const Text('Reconnect'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF6C63FF),
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 12),
                  ),
                  onPressed: () {
                    bleService.startAutoConnect();
                    _addLog('Manual reconnect');
                  },
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: ElevatedButton.icon(
                  icon: const Icon(Icons.upload, size: 16),
                  label: const Text('Upload All'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF2D2D44),
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 12),
                  ),
                  onPressed: _uploading ? null : () async {
                    _addLog('Manual upload all...');
                    setState(() => _uploading = true);
                    final count = await uploader.uploadPending();
                    _addLog(count > 0 ? '✓ Uploaded $count file(s)' : 'No pending files');
                    setState(() => _uploading = false);
                    await _refreshFiles();
                  },
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildFilesTab() {
    final history = uploader.history;
    if (history.isEmpty) {
      return const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.history, size: 48, color: Colors.white24),
            SizedBox(height: 12),
            Text('No uploads yet', style: TextStyle(color: Colors.white38)),
            SizedBox(height: 4),
            Text('History appears after first upload', style: TextStyle(fontSize: 11, color: Colors.white24)),
          ],
        ),
      );
    }
    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
      itemCount: history.length,
      itemBuilder: (ctx, i) {
        final r = history[i];
        final time = '${r.time.hour.toString().padLeft(2,'0')}:${r.time.minute.toString().padLeft(2,'0')}';
        final date = '${r.time.day.toString().padLeft(2,'0')}.${r.time.month.toString().padLeft(2,'0')}';
        return Container(
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: const Color(0xFF161622),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: r.success ? Colors.greenAccent.withOpacity(0.2) : Colors.redAccent.withOpacity(0.2),
              width: 1,
            ),
          ),
          child: Row(
            children: [
              Icon(
                r.success ? Icons.check_circle_outline : Icons.error_outline,
                color: r.success ? Colors.greenAccent : Colors.redAccent,
                size: 20,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '$date  $time  ·  ${r.sizeKb} KB',
                      style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold),
                    ),
                    if (r.error != null)
                      Text(r.error!, style: const TextStyle(fontSize: 10, color: Colors.redAccent)),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _LocalFile {
  final String name, path;
  final int sizeKb;
  final DateTime modified;
  _LocalFile({required this.name, required this.path, required this.sizeKb, required this.modified});
}

class _StatCard extends StatelessWidget {
  final String label, value;
  final IconData icon;
  final Color color;
  const _StatCard({required this.label, required this.value, required this.icon, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFF161622),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: color, size: 16),
          const SizedBox(height: 4),
          Text(value, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold)),
          Text(label, style: const TextStyle(fontSize: 10, color: Colors.white38)),
        ],
      ),
    );
  }
}
