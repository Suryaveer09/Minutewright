# Minutewright — Build & Repository Guide

> **Revision 4 (Jul 2026) — shipped.** v0.1.0 is released: two Windows
> editions (Standard/CPU and NVIDIA-GPU) on the Releases page. This guide
> is the project's engineering log, written as things actually happened —
> including the debugging lessons — so a future contributor (or future
> you) can understand not just *what* the code does but *why* it's shaped
> this way.

Minutewright is a local meeting recorder for Windows. It records system audio
and the microphone together, transcribes live, and offers AI summaries and
chat-with-transcript — all on-device. It also imports existing recordings and
supports click-to-seek transcripts.

## Architecture at a glance

- **desktop.py** — entry point. Runs the FastAPI engine + uvicorn in
  background threads, opens the UI in a native pywebview window (Edge
  WebView2). This is what PyInstaller packages.
- **main.py** — the FastAPI engine: recording control, uploads, transcripts,
  summaries, chat, settings. Model loads in a background thread at startup.
- **capture.py** — WASAPI loopback + optional mic capture, mixed and
  transcribed in chunks live; also `transcribe_file()` for uploads. All
  transcription requests word timestamps (click-to-seek).
- **hardware.py** — CPU/GPU detection → model-tier selection; owns the
  Windows CUDA-DLL loader (dev site-packages *and* the frozen bundle).
- **llm.py** — in-process LLM (llama-cpp-python) for summaries/chat, with an
  in-app model downloader. No external services.
- **summarize.py / chat.py** — prompts + calls over the shared LLM client.
- **paths.py** — dev-vs-frozen path resolution; keeps user data out of the
  executable and in `%LOCALAPPDATA%\Minutewright` when packaged.
- **static/index.html** — the entire UI, framework-free, one file.

| Phase | Deliverable | Status |
|-------|-------------|--------|
| 0 | Repo skeleton on GitHub (license, gitignore, README) | Done |
| 1 | Spike: WASAPI loopback capture to WAV | Done |
| 2 | Spike: local transcription with faster-whisper | Done |
| 3 | Live captions in the console (`capture.py`) | Done |
| 4 | Hardware detection → automatic model choice (+ tests) | Done |
| 5 | FastAPI engine with record/live/library API | Done |
| 6 | Native desktop window + full UI, audio playback | Done |
| 7 | AI summaries (originally Ollama; later bundled) | Done |
| 8 | Chat with a transcript | Done |
| 9a | Bundled in-process LLM + in-app model download | Done |
| 9b | Upload existing recordings, background transcription | Done |
| 9c | Click-to-seek transcript with word timestamps | Done |
| 9d | Microphone capture + mix, device selection | Done |
| 9e | Nameable recordings | Done |
| 9f | Central path resolution (clean packaged data) | Done |
| 10 | Package to `Minutewright.exe`, two editions, release | Done |

## Documentation habits (applied every phase)

1. **README is the front door**, updated in full each phase.
2. **Every module opens with a docstring** on why it exists and how it works;
   comments only for the non-obvious (loopback dance, resampling math, the
   CUDA DLL workaround, the packaging path split).
3. **Spikes are kept, not deleted** (`spikes/`) — runnable minimal examples of
   the hard tricks. `gpu_check.py` earned its keep within a day.
4. **Commit messages: `type: what and why`** — `chore`, `spike`, `feat`,
   `fix`, `docs`, `refactor`, `build`, `release`.

---

## Phase 0 — Repo skeleton  [DONE]

Environment: conda + cmd (not venv/PowerShell), Python 3.11 (the range
PyAudioWPatch ships wheels for). `.gitignore` created **before any code** —
its most important line is `recordings/`, so a stray `git add .` after a test
meeting can never publish other people's voices. License: Apache-2.0 (chosen
for adoption; AGPL-3.0 is the switch to make before external contributions if
"nobody may take it proprietary" ever becomes the goal — Apache is permissive
and allows closed-source reuse).

