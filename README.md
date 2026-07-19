# Minutewright

A local meeting recorder for Windows. It captures whatever your PC is playing
(Teams, Zoom, Meet...), shows a live transcript while you record, and stores
audio, transcripts, and AI summaries entirely on your machine. No cloud, no
accounts.

**Status:** early development. Build progress is tracked in
[docs/BUILD_GUIDE.md](docs/BUILD_GUIDE.md).

## Why "Minutewright"

A wright is a craftsman — wheelwright, playwright, shipwright. This one
crafts meeting minutes.

## How it works

- Captures system audio through the speakers' WASAPI loopback device —
  records what you hear, so it works with any meeting app.
- Transcribes locally with faster-whisper (OpenAI's open-source Whisper,
  reimplemented for speed). Nothing leaves the machine after the one-time
  model download.
- Detects the CPU/GPU on first run and automatically picks the largest
  Whisper model that machine can handle in real time — no configuration
  needed. If a GPU is present but its CUDA libraries can't actually run
  inference, the app verifies this at startup and falls back to a CPU
  model instead of crashing mid-meeting.
- A local FastAPI server exposes recording control and transcripts over
  HTTP — see [docs/API.md](docs/API.md).

## Run the app

    conda activate minutewright
    pip install -r requirements.txt
    python main.py

Your browser opens the interactive API tester at http://127.0.0.1:8737/docs.
Start a recording with `POST /api/record/start`, watch `GET /api/live`,
stop with `POST /api/record/stop`. Transcripts land in `recordings/<id>/`.

(A real browser UI replaces the API tester in an upcoming phase.)

### Optional: GPU acceleration (NVIDIA)

The default install runs on CPU everywhere. If you have an NVIDIA card,
install the CUDA runtime libraries for a large speed and accuracy boost:

    pip install nvidia-cublas-cu12 nvidia-cudnn-cu12

The app finds and loads these automatically at startup (including the
Windows DLL-discovery workaround), verifies real GPU inference works, and
falls back to CPU with a clear reason in `/api/status` if it doesn't.
To check your GPU path in isolation: `python spikes/gpu_check.py`.

## Console captions (no server)

    python live_console.py

Play a meeting or video and captions print roughly every 5 seconds.
Known limitation: words at chunk boundaries can be cut off or garbled —
fixed properly in a later phase with overlapping windows.

## How the model is chosen

| Hardware found                  | Model chosen             |
|----------------------------------|---------------------------|
| NVIDIA GPU with 9 GB+ VRAM       | large-v3-turbo (float16)  |
| NVIDIA GPU with 6–9 GB VRAM      | medium (float16)          |
| NVIDIA GPU with 3.5–6 GB VRAM    | small (int8_float16)      |
| CPU, 8+ cores and 8 GB+ RAM      | small (int8)              |
| CPU, 4+ cores                    | base (int8)               |
| Anything weaker                  | tiny (int8)               |

## Running the tests

    pytest

## License

Apache License 2.0 — see [LICENSE](LICENSE).