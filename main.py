"""FastAPI backend for Minutewright.

Wraps capture.LiveCapture behind an HTTP API so a browser UI (or anything
else) can start/stop recordings and poll live captions. The Whisper model
loads in a background thread at startup so the server itself comes up
instantly - the UI can show "loading model..." instead of hanging.
"""

import json
import re
import shutil
import threading
import traceback
import wave
from datetime import datetime
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from faster_whisper import WhisperModel

from capture import LiveCapture
from hardware import choose_model, cpu_choice, detect_hardware, enable_cuda_dlls

enable_cuda_dlls()

BASE = Path(__file__).resolve().parent
REC_DIR = BASE / "recordings"
REC_DIR.mkdir(exist_ok=True)
ID_RE = re.compile(r"^[0-9_\-]+$")


class AppState:
    """Holds the loaded model plus which recording (if any) is in progress."""

    def __init__(self):
        self.model = None
        self.choice = None
        self.error = None
        self.gpu_error = None      # why the GPU path failed, if it did
        self.ready = threading.Event()
        self.capture: LiveCapture | None = None
        self.session_id: str | None = None
        self.session_folder: Path | None = None


STATE = AppState()


def load_model_background():
    hw = detect_hardware()
    choice = choose_model(hw)
    STATE.choice = choice  # visible in /api/status immediately, even while loading

    def try_load(dev, compute_type):
        model = WhisperModel(choice.model, device=dev, compute_type=compute_type)
        # transcribe() returns a lazy generator - nothing actually runs on
        # the GPU until it's iterated. Force that now, at startup, so a
        # missing-DLL error surfaces here instead of during a real meeting.
        segments, _ = model.transcribe(np.zeros(16000, dtype=np.float32), language="en")
        list(segments)
        return model

    try:
        model = try_load(choice.device, choice.compute_type)
    except Exception:
        if choice.device == "cuda":
            # GPU was detected but couldn't actually run inference - record
            # exactly why, then fall back to the CPU-sized pick instead of
            # crashing later mid-recording.
            STATE.gpu_error = traceback.format_exc(limit=3)
            print("GPU load failed, falling back to CPU:\n" + STATE.gpu_error)
            choice = cpu_choice(hw)
            choice.reason += " - GPU libraries unavailable, using CPU"
            STATE.choice = choice
            try:
                model = try_load("cpu", choice.compute_type)
            except Exception as exc:
                STATE.error = f"Could not load speech model: {exc}"
                STATE.ready.set()
                return
        else:
            STATE.error = "Could not load speech model:\n" + traceback.format_exc(limit=3)
            STATE.ready.set()
            return

    STATE.model = model
    STATE.ready.set()


app = FastAPI(title="Minutewright")


def rec_folder(rec_id: str) -> Path:
    """Validate a recording id and return its folder, or raise 400/404.

    The regex stops path tricks like '../../secrets' from ever touching
    the filesystem - ids we generate are only digits, dashes, underscores.
    """
    if not ID_RE.match(rec_id):
        raise HTTPException(400, "Bad recording id")
    folder = REC_DIR / rec_id
    if not folder.is_dir():
        raise HTTPException(404, "Recording not found")
    return folder


@app.get("/")
def index():
    ui = BASE / "static" / "index.html"
    if ui.exists():
        return FileResponse(ui)
    return HTMLResponse(
        "<h1>Minutewright</h1><p>The UI lands in the next build step - "
        "use <a href='/docs'>/docs</a> for now.</p>"
    )


@app.get("/api/status")
def status():
    c = STATE.choice
    return {
        "model_ready": STATE.model is not None,
        "model_error": STATE.error,
        "gpu_error": STATE.gpu_error,
        "model": c.model if c else None,
        "device": c.device if c else None,
        "reason": c.reason if c else None,
        "recording": STATE.capture is not None,
    }


@app.post("/api/record/start")
def record_start():
    if STATE.capture is not None:
        raise HTTPException(409, "Already recording")
    if STATE.model is None:
        raise HTTPException(503, "Speech model isn't loaded yet - check /api/status")

    rec_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    folder = REC_DIR / rec_id
    folder.mkdir(parents=True, exist_ok=True)

    cap = LiveCapture(STATE.model, wav_path=folder / "audio.wav")
    cap.start()
    STATE.capture = cap
    STATE.session_id = rec_id
    STATE.session_folder = folder
    return {"id": rec_id}


@app.post("/api/record/stop")
def record_stop():
    if STATE.capture is None:
        raise HTTPException(409, "Not recording")

    STATE.capture.stop()
    lines = STATE.capture.lines
    folder = STATE.session_folder

    transcript = "\n".join(
        f"[{int(l['t']//60):02d}:{int(l['t']%60):02d}] {l['text']}" for l in lines
    )
    (folder / "transcript.txt").write_text(transcript, encoding="utf-8")

    duration = 0.0
    audio_file = folder / "audio.wav"
    if audio_file.exists():
        try:
            with wave.open(str(audio_file)) as wf:
                duration = wf.getnframes() / wf.getframerate()
        except wave.Error:
            pass

    meta = {
        "id": STATE.session_id,
        "title": "Meeting " + datetime.now().strftime("%b %d, %H:%M"),
        "lines": len(lines),
        "duration_sec": round(duration, 1),
        "model": STATE.choice.model if STATE.choice else "?",
    }
    (folder / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    STATE.capture = None
    STATE.session_id = None
    STATE.session_folder = None
    return meta


@app.get("/api/live")
def live():
    if STATE.capture is None:
        return {"recording": False}
    return {"recording": True, "id": STATE.session_id, "lines": STATE.capture.lines}


@app.get("/api/recordings")
def recordings():
    items = []
    for d in sorted(REC_DIR.iterdir(), reverse=True):
        meta_file = d / "meta.json"
        if d.is_dir() and meta_file.exists():
            items.append(json.loads(meta_file.read_text(encoding="utf-8")))
    return items


@app.get("/api/recordings/{rec_id}/audio")
def audio(rec_id: str):
    f = rec_folder(rec_id) / "audio.wav"
    if not f.exists():
        raise HTTPException(404, "No audio saved for this recording")
    return FileResponse(f, media_type="audio/wav", filename=f"{rec_id}.wav")


@app.get("/api/recordings/{rec_id}/transcript")
def transcript(rec_id: str):
    f = rec_folder(rec_id) / "transcript.txt"
    if not f.exists():
        raise HTTPException(404, "Recording not found")
    return {"text": f.read_text(encoding="utf-8")}


@app.delete("/api/recordings/{rec_id}")
def delete_recording(rec_id: str):
    shutil.rmtree(rec_folder(rec_id))
    return {"ok": True}


if __name__ == "__main__":
    import webbrowser
    import uvicorn

    threading.Thread(target=load_model_background, daemon=True).start()
    threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8737/docs")).start()
    uvicorn.run(app, host="127.0.0.1", port=8737, log_level="warning")