Recovery note that came up: if the GitHub repo was created with its own
README/license, histories are unrelated and a plain push is rejected — fix
with `git pull origin main --allow-unrelated-histories`, resolve the README
conflict keeping the fuller version, commit, push.

---

## Phase 1 — Hear what the PC hears  [DONE]

`spikes/record_test.py`: Windows hides a "loopback" twin of every output
device; PyAudioWPatch exposes it, so the default speakers open *as an input*
and capture exactly what the user hears — no meeting-app API, no virtual
cables. The hardest platform-specific trick in the app, proven first.

---

## Phase 2 — Transcribe locally  [DONE]

`spikes/transcribe_test.py`: faster-whisper (`base`, CPU, int8) with
`vad_filter=True`. The model downloads once to the user-profile Hugging Face
cache — never into the repo — and runs offline after.

---

## Phase 3 — Live captions  [DONE]

`capture.py`, the engine. Design that stuck for the whole project:

- The audio callback does *only* `queue.put(bytes)` and returns — callbacks
  run on a real-time thread; anything slow there causes crackle/drops.
- A worker thread drains the queue, converts to 16 kHz mono float32
  (`to_mono_16k`), buffers, and transcribes every ~5 s (`CHUNK_SECONDS`).
  Whisper isn't a streaming model — chunk-on-timer is how every live-Whisper
  app fakes it.
- **On stop, flush** the partial buffer, or the tail of every recording is
  silently lost (found the hard way when a short test produced empty output).

Known limits documented honestly: chunk-boundary words can garble; VAD
correctly emits nothing for silent/music-only chunks.

---

## Phase 4 — The machine picks its model  [DONE]

`hardware.py`: `nvidia-smi` for GPU (its absence *is* the "no GPU" signal),
psutil for cores/RAM, a tier table, and a separate `cpu_choice()` so the later
CUDA-failure fallback can call it and say *why*. Thresholds leave headroom
above each model's raw need because the OS, browser, and meeting app share GPU
memory. First tests in `tests/test_hardware.py`; `pytest.ini` sets
`pythonpath = .` so tests import project-root modules.

---

## Phase 5 — Backend + the CUDA battle  [DONE]

FastAPI engine, model loaded in a background thread so the server is instant.
The hard-won lessons, documented so nobody pays twice:

