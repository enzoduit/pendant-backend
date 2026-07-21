import 'dart:io';
import 'dart:typed_data';
import 'package:path_provider/path_provider.dart';

class AudioWriter {
  IOSink? _sink;
  String? _filePath;

  Future<void> open() async {
    final dir = await getApplicationDocumentsDirectory();
    final ts = (DateTime.now().millisecondsSinceEpoch ~/ 1000).toString();
    final filename = 'audio_omibatchlimitless_opus_16000_1_fs320_$ts.bin';
    _filePath = '${dir.path}/$filename';
    _sink = File(_filePath!).openWrite();
  }

  void write(Uint8List data) {
    _sink?.add(data);
  }

  Future<String?> close() async {
    await _sink?.flush();
    await _sink?.close();
    _sink = null;
    return _filePath;
  }

  String? get currentPath => _filePath;
}
