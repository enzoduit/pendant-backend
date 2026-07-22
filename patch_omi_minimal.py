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
