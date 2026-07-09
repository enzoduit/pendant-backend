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

# 2. Patch mobile_app.dart - skip onboarding, go straight to HomePageWrapper
app_path = f"{base}/mobile/mobile_app.dart"
with open(app_path) as f:
    app = f.read()

# Find and replace the signed-in block
old_block = """        if (authProvider.isSignedIn()) {
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
        }"""

new_block = """        if (authProvider.isSignedIn()) {
          // BYPASS: skip onboarding for personal use
          return const HomePageWrapper();
        } else {
          return const DeviceSelectionPage();
        }"""

if old_block in app:
    app = app.replace(old_block, new_block)
    print("mobile_app.dart patched - onboarding bypassed")
else:
    print("WARNING: mobile_app.dart pattern not found exactly, trying regex")
    # Fallback: simpler replacement
    app = re.sub(
        r'if \(authProvider\.isSignedIn\(\)\) \{.*?return const DeviceSelectionPage\(\);',
        'if (authProvider.isSignedIn()) {\n          return const HomePageWrapper(); // BYPASS\n        } else {\n          return const DeviceSelectionPage();',
        app, flags=re.DOTALL
    )
    print("mobile_app.dart patched via regex")

with open(app_path, "w") as f:
    f.write(app)

print("All patches done!")
