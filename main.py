"""FastAPI backend for Minutewright.

Wraps capture.LiveCapture behind an HTTP API so the desktop window (or
anything else) can start/stop recordings, upload existing recordings,
poll live captions, generate summaries, and chat with transcripts.
The Whisper model loads in a background thread at startup; the LLM for
summaries/chat is bundled in-process (llm.py) and its weights are
downloaded in-app on first use. Audio-device choices (which speakers to
loop back, which mic, mic on/off) persist in settings.json.
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
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from faster_whisper import WhisperModel
from pydantic import BaseModel

import chat as chatmod
import llm
import summarize as summarizer
from capture import LiveCapture, list_devices, transcribe_file
from hardware import choose_model, cpu_choice, detect_hardware, enable_cuda_dlls

enable_cuda_dlls()

BASE = Path(__file__).resolve().parent
REC_DIR = BASE / "recordings"
REC_DIR.mkdir(exist_ok=True)
ID_RE = re.compile(r"^[0-9_\-]+$")
TS_LINE_RE = re.compile(r"^\[(\d+):(\d{2})\]\s?(.*)$")

# Formats faster-whisper can decode out of the box (bundled FFmpeg via PyAV).
AUDIO_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "video/mp4",     # Teams saves meeting recordings as .mp4
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".webm": "audio/webm",
}

# ------------------------------------------------------------- settings
SETTINGS_FILE = BASE / "settings.json"
DEFAULT_SETTINGS = {"capture_mic": True, "mic_index": None, "loopback_index": None}
_settings_lock = threading.Lock()


def load_settings() -> dict:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    s = dict(DEFAULT_SETTINGS)
    s.update({k: data[k] for k in DEFAULT_SETTINGS if k in data})
    return s


def save_settings(s: dict):
    with _settings_lock:
        SETTINGS_FILE.write_text(json.dumps(s, indent=2), encoding="utf-8")


class SettingsBody(BaseModel):
    capture_mic: bool = True
    mic_index: int | None = None
    loopback_index: int | None = None


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

# One background transcription job at a time: uploads and live recording
# share the single Whisper instance, and interleaving them would starve
# live captions. v1 keeps them mutually exclusive and says so politely.
_upload_lock = threading.Lock()
UPLOAD = {"active": False, "id": None, "filename": None, "progress": 0.0,
          "error": None, "done_id": None}


def _upload_set(**kw):
    with _upload_lock:
        UPLOAD.update(kw)


def upload_status() -> dict:
    with _upload_lock:
        s = dict(UPLOAD)
    s["progress"] = round(s["progress"], 1)
    return s


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


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


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


def write_session_files(folder: Path, rec_id: str, title: str, lines: list,
                        duration: float, source: str):
    """Write transcript.txt + lines.json + meta.json.

    transcript.txt stays the plain, human/LLM-friendly format; lines.json
    carries the structured version with word timestamps for click-to-seek.
    """
    transcript = "\n".join(
        f"[{int(l['t']//60):02d}:{int(l['t']%60):02d}] {l['text']}" for l in lines
    )
    (folder / "transcript.txt").write_text(transcript, encoding="utf-8")
    (folder / "lines.json").write_text(
        json.dumps(lines, ensure_ascii=False), encoding="utf-8"
    )
    meta = {
        "id": rec_id,
        "title": title,
        "lines": len(lines),
        "duration_sec": round(duration, 1),
        "model": STATE.choice.model if STATE.choice else "?",
        "source": source,
    }
    (folder / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


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


@app.get("/api/devices")
def devices():
    try:
        return list_devices()
    except Exception as exc:
        raise HTTPException(500, f"Couldn't list audio devices: {exc}")


@app.get("/api/settings")
def get_settings():
    return load_settings()


@app.post("/api/settings")
def set_settings(body: SettingsBody):
    if STATE.capture is not None:
        raise HTTPException(409, "Stop the recording before changing audio settings.")
    s = {"capture_mic": body.capture_mic,
         "mic_index": body.mic_index,
         "loopback_index": body.loopback_index}
    save_settings(s)
    return s


@app.get("/api/llm/status")
def llm_status():
    return llm.get_status()


@app.post("/api/llm/download")
def llm_download():
    llm.start_download()
    return llm.get_status()


@app.post("/api/record/start")
def record_start():
    if STATE.capture is not None:
        raise HTTPException(409, "Already recording")
    if upload_status()["active"]:
        raise HTTPException(409, "An uploaded file is still being transcribed - "
                                 "wait for it to finish before recording.")
    if STATE.model is None:
        raise HTTPException(503, "Speech model isn't loaded yet - check /api/status")

    s = load_settings()
    rec_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    folder = REC_DIR / rec_id
    folder.mkdir(parents=True, exist_ok=True)

    cap = LiveCapture(
        STATE.model,
        wav_path=folder / "audio.wav",
        loopback_index=s["loopback_index"],
        mic_index=s["mic_index"],
        capture_mic=s["capture_mic"],
    )
    try:
        info = cap.start()
    except Exception as exc:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(500, f"Could not start recording: {exc}")

    STATE.capture = cap
    STATE.session_id = rec_id
    STATE.session_folder = folder
    return {"id": rec_id, **info}


@app.post("/api/record/stop")
def record_stop():
    if STATE.capture is None:
        raise HTTPException(409, "Not recording")

    STATE.capture.stop()
    lines = STATE.capture.lines
    folder = STATE.session_folder

    duration = 0.0
    audio_file = folder / "audio.wav"
    if audio_file.exists():
        try:
            with wave.open(str(audio_file)) as wf:
                duration = wf.getnframes() / wf.getframerate()
        except wave.Error:
            pass

    meta = write_session_files(
        folder, STATE.session_id,
        "Meeting " + datetime.now().strftime("%b %d, %H:%M"),
        lines, duration, source="live",
    )

    STATE.capture = None
    STATE.session_id = None
    STATE.session_folder = None
    return meta


# ------------------------------------------------------------ uploads
@app.post("/api/upload")
def upload_recording(file: UploadFile = File(...)):
    if STATE.capture is not None:
        raise HTTPException(409, "Stop the current recording before uploading a file.")
    if upload_status()["active"]:
        raise HTTPException(409, "Another upload is still being transcribed.")
    if STATE.model is None:
        raise HTTPException(503, "Speech model isn't loaded yet - check /api/status")

    original = file.filename or "recording"
    ext = Path(original).suffix.lower()
    if ext not in AUDIO_TYPES:
        raise HTTPException(400, "Unsupported file type. Use one of: "
                                 + ", ".join(sorted(AUDIO_TYPES)))

    rec_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    folder = REC_DIR / rec_id
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"audio{ext}"
    try:
        with open(dest, "wb") as out:
            shutil.copyfileobj(file.file, out)
    finally:
        file.file.close()

    title = f"Upload · {Path(original).stem[:60]}"
    _upload_set(active=True, id=rec_id, filename=original, progress=0.0, error=None)
    threading.Thread(
        target=_process_upload, args=(rec_id, folder, dest, title), daemon=True
    ).start()
    return {"id": rec_id}


def _process_upload(rec_id: str, folder: Path, dest: Path, title: str):
    try:
        lines, duration = transcribe_file(
            STATE.model, dest,
            on_progress=lambda p: _upload_set(progress=p),
        )
        write_session_files(folder, rec_id, title, lines, duration, source="upload")
        _upload_set(active=False, progress=100.0, done_id=rec_id)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        print("Upload transcription failed:\n" + traceback.format_exc(limit=3))
        _upload_set(
            active=False,
            error="Couldn't transcribe that file - it may be corrupted or an "
                  "unsupported codec. Try converting it to .mp3 or .wav.",
        )


@app.get("/api/upload/status")
def get_upload_status():
    return upload_status()


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
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            meta["has_summary"] = (d / "summary.md").exists()
            items.append(meta)
    return items


@app.get("/api/recordings/{rec_id}/audio")
def audio(rec_id: str):
    folder = rec_folder(rec_id)
    for ext, media in AUDIO_TYPES.items():
        f = folder / f"audio{ext}"
        if f.exists():
            return FileResponse(f, media_type=media, filename=f"{rec_id}{ext}")
    raise HTTPException(404, "No audio saved for this recording")


@app.get("/api/recordings/{rec_id}/transcript")
def transcript(rec_id: str):
    f = rec_folder(rec_id) / "transcript.txt"
    if not f.exists():
        raise HTTPException(404, "Recording not found")
    return {"text": f.read_text(encoding="utf-8")}


@app.get("/api/recordings/{rec_id}/lines")
def transcript_lines(rec_id: str):
    """Structured transcript for the UI: line + word timestamps.

    Sessions from before word timestamps existed fall back to parsing
    transcript.txt into line-level entries, so old recordings stay
    clickable (line-accurate instead of word-accurate).
    """
    folder = rec_folder(rec_id)
    jf = folder / "lines.json"
    if jf.exists():
        return {"lines": json.loads(jf.read_text(encoding="utf-8"))}
    tf = folder / "transcript.txt"
    lines = []
    if tf.exists():
        for raw in tf.read_text(encoding="utf-8").splitlines():
            m = TS_LINE_RE.match(raw)
            if m:
                t = int(m.group(1)) * 60 + int(m.group(2))
                lines.append({"t": t, "text": m.group(3), "words": []})
            elif raw.strip():
                lines.append({"t": 0, "text": raw.strip(), "words": []})
    return {"lines": lines}


@app.get("/api/recordings/{rec_id}/summary")
def get_summary(rec_id: str):
    f = rec_folder(rec_id) / "summary.md"
    return {"summary": f.read_text(encoding="utf-8") if f.exists() else None}


@app.post("/api/recordings/{rec_id}/summarize")
def make_summary(rec_id: str):
    folder = rec_folder(rec_id)
    t_file = folder / "transcript.txt"
    text = t_file.read_text(encoding="utf-8").strip() if t_file.exists() else ""
    if not text:
        raise HTTPException(400, "This recording has no transcript to summarize.")
    try:
        result = summarizer.summarize(text)
    except llm.LLMError as exc:
        raise HTTPException(503, str(exc))
    (folder / "summary.md").write_text(result, encoding="utf-8")
    return {"summary": result}


@app.post("/api/recordings/{rec_id}/chat")
def chat_with_recording(rec_id: str, req: ChatRequest):
    folder = rec_folder(rec_id)
    t_file = folder / "transcript.txt"
    text = t_file.read_text(encoding="utf-8").strip() if t_file.exists() else ""
    if not text:
        raise HTTPException(400, "This recording has no transcript to chat about.")
    if not req.message.strip():
        raise HTTPException(400, "Empty message.")
    try:
        reply = chatmod.chat(text, req.history, req.message.strip())
    except llm.LLMError as exc:
        raise HTTPException(503, str(exc))
    return {"reply": reply}


@app.delete("/api/recordings/{rec_id}")
def delete_recording(rec_id: str):
    if STATE.capture is not None and STATE.session_id == rec_id:
        raise HTTPException(409, "Stop the recording before deleting it.")
    st = upload_status()
    if st["active"] and st["id"] == rec_id:
        raise HTTPException(409, "This upload is still being transcribed.")
    shutil.rmtree(rec_folder(rec_id))
    return {"ok": True}


if __name__ == "__main__":
    import webbrowser
    import uvicorn

    threading.Thread(target=load_model_background, daemon=True).start()
    threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8737/docs")).start()
    uvicorn.run(app, host="127.0.0.1", port=8737, log_level="warning")