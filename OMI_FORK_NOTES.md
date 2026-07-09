# Omi Android Fork Notes
## Research Date: 2026-07-09
## Repo: https://github.com/BasedHardware/omi (depth-1 clone)

---

## 1. Backend URL Configuration

### Primary Config File
**File:** `app/lib/env/env.dart`  
**Key line:** `static String? get apiBaseUrl => _apiBaseUrlOverride ?? _instance.apiBaseUrl;`

The `apiBaseUrl` is loaded from a `.env` file at build time via the `envied` package (code generation).

### How it works:
- **Production:** `app/.env` → key `API_BASE_URL` → compiled into `app/lib/env/prod_env.g.dart`
- **Dev:** `app/.dev.env` → key `API_BASE_URL` → compiled into `app/lib/env/dev_env.g.dart`
- Template: `app/.env.template` shows required fields

**To point to our backend:** Set `API_BASE_URL=https://pendant-api-production.up.railway.app/` in `app/.env` before building.

### Env Template (`app/.env.template`):
```
OPENAI_API_KEY=
API_BASE_URL=
GOOGLE_MAPS_API_KEY=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
USE_WEB_AUTH=false
USE_AUTH_CUSTOM_TOKEN=false
STAGING_API_URL=
POSTHOG_API_KEY=
```

---

## 2. API Endpoints the App Uses

The app talks to the backend via:
- **REST:** `${Env.apiBaseUrl}v1/...`, `${Env.apiBaseUrl}v3/...`  
  e.g., `${Env.apiBaseUrl}v1/auth/authorize`, `${Env.apiBaseUrl}v3/memories`
- **WebSocket (audio streaming):** `wss://${host}/v4/listen` — for real-time transcription
  - File: `app/lib/services/sockets/transcription_service.dart` line ~128
  - `Env.apiBaseUrl.replaceFirst('https://', 'wss://') + 'v4/listen$params'`

### Key auth flow:
- Uses Firebase Auth (google sign-in) + sends `Bearer ${authToken}` to backend
- Our fork needs to: disable Firebase auth OR implement a compatible token pass-through

---

## 3. Limitless Pendant Hardware Support

**YES — Limitless Pendant is already supported!**

- `DeviceType.limitless` enum value: `app/lib/backend/schema/bt_device/bt_device.dart:187`
- Connection guide references `'id': 'limitless'`: `app/lib/widgets/connection_guide_sheet.dart:52`
- Special handling in capture controller:
  - `case DeviceType.limitless: return 'limitless';` (line 306)
  - `_applyLimitlessRealtimeSuppression()` method — manages BLE audio suppression
  - Limitless does NOT support background mode (line 1111)
- **Conclusion:** The Omi app already knows about the Limitless Pendant. No hardware changes needed.

---

## 4. Fork Strategy — Simple URL Change?

**Partially yes, but with caveats:**

### What a URL change gives us:
✅ Audio streaming goes to our websocket endpoint (`wss://our-backend/v4/listen`)  
✅ REST API calls go to our backend  
✅ Limitless Pendant hardware is recognized  

### What needs more work:
⚠️ **Firebase Auth:** The app uses Firebase for auth and sends a Firebase token to the backend. Our pendant-backend doesn't validate Firebase tokens. Options:
  1. Set `USE_AUTH_CUSTOM_TOKEN=true` and implement custom token endpoint
  2. Disable auth in backend (fine for personal use — our backend is personal)
  3. Modify the app to skip auth (more invasive)

⚠️ **WebSocket `/v4/listen`:** Our current backend has `/audio` (REST file upload) and `/webhook`. We'd need to add a WebSocket endpoint that matches Omi's protocol for real-time streaming.

### Recommended approach for Ed:
Use the **webhook/batch mode** path: configure the Omi app to send completed audio segments as webhooks to `/webhook`. This avoids the websocket complexity for now.

---

## 5. Flutter Build Instructions

### Prerequisites:
```bash
flutter pub get
dart run build_runner build --delete-conflicting-outputs
```

### Step-by-step to build a custom APK:

```bash
# 1. Clone the repo
git clone --depth 1 https://github.com/BasedHardware/omi omi-fork
cd omi-fork/app

# 2. Create your .env file
cat > .env << 'EOF'
API_BASE_URL=https://pendant-api-production.up.railway.app/
OPENAI_API_KEY=
GOOGLE_MAPS_API_KEY=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
USE_WEB_AUTH=false
USE_AUTH_CUSTOM_TOKEN=false
STAGING_API_URL=
POSTHOG_API_KEY=
EOF

# 3. Install dependencies
flutter pub get

# 4. Generate env code (REQUIRED - compiles .env into Dart)
dart run build_runner build --delete-conflicting-outputs

# 5. Build APK (debug for testing)
flutter build apk --debug --flavor prod

# 6. Or release APK (needs signing keystore)
flutter build apk --release --flavor prod
```

### Notes:
- The app uses **flavors** (`prod` and `dev`) — always specify `--flavor prod` for production
- Firebase requires `google-services.json` in `android/app/` — you'll need to create a Firebase project or reuse BasedHardware's (if they allow it)
- For sideloading on Android: enable "Install from unknown sources", install the debug APK directly

### Easier alternative — use Omi's webhook integration:
Instead of building a custom APK, configure the official Omi app to forward transcripts via webhook to our backend:
1. In Omi app: Settings → Developer → Webhook URL
2. Set to: `https://pendant-api-production.up.railway.app/webhook`
3. Our `/webhook` endpoint handles the Omi webhook format

---

## 6. Architecture Summary

```
Limitless Pendant (BLE)
        ↓
  Omi Android App
  (captures audio)
        ↓
  [Option A - Webhook]           [Option B - Custom APK]
  Official app + webhook URL  OR  Fork with API_BASE_URL changed
        ↓                                ↓
  POST /webhook                   WebSocket /v4/listen + REST
        ↓                                ↓
  pendant-backend (Railway)
        ↓
  OpenAI Whisper API
        ↓
  Human Input Store (HIS)
```
