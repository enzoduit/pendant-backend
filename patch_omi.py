#!/usr/bin/env python3
"""Patches Omi app source to bypass auth and onboarding for personal use."""
import re, sys, os

base = "app/lib"

# 1. Patch auth_provider.dart
auth_path = f"{base}/providers/auth_provider.dart"
with open(auth_path) as f:
    auth = f.read()

auth = auth.replace(
    "return _auth.currentUser != null && !_auth.currentUser!.isAnonymous;",
    "return true; // BYPASS"
)
auth = auth.replace(
    "String? token = await _getIdToken();",
    'String? token = "ed-pendant-token"; // BYPASS'
)
auth = auth.replace(
    "String newUid = user.uid;",
    "String newUid = 'ed-pendant-uid';"
)
auth = auth.replace(
    "user = FirebaseAuth.instance.currentUser!;",
    "// user = FirebaseAuth.instance.currentUser!; // BYPASS"
)
with open(auth_path, "w") as f:
    f.write(auth)
print("auth_provider.dart patched")

# 2. Pre-seed paired Limitless Pendant device into SharedPreferences
prefs_path = f"{base}/backend/preferences.dart"
with open(prefs_path) as f:
    prefs = f.read()

DEVICE_SEED = '''
  // BYPASS: pre-seed Limitless Pendant so app reconnects without onboarding
  void seedLimitlessDevice() {
    // Always set sync prefs, even if device already seeded
    saveBool('autoSyncOfflineRecordings', true);  // BYPASS: ensure auto-sync is on
    saveBool('useCustomStt', false);  // BYPASS: must be false for auto-upload to work
    saveBool('batchModeEnabled', true);  // BYPASS: Transcribe Later mode for Limitless
    saveBool('unlimitedLocalStorageEnabled', true);  // BYPASS: must be true for flash WALs to be stored locally
    if (getString('btDevice')?.isNotEmpty == true) return;
    // Only seed device if not already paired (preserves user's actual paired device)
    if (getString('btDevice')?.isEmpty != false) {
      const deviceJson = '{"name":"Pendant","id":"FD:04:D0:EB:84:88","type":"limitless","rssi":-60,"locator":null,"modelNumber":"Limitless Pendant","firmwareRevision":"1.0.0","hardwareRevision":"Unknown","manufacturerName":"Limitless","serialNumber":null}';
      saveString('btDevice', deviceJson);
    }
    saveBool('onboardingCompleted', true);
    saveBool('deviceOnboardingCompleted', true);
    saveBool('autoSyncOfflineRecordings', true);  // BYPASS: ensure auto-sync is on
    saveBool('useCustomStt', false);  // BYPASS: must be false for auto-upload to work
    saveBool('batchModeEnabled', true);  // BYPASS: Transcribe Later mode for Limitless
    saveBool('unlimitedLocalStorageEnabled', true);  // BYPASS: must be true for flash WALs to be stored locally
    saveBool('permissionsCompleted', true);
    saveBool('aiConsentGiven', true);
  }
'''

target = "class SharedPreferencesUtil {"
if target in prefs and "seedLimitlessDevice" not in prefs:
    prefs = prefs.replace(target, target + DEVICE_SEED)
    with open(prefs_path, "w") as f:
        f.write(prefs)
    print("preferences.dart patched with seedLimitlessDevice()")
else:
    print("preferences.dart: skipped (already patched or target not found)")

# 3. Patch mobile_app.dart - replace entire Consumer/auth routing with direct HomePageWrapper
app_path = f"{base}/mobile/mobile_app.dart"
with open(app_path) as f:
    app = f.read()

# Strategy: replace the entire build() method body using regex (robust to comment changes)
# Match from the Consumer<AuthenticationProvider> to the closing brace of the else block
bypass_build = """  @override
  Widget build(BuildContext context) {
    // BYPASS: skip Firebase auth entirely, go straight to home
    SharedPreferencesUtil().seedLimitlessDevice();
    return const HomePageWrapper();
  }
}"""

