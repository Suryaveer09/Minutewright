# Minutewright API

Local server on `http://127.0.0.1:8737`. Interactive tester at `/docs`.

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET    | /api/status | Model ready? Which model/device and why? GPU error if fallback happened. Recording in progress? |
| POST   | /api/record/start | Begin a recording session. Returns `{"id": ...}`. 409 if already recording, 503 if model not loaded yet. |
| POST   | /api/record/stop | Finalize: writes `transcript.txt` + `meta.json` to `recordings/<id>/`. Returns the meta object. |
| GET    | /api/live | `{"recording": false}` or `{"recording": true, "id": ..., "lines": [...]}`. UI polls this. |
| GET    | /api/recordings | List of saved sessions (newest first), from each folder's `meta.json`. |
| GET    | /api/recordings/{id}/transcript | The saved transcript text. 404 if missing. |
| DELETE | /api/recordings/{id} | Remove a session folder entirely. |

Not yet implemented: audio file serving (`/api/recordings/{id}/audio`) — the
capture engine doesn't save a WAV yet. Added alongside the playback UI.