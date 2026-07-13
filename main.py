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

app = FastAPI(title="Pendant Backend", version="3.0.0")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
HIS_TOKEN = os.environ.get("HIS_TOKEN", "")
HIS_URL = os.environ.get("HIS_URL", "http://188.245.214.39:8765/ingest")
SESSION_ID = "pendant-stream"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def push_to_his(transcript: str, ts: datetime.datetime) -> dict:
    ts_iso = ts.isoformat()
    date_str = ts.strftime("%Y-%m-%d")
    uid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{SESSION_ID}:{ts_iso}"))
    word_count = len(transcript.split())
    payload = {
        "id": uid, "ts": ts_iso, "date": date_str, "source": "pendant",
        "channel": "pendant", "session_id": SESSION_ID, "raw_text": transcript,
        "speaker_confidence": "certain", "speaker_raw": "Ed (pendant)", "word_count": word_count,
    }
    headers = {"Authorization": f"Bearer {HIS_TOKEN}", "Content-Type": "application/json"}
    resp = requests.post(HIS_URL, json={"rows": [payload]}, headers=headers, timeout=10)
    print(f"[HIS] push status={resp.status_code} text={transcript[:60]}")
    return payload


def transcribe_with_whisper(audio_bytes: bytes, language: str = "en") -> str:
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not set")
    if len(audio_bytes) < 1000:
        print(f"[ws] audio too short ({len(audio_bytes)} bytes), skipping")
        return ""
    print(f"[ws] sending {len(audio_bytes)} bytes to Whisper...")
    resp = requests.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        files={"file": ("audio.opus", audio_bytes, "audio/ogg; codecs=opus")},
        data={"model": "whisper-1", "language": language},
        timeout=60,
    )
    resp.raise_for_status()
    text = resp.json().get("text", "").strip()
    print(f"[ws] transcript: {text[:100]}")
    return text

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.post("/v1/auth/authorize")
async def authorize(request: Request):
    return JSONResponse({"uid": "ed-pendant", "token": "ed-pendant-session-token", "name": "Ed"})

@app.get("/v1/me")
async def get_me():
    return JSONResponse({"uid": "ed-pendant", "name": "Ed", "email": "e.duit@augedo.com"})

# ---------------------------------------------------------------------------
# Language endpoints
# ---------------------------------------------------------------------------