# Find the class that contains the routing Consumer and replace its build method
# Target the pattern: @override\n  Widget build ... Consumer<AuthenticationProvider> ... DeviceSelectionPage
pattern = r'(@override\s+Widget build\(BuildContext context\)\s*\{.*?Consumer<AuthenticationProvider>.*?DeviceSelectionPage\(\);\s*\}\s*\}\s*\}\s*\})'
match = re.search(pattern, app, re.DOTALL)
if match:
    app = app[:match.start()] + bypass_build + app[match.end():]
    with open(app_path, "w") as f:
        f.write(app)
    print("mobile_app.dart patched - Consumer replaced with direct HomePageWrapper")
else:
    # Fallback: just patch the isSignedIn check
    print("WARNING: regex pattern not found, trying simpler patch")
    app = re.sub(
        r'if \(authProvider\.isSignedIn\(\)\) \{.*?return const DeviceSelectionPage\(\);\s*\}',
        'return const HomePageWrapper(); // BYPASS',
        app, flags=re.DOTALL, count=1
    )
    with open(app_path, "w") as f:
        f.write(app)
    print("mobile_app.dart patched via fallback regex")

print("All patches done!")

# 5. Patch auth_service.dart - make getIdToken() always return permanent fake token
auth_svc_path = f"{base}/services/auth_service.dart"
with open(auth_svc_path) as f:
    svc = f.read()

old_getid = "  Future<String?> getIdToken() async {"
bypass_line = "    // BYPASS: permanent fake token\n    SharedPreferencesUtil().authToken = 'ed-pendant-token';\n    SharedPreferencesUtil().tokenExpirationTime = DateTime.now().add(const Duration(days: 3650)).millisecondsSinceEpoch;\n    return 'ed-pendant-token';"

if old_getid in svc and "BYPASS: permanent" not in svc:
    svc = svc.replace(old_getid, old_getid + "\n" + bypass_line, 1)
    with open(auth_svc_path, "w") as f:
        f.write(svc)
    print("auth_service.dart patched - getIdToken returns permanent fake token")
else:
    print("auth_service.dart: skipped (already patched or not found)")

# 6. Patch shared.dart - make _isRequiredAuthCheck always return false for our backend
# This prevents any auth token logic entirely - no Firebase calls needed
shared_path = f"{base}/backend/http/shared.dart"
with open(shared_path) as f:
    shared = f.read()

old_auth_check = """bool _isRequiredAuthCheck(String url) {
  // Agent VM endpoints always hit prod even when app uses dev
  if (url.contains('api.omi.me')) return true;
  if (url.contains(Env.apiBaseUrl!)) {
    return true;
  }
  return false;
}"""

new_auth_check = """bool _isRequiredAuthCheck(String url) {
  // BYPASS: no auth required for personal backend
  if (url.contains('api.omi.me')) return true;
  return false;
}"""

if old_auth_check in shared and "BYPASS: no auth required" not in shared:
    shared = shared.replace(old_auth_check, new_auth_check)
    with open(shared_path, "w") as f:
        f.write(shared)
    print("shared.dart patched - _isRequiredAuthCheck always false for our backend")
else:
    print("shared.dart: skipped (already patched or pattern not found)")

# 7. Patch sync_provider.dart — wake transfer coordinator when WALs arrive from flash drain
# In new omi, onWalUpdated does NOT wake the coordinator → flash drain WALs never auto-upload
sync_provider_path = f"{base}/providers/sync_provider.dart"
with open(sync_provider_path) as f:
    sp = f.read()

old_wal_updated = """  void onWalUpdated() async {
    await refreshWals();
  }"""
new_wal_updated = """  void onWalUpdated() async {
    await refreshWals();
    // BYPASS: debounced userRetry after flash-drain completes
    // cooldownElapsed corrupts coordinator state; userRetry bypasses gate safely
    _walUploadDebounce?.cancel();
    _walUploadDebounce = Timer(const Duration(seconds: 5), () {
      _walUploadDebounce = null;
      if (_startBackgroundSync) {
        unawaited(_wakeTransfer(WakeTrigger.userRetry));
      }
    });
  }"""

