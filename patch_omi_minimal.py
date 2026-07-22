"""
Minimal Omi patch — only 3 changes:
1. API_BASE_URL in .env (done via GitHub Actions workflow, not here)
2. Auth bypass in mobile_app.dart (skip Firebase login, go straight to home)
3. seedLimitlessDevice() in LocalRecordingsProvider constructor (timing fix for autoSyncOfflineRecordings)
"""
import re, sys, os

base = "app/lib"

# ─── 1. Auth bypass — mobile_app.dart ────────────────────────────────────────
app_path = f"{base}/mobile/mobile_app.dart"
with open(app_path) as f:
    app = f.read()

old_build_body = """    return Consumer<AuthenticationProvider>(
      builder: (context, authProvider, child) {
        if (authProvider.requiresReauthentication) {
          _presentSessionExpiration(authProvider.sessionExpirationGeneration);
          return const OnboardingWrapper(forceAuthPage: true);
        }
        if (authProvider.isSignedIn()) {
          // Returning users who haven't yet given consent under the new
          // model must see the consent screen before any AI processing
          // begins, even if the server says they completed onboarding
          // previously. OnboardingWrapper renders the consent step in
          // that case and routes them straight to home after Continue.
          if (!SharedPreferencesUtil().aiConsentGiven) {
            return const OnboardingWrapper();
          }
          if (SharedPreferencesUtil().onboardingCompleted) {
            if (!SharedPreferencesUtil().permissionsCompleted) {
              return const _PermissionsGate();
            }
            return const HomePageWrapper();
          } else {
            return const OnboardingWrapper();
          }
        } else {
          return const DeviceSelectionPage();
        }
      },
    );"""

new_build_body = """    // BYPASS: skip Firebase auth — go straight to home
    SharedPreferencesUtil().seedLimitlessDevice();
    return const HomePageWrapper();"""

if old_build_body in app:
    app = app.replace(old_build_body, new_build_body, 1)
    with open(app_path, "w") as f:
        f.write(app)
    print("✅ mobile_app.dart: auth bypass applied (exact match)")
else:
    print("❌ mobile_app.dart: exact match failed — app may show login")
    sys.exit(1)

# ─── 2. seedLimitlessDevice in LocalRecordingsProvider constructor ────────────
lrp_path = f"{base}/providers/local_recordings_provider.dart"
with open(lrp_path) as f:
    lrp = f.read()

old_ctor = "  LocalRecordingsProvider() {\n    _audio.addListener(_onAudioChanged);"
new_ctor = (
    "  LocalRecordingsProvider() {\n"
    "    // BYPASS: seed prefs before _maybeAutoUpload() reads autoSyncOfflineRecordings\n"
    "    SharedPreferencesUtil().seedLimitlessDevice();\n"
    "    _audio.addListener(_onAudioChanged);"
)

if old_ctor in lrp and "BYPASS: seed prefs" not in lrp:
    lrp = lrp.replace(old_ctor, new_ctor, 1)
    with open(lrp_path, "w") as f:
        f.write(lrp)
    print("✅ local_recordings_provider.dart: seedLimitlessDevice in constructor")
else:
    print(f"local_recordings_provider.dart: found={old_ctor in lrp}, already={'BYPASS: seed prefs' in lrp}")

print("Done — 2 patches applied")
# Wed Jul 22 08:35:43 AM UTC 2026
# build trigger Wed Jul 22 09:19:58 AM UTC 2026
# Wed Jul 22 10:45:13 AM UTC 2026

# ─── 3. Add seedLimitlessDevice() to SharedPreferencesUtil ───────────────────
prefs_path = f"{base}/backend/preferences.dart"
with open(prefs_path) as f:
    prefs = f.read()

SEED_METHOD = """
  // BYPASS: seed Limitless Pendant prefs so _maybeAutoUpload works
  void seedLimitlessDevice() {
    saveBool('autoSyncOfflineRecordings', true);
    saveBool('useCustomStt', false);
    saveBool('batchModeEnabled', true);
    saveBool('unlimitedLocalStorageEnabled', true);
    if (getString('btDevice')?.isEmpty != false) {
      saveString('btDevice', '{"name":"Pendant","id":"FD:04:D0:EB:84:88","type":"limitless","rssi":-60,"locator":null,"modelNumber":"Limitless Pendant","firmwareRevision":"1.0.0","hardwareRevision":"Unknown","manufacturerName":"Limitless","serialNumber":null}');
    }
    saveBool('onboardingCompleted', true);
    saveBool('deviceOnboardingCompleted', true);
    saveBool('permissionsCompleted', true);
    saveBool('aiConsentGiven', true);
  }
"""

target = "class SharedPreferencesUtil {"
if target in prefs and "seedLimitlessDevice" not in prefs:
    prefs = prefs.replace(target, target + SEED_METHOD)
    with open(prefs_path, "w") as f:
        f.write(prefs)
    print("✅ SharedPreferencesUtil.seedLimitlessDevice() added")
else:
    print(f"prefs: found={target in prefs}, already={'seedLimitlessDevice' in prefs}")

# ─── 4. Change package ID to avoid Android signing/identity conflict ─────────
import subprocess

# Update applicationId in build.gradle
build_gradle = "app/android/app/build.gradle"
with open(build_gradle) as f:
    gradle = f.read()

gradle = gradle.replace(
    'applicationId "com.friend.ios"',
    'applicationId "com.enzoduit.listen"'
)
gradle = gradle.replace(
    'applicationId "com.friend.ios.dev"',
    'applicationId "com.enzoduit.listen.dev"'
)

with open(build_gradle, "w") as f:
    f.write(gradle)
print("✅ applicationId changed to com.enzoduit.listen")

# Update namespace
gradle2 = open(build_gradle).read()
gradle2 = gradle2.replace('namespace "com.friend.ios"', 'namespace "com.enzoduit.listen"')
open(build_gradle, "w").write(gradle2)

# Update MainActivity.kt
import os
for root, dirs, files in os.walk("app/android"):
    for fname in files:
        if fname == "MainActivity.kt":
            path = os.path.join(root, fname)
            content = open(path).read()
            content = content.replace("package com.friend.ios", "package com.enzoduit.listen")
            open(path, "w").write(content)
            print(f"✅ MainActivity.kt package updated: {path}")

# ─── 5. Update google-services.json with new package name ────────────────────
import json as json_mod

gservices_path = "app/android/app/src/prod/google-services.json"
with open(gservices_path) as f:
    gs = json_mod.load(f)

# Update package name in all client entries
for client in gs.get("client", []):
    info = client.get("client_info", {})
    android_info = info.get("android_client_info", {})
    if android_info.get("package_name") == "com.friend.ios":
        android_info["package_name"] = "com.enzoduit.listen"
        print("✅ google-services.json package_name updated")

with open(gservices_path, "w") as f:
    json_mod.dump(gs, f, indent=2)
