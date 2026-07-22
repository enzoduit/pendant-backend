import 'dart:io';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:path/path.dart' as p;

const String kWebhookUrl = 'https://pendant.enzoduit.com/v2/sync-local-files';
const String kApiKey = 'pendant-ed-2026';

class UploadRecord {
  final String filename;
  final bool success;
  final DateTime time;
  final int sizeKb;
  final String? error;

  UploadRecord({
    required this.filename,
    required this.success,
    required this.time,
    required this.sizeKb,
    this.error,
  });

  Map<String, dynamic> toJson() => {
    'filename': filename,
    'success': success,
    'time': time.toIso8601String(),
    'sizeKb': sizeKb,
    'error': error,
  };

  factory UploadRecord.fromJson(Map<String, dynamic> j) => UploadRecord(
    filename: j['filename'] ?? '',
    success: j['success'] ?? false,
    time: DateTime.parse(j['time'] ?? DateTime.now().toIso8601String()),
    sizeKb: j['sizeKb'] ?? 0,
    error: j['error'],
  );
}

class Uploader {
  int uploadCount = 0;
  DateTime? lastUploadTime;
  List<UploadRecord> history = [];

  Future<File> _historyFile() async {
    final dir = await getApplicationDocumentsDirectory();
    return File(p.join(dir.path, 'upload_history.json'));
  }

  Future<void> loadHistory() async {
    try {
      final f = await _historyFile();
      if (await f.exists()) {
        final data = jsonDecode(await f.readAsString()) as List;
        history = data.map((e) => UploadRecord.fromJson(e)).toList();
        uploadCount = history.where((r) => r.success).length;
        final successful = history.where((r) => r.success).toList();
        if (successful.isNotEmpty) {
          successful.sort((a, b) => b.time.compareTo(a.time));
          lastUploadTime = successful.first.time;
        }
      }
    } catch (_) {}
  }

  Future<void> _saveHistory() async {
    try {
      final f = await _historyFile();
      // Keep last 200 records
      final trimmed = history.length > 200 ? history.sublist(0, 200) : history;
      await f.writeAsString(jsonEncode(trimmed.map((r) => r.toJson()).toList()));
    } catch (_) {}
  }

  Future<bool> uploadFile(String filePath) async {
    final file = File(filePath);
    if (!await file.exists()) return false;

    final filename = p.basename(filePath);
    final sizeKb = (await file.length()) ~/ 1024;

    try {
      final req = http.MultipartRequest('POST', Uri.parse(kWebhookUrl));
      req.headers['X-API-Key'] = kApiKey;
      req.files.add(await http.MultipartFile.fromPath('file', filePath, filename: filename));

      final response = await req.send().timeout(const Duration(seconds: 60));
      await response.stream.bytesToString();

      if (response.statusCode >= 200 && response.statusCode < 300) {
        uploadCount++;
        lastUploadTime = DateTime.now();
        history.insert(0, UploadRecord(filename: filename, success: true, time: DateTime.now(), sizeKb: sizeKb));
        await _saveHistory();
        await file.delete();
        return true;
      } else {
        history.insert(0, UploadRecord(filename: filename, success: false, time: DateTime.now(), sizeKb: sizeKb, error: 'HTTP ${response.statusCode}'));
        await _saveHistory();
        return false;
      }
    } catch (e) {
      history.insert(0, UploadRecord(filename: filename, success: false, time: DateTime.now(), sizeKb: sizeKb, error: e.toString()));
      await _saveHistory();
      return false;
    }
  }

  Future<int> uploadPending() async {
    final dir = await getApplicationDocumentsDirectory();
    final files = dir.listSync()
        .whereType<File>()
        .where((f) => f.path.endsWith('.bin') && p.basename(f.path).startsWith('audio_omibatch'))
        .toList();

    int count = 0;
    for (final file in files) {
      final ok = await uploadFile(file.path);
      if (ok) count++;
    }
    return count;
  }

  Future<void> queueAndUpload(String path) async {
    await uploadFile(path);
  }
}
