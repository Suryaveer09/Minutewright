# Minutewright

A local meeting recorder for Windows. It captures whatever your PC is playing
(Teams, Zoom, Meet...), shows a live transcript while you record, and stores
audio, transcripts, and AI summaries entirely on your machine. No cloud, no
accounts. You can even chat with a transcript to ask what you missed.

![Minutewright UI](docs/images/ui.png)

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
  needed. If a GPU is present but its CUDA libraries can't run inference,
  the app verifies this at startup and falls back to a CPU model instead
  of crashing mid-meeting.
- One-click AI meeting minutes (Overview / Key points / Decisions /
  Action items) via a local LLM through Ollama — optional, and everything
  else works without it.
- **Chat with any recording**: ask "what were the action items?" and get
  answers grounded only in that meeting's transcript — same local LLM,
  honest "that wasn't discussed" when the answer isn't there.
- A native desktop window (pywebview) over a local FastAPI engine — see
  [docs/API.md](docs/API.md) for the endpoint contract.

## Run the app

    conda activate minutewright
    pip install -r requirements.txt
    python desktop.py

A native Minutewright window opens: press **Start recording** during any
meeting or video, watch the live transcript, stop, then play back audio,
read transcripts, generate summaries, and chat — all from the Library.
Everything lands in `recordings/<id>/`.

Developer mode (API tester instead of the window): `python main.py`, then
visit http://127.0.0.1:8737/docs.

### Summaries & chat (optional)

Both run through [Ollama](https://ollama.com) so they stay local too:

1. Install Ollama for Windows and let it run in the tray.
2. Pull a small model once: `ollama pull llama3.2:3b`
3. Open a recording and press **Generate summary**, or use the **Chat** tab.

Set the `SUMMARY_MODEL` environment variable to force a specific Ollama
model (e.g. `qwen2.5:7b` for better answers at the cost of speed). Without
Ollama installed, both features show setup instructions instead of failing.

### Optional: GPU acceleration (NVIDIA)

The default install runs on CPU everywhere. If you have an NVIDIA card,
install the CUDA runtime libraries for a large speed and accuracy boost:

    pip install nvidia-cublas-cu12 nvidia-cudnn-cu12

The app finds and loads these automatically at startup (including the
Windows DLL-discovery workaround), verifies real GPU inference works, and
falls back to CPU with a clear reason if it doesn't.
To check your GPU path in isolation: `python spikes/gpu_check.py`.

## How the model is chosen

| Hardware found                  | Model chosen             |
|----------------------------------|---------------------------|
| NVIDIA GPU with 9 GB+ VRAM       | large-v3-turbo (float16)  |
| NVIDIA GPU with 6–9 GB VRAM      | medium (float16)          |
| NVIDIA GPU with 3.5–6 GB VRAM    | small (int8_float16)      |
| CPU, 8+ cores and 8 GB+ RAM      | small (int8)              |
| CPU, 4+ cores                    | base (int8)               |
| Anything weaker                  | tiny (int8)               |

## Roadmap

- Package as a standalone `Minutewright.exe`
- Mix in the user's own microphone (currently records system audio only)
- Search across all meetings

## Running the tests

    pytest

## License

Apache License 2.0 — see [LICENSE](LICENSE).