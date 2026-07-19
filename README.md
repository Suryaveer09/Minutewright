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
  needed.

## Try it

    conda activate minutewright
    pip install -r requirements.txt
    python live_console.py

Play a meeting or video and captions will print roughly every 5 seconds.
Known limitation right now: words at chunk boundaries can be cut off or
garbled — this is fixed properly in a later phase with overlapping windows.

## How the model is chosen

| Hardware found                  | Model chosen             |
|----------------------------------|---------------------------|
| NVIDIA GPU with 9 GB+ VRAM       | large-v3-turbo (float16)  |
| NVIDIA GPU with 6–9 GB VRAM      | medium (float16)          |
| NVIDIA GPU with 3.5–6 GB VRAM    | small (int8_float16)      |
| CPU, 8+ cores and 8 GB+ RAM      | small (int8)              |
| CPU, 4+ cores                    | base (int8)               |
| Anything weaker                  | tiny (int8)               |

If a GPU is detected but its CUDA libraries aren't installed, the app is
designed to fall back to the CPU pick automatically (wired up in a later
phase) rather than crash.

## Running the tests

    pytest

## License

Apache License 2.0 — see [LICENSE](LICENSE).