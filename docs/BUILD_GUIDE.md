# Minutewright — Build & Repository Guide

> **Revision 3 (Jul 2026).** Phases 7 (Ollama summaries) and 8 (chat with
> a transcript) are now recorded as built, including the Windows
> event-loop noise fix. Phase 9 — packaging to `Minutewright.exe` — is
> next. Earlier context: **Revision 2** changed the target from a browser
> UI to a native desktop app (pywebview shell over a local FastAPI
> engine) and switched the workflow to **conda** and **cmd**. Completed
> phases are written as they actually happened — including the debugging
> lessons — so the guide doubles as the project's engineering log.

Minutewright is a local meeting recorder for Windows: it captures whatever
the PC is playing (Teams, Zoom, anything), shows a live transcript, and
stores audio, transcripts, AI summaries, and a chat-with-transcript
assistant entirely on the user's machine.

| Phase | Deliverable | Status |
|-------|-------------|--------|
| 0 | Repo skeleton on GitHub (license, gitignore, README) | Done |
| 1 | Spike: WASAPI loopback capture to WAV | Done |
| 2 | Spike: local transcription with faster-whisper | Done |
| 3 | Live captions in the console (`capture.py`) | Done |
| 4 | Hardware detection → automatic model choice (+ tests) | Done |
| 5 | FastAPI engine with record/live/library API | Done |
| 6 | Native desktop window + full UI, audio playback | Done |
| 7 | AI summaries via local Ollama | Done |
| 8 | Chat with a transcript | Done |
| 9 | Package as standalone `Minutewright.exe`, release v0.1.0 | Next |

Each phase ends with a **working checkpoint**, a **directory tree**, the
**documentation to write**, and a **commit**. Commit at the end of every
phase — small commits with clear messages *are* documentation.

---

## How this repo stays documented

Four habits, applied every phase:

1. **README.md is the front door.** It grows a little each phase. A stranger
   reading only the README should know what the app does, how to run it, and
   what state it's in. After every phase, the README is updated in full.
2. **Every module opens with a docstring** answering *why does this file
   exist* and *how does it work*, in 3-10 lines. Public functions get a
   one-line docstring. Comments are reserved for the non-obvious (the WASAPI
   loopback dance, resampling math, the CUDA DLL workaround) — not for
   narrating ordinary code.
3. **Spikes are kept, not deleted.** Proof-of-concept and diagnostic scripts
   live in `spikes/` forever. They document what was learned and give future
   contributors runnable, minimal examples of the hard tricks —
   `gpu_check.py` earned its keep within a day of being written.
4. **Commit messages follow `type: what and why`.** Types used here:
   `chore`, `spike`, `feat`, `fix`, `docs`, `release`.

---

## Phase 0 — An empty repo done right  [DONE]

**Goal:** a public GitHub repo containing a license, a .gitignore, and a
one-paragraph README. No code yet.

### Environment

```cmd
mkdir minutewright
cd minutewright
git init -b main
conda create -n minutewright python=3.11 -y
conda activate minutewright
```

Python 3.11 (3.10-3.12 range): that's what PyAudioWPatch ships wheels for.
The conda env lives outside the project folder, so nothing env-related needs
committing or ignoring by default.

### .gitignore — create this before any code exists

```gitignore
# Conda / Python
env/
__pycache__/
*.pyc
*.pyo

# App data — NEVER commit recordings. They contain other people's voices.
recordings/
*.wav

# Packaging output
build/
dist/
*.spec

# Local machine / secrets
.env
Thumbs.db

# VS Code
.vscode/*
!.vscode/settings.json
```

> **Why the recordings/ line matters:** one careless `git add .` after a
> test meeting would publish coworkers' voices to the public internet. The
> ignore rule makes that mistake impossible. Keep it forever.

### LICENSE

