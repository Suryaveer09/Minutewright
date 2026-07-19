# Minutewright API

Local server on `http://127.0.0.1:8737`. Interactive tester at `/docs`
(run `python main.py` for developer mode; the desktop app uses the same
server internally).

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET    | / | The desktop UI (`static/index.html`), or a placeholder if it's missing. |
| GET    | /api/status | Model ready? Which model/device and why? `gpu_error` holds the traceback if GPU fallback happened. Recording in progress? |
| POST   | /api/record/start | Begin a recording session. Returns `{"id": "..."}`. 409 if already recording, 503 if the model isn't loaded yet. |
| POST   | /api/record/stop | Finalize: writes `audio.wav`, `transcript.txt`, `meta.json` to `recordings/<id>/`. Returns the meta object (title, lines, duration_sec, model). |
| GET    | /api/live | `{"recording": false}` or `{"recording": true, "id": ..., "lines": [{"t": seconds, "text": "..."}]}`. The UI polls this every ~1.2s. |
| GET    | /api/recordings | List of saved sessions (newest first) from each folder's `meta.json`, plus `has_summary`. |
| GET    | /api/recordings/{id}/audio | The recording's WAV (`audio/wav`). 404 if no audio was saved (sessions from before audio saving existed). |
| GET    | /api/recordings/{id}/transcript | The saved transcript text. 404 if missing. |
| GET    | /api/recordings/{id}/summary | `{"summary": "..."}` or `{"summary": null}` if none generated yet. |
| POST   | /api/recordings/{id}/summarize | Generate minutes via local Ollama and save `summary.md`. Returns `{"summary": "..."}`. 400 if no transcript; 503 with setup instructions if Ollama is absent. Can take up to a minute. |
| POST   | /api/recordings/{id}/chat | Ask a question about a transcript. Body: `{"message": "...", "history": [{"role": "user"\|"assistant", "content": "..."}]}`. Returns `{"reply": "..."}`. Stateless — the client sends the running history each time. 400 if no transcript or empty message; 503 with setup instructions if Ollama is absent. |
| DELETE | /api/recordings/{id} | Remove a session folder entirely (audio, transcript, summary). |

Notes:

- Recording ids are timestamps (`2026-07-19_16-20-12`) and validated
  against `^[0-9_\-]+$` server-side before any filesystem access.
- All Ollama-backed endpoints (`summarize`, `chat`) are optional features:
  their 503 messages are user-facing and actionable, and the rest of the
  app works without Ollama installed.
- The server is stateless about conversations; chat history lives in the
  UI per opened recording.