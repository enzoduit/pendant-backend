# Pendant Backend — Status

## ✅ Railway Backend LIVE

**URL:** https://pendant-backend-production.up.railway.app
**Health:** https://pendant-backend-production.up.railway.app/health → {"status":"ok"}
**GitHub:** https://github.com/enzoduit/pendant-backend (private)
**Deployed:** 2026-07-09

### Endpoints
- `GET /health` — liveness check
- `POST /audio` — multipart audio file → Whisper → Human Input Store
- `POST /webhook` — Omi-style webhook JSON → Human Input Store

### Env vars set
- OPENAI_API_KEY ✅
- HIS_TOKEN ✅
- HIS_URL ✅

---

## Omi Fork — Findings

See OMI_FORK_NOTES.md for full details.

**TL;DR:**
- Limitless Pendant IS natively supported in Omi app ✅
- Backend URL set via `app/.env` key `API_BASE_URL` before Flutter build
- App uses WebSocket `wss://backend/v4/listen` for real-time audio streaming
- Also uses REST endpoints for auth/memories

**Easiest path (no APK build needed):**
1. Use official Omi app from Play Store
2. In app settings → set Webhook URL to: https://pendant-backend-production.up.railway.app/webhook
3. Transcripts land in Human Input Store automatically

**Full control path (custom APK):**
1. Clone enzoduit/pendant-backend (or BasedHardware/omi)
2. Set API_BASE_URL=https://pendant-backend-production.up.railway.app/ in app/.env
3. Add WebSocket /v4/listen endpoint to backend (for real-time mode)
4. Build with: flutter build apk --debug --flavor prod

---

## Next Steps
1. **Try webhook path first** — install Omi app, pair Limitless Pendant, set webhook URL
2. If webhook works: done ✅
3. If custom APK needed: Ed needs Flutter installed, or we build in CI