This project uses **Apache-2.0** (added via GitHub's license picker). Be
clear-eyed about what that means: Apache is *permissive* — anyone may use,
modify, sell, and redistribute the code, including inside closed-source
products, provided they keep the copyright and license notices. If the goal
ever becomes "nobody may take a modified version proprietary," the standard
open-source answer is **AGPL-3.0** instead. Optionally add a one-line
`NOTICE` file: `Minutewright — Copyright (c) 2026 <your name>`.

### README stub, first commit, publish

Create `README.md` (one-paragraph description + status line), put this
guide at `docs/BUILD_GUIDE.md`, then:

```cmd
git add .
git commit -m "chore: project skeleton - readme, license, gitignore, build guide"
git remote add origin https://github.com/<YOUR-USERNAME>/minutewright.git
git push -u origin main
```

> **If the GitHub repo was created with its own README/license** (the
> checkboxes on the New Repository page), the histories are unrelated and a
> plain push is rejected. Recover with:
> `git pull origin main --allow-unrelated-histories`, resolve the README
> merge conflict keeping your fuller version, commit, then push.

### Directory after Phase 0

```
minutewright/
├── .git/
├── .gitignore
├── LICENSE
├── README.md
└── docs/
    └── BUILD_GUIDE.md
```

**Done when:** the repo renders README + LICENSE on github.com.

---

## Phase 1 — Prove you can hear what the PC hears  [DONE]

**Goal:** record 5 seconds of system audio to `test.wav` via WASAPI
loopback — the hardest platform-specific trick in the whole app.

```cmd
pip install PyAudioWPatch
echo PyAudioWPatch>=0.2.12.5 > requirements.txt
```

Create **spikes/record_test.py**: Windows hides a "loopback" twin of every
output device; PyAudioWPatch exposes it, so the default speakers can be
opened *as an input* and capture exactly what the user hears — no Teams
API, no virtual audio cables. The spike records 5 seconds and writes
`test.wav` (gitignored by the `*.wav` rule).

**Docs:** README gains a "How it works" section, first bullet about
loopback capture.

**Commit:** `spike: capture system audio via wasapi loopback`

**Done when:** play a video, run the spike, and `test.wav` plays back that
exact audio.

---

## Phase 2 — Prove the model transcribes  [DONE]

**Goal:** turn `test.wav` into text locally.

```cmd
pip install faster-whisper
echo faster-whisper>=1.0.3 >> requirements.txt
```

Create **spikes/transcribe_test.py**: load `WhisperModel("base",
device="cpu", compute_type="int8")`, transcribe `test.wav` with
`vad_filter=True`, print `[start] text` lines. First run downloads the
model to the Hugging Face cache in the user profile — *not* into the repo;
fully offline afterward. Record a clip with actual speech (music
transcribes to garbage, correctly).

**Commit:** `spike: transcribe wav locally with faster-whisper`

**Done when:** the console prints a recognizable transcript.

---

## Phase 3 — Live captions (first real module)  [DONE]

**Goal:** captions print in the console *while* audio plays.

```cmd
pip install numpy scipy
echo numpy>=1.26 >> requirements.txt
echo scipy>=1.11 >> requirements.txt
```

Create **capture.py** — the engine. Design:

- The audio callback does *only* `queue.put(bytes)` and returns. Callbacks
  run on a real-time audio thread; anything slow there causes crackle and
  dropped audio.
- A worker thread drains the queue, converts to 16 kHz mono float32
  (`to_mono_16k`: /32768 normalization, channel-mean downmix,
  `resample_poly` with a gcd-reduced ratio), and buffers.
- Every 5 s of buffered audio (`CHUNK_SECONDS`) is transcribed with
  `vad_filter=True`, `beam_size=1`, `condition_on_previous_text=False`.
  Whisper isn't a streaming model — chunk-on-timer is how every live-Whisper
  app fakes it.
- **On stop, flush**: drain the queue one last time and transcribe the
  remaining partial buffer (if ≥ 0.5 s). Without this, the tail of every
  recording is silently lost — found the hard way when a short test
  produced an empty transcript.

Create **live_console.py** — a ~25-line entry point (load model, start
capture, Ctrl+C to stop) so the engine is testable with no server or UI.

**Known limitation to document honestly:** words spanning chunk boundaries
get cut or garbled; VAD correctly produces nothing for silent/music-only
chunks. Both go in the README.

**Commits:** `feat: live captions from system audio (capture engine)` ·
`docs: add try-it instructions and known chunking limitation`

**Done when:** captions of a playing video appear within ~5-8 s of the
words being spoken.

---

## Phase 4 — The machine picks its own model  [DONE]

**Goal:** detect CPU/GPU and choose the largest Whisper model the machine
can run in real time — the app's signature install-time behavior.

```cmd
pip install psutil pytest
echo psutil>=5.9 >> requirements.txt
echo pytest>=8.0 >> requirements.txt
```

Create **hardware.py**:

- `detect_gpu()` shells out to `nvidia-smi`. `FileNotFoundError` *is* the
  detection result (no NVIDIA GPU), not an error.
- `detect_hardware()` adds CPU cores + RAM via psutil.
- `choose_model()` implements the tier table; `cpu_choice()` is deliberately
  a separate function so the CUDA-failure fallback (Phase 5) can call it
  directly and say *why*.

| Hardware found | Model chosen |
|---|---|
| NVIDIA GPU, 9 GB+ VRAM | large-v3-turbo (float16) |
| NVIDIA GPU, 6-9 GB VRAM | medium (float16) |
| NVIDIA GPU, 3.5-6 GB VRAM | small (int8_float16) |
| CPU, 8+ cores and 8 GB+ RAM | small (int8) |
| CPU, 4+ cores | base (int8) |
| Anything weaker | tiny (int8) |

Thresholds leave headroom above each model's raw requirement because the
OS, browser, and the meeting app itself share the same GPU memory.

Create **tests/test_hardware.py** — selection is pure logic, so it's the
easiest, highest-value thing to test (big GPU→turbo, this machine's real
numbers→its expected pick, no GPU→small, weak CPU→tiny). And create
**pytest.ini** in the project root:

```ini
[pytest]
pythonpath = .
```

Without it, pytest can't import project-root modules from `tests/` and
fails collection with `ModuleNotFoundError` — a standard structure quirk.

**Commits:** `feat: auto-select whisper model from detected cpu/gpu` ·
`docs: readme after phase 4` (adds the table above)

**Done when:** `pytest` is green and a one-liner prints a sensible
`ModelChoice` for the current machine.

---

## Phase 5 — A backend the UI can talk to  [DONE]

**Goal:** the engine behind an HTTP API. FastAPI's free `/docs` page serves
as the tester until the real UI exists.

```cmd
pip install fastapi uvicorn
echo fastapi>=0.110 >> requirements.txt
echo uvicorn>=0.29 >> requirements.txt
```

Create **main.py**: model loads in a background thread at startup (server
up instantly; `/api/status` shows the chosen model *while it loads*), plus
the endpoints — the authoritative contract lives in **docs/API.md**:
status, record/start, record/stop (writes `transcript.txt` + `meta.json`
to `recordings/<timestamp>/`), live (polled by the UI), recordings list,
transcript fetch, delete. Recording ids are validated with
`^[0-9_\-]+$` before touching the filesystem so crafted ids like `../..`
can't escape the recordings folder.

### Hard-won lessons of this phase (the CUDA battle)

These cost real debugging time; they're documented so nobody pays twice.

1. **GPU model loading succeeds even when the GPU can't run.**
   `WhisperModel(..., device="cuda")` constructs fine; cuBLAS isn't touched
   until the first inference — and `transcribe()` returns a *lazy
   generator*, so even calling it does nothing until iterated. The app
   therefore runs a forced dummy inference at startup
   (`list(segments)` on 1 s of zeros) so a broken GPU path fails **at
   launch**, where the fallback lives — not mid-meeting.
2. **Windows can't find pip-installed CUDA DLLs.** `nvidia-cublas-cu12` /
   `nvidia-cudnn-cu12` land in `site-packages\nvidia\*\bin`, which the OS
   loader never searches — and ctranslate2 delay-loads `cublas64_12.dll`
   *by name* from C++, a lookup that ignores `os.add_dll_directory`. The
   fix is `hardware.enable_cuda_dlls()`: register the dirs, prepend them to
   `PATH`, **and preload every DLL with `ctypes.WinDLL`** so by-name lookups
   resolve against already-loaded modules.
3. **Never swallow exceptions silently.** The first fallback implementation
   caught the GPU error and discarded it, leaving only guesswork. Now the
   traceback is printed to the console and exposed as `gpu_error` in
   `/api/status`, and the fallback reason is appended to the model-choice
   string users see.
4. **Diagnose in isolation.** `spikes/gpu_check.py` prints which nvidia DLL
   folders were found, then attempts one real GPU inference and reports
   SUCCESS or the full traceback — seconds per iteration instead of
   restarting the whole server.
5. **Keep requirements.txt CPU-safe.** The nvidia packages are ~1 GB and
   useless on CPU-only machines, so they are an *optional* install
   documented in the README, not a hard requirement. The app handles both
   worlds by design.

**Commits:** `feat: fastapi backend with record/live/library endpoints; fix
cuda dll loading on windows (ctypes preload) and flush partial audio chunk
on stop` · `docs: readme and api contract after phase 5`

**Done when:** the full loop works through `/docs` — start → live lines →
stop → transcript fetched — with `/api/status` showing the GPU model and
`gpu_error: null` (or a truthful CPU fallback reason).

---

## Phase 6 — A real desktop app  [DONE]

> Revised from the original "browser UI" plan. An .exe is a **packaging**
> decision, not an architecture one: the FastAPI engine stays, and the UI
> renders in a native window via **pywebview** (Edge WebView2) — own
> taskbar entry, no browser chrome. PyInstaller wraps it in Phase 9.

### 6a — audio becomes real + the window shell

Until now the engine threw audio away after transcribing. Changes to
**capture.py**: `LiveCapture(model, wav_path=...)` writes raw audio to the
WAV **incrementally from the worker thread** (never the callback, never
RAM-buffered — an hour-long meeting streams to disk), the WAV close lives
in `try/finally` (the `wave` module only writes correct headers on
`close()`, so a crash otherwise corrupts the file), and `_transcribe`
catches per-chunk errors so **one bad chunk can no longer kill the whole
meeting** — the exact failure mode of the cuBLAS crash.

**main.py** gains `GET /api/recordings/{id}/audio` (FileResponse,
`audio/wav`), real duration measured from the WAV into `meta.json`, and a
`GET /` that serves `static/index.html` when present.

```cmd
pip install pywebview
echo pywebview>=5.0 >> requirements.txt
```

**desktop.py** — the app's real entry point (~40 lines): engine thread +
uvicorn thread, then `webview.create_window("Minutewright",
"http://127.0.0.1:8737", ...)`. Closing the window exits the app;
`main.py` remains the developer entry (`/docs` tester).

### 6b — the interface

**static/index.html** — one file, framework-free, plain JS:

- Header: wordmark + model badge polling `/api/status` every 2.5 s
  (pulses while loading, shows model · device · reason, disables the
  record button until the model is genuinely ready).
- Deck: record/stop button, client-side timer, animated meter
  (reduced-motion respected), live caption feed polling `/api/live`
  every 1.2 s with stick-to-bottom scrolling.
- Library: sessions newest-first; detail view with `<audio controls>`
  playback, the timestamped transcript, and delete.
- **Two-click delete confirm** (button arms for 3 s) — native
  `confirm()` dialogs are unreliable inside webview windows.
- Old sessions recorded before 6a have no `audio.wav`; the audio
  element's error handler swaps in an explanatory note instead of a
  broken player.

**Docs:** screenshot at `docs/images/ui.png`, embedded at the top of the
README — the highest-value documentation a GitHub project has. README
"Run the app" now leads with `python desktop.py`.

**Commits:** `feat: save recording audio to wav and serve it for playback;
survive per-chunk transcription errors` · `feat: native desktop window
shell (pywebview); revise roadmap toward exe` · `feat: desktop ui - record
deck, live transcript, library, playback` · `docs: readme after phase 6
with screenshot and roadmap`

**Done when (five-step test):** window opens → badge settles and enables
recording → live captions stream during a talking video → stop
auto-opens the new session → audio plays and the transcript reads clean.

---

## Phase 7 — AI summaries, still local  [DONE]

**Goal (met):** one-click meeting minutes via a local LLM through
[Ollama](https://ollama.com) — optional, and graceful when Ollama is
absent. This phase also built the exact LLM plumbing Phase 8's chat
reuses.

### As built

Setup: install Ollama for Windows (lives in the tray), then a one-time
`ollama pull llama3.2:3b` (~2 GB). VRAM note for GPU machines: a 3B model
takes ~2-3 GB alongside Whisper-medium's ~3-4 GB — both fit in 8 GB.

```cmd
pip install requests
echo requests>=2.31 >> requirements.txt
```

- **summarize.py**: `pick_model()` queries `http://localhost:11434/api/tags`
  and prefers small llama/qwen-class models (`SUMMARY_MODEL` env var
  overrides); a fixed minutes prompt with exactly four sections (Overview /
  Key points / Decisions / Action items) and an explicit "do not invent
  details" rule; transcripts truncated to `MAX_CHARS = 24000` to fit a
  small model's context (map-reduce summarization stays a roadmap item).
  `SummaryError` carries a **user-facing, actionable** message ("install
  from ollama.com, run 'ollama pull llama3.2:3b'") that the UI shows
  verbatim — error messages as product copy, not stack traces.
- **main.py**: `GET /api/recordings/{id}/summary`,
  `POST /api/recordings/{id}/summarize` (saves `summary.md` in the session
  folder), `has_summary` in the library listing. The summarize endpoint is
  a plain `def` on purpose: FastAPI runs sync endpoints in a threadpool,
  so a 60-second summary doesn't freeze the rest of the app.
- **UI**: Transcript | Summary tabs, Generate/Regenerate button with a
  working state, amber "summary" flag on library rows, Ollama errors in
  the banner.

Verified in practice: real recordings produced structured minutes, and the
prompt's honesty rule held — sections with nothing to report came back as
"None mentioned." rather than inventions. With Ollama quit from the tray,
the endpoint returned a clean 503 with setup instructions — the
graceful-absence behavior tested like the feature it is.

### Side lesson: benign Windows disconnect noise

Polling UIs constantly abandon in-flight HTTP requests (superseded polls,
cancelled audio range requests). On Windows, asyncio's **Proactor** event
loop logs each one as a scary `ConnectionResetError: [WinError 10054]`
traceback — cosmetic, but it frightens users and buries real errors.
Fixed in **desktop.py** with two layers: a targeted logging filter that
silences exactly that error, and switching uvicorn's thread to
`WindowsSelectorEventLoopPolicy`, which doesn't have the quirk (a
localhost app needs nothing Proactor-specific).

**Commits:** `feat: local meeting summaries via ollama (backend + api)` ·
`feat: summary tab and generate button in desktop ui` · `fix: silence
benign win32 connection-reset noise from polling ui` · `docs: readme after
phase 7`

**Done when (met):** with Ollama running, a recording produces structured
minutes; with Ollama stopped, the button yields a helpful message, never a
crash.

---

## Phase 8 — Chat with a transcript  [DONE]

**Goal (met):** an in-app chat panel that answers questions about the open
recording, using the same local LLM.

### As built

Key design decision, stated up front: **no RAG for v1.** A full hour-long
meeting transcript is ~8-10k words and fits in a small local model's
context window, so the transcript is stuffed into the system prompt and
the conversation rides along with it. Embeddings + a vector store only
become worth it for "search across *all* my meetings" — roadmap, not now.

- **chat.py**: reuses `pick_model` / `OLLAMA_URL` / `SummaryError` from
  summarize.py — one Ollama client, two features. The system prompt embeds
  the transcript (same `MAX_CHARS` cap) with three rules: answer only from
  the transcript, say plainly when something wasn't discussed, don't
  invent names/numbers/dates. History is trimmed to the last
  `MAX_HISTORY = 12` turns so long conversations can't blow a 3B model's
  context — the transcript is the expensive part and is always included.
  Uses Ollama's `/api/chat` (proper messages array) rather than
  `/api/generate`.
- **main.py**: `POST /api/recordings/{id}/chat` with a pydantic
  `ChatRequest {message, history}`. The server is **stateless** — the UI
  sends the running history with every request, consistent with everything
  else in this app being plain files on disk. Ollama absence surfaces as
  the same actionable 503.
- **UI**: a Chat tab beside Transcript | Summary. Each recording opens a
  **fresh conversation** (history is about *this* transcript; carrying it
  across recordings would confuse the model). A "Thinking…" bubble shows
  while the model works; the input locks during a request so overlapping
  questions can't pile into a single-threaded local LLM; a failed send
  **removes the question from history** so retrying doesn't double it.

Verified: grounded questions answered from the transcript; a follow-up
question proved multi-turn history flows; an off-transcript question got
an honest "that wasn't discussed." Known caveat, documented rather than
hidden: a 3B model's grounding is good-not-perfect — the `SUMMARY_MODEL`
upgrade path (e.g. `qwen2.5:7b`) exists for exactly this.

**Commits:** `feat: chat with a transcript via local llm (backend + api)` ·
`feat: chat tab in desktop ui - per-recording history, thinking state` ·
`docs: readme and api after phase 8`

**Done when (met):** asking "what were the action items?" returns an
answer grounded in that transcript; asking something not in the meeting
gets an honest "that wasn't discussed."

### Directory after Phase 8

```
minutewright/
├── desktop.py           # native-window entry point (the future .exe)
├── main.py              # FastAPI engine + endpoints (dev entry: /docs)
├── capture.py           # loopback capture, chunked live transcription, WAV
├── hardware.py          # CPU/GPU detection, model tiers, CUDA DLL loader
├── summarize.py         # Ollama client + minutes prompt (optional feature)
├── chat.py              # chat-with-transcript on the same Ollama client
├── live_console.py      # engine demo without server or UI (debugging)
├── static/
│   └── index.html       # the whole UI, no build step
├── spikes/
│   ├── record_test.py   # minimal WASAPI loopback proof
│   ├── transcribe_test.py
│   └── gpu_check.py     # GPU-path diagnostic (DLL dirs + real inference)
├── tests/
│   └── test_hardware.py
├── docs/
│   ├── BUILD_GUIDE.md   # this file
│   ├── API.md           # endpoint contract
│   └── images/ui.png
├── recordings/          # runtime data - gitignored (audio.wav,
│                        #   transcript.txt, meta.json, summary.md per id)
├── pytest.ini
├── requirements.txt
├── README.md
├── LICENSE
└── .gitignore
```

---

## Phase 9 — Ship `Minutewright.exe`, release v0.1.0  [NEXT]

**Goal:** a stranger double-clicks one file and uses the app — no Python,
no conda.

Plan:

- `pip install pyinstaller`, then build from **desktop.py** with
  `--add-data static;static` (and a `.spec` file once flags stabilize —
  `*.spec` is already gitignored as build output; the final spec gets
  force-added when it becomes source).
- **Frozen-app path handling:** when running as an exe, `recordings/` and
  logs move to `%LOCALAPPDATA%\Minutewright\` instead of next to the
  executable (Program Files isn't writable); code branches on
  `sys.frozen`.
- Whisper models keep downloading to the user-profile cache on first run —
  the exe stays hundreds of MB instead of gigabytes. Ollama remains a
  separate user install for summaries/chat, documented in the README.
- **Honest expectations to document in the README:** the exe will be a few
  hundred MB (Whisper runtime), first launch is slow (model download), and
  unsigned exes can trigger SmartScreen/antivirus warnings — normal for
  unsigned software; code-signing is a paid, later step.
- Windows-only remains true and stated plainly.
- **CHANGELOG.md** with a `## 0.1.0` section; tag and release:

```cmd
git add .
git commit -m "release: v0.1.0 - packaged desktop app, changelog"
git tag -a v0.1.0 -m "First packaged release"
git push && git push --tags
```

Then GitHub → Releases → draft from the tag, paste the changelog, attach
the exe (or a zip of the dist folder).

**Done when:** on a machine (or clean folder) without the conda env,
double-clicking `Minutewright.exe` reaches a working record → transcript →
summary → chat loop.

---

## After v0.1.0 — working like a maintainer

- **Branch per feature:** `git switch -c feat/mic-mixing`, push, open a PR
  to yourself, merge. Keeps `main` always-working for anyone who clones.
- **Issues as the roadmap**, seeded from the known limitations: mix the
  user's own microphone in (currently system audio only — remote voices,
  not yours), speaker labels via pyannote, word-level streaming captions
  (RealtimeSTT / overlapping windows), map-reduce summaries for long
  meetings, cross-meeting search (the actual RAG use case), code signing.
- **CONTRIBUTING.md** the day a stranger opens their first issue, not
  before.

## Naming & license note (checked July 2026)

Candidates rejected during the name search: *Earshot* (existing classroom
audio-transcription startup, podcast platform, hearing-aid app), *Susurrus*
(existing Whisper-based transcription GUI on GitHub), *MinuteDeck* (one
letter from MinuteDock, an established time tracker). *Minutewright*
surfaced zero apps, repos, or products. Before publishing widely,
re-verify: GitHub search, both app stores, a domain lookup, and — if ever
commercializing — a proper trademark search (USPTO for the US). The
license is Apache-2.0 by deliberate choice (adoption over exclusivity);
AGPL-3.0 remains the switch to make *before* accepting external
contributions if that goal changes. None of this is legal advice.