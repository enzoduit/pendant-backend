import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';
import 'ble_service.dart';
import 'uploader.dart';
import 'status_screen.dart';

final BleService bleService = BleService();
final Uploader uploader = Uploader();

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const PendantApp());
}

class PendantApp extends StatelessWidget {
  const PendantApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Pendant',
      theme: ThemeData.dark(useMaterial3: true).copyWith(
        colorScheme: ColorScheme.dark(
          primary: const Color(0xFF6C63FF),
          surface: const Color(0xFF1E1E2E),
        ),
        scaffoldBackgroundColor: const Color(0xFF1E1E2E),
      ),
      home: const StatusScreen(),
    );
  }
}

Future<bool> requestPermissions() async {
  final statuses = await [
    Permission.bluetooth,
    Permission.bluetoothScan,
    Permission.bluetoothConnect,
    Permission.locationWhenInUse,
  ].request();
  return statuses.values.every((s) => s.isGranted || s.isLimited);
}
