import os
import uuid
import datetime
import asyncio
import io
import requests
import httpx
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Allow running directly: python main.py (Railway-friendly)
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, ws="websockets")

app = FastAPI(title="Pendant Backend", version="2.0.0")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
HIS_TOKEN = os.environ.get("HIS_TOKEN", "")
HIS_URL = os.environ.get("HIS_URL", "http://188.245.214.39:8765/ingest")

SESSION_ID = "pendant-stream"

# ---------------------------------------------------------------------------
# Bearer token middleware — accept any bearer token, or no token (personal use)
# ---------------------------------------------------------------------------

class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Always allow /health and WebSocket upgrades (handled separately)
        if request.url.path == "/health":
            return await call_next(request)
        # For all other paths: just pass through (no verification needed)
        return await call_next(request)

app.add_middleware(BearerAuthMiddleware)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def push_to_his(transcript: str, ts: datetime.datetime) -> dict:
    """Push transcript to Human Input Store."""
    ts_iso = ts.isoformat()
    date_str = ts.strftime("%Y-%m-%d")
    uid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{SESSION_ID}:{ts_iso}"))
    word_count = len(transcript.split())

    payload = {
        "id": uid,
        "ts": ts_iso,
        "date": date_str,
        "source": "pendant",
        "channel": "pendant",
        "session_id": SESSION_ID,
        "raw_text": transcript,
        "speaker_confidence": "certain",
        "speaker_raw": "Ed (pendant)",
        "word_count": word_count,
    }

    headers = {
        "Authorization": f"Bearer {HIS_TOKEN}",
        "Content-Type": "application/json",
    }

    resp = requests.post(HIS_URL, json=payload, headers=headers, timeout=10)
    resp.raise_for_status()
    return payload


def transcribe_with_whisper(audio_bytes: bytes, language: str = "en") -> str:
    """Send audio bytes to OpenAI Whisper and return transcript text."""
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not set")

    resp = requests.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        files={"file": ("audio.wav", audio_bytes, "audio/wav")},
        data={"model": "whisper-1", "language": language},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json().get("text", "").strip()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Auth endpoint — Omi calls this on startup
# ---------------------------------------------------------------------------

@app.post("/v1/auth/authorize")
async def authorize(request: Request):
    """Omi auth endpoint — skip Firebase verification for personal use."""
    # Accept any token, return fixed personal user
    return JSONResponse({
        "uid": "ed-pendant",
        "token": "ed-pendant-session-token",
        "name": "Ed",
    })


# ---------------------------------------------------------------------------
# User endpoint
# ---------------------------------------------------------------------------

@app.get("/v1/me")
async def get_me():
    return JSONResponse({
        "uid": "ed-pendant",
        "name": "Ed",
        "email": "e.duit@augedo.com",
    })


# ---------------------------------------------------------------------------
# Memories endpoints
# ---------------------------------------------------------------------------

@app.get("/v3/memories")
async def get_memories():
    return JSONResponse({"memories": []})


@app.post("/v3/memories")
async def create_memory(request: Request):
    return JSONResponse({"id": "ok"})


# ---------------------------------------------------------------------------
# WebSocket audio streaming — /v4/listen
# ---------------------------------------------------------------------------

AUDIO_FLUSH_INTERVAL = 30  # seconds

@app.websocket("/v4/listen")
async def websocket_listen(
    websocket: WebSocket,
    uid: str = "ed-pendant",
    language: str = "en",
    sample_rate: int = 16000,
):
    """
    Omi app streams binary audio chunks here.
    Every ~30s (or on disconnect) we transcribe with Whisper + push to HIS.
    We send back JSON messages: {"text": "...", "is_final": true/false}
    """
    await websocket.accept()

    audio_buffer = bytearray()
    last_flush = asyncio.get_event_loop().time()

    async def flush_buffer(is_final: bool):
        nonlocal audio_buffer, last_flush
        if not audio_buffer:
            return
        chunk = bytes(audio_buffer)
        audio_buffer = bytearray()
        last_flush = asyncio.get_event_loop().time()

        try:
            text = transcribe_with_whisper(chunk, language=language)
        except Exception as e:
            print(f"[ws] Whisper error: {e}")
            text = ""

        if text:
            ts = datetime.datetime.utcnow()
            try:
                push_to_his(text, ts)
            except Exception as e:
                print(f"[ws] HIS push failed: {e}")

            try:
                await websocket.send_json({"text": text, "is_final": is_final})
            except Exception:
                pass

    try:
        while True:
            try:
                # Wait for audio data (binary) or a text ping; timeout every second
                data = await asyncio.wait_for(websocket.receive(), timeout=1.0)
            except asyncio.TimeoutError:
                # Check if we should flush
                elapsed = asyncio.get_event_loop().time() - last_flush
                if elapsed >= AUDIO_FLUSH_INTERVAL and audio_buffer:
                    await flush_buffer(is_final=False)
                continue

            if data["type"] == "websocket.disconnect":
                break

            if data["type"] == "websocket.receive":
                if data.get("bytes"):
                    audio_buffer.extend(data["bytes"])
                # Check time-based flush
                elapsed = asyncio.get_event_loop().time() - last_flush
                if elapsed >= AUDIO_FLUSH_INTERVAL and audio_buffer:
                    await flush_buffer(is_final=False)

    except WebSocketDisconnect:
        pass
    finally:
        # Flush remaining audio on disconnect
        await flush_buffer(is_final=True)


