# Minutewright API

The desktop app runs a local FastAPI server on `http://127.0.0.1:8737` and
renders its UI in a native window over it. Run `python main.py` for developer
mode with an interactive tester at `/docs`.

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET    | / | The desktop UI (`static/index.html`), or a placeholder if missing. |
| GET    | /api/status | Whisper model ready? Which model/device and why? `gpu_error` holds the traceback if GPU fallback happened. Recording in progress? |
| GET    | /api/devices | Available audio capture sources: `{"speakers": [...], "mics": [...]}` with `index` + `name` for each (WASAPI loopback devices and real microphones). |
| GET    | /api/settings | Current audio settings: `{"capture_mic", "mic_index", "loopback_index"}`. |
| POST   | /api/settings | Save audio settings. Body mirrors the GET shape. 409 while recording. |
| GET    | /api/llm/status | Bundled LLM state: `missing`, `downloading` (with `progress`, `downloaded`, `size_mb`), `loading`, `ready`, or `error` (with a user-facing message). |
| POST   | /api/llm/download | Start (or retry) the one-time ~2 GB model download in the background. Idempotent. Returns current status. |
| POST   | /api/record/start | Begin recording. Returns `{"id", "mic_requested", "mic_active", "mic_error"}` — `mic_active` is false (with a reason) if the mic couldn't open, and recording proceeds system-audio-only. 409 if already recording or an upload is processing; 503 if the Whisper model isn't loaded. |
| POST   | /api/record/stop | Finalize: writes `audio.wav`, `transcript.txt`, `lines.json`, `meta.json` to `recordings/<id>/`. Returns the meta object. |
| POST   | /api/recordings/{id}/title | Rename a session (display title in `meta.json`; the folder id — a timestamp — never changes). Body `{"title": "..."}`. |
| POST   | /api/upload | Upload an audio/video file (multipart `file`). Saves it and starts background transcription. Returns `{"id"}`. 400 on unsupported type; 409 if recording or another upload is active; 503 if the model isn't loaded. |
| GET    | /api/upload/status | `{"active", "id", "filename", "progress", "error", "done_id"}` — the UI polls this and opens the finished session when `done_id` appears. |
| GET    | /api/live | `{"recording": false}` or `{"recording": true, "id", "lines": [{"t", "text", "words"}]}`. Polled ~every 1.2s while recording. |
| GET    | /api/recordings | Saved sessions (newest first) from each `meta.json`, plus `has_summary`. |
| GET    | /api/recordings/{id}/audio | The recording's audio, served with the correct media type for its stored format. 404 if none. |
| GET    | /api/recordings/{id}/transcript | Plain timestamped transcript text. |
| GET    | /api/recordings/{id}/lines | Structured transcript for click-to-seek: `{"lines": [{"t", "text", "words": [{"w", "s"}]}]}`. Sessions from before word timestamps existed fall back to line-level entries parsed from `transcript.txt`. |
| GET    | /api/recordings/{id}/export/{fmt} | Render the transcript (plus summary, when present) in a given format and return it as a file download with a Content-Disposition filename derived from the session title. Formats: `txt`, `md`, `html`, `pdf`, `docx`, `srt`, `vtt`, `json`, `csv`. 400 for unknown formats or empty transcripts. |
| GET    | /api/recordings/{id}/export/{fmt}/text | The rendered export as raw text, `{"text": "..."}` — powers the Export tab's preview and copy-to-clipboard. Text formats only (`txt`, `md`, `html`, `srt`, `vtt`, `json`, `csv`); 400 for binary formats (`pdf`, `docx`). |
| GET    | /api/recordings/{id}/summary | `{"summary": "..."}` or `{"summary": null}`. |
| POST   | /api/recordings/{id}/summarize | Generate minutes with the bundled LLM and save `summary.md`. 400 if no transcript; 503 if the model isn't downloaded or generation fails. CPU inference: expect a minute or two. |
| POST   | /api/recordings/{id}/chat | Ask a question about a transcript. Body `{"message", "history": [{"role", "content"}]}`. Returns `{"reply"}`. Stateless — the client sends the running history each turn. 400 if no transcript/empty message; 503 if the model isn't downloaded. |
| DELETE | /api/recordings/{id} | Remove a session folder entirely. 409 if it's currently recording or being transcribed. |

## Beyond HTTP: the desktop bridge

The HTTP API above is not the app's entire Python↔UI surface. In the
desktop window, pywebview's **js_api bridge** exposes a few Python methods
directly to the page as `window.pywebview.api.*` — used where a sandboxed
web page can't act:

- `save_export(rec_id, fmt)` — renders an export and opens the OS-native
  Save As dialog, writing the file wherever the user chooses. Returns
  `{"ok", "path"}`, `{"ok": false, "cancelled": true}`, or an error.
- `get_clipboard_text()` — reads the Windows clipboard (via .NET on an
  STA thread) to power Paste in the app's own right-click menu, since
  clipboard *reads* are permission-gated inside webviews.

In plain-browser dev mode (`python main.py`) the bridge doesn't exist;
the UI falls back to browser downloads and `navigator.clipboard`.

## Notes

- **Paths.** Bundled read-only assets (`static/`) resolve via
  `paths.resource_dir()`; user-writable data (`recordings/`,
  `settings.json`, the LLM `models/`) via `paths.data_dir()`. In dev both
  are the project folder; in a packaged build, data moves to
  `%LOCALAPPDATA%\Minutewright` so the executable stays clean and user
  data survives app updates.
- **Recording ids** are timestamps (`2026-07-19_16-20-12`), validated
  against `^[0-9_\-]+$` before any filesystem access.
- **Session folder** contents: `audio.<ext>`, `transcript.txt`,
  `lines.json`, `meta.json`, and `summary.md` once generated.
- **The LLM is bundled in-process** (llama-cpp-python, CPU) — no external
  services. Only one LLM request runs at a time; the UI serializes
  summary and chat calls accordingly.
- **One transcription job at a time.** Live recording and file uploads
  share the single Whisper instance and are mutually exclusive by design;
  the server enforces this and the UI reflects it.
- **Conversation state** lives in the UI per opened recording; the server
  is stateless about chat history.