@app.patch("/v1/users/language")
async def set_language(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    lang = data.get("language", "en")
    multi_lang = ["multi", "de", "es", "fr", "it", "pt", "nl", "pl", "ru", "zh", "ja", "ko", "ar", "tr", "sv", "da", "fi", "no", "cs", "hu", "ro", "uk", "he", "el", "th", "id", "ms", "vi", "hi"]
    return JSONResponse({"status": "ok", "message": "Language updated", "single_language_mode": lang not in multi_lang})

@app.get("/v1/users/language")
async def get_language():
    return JSONResponse({"status": "ok", "language": "en", "single_language_mode": False})

# ---------------------------------------------------------------------------
# Memories
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
    await websocket.accept()
    print(f"[ws] connected uid={uid} lang={language} sr={sample_rate}")

    audio_buffer = bytearray()
    last_flush = asyncio.get_event_loop().time()
    bytes_received = 0

    async def flush_buffer(is_final: bool):
        nonlocal audio_buffer, last_flush, bytes_received
        if not audio_buffer:
            print(f"[ws] flush called but buffer empty")
            return
        chunk = bytes(audio_buffer)
        audio_buffer = bytearray()
        last_flush = asyncio.get_event_loop().time()
        print(f"[ws] flushing {len(chunk)} bytes (is_final={is_final})")

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
                data = await asyncio.wait_for(websocket.receive(), timeout=1.0)
            except asyncio.TimeoutError:
                elapsed = asyncio.get_event_loop().time() - last_flush
                if elapsed >= AUDIO_FLUSH_INTERVAL and audio_buffer:
                    await flush_buffer(is_final=False)
                continue

            if data["type"] == "websocket.disconnect":
                print(f"[ws] disconnect received, total bytes={bytes_received}")
                break

            if data["type"] == "websocket.receive":
                if data.get("bytes"):
                    chunk = data["bytes"]
                    audio_buffer.extend(chunk)
                    bytes_received += len(chunk)
                    if bytes_received % 10000 < len(chunk):
                        print(f"[ws] received {bytes_received} bytes total, buffer={len(audio_buffer)}")
                elif data.get("text"):
                    print(f"[ws] text frame: {data['text'][:50]}")

                elapsed = asyncio.get_event_loop().time() - last_flush
                if elapsed >= AUDIO_FLUSH_INTERVAL and audio_buffer:
                    await flush_buffer(is_final=False)

    except WebSocketDisconnect:
        print(f"[ws] WebSocketDisconnect, total bytes={bytes_received}")
    except Exception as e:
        print(f"[ws] unexpected error: {e}")
    finally:
        print(f"[ws] closing, flushing final buffer ({len(audio_buffer)} bytes)")
        await flush_buffer(is_final=True)

# ---------------------------------------------------------------------------
# Legacy REST audio endpoint
# ---------------------------------------------------------------------------

@app.post("/audio")
async def transcribe_audio(file: UploadFile = File(...)):
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
    return JSONResponse({"transcript": transcript, "pushed": pushed, "his_id": his_payload.get("id")})

@app.post("/webhook")
async def omi_webhook(request: Request):
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
    return JSONResponse({"status": "ok", "transcript": transcript, "pushed": pushed})


# ---------------------------------------------------------------------------
# POST /v2/sync-local-files — "Transcribir después" mode
# App sends recorded audio file after conversation ends
# ---------------------------------------------------------------------------

@app.post("/v2/sync-local-files")
async def sync_local_files(request: Request):
    """Receive recorded audio from Omi app, transcribe via Whisper, push to HIS."""
    import tempfile, os
    from fastapi import Form

    content_type = request.headers.get("content-type", "")
    audio_bytes = None
    filename = "audio.opus"

    if "multipart" in content_type:
        from starlette.datastructures import UploadFile as StarletteUpload
        form = await request.form()
        print(f"[sync] form fields: {list(form.keys())}")
        for key, val in form.items():
            if hasattr(val, "read"):
                audio_bytes = await val.read()
                filename = val.filename or "audio.opus"
                print(f"[sync] received file: {filename} ({len(audio_bytes)} bytes)")
                break
    else:
        audio_bytes = await request.body()
        print(f"[sync] received raw body: {len(audio_bytes)} bytes")

    if not audio_bytes or len(audio_bytes) < 100:
        print(f"[sync] no audio or too short")
        return JSONResponse({
            "failed_segments": 0, "total_segments": 0,
            "new_memories": [], "updated_memories": [], "errors": []
        })

    # Decode WAL format if .bin file (Omi WAL: [u32_le length][opus frame] repeated)
    whisper_bytes = audio_bytes
    whisper_filename = filename
    if filename.endswith(".bin"):
        try:
            import struct, subprocess, tempfile as tf
            # Extract raw opus frames from WAL framing
            frames = []
            offset = 0
            data = audio_bytes
            while offset + 4 <= len(data):
                frame_len = struct.unpack_from("<I", data, offset)[0]
                offset += 4
                if frame_len == 0 or offset + frame_len > len(data):
                    break
                frames.append(data[offset:offset + frame_len])
                offset += frame_len
            print(f"[sync] WAL decoded: {len(frames)} opus frames from {len(audio_bytes)} bytes")

            if frames:
                # Write frames to temp opus file then convert to wav via ffmpeg
                tmp_opus = tf.NamedTemporaryFile(suffix=".opus", delete=False)
                # Wrap in ogg container using ffmpeg from raw opus frames
                raw_opus_path = tmp_opus.name
                # Write raw concatenated opus frames
                tmp_raw = tf.NamedTemporaryFile(suffix=".raw", delete=False)
                for f in frames:
                    tmp_raw.write(f)
                tmp_raw.flush()
                tmp_raw.close()

                tmp_wav = tf.NamedTemporaryFile(suffix=".wav", delete=False)
                tmp_wav.close()

                # Use ffmpeg to convert raw opus frames (as ogg) to wav
                # First wrap in ogg, then to wav
                result = subprocess.run([
                    "ffmpeg", "-y",
                    "-f", "data", "-i", tmp_raw.name,
                    "-ar", "16000", "-ac", "1",
                    tmp_wav.name
                ], capture_output=True, timeout=30)

                if result.returncode != 0:
                    # Fallback: try treating raw data as opus directly
                    print(f"[sync] ffmpeg failed ({result.stderr[:100]}), sending raw to whisper")
                    whisper_bytes = audio_bytes
                    whisper_filename = "audio.ogg"
                else:
                    with open(tmp_wav.name, "rb") as wf:
                        whisper_bytes = wf.read()
                    whisper_filename = "audio.wav"
                    print(f"[sync] converted to wav: {len(whisper_bytes)} bytes")

                import os as _os
                for p in [tmp_raw.name, tmp_wav.name, tmp_opus.name]:
                    try: _os.unlink(p)
                    except: pass
        except Exception as e:
            print(f"[sync] WAL decode error: {e}, sending raw")
            whisper_filename = "audio.ogg"

    # Transcribe
    try:
        mime = "audio/ogg; codecs=opus"
        if whisper_filename.endswith(".wav"):
            mime = "audio/wav"
        elif whisper_filename.endswith(".mp4") or whisper_filename.endswith(".m4a"):
            mime = "audio/mp4"

        resp = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            files={"file": (whisper_filename, whisper_bytes, mime)},
            data={"model": "whisper-1"},
            timeout=120,
        )
        resp.raise_for_status()
        transcript = resp.json().get("text", "").strip()
        print(f"[sync] transcript: {transcript[:100]}")
    except Exception as e:
        print(f"[sync] Whisper error: {e}")
        return JSONResponse({
            "failed_segments": 1, "total_segments": 1,
            "new_memories": [], "updated_memories": [], "errors": [str(e)]
        })

    if transcript:
        ts = datetime.datetime.utcnow()
        try:
            push_to_his(transcript, ts)
        except Exception as e:
            print(f"[sync] HIS push failed: {e}")

    return JSONResponse({
        "failed_segments": 0,
        "total_segments": 1,
        "new_memories": [],
        "updated_memories": [],
        "errors": []
    })

@app.get("/v2/sync-local-files/{job_id}")
async def sync_job_status(job_id: str):
    return JSONResponse({"job_id": job_id, "status": "done", "result": {
        "failed_segments": 0, "total_segments": 1,
        "new_memories": [], "updated_memories": [], "errors": []
    }})

# ---------------------------------------------------------------------------
# Catch-all for all other Omi endpoints
# ---------------------------------------------------------------------------

@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def v1_catchall(path: str, request: Request):
    print(f"[catchall] {request.method} /v1/{path}")
    return JSONResponse({"status": "ok", "message": "ok"})

@app.api_route("/v2/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def v2_catchall(path: str, request: Request):
    return JSONResponse({"status": "ok"})

@app.api_route("/v3/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def v3_catchall(path: str, request: Request):
    return JSONResponse({"status": "ok", "memories": [], "conversations": []})
