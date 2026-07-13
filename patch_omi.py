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
    if (getString('btDevice')?.isNotEmpty == true) return; // already set
    const deviceJson = '{"name":"Pendant","id":"FD:04:D0:EB:84:88","type":"limitless","rssi":-60,"locator":null,"modelNumber":"Limitless Pendant","firmwareRevision":"1.0.0","hardwareRevision":"Unknown","manufacturerName":"Limitless","serialNumber":null}';
    saveString('btDevice', deviceJson);
    saveBool('onboardingCompleted', true);
    saveBool('deviceOnboardingCompleted', true);
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
