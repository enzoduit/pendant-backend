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
# ---------------------------------------------------------------------------
# Request logging — track all inbound calls
# ---------------------------------------------------------------------------
_request_log = []

@app.middleware("http")
async def log_requests(request: Request, call_next):
    import time
    start = time.time()
    response = await call_next(request)
    elapsed = round((time.time() - start) * 1000)
    entry = {
        "ts": datetime.datetime.utcnow().isoformat(),
        "method": request.method,
        "path": str(request.url.path),
        "status": response.status_code,
        "ms": elapsed,
        "ua": request.headers.get("user-agent", "")[:60],
    }
    _request_log.append(entry)
    if len(_request_log) > 200:
        _request_log.pop(0)
    print(f"[req] {entry['method']} {entry['path']} → {entry['status']} ({elapsed}ms)")
    return response

@app.get("/v1/debug/requests")
async def get_request_log():
    return {"entries": _request_log[-50:]}



OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
HIS_TOKEN = os.environ.get("HIS_TOKEN", "")
HIS_URL = os.environ.get("HIS_URL", "http://188.245.214.39:8765/ingest")
SESSION_ID = "pendant-stream"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Known Whisper hallucinations on silence/noise
WHISPER_HALLUCINATIONS = {
    "谢谢观看", "谢谢观看 欢迎订阅我的频道", "欢迎订阅我的频道",
    "thank you for watching", "thanks for watching",
    "please subscribe", "like and subscribe",
    "ご視聴ありありがとうございました", "字幕",
    "subtitles by", "transcribed by", "www.",
    "[music]", "[applause]", "[silence]", "[ silence ]",
    "you", ".", "..", "...", "♪", "♫",
}

