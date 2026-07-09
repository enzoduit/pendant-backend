import os
import uuid
import datetime
import requests
import httpx
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import JSONResponse

# Allow running directly: python main.py (Railway-friendly)
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)

app = FastAPI(title="Pendant Backend", version="1.0.0")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
HIS_TOKEN = os.environ.get("HIS_TOKEN", "")
HIS_URL = os.environ.get("HIS_URL", "http://188.245.214.39:8765/ingest")

SESSION_ID = "pendant-stream"


def push_to_his(transcript: str, ts: datetime.datetime) -> dict:
    """Push transcript to Human Input Store."""
    ts_iso = ts.isoformat()
    date_str = ts.strftime("%Y-%m-%d")
    # uuid5 from session_id + timestamp
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


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/audio")
async def transcribe_audio(file: UploadFile = File(...)):
    """Receive audio file, transcribe via Whisper, push to HIS."""
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not set")

    audio_bytes = await file.read()
    filename = file.filename or "audio.wav"

    # Call OpenAI Whisper
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

    # Push to Human Input Store
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
        # Try nested segments
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
