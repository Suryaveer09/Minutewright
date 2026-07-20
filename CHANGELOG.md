# Changelog

## 0.1.0 — first release

A local meeting recorder for Windows. Everything runs on your machine; no
cloud, no accounts.

- Record system audio and your microphone together, with device selection
  and a mic on/off toggle — captures both sides of any meeting (Teams,
  Zoom, Meet, anything that plays through your PC).
- Live transcript while recording, powered by faster-whisper (Whisper).
- Automatic model selection: detects your CPU/GPU and picks the largest
  Whisper model it can run in real time, falling back safely if a GPU's
  drivers can't run inference. Two editions — Standard (CPU) and GPU
  (bundles NVIDIA CUDA libraries).
- Upload existing recordings (.mp3, .m4a, .mp4, .wav, and more) and get a
  full, high-quality transcript — useful when your work laptop won't run
  outside apps.
- Click any word in a transcript to jump the audio to that moment; the
  playing line highlights as it goes.
- AI meeting summaries and chat-with-transcript, running on a language
  model built into the app (Llama 3.2 3B) — no Ollama, no setup. The model
  downloads once (~2 GB) from a button in the app.
- Name your recordings; play back, review, and delete from the Library.
- Your data (recordings, models, settings) lives in
  %LOCALAPPDATA%\Minutewright and never leaves your device.

Known limitations: transcription/summary/chat run on CPU in the Standard
edition (GPU edition accelerates transcription); summaries and chat run on
CPU in both editions; live captions arrive in ~5-second chunks; no speaker
labels yet. See the roadmap in the README.