def is_hallucination(text: str) -> bool:
    """Detect Whisper hallucinations on silent/noisy audio."""
    if not text or len(text.strip()) < 3:
        return True
    t = text.strip().lower()
    # Check exact matches
    if t in {h.lower() for h in WHISPER_HALLUCINATIONS}:
        return True
    # Check if it's just punctuation/symbols
    if all(c in '.,!?;:()[]{}♪♫-_=+*/|<>` \t\n' for c in t):
        return True
    # Very short with no real words
    words = [w for w in t.split() if len(w) > 1]
    if len(words) == 0:
        return True
    return False


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
# Shared in-memory log (must be before /logs endpoints and sync functions)
# ---------------------------------------------------------------------------
_debug_log = []

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.post("/logs")
async def logs_post(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {"raw": await request.text()}
    entry = {"ts": datetime.datetime.utcnow().isoformat(), **data}
    _debug_log.append(entry)
    if len(_debug_log) > 1000:
        _debug_log.pop(0)
    msg = entry.get("msg", str(data))
    print(f"[APP] {entry['ts']} {msg}")
    try:
        with open("/tmp/app_debug.log", "a") as f:
            f.write(f"{entry['ts']} {msg}\n")
    except Exception:
        pass
    return JSONResponse({"ok": True})

@app.get("/logs")
async def logs_get():
    entries = list(_debug_log[-200:])
    if not entries:
        try:
            with open("/tmp/app_debug.log", "r") as f:
                lines = f.readlines()[-200:]
            entries = [{"msg": l.strip()} for l in lines]
        except Exception:
            pass
    return JSONResponse({"entries": entries})

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

    print(f"[webhook] received keys: {list(data.keys())}")

    transcript = ""

    # String transcript (simple format)
    raw = data.get("transcript") or data.get("text") or ""
    if isinstance(raw, str) and raw.strip():
        transcript = raw.strip()

    # Omi's actual conversation event format: transcript_segments or segments
    if not transcript:
        segments = data.get("transcript_segments") or data.get("segments") or []
        if segments:
            transcript = " ".join(s.get("text", "") for s in segments if s.get("text")).strip()

    if not transcript:
        print(f"[webhook] no transcript found in payload: {str(data)[:200]}")
        return JSONResponse({"status": "no_transcript"})

    ts = datetime.datetime.utcnow()
    try:
        his_payload = push_to_his(transcript, ts)
        pushed = True
    except Exception as e:
        print(f"[webhook] HIS push error: {e}")
        his_payload = {}
        pushed = False
    return JSONResponse({"status": "ok", "transcript": transcript[:200], "pushed": pushed})


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
                msg = f"[sync] received file: {filename} ({len(audio_bytes)} bytes)"
                print(msg); _debug_log.append({"ts": datetime.datetime.utcnow().isoformat(), "msg": msg})
                # Save every upload to disk for inspection
                import os as _os
                _os.makedirs("/tmp/pendant_uploads", exist_ok=True)
                with open(f"/tmp/pendant_uploads/{filename}", "wb") as _f:
                    _f.write(audio_bytes)
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
    # Uses opuslib to decode raw Opus frames -> PCM -> WAV (same as OMI backend)
    whisper_bytes = audio_bytes
    whisper_filename = filename
    if filename.endswith(".bin"):
        try:
            import struct, wave, io
            # Parse sample rate and frame size from filename
            # e.g. audio_omibatchlimitless_opus_fs320_16000_1_fs320_1783950337.bin
            sample_rate = 16000
            channels = 1
            frame_size = 320  # default for Limitless
            parts = filename.replace(".bin", "").split("_")
            for i, p in enumerate(parts):
                if p.isdigit() and int(p) in (8000, 16000, 24000, 48000):
                    sample_rate = int(p)
                if p.startswith("fs") and p[2:].isdigit():
                    frame_size = int(p[2:])

            # Extract raw opus frames from WAL framing
            frames = []
            offset = 0
            data = audio_bytes
            while offset + 4 <= len(data):
                frame_len = struct.unpack_from("<I", data, offset)[0]
                offset += 4
                if frame_len == 0 or frame_len > 65536 or offset + frame_len > len(data):
                    break
                frames.append(data[offset:offset + frame_len])
                offset += frame_len
            msg2 = f"[sync] WAL decoded: {len(frames)} opus frames, sr={sample_rate}, fs={frame_size}"
            print(msg2); _debug_log.append({"ts": datetime.datetime.utcnow().isoformat(), "msg": msg2})

            if frames:
                # Write raw opus frames into OGG container via ffmpeg (more robust than opuslib)
                import subprocess, tempfile
                # Write WAL frames as raw concatenated opus packets with OGG framing via ffmpeg
                # First write frames to a temp raw file, then use ffmpeg to wrap in OGG
                with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as tmp_in:
                    tmp_in_path = tmp_in.name
                    # Write as simple raw opus: just concatenate frames (ffmpeg can handle with -f data)
                    # Actually write as OGG opus using ffmpeg pipe
                    for frame in frames:
                        tmp_in.write(struct.pack('<I', len(frame)))
                        tmp_in.write(frame)
                
                tmp_wav_path = tmp_in_path + '.wav'
                try:
                    # Use ffmpeg to decode: read WAL format via python pipe → pcm → wav
                    import opuslib
                    decoder = opuslib.Decoder(sample_rate, channels)
                    wav_buf = io.BytesIO()
                    with wave.open(wav_buf, 'wb') as wf:
                        wf.setnchannels(channels)
                        wf.setsampwidth(2)
                        wf.setframerate(sample_rate)
                        good = 0
                        for frame in frames:
                            try:
                                pcm = decoder.decode(bytes(frame), frame_size=frame_size)
                                wf.writeframes(pcm)
                                good += 1
                            except Exception as fe:
                                continue
                    whisper_bytes = wav_buf.getvalue()
                    whisper_filename = "audio.wav"
                    msg3 = f"[sync] opuslib decode: {good}/{len(frames)} frames ok, {len(whisper_bytes)} bytes WAV"
                    print(msg3); _debug_log.append({"ts": datetime.datetime.utcnow().isoformat(), "msg": msg3})
                except Exception as oe:
                    print(f"[sync] opuslib failed ({oe}), trying ffmpeg OGG concat")
                    # Fallback: write raw frames concatenated as ogg-like and send directly
                    raw_opus = b''.join(frames)
                    # Use ffmpeg to convert raw opus frames to wav
                    try:
                        result = subprocess.run(
                            ['ffmpeg', '-y', '-f', 'opus', '-i', 'pipe:0', '-ar', str(sample_rate), '-ac', str(channels), '-f', 'wav', 'pipe:1'],
                            input=raw_opus, capture_output=True, timeout=30
                        )
                        if result.returncode == 0 and len(result.stdout) > 100:
                            whisper_bytes = result.stdout
                            whisper_filename = "audio.wav"
                            print(f"[sync] ffmpeg decode ok: {len(whisper_bytes)} bytes WAV")
                        else:
                            print(f"[sync] ffmpeg failed: {result.stderr[:200]}")
                    except Exception as fe2:
                        print(f"[sync] ffmpeg also failed: {fe2}")
                finally:
                    import os as _os
                    try: _os.unlink(tmp_in_path)
                    except: pass
                # Split into 24MB chunks if needed (Whisper limit is 25MB)
                MAX_WHISPER_BYTES = 24 * 1024 * 1024
                if len(whisper_bytes) > MAX_WHISPER_BYTES:
                    print(f"[sync] large file {len(whisper_bytes)} bytes, splitting into chunks")
                    # WAV header is 44 bytes, audio data follows
                    header = whisper_bytes[:44]
                    audio_data = whisper_bytes[44:]
                    chunk_size = MAX_WHISPER_BYTES - 44
                    chunks = [audio_data[i:i+chunk_size] for i in range(0, len(audio_data), chunk_size)]
                    print(f"[sync] split into {len(chunks)} chunks")
                    chunk_transcripts = []
                    for ci, chunk in enumerate(chunks):
                        chunk_wav = header + chunk
                        try:
                            chunk_resp = requests.post(
                                "https://api.openai.com/v1/audio/transcriptions",
                                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                                files={"file": (f"chunk_{ci}.wav", chunk_wav, "audio/wav")},
                                data={"model": "whisper-1"},
                                timeout=120,
                            )
                            chunk_resp.raise_for_status()
                            t = chunk_resp.json().get("text", "").strip()
                            if t:
                                chunk_transcripts.append(t)
                            print(f"[sync] chunk {ci}: {t[:50]}")
                        except Exception as ce:
                            print(f"[sync] chunk {ci} error: {ce}")
                    # Replace whisper_bytes with a sentinel to skip the main whisper call
                    whisper_bytes = b''
                    transcript = " ".join(chunk_transcripts).strip()
                    print(f"[sync] combined transcript: {transcript[:100]}")
        except Exception as e:
            print(f"[sync] WAL decode error: {e}, sending raw as ogg")
            whisper_filename = "audio.ogg"

    # Transcribe (skip if already transcribed via chunking)
    if 'transcript' not in dir():
        transcript = None
    if transcript is None:
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
            msg4 = f"[sync] transcript: '{transcript[:100]}'"
            print(msg4); _debug_log.append({"ts": datetime.datetime.utcnow().isoformat(), "msg": msg4})
        except Exception as e:
            msg5 = f"[sync] Whisper error: {e}"
            print(msg5); _debug_log.append({"ts": datetime.datetime.utcnow().isoformat(), "msg": msg5})
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


@app.get("/v1/fair-use/status")
async def fair_use_status():
    # Must return stage=none so SyncUploadGate allows uploads
    return JSONResponse({"stage": "none", "status": "ok"})

# ---------------------------------------------------------------------------
# Debug log endpoints — MUST be before the v1 catch-all
# ---------------------------------------------------------------------------

@app.post("/v1/debug/log")
async def debug_log_post(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {"raw": await request.text()}
    entry = {"ts": datetime.datetime.utcnow().isoformat(), **data}
    _debug_log.append(entry)
    if len(_debug_log) > 1000:
        _debug_log.pop(0)
    msg = entry.get("msg", str(entry))
    print(f"[APP] {entry.get('ts','')} {msg}")
    try:
        with open("/tmp/app_debug.log", "a") as f:
            f.write(f"{entry.get('ts','')} {msg}\n")
    except Exception:
        pass
    return JSONResponse({"ok": True})

@app.get("/v1/debug/log")
async def debug_log_get():
    entries = list(_debug_log[-200:])
    if not entries:
        try:
            with open("/tmp/app_debug.log", "r") as f:
                lines = f.readlines()[-200:]
            entries = [{"msg": l.strip()} for l in lines]
        except Exception:
            pass
    return JSONResponse({"entries": entries})

# ---------------------------------------------------------------------------
# Catch-all for all other Omi endpoints
# ---------------------------------------------------------------------------

@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def v1_catchall(path: str, request: Request):
    print(f"[catchall] {request.method} /v1/{path}")
    # Endpoints that expect a JSON array
    if path.startswith("conversations") or path.startswith("memories") or path.startswith("action-items"):
        return JSONResponse([])
    # Fair-use status: must return stage=none to unlock uploads
    if path == "fair-use/status" or "fair-use" in path:
        return JSONResponse({"stage": "none", "status": "ok"})
    # Endpoints that expect specific shapes
    if path == "users/me/subscription":
        return JSONResponse({"is_premium": True, "product_id": "none", "platform": "none"})
    if path.startswith("goals"):
        return JSONResponse([])
    if path.startswith("folders"):
        return JSONResponse([])
    if path.startswith("users/people"):
        return JSONResponse([])
    if path.startswith("apps") or path.startswith("app-categories") or path.startswith("app-capabilities") or path.startswith("app/plans"):
        return JSONResponse([])
    if path.startswith("announcements"):
        return JSONResponse([])
    if path.startswith("task-integrations"):
        return JSONResponse([])
    if path.startswith("phone"):
        return JSONResponse([])
    return JSONResponse({"status": "ok", "message": "ok"})

@app.api_route("/v2/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def v2_catchall(path: str, request: Request):
    return JSONResponse({"status": "ok"})

@app.api_route("/v3/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def v3_catchall(path: str, request: Request):
    return JSONResponse({"status": "ok", "memories": [], "conversations": []})


# ---------------------------------------------------------------------------
# (debug log routes moved above v1 catch-all)


# ---------------------------------------------------------------------------
# Realtime Audio Bytes endpoint — OMI Developer Mode streams PCM16 here
# Settings → Developer Mode → Realtime audio bytes → set URL
# ---------------------------------------------------------------------------
@app.post("/api/audio")
async def realtime_audio(request: Request):
    """Receive raw PCM16 audio chunks from OMI app, transcribe via Whisper, push to HIS."""
    audio_bytes = await request.body()
    
    if not audio_bytes or len(audio_bytes) < 1000:
        return JSONResponse({"status": "too_short", "bytes": len(audio_bytes)})
    
    print(f"[realtime] received {len(audio_bytes)} PCM16 bytes")
    
    try:
        # PCM16 at 16kHz mono → wrap in WAV header for Whisper
        import io, wave, struct
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(16000)
            wf.writeframes(audio_bytes)
        wav_bytes = wav_buf.getvalue()
        
        resp = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            files={"file": ("audio.wav", wav_bytes, "audio/wav")},
            data={"model": "whisper-1"},
            timeout=60,
        )
        resp.raise_for_status()
        transcript = resp.json().get("text", "").strip()
        print(f"[realtime] transcript: {transcript[:100]}")
        
        if transcript and not is_hallucination(transcript):
            ts = datetime.datetime.utcnow()
            push_to_his(transcript, ts)
        
        return JSONResponse({"status": "ok", "transcript": transcript[:100]})
    except Exception as e:
        print(f"[realtime] error: {e}")
        return JSONResponse({"status": "error", "error": str(e)})
# deployed Thu Jul 23 11:27:03 AM UTC 2026
# v1784807433