# ---------------------------------------------------------------------------
# Legacy endpoints (kept for compatibility)
# ---------------------------------------------------------------------------

@app.post("/audio")
async def transcribe_audio(file: UploadFile = File(...)):
    """Receive audio file, transcribe via Whisper, push to HIS."""
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not set")

    audio_bytes = await file.read()
    filename = file.filename or "audio.wav"

    try:
        resp = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            files={"file": (filename, audio_bytes, file.content_type or "audio/wav")},
            data={"model": "whisper-1"},
            timeout=60,
        )
        resp.raise_for_status()
        transcript = resp.json().get("text", "").strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Whisper error: {str(e)}")

    if not transcript:
        return JSONResponse({"transcript": "", "pushed": False})

    ts = datetime.datetime.utcnow()
    try:
        his_payload = push_to_his(transcript, ts)
        pushed = True
    except Exception as e:
        his_payload = {}
        pushed = False
        print(f"HIS push failed: {e}")

    return JSONResponse({
        "transcript": transcript,
        "pushed": pushed,
        "his_id": his_payload.get("id"),
    })


@app.post("/webhook")
async def omi_webhook(request: Request):
    """Receive Omi-style webhook JSON with transcript."""
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    transcript = data.get("transcript") or data.get("text") or ""
    if not transcript:
        segments = data.get("segments", [])
        if segments:
            transcript = " ".join(s.get("text", "") for s in segments).strip()

    if not transcript:
        return JSONResponse({"status": "no_transcript"})

    ts = datetime.datetime.utcnow()
    try:
        his_payload = push_to_his(transcript, ts)
        pushed = True
    except Exception as e:
        his_payload = {}
        pushed = False
        print(f"HIS push failed: {e}")

    return JSONResponse({
        "status": "ok",
        "transcript": transcript,
        "pushed": pushed,
        "his_id": his_payload.get("id"),
    })



# ---------------------------------------------------------------------------
# Language endpoint — must return exact schema the app expects
# ---------------------------------------------------------------------------

@app.patch("/v1/users/language")
async def set_language(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    lang = data.get("language", "en")
    multi_lang = ["multi", "de", "es", "fr", "it", "pt", "nl", "pl", "ru", "zh", "ja", "ko", "ar", "tr", "sv", "da", "fi", "no", "cs", "hu", "ro", "uk", "he", "el", "th", "id", "ms", "vi", "hi"]
    single_language_mode = lang not in multi_lang
    return JSONResponse({
        "status": "ok",
        "message": "Language updated",
        "single_language_mode": single_language_mode,
    })

@app.get("/v1/users/language")
async def get_language():
    return JSONResponse({
        "status": "ok",
        "language": "en",
        "single_language_mode": False,
    })

# ---------------------------------------------------------------------------
# Catch-all — return 200 for any unknown endpoint the Omi app calls
# This prevents "Error" popups for endpoints we haven't implemented yet
# ---------------------------------------------------------------------------

from fastapi import APIRouter
from fastapi.routing import APIRoute
from starlette.routing import Route, Mount

@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def v1_catchall(path: str, request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    print(f"[catchall] {request.method} /v1/{path} body={body}")
    return JSONResponse({"status": "ok", "message": "ok"})

@app.api_route("/v2/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def v2_catchall(path: str, request: Request):
    return JSONResponse({"status": "ok"})

@app.api_route("/v3/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def v3_catchall(path: str, request: Request):
    return JSONResponse({"status": "ok", "memories": [], "conversations": []})
