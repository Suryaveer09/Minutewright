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

## Try it

    conda activate minutewright
    pip install -r requirements.txt
    python live_console.py

Play a meeting or video and captions will print roughly every 5 seconds.
Known limitation right now: words at chunk boundaries can be cut off or
garbled — this is fixed properly in a later phase with overlapping windows.

## License

Apache License 2.0 — see [LICENSE](LICENSE).