1. **GPU load succeeds even when the GPU can't run.** `WhisperModel(...,
   device="cuda")` constructs fine; cuBLAS isn't touched until first
   inference — and `transcribe()` returns a *lazy generator*, so even calling
   it does nothing until iterated. Fix: a forced dummy inference
   (`list(segments)` on 1 s of zeros) at startup, so a broken GPU path fails
   at launch where the fallback lives, not mid-meeting.
2. **Windows can't find pip-installed CUDA DLLs.** They land in
   `site-packages\nvidia\*\bin`, which the OS loader never searches, and
   ctranslate2 delay-loads `cublas64_12.dll` *by name* from C++ (ignoring
   `os.add_dll_directory`). Fix: `enable_cuda_dlls()` registers the dirs,
   prepends them to PATH, **and preloads every DLL with `ctypes.WinDLL`** so
   by-name lookups resolve to already-loaded modules.
3. **Never swallow exceptions silently** — the first fallback hid the error
   and cost real time. The traceback now prints and is exposed as `gpu_error`
   in `/api/status`.
4. **Diagnose in isolation** — `spikes/gpu_check.py` prints the DLL folders
   found, then attempts one real GPU inference: seconds per iteration instead
   of restarting the server.
5. **Keep requirements.txt CPU-safe** — the nvidia packages are ~1 GB and
   useless on CPU-only machines, so they're an optional install.

---

## Phase 6 — Real desktop app  [DONE]

An .exe is a *packaging* decision, not an architecture one: the FastAPI engine
stays, the UI renders in a native pywebview window. Audio became real
(incremental WAV writing from the worker, `try/finally` close so a crash can't
corrupt the header, per-chunk error isolation so one bad chunk can't kill a
meeting). The UI: model badge, record deck with live feed, library with
playback, two-click delete (native `confirm()` is unreliable in webview).
Also fixed benign Windows `ConnectionResetError(10054)` console noise from
polling, via a targeted log filter + `WindowsSelectorEventLoopPolicy`.

---

## Phase 7–8 — Summaries & chat  [DONE]

Originally built on Ollama (a separate local service), with graceful absence
when it wasn't running. Chat uses the same client; **no RAG** — an hour-long
transcript (~8-10k words) fits a small model's context, so it rides in the
system prompt and the UI sends history each turn (stateless server). These
were later re-based onto the bundled engine (Phase 9a) so users install
nothing.

---

## Phase 9 — Making it a product

### 9a — Bundled LLM + in-app download
Replaced Ollama with **llama-cpp-python** running in-process, so end users
install nothing. Model weights (~2 GB GGUF, Llama 3.2 3B) download *from the
app* on first use with a progress bar — the same pattern Whisper already used.
Inference is CPU (works everywhere; GPU offload is roadmap). Single instance,
serialized requests. States surfaced to the UI: missing → downloading →
loading → ready (or error). Attribution: "Built with Llama" per the license.

### 9b — Upload existing recordings
`transcribe_file()` does one full-context pass — better quality than live
chunking (no boundary garbling) — for any format faster-whisper decodes
(mp3/m4a/mp4/wav/…, via bundled FFmpeg/PyAV). Runs as a background job with
progress; uploads and live recording are mutually exclusive (one Whisper
instance). This is also the answer for locked-down work laptops that won't run
outside apps: record on the phone, transcribe here.

### 9c — Click-to-seek transcript
All transcription now requests `word_timestamps=True`. Sessions save
`lines.json` (structured, word-timed); the UI makes each word a seek target
and highlights the playing line. Old sessions fall back to line-level seeking
parsed from `transcript.txt`.

### 9d — Microphone capture + device selection
The app's original #1 limitation, closed. The mic is a second stream with its
own queue; both are converted to 16 kHz mono and summed (clip-protected). The
saved WAV is the mixed mono track, so playback has both sides. Mic on by
default with a toggle; speaker + mic pickers; soft failure (missing/busy mic →
system-audio-only + a banner, never a dead button). Headphones advised to
avoid the mic re-hearing remote voices.

### 9e — Nameable recordings
Display titles in `meta.json` (the folder id — a timestamp — never moves, so
renaming can't break audio paths or summaries). Inline editor, Enter/Escape,
auto-opens after Stop and after an upload completes; Rename stays available
forever.

### 9f — Central path resolution
`paths.py` splits `resource_dir()` (bundled read-only assets) from
`data_dir()` (user-writable). Critical for packaging: a one-file exe unpacks
to a temp folder Windows deletes on exit, so data written "next to the code"
would vanish; and Program Files isn't writable. Packaged builds put data in
`%LOCALAPPDATA%\Minutewright`, which also guarantees a **clean app** — the exe
is program only, the user's machine grows its own data folder, and updates
never touch recordings.

---

## Phase 10 — Ship it  [DONE]

PyInstaller, driven by `build_exe.py` (batch wrapper `build_exe.bat`). Key
decisions and lessons:

- **`--onedir`, not one-file.** With ~1 GB of AI runtime, one-file re-extracts
  to temp on every launch (slow) and trips antivirus more.
- **Only `static/` is bundled data** — no recordings, no models, no settings.
  The clean-app guarantee is visible right in the build command.
- **`--collect-all`** for llama_cpp, faster_whisper, ctranslate2, webview —
  their native DLLs / data files aren't seen by the import scanner.
- **Two editions.** GPU edition bundles the CUDA DLLs by locating each
  `nvidia/*/bin` and passing `--add-binary` (the nvidia wheels are data-style
  packages `--collect-all` mishandles). `enable_cuda_dlls()` learned to scan
  the frozen bundle (`resource_dir()`) as well as site-packages, so the same
  loader serves dev, the CPU exe (finds nothing, falls back), and the GPU exe
  (finds the bundled DLLs, runs on cuda). Both editions are safe on the wrong
  hardware thanks to the Phase 5 fallback logic — the CPU exe on an NVIDIA box
  falls back cleanly; the GPU exe on a non-NVIDIA box just carries dead weight.
- **`build\` vs `dist\`.** A late scare: the app "wouldn't open on
  double-click." Cause was running the exe from `build\` (PyInstaller scratch,
  not a complete app — it can't find `python311.dll`). The real product is
  always in `dist\`. Also added `os.chdir(exe_dir)` when frozen as
  belt-and-suspenders against odd launch working directories, and disabled the
  WebView2 right-click dev menu for release.
- **Release:** windowed builds of both editions, zipped, tagged `v0.1.0`, and
  published on GitHub with a "which download?" chooser and a SmartScreen note
  (unsigned apps warn on first run — "More info → Run anyway"; code signing is
  a paid, later step).

Final directory:

```
minutewright/
├── desktop.py           # native-window entry point (packaged to exe)
├── main.py              # FastAPI engine + endpoints
├── capture.py           # loopback + mic capture, mix, chunked transcription,
│                        #   word timestamps, transcribe_file() for uploads
├── hardware.py          # CPU/GPU detection, model tiers, CUDA DLL loader
├── llm.py               # in-process LLM + in-app model downloader
├── summarize.py         # minutes prompt over the shared LLM client
├── chat.py              # chat-with-transcript over the shared LLM client
├── paths.py             # dev-vs-frozen path resolution
├── live_console.py      # engine demo without server or UI (debugging)
├── build_exe.py         # PyInstaller build logic (both editions)
├── build_exe.bat        # thin wrapper over build_exe.py
├── static/
│   └── index.html       # the whole UI, no build step
├── spikes/
│   ├── record_test.py
│   ├── transcribe_test.py
│   └── gpu_check.py
├── tests/
│   └── test_hardware.py
├── docs/
│   ├── BUILD_GUIDE.md   # this file
│   ├── API.md
│   └── images/ui.png
├── recordings/          # runtime data — gitignored (dev only; packaged app
│                        #   uses %LOCALAPPDATA%\Minutewright)
├── models/              # LLM weights — gitignored (dev only; same as above)
├── settings.json        # per-machine prefs — gitignored
├── pytest.ini
├── requirements.txt     # app deps only (NOT pyinstaller, NOT nvidia-*)
├── CHANGELOG.md
├── README.md
├── LICENSE
└── .gitignore
```

---

## After v0.1.0 — working like a maintainer

- **Branch per feature** from now on (`git switch -c feat/...`), PR to
  yourself, merge — keeps `main` always-working for anyone who clones.
- **Issues as the roadmap**, seeded from the known limits: GPU-accelerated
  summaries/chat (or an in-app "enable GPU" CUDA download, the slicker v0.2
  option that was deferred at the finish line); word-level streaming captions;
  speaker labels via diarization; chunked (map-reduce) summaries for long
  meetings; cross-meeting search (the real RAG use case); dual-track
  native-quality recording; code signing.
- **CONTRIBUTING.md** the day a stranger opens their first issue, not before.

## Naming & license note (checked Jul 2026)

Rejected names during the search: *Earshot* (existing classroom
transcription startup, podcast platform, hearing-aid app), *Susurrus*
(existing Whisper GUI on GitHub), *MinuteDeck* (one letter from MinuteDock, a
time tracker). *Minutewright* surfaced clean. Before wider publishing,
re-verify GitHub, both app stores, a domain lookup, and — if commercializing —
a proper trademark search (USPTO for the US). License is Apache-2.0 by choice;
AGPL-3.0 is the pre-contribution switch if that goal changes. None of this is
legal advice.