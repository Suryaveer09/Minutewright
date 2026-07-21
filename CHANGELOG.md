# Changelog

All notable changes to Minutewright are documented in this file.

## [0.2.0] - 2026-07-21

### Added

- **Export tab.** Export any transcript to nine formats — Text, Markdown,
  HTML, PDF, Word, SRT, VTT, JSON, and CSV — with a live, mouse-selectable
  preview of the rendered output, one-click **Copy all**, and a native
  **Save as…** dialog so you choose exactly where the file goes. When a
  recording has a summary, it is included in the export.
- **Right-click menu.** Cut, Copy, Paste, and Select all now work from a
  context menu on text selections and input fields throughout the app.
- **App icon.** Minutewright has its own icon in the window, the taskbar,
  and on the executable itself.

### Fixed

- Freshly downloaded copies could fail to launch with a
  `Failed to resolve Python.Runtime.Loader.Initialize` error. The .NET
  bridge components the app depends on are now fully bundled.

### Note for downloaders

If the app still won't launch after allowing it through SmartScreen:
Windows marks files downloaded from the internet as blocked. Open
PowerShell in the extracted app folder (right-click an empty space in the
folder and choose **Open in Terminal**), run:

    Get-ChildItem -Recurse | Unblock-File

then double-click the exe again. A proper installer that removes this
friction entirely is on the roadmap.

## [0.1.0] - 2026-07-21

First release. A local meeting recorder for Windows — everything runs on
your machine; no cloud, no accounts.

- Record system audio and your microphone together, with device selection
  and a mic on/off toggle — captures both sides of any meeting (Teams,
  Zoom, Meet, anything that plays through your PC).
- Live transcript while recording, powered by faster-whisper (Whisper).
- Automatic model selection: detects your CPU/GPU and picks the largest
  Whisper model it can run in real time, falling back safely to CPU if a
  GPU's drivers can't run inference. Two editions — Standard (works on
  every PC) and NVIDIA-GPU (much faster transcription on NVIDIA cards).
- Upload existing recordings (.mp3, .m4a, .mp4, .wav, and more) and get a
  full, high-quality transcript — useful when a locked-down work laptop
  won't run outside apps.
- Click any word in a transcript to jump the audio to that moment; the
  line being spoken highlights during playback.
- AI meeting summaries and chat-with-transcript, running on a language
  model built into the app (Llama 3.2 3B) — no extra software, no setup.
  The model downloads once (~2 GB) from a button in the app, then works
  fully offline.
- Name your recordings; play back, review, and delete from the Library.
- Your data (recordings, models, settings) lives in
  `%LOCALAPPDATA%\Minutewright` and never leaves your device.

Known limitations: summaries and chat run on CPU in both editions (a
minute or two per summary); live captions arrive in ~5-second chunks;
uploaded files transcribe more cleanly than live recording; no speaker
labels yet. See the roadmap in the README.