if old_wal_updated in sp and "BYPASS: wake transfer" not in sp:
    # Also add Timer field to SyncProvider class
    timer_field = "  Timer? _walUploadDebounce; // BYPASS: debounce for flash-drain upload"
    class_decl = "class SyncProvider extends ChangeNotifier"
    if class_decl in sp and "_walUploadDebounce" not in sp:
        # Find first field after class declaration
        insert_after = "  final AudioPlayerUtils _audioPlayerUtils = AudioPlayerUtils.instance;"
        if insert_after in sp:
            sp = sp.replace(insert_after, insert_after + "\n" + timer_field)
        else:
            # Fallback: add after class declaration line
            sp = sp.replace(class_decl + " ", class_decl + " ")  # no-op if not found
    sp = sp.replace(old_wal_updated, new_wal_updated)
    with open(sync_provider_path, "w") as f:
        f.write(sp)
    print("sync_provider.dart patched: onWalUpdated wakes coordinator after flash drain")
else:
    print(f"sync_provider.dart: pattern found={old_wal_updated in sp}, already patched={'BYPASS: wake transfer' in sp}")

# 8. Patch recording_transfer_coordinator.dart — add print debug for may_upload and drain
coordinator_path = f"{base}/services/wals/recording_transfer_coordinator.dart"
with open(coordinator_path) as f:
    coord = f.read()

if "BYPASS_DEBUG" not in coord:
    old_may_upload = "      final mayUpload = trigger == WakeTrigger.userRetry || _autoUploadEnabled();\n      if (!mayUpload) return;"
    new_may_upload = """      final autoEnabled = _autoUploadEnabled();
      final mayUpload = trigger == WakeTrigger.userRetry || autoEnabled;
      // ignore: avoid_print
      print('[COORD] BYPASS_DEBUG may_upload=$mayUpload trigger=${trigger.name} autoEnabled=$autoEnabled');
      if (!mayUpload) return;"""

    old_drain = "      final result = await _drain();"
    new_drain = """      // ignore: avoid_print
      print('[COORD] BYPASS_DEBUG drain starting trigger=${trigger.name}');
      final result = await _drain();
      // ignore: avoid_print
      print('[COORD] BYPASS_DEBUG drain result: attempted=${result.attempted} failed=${result.failed} contended=${result.contended}');"""

    if old_may_upload in coord:
        coord = coord.replace(old_may_upload, new_may_upload)
        print("coordinator: may_upload debug patch applied")
    else:
        print("coordinator: may_upload pattern NOT FOUND")

    if old_drain in coord:
        coord = coord.replace(old_drain, new_drain)
        print("coordinator: drain debug patch applied")
    else:
        print("coordinator: drain pattern NOT FOUND")

    with open(coordinator_path, "w") as f:
        f.write(coord)
    print("recording_transfer_coordinator.dart patched")
else:
    print("coordinator: already patched")

# 9. Patch sync_upload_gate.dart — log when gate blocks uploads
gate_path = f"{base}/services/wals/sync_upload_gate.dart"
with open(gate_path) as f:
    gate = f.read()

if "_debugLog" not in gate and "prepareToUpload" in gate:
    old_prepare = "    if (lane == SyncUploadLane.fresh && _limiter.hasPersistedFairUseState) {\n      await reconcileFairUseStatus();\n    }\n    return !_limiter.isLimitedForLane(lane.name);"
    new_prepare = """    if (lane == SyncUploadLane.fresh && _limiter.hasPersistedFairUseState) {
      await reconcileFairUseStatus();
    }
    final allowed = !_limiter.isLimitedForLane(lane.name);
    try {
      final url = Uri.parse('UNUSED_PLACEHOLDER.contains("http") ? "" : ""}');
      // minimal debug — just print to console since we don't have easy access to apiBaseUrl here
    } catch (_) {}
    return allowed;"""

    # Simpler: just add a print statement
    old_return = "    return !_limiter.isLimitedForLane(lane.name);"
    new_return = """    final _gateAllowed = !_limiter.isLimitedForLane(lane.name);
    // ignore: avoid_print
    print('[GATE] prepareToUpload lane=${lane.name} allowed=$_gateAllowed hasPersistedFairUse=${_limiter.hasPersistedFairUseState}');
    return _gateAllowed;"""

    if old_return in gate:
        gate = gate.replace(old_return, new_return, 1)
        with open(gate_path, "w") as f:
            f.write(gate)
        print("sync_upload_gate.dart patched with gate logging")
    else:
        print("sync_upload_gate.dart: return pattern not found")
