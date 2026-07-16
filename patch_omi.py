#!/usr/bin/env python3
"""Patches Omi app source to bypass auth and onboarding for personal use."""
import re, sys, os

base = "/tmp/omi/app/lib"

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
    const deviceJson = '{"name":"Pendant","id":"FD:04:D0:EB:84:88","type":"limitless","rssi":-60,"locator":null,"modelNumber":"Limitless Pendant","firmwareRevision":"1.0.0","hardwareRevision":"Unknown","manufacturerName":"Limitless","serialNumber":null}';
    saveString('btDevice', deviceJson);
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

old_wal_updated = "  void onWalUpdated() async {\n    await refreshWals();\n  }"
new_wal_updated = """  void onWalUpdated() async {
    await refreshWals();
    // BYPASS: wake transfer coordinator when new WALs arrive (e.g. after flash drain)
    if (_startBackgroundSync && !_syncState.isProcessing) {
      unawaited(_wakeTransfer(WakeTrigger.cooldownElapsed));
    }
  }"""

if old_wal_updated in sp and "BYPASS: wake transfer" not in sp:
    sp = sp.replace(old_wal_updated, new_wal_updated)
    with open(sync_provider_path, "w") as f:
        f.write(sp)
    print("sync_provider.dart patched: onWalUpdated wakes coordinator after flash drain")
else:
    print(f"sync_provider.dart: pattern found={old_wal_updated in sp}, already patched={'BYPASS: wake transfer' in sp}")
