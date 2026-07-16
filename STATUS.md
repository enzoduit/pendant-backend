# Pendant Backend — Status
_Last updated: 2026-07-09_

## ✅ Railway Backend

**URL (NEW):** https://pendant-backend-production-e97c.up.railway.app  
**URL (OLD - stale):** https://pendant-api-production.up.railway.app  
**GitHub:** https://github.com/enzoduit/pendant-backend  
**Railway Project:** b60595e4-1b1d-418c-8e51-41fb7006fa0e  
**Service (NEW):** 9f9bd815-06da-4466-a810-e72f2a1a352a  
**Service (OLD - stale):** 29ec5ed6-b391-4d42-b15d-d9933428504a  

### Health Check
```
GET /health → {"status":"ok"} ✅
```

### Endpoints
- `GET /health` — health check
- `POST /audio` — multipart file upload → Whisper → HIS
- `POST /webhook` — Omi-style JSON webhook → HIS

### Env Vars Set on Railway
- `OPENAI_API_KEY` ✅
- `HIS_TOKEN` ✅
- `HIS_URL` ✅ (http://188.245.214.39:8765/ingest)

---

## 📱 Omi Fork Summary

### Good News: Limitless Pendant is Already Supported
The Omi app has native `DeviceType.limitless` support — no hardware hacks needed.

### Backend URL Config
- File: `app/lib/env/env.dart` + `app/.env` (template at `app/.env.template`)
- Variable: `API_BASE_URL=https://pendant-api-production.up.railway.app/`
- Built via `envied` code-gen: `dart run build_runner build`

### Two Integration Paths

#### Path A — Easiest: Official App + Webhook (no build needed)
1. Install official Omi app on Android
2. Go to Settings → Developer → Webhook URL
3. Set to: `https://pendant-api-production.up.railway.app/webhook`
4. Done — transcripts flow to HIS automatically

#### Path B — Custom APK (full control)
Fork enzoduit/omi, set `API_BASE_URL` in `.env`, run:
```
flutter pub get
dart run build_runner build --delete-conflicting-outputs
flutter build apk --debug --flavor prod
```
⚠️ Requires Firebase `google-services.json` + Flutter SDK

Full fork details: `OMI_FORK_NOTES.md`

---

## 🔜 Next Steps

1. **Immediate:** Test webhook integration with official Omi app
   - Set webhook URL in Omi: `https://pendant-api-production.up.railway.app/webhook`
   - Speak something with the Limitless Pendant
   - Check HIS: `curl http://188.245.214.39:8765/health`

2. **Optional:** Add WebSocket `/v4/listen` endpoint to pendant-backend for real-time streaming (needed for custom APK path)

3. **Optional:** Custom APK build — needs Firebase project + Flutter SDK on build machine

4. **Monitor:** Check Railway logs for successful Whisper transcriptions:
   `railway logs --service pendant-api`
# Rebuilt Thu Jul  9 11:32:59 PM UTC 2026
# Tue Jul 14 08:46:22 AM UTC 2026
# rebuild Thu Jul 16 02:02:22 PM UTC 2026
