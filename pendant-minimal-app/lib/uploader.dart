import 'dart:io';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:path/path.dart' as p;

const String kWebhookUrl = 'https://pendant.enzoduit.com/v2/sync-local-files';
const String kApiKey = 'pendant-ed-2026';

class UploadResult {
  final String filename;
  final bool success;
  final String? error;
  UploadResult(this.filename, {required this.success, this.error});
}

class Uploader {
  int uploadCount = 0;
  DateTime? lastUploadTime;
  final List<UploadResult> history = [];

  // Upload a specific file
  Future<bool> uploadFile(String filePath) async {
    final file = File(filePath);
    if (!await file.exists()) return false;

    final filename = p.basename(filePath);
    try {
      final req = http.MultipartRequest('POST', Uri.parse(kWebhookUrl));
      req.headers['X-API-Key'] = kApiKey;
      req.files.add(await http.MultipartFile.fromPath('file', filePath, filename: filename));

      final response = await req.send().timeout(const Duration(seconds: 60));
      final body = await response.stream.bytesToString();

      if (response.statusCode >= 200 && response.statusCode < 300) {
        uploadCount++;
        lastUploadTime = DateTime.now();
        history.insert(0, UploadResult(filename, success: true));
        await file.delete(); // Remove after successful upload
        return true;
      } else {
        history.insert(0, UploadResult(filename, success: false, error: 'HTTP ${response.statusCode}: $body'));
        return false;
      }
    } catch (e) {
      history.insert(0, UploadResult(filename, success: false, error: e.toString()));
      return false;
    }
  }

  // Upload all pending .bin files on app open
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

  // Queue a file for upload (called when BLE session ends)
  Future<void> queueAndUpload(String path) async {
    await uploadFile(path);
  }
}
