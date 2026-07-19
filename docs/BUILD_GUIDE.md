# Minutewright — Build & Repository Guide

Minutewright is a local meeting recorder for Windows: it captures whatever the
PC is playing (Teams, Zoom, anything), shows a live transcript, and stores
audio, transcripts, and AI summaries entirely on the user's machine.

This guide takes the project from an empty folder to a tagged v0.1.0 release
on GitHub in nine phases. Each phase ends with a **working checkpoint**, a
**directory tree**, the **documentation to write**, and a **commit**. Commit at
the end of every phase — small commits with clear messages *are* documentation.

Save this file as `docs/BUILD_GUIDE.md` in the repo (Phase 0 shows where).

---

## How this repo stays documented

Four habits, applied every phase:

1. **README.md is the front door.** It grows a little each phase. A stranger
   reading only the README should know what the app does, how to run it, and
   what state it's in.
2. **Every module opens with a docstring** answering *why does this file
   exist* and *how does it work*, in 3–10 lines. Public functions get a
   one-line docstring. Comments are reserved for the non-obvious (the WASAPI
   loopback dance, resampling math) — not for narrating ordinary code.
3. **Spikes are kept, not deleted.** Throwaway proof-of-concept scripts live
   in `spikes/` forever. They document what you learned and give future
   contributors runnable, minimal examples of the hard tricks.
4. **Commit messages follow `type: what and why`.** Types used here:
   `chore`, `spike`, `feat`, `fix`, `docs`, `release`. Example:
   `feat: auto-select whisper model from detected cpu/gpu`.

---

## Phase 0 — An empty repo done right

**Goal:** a public GitHub repo containing a license, a .gitignore, and a
one-paragraph README. No code yet.

### Steps

```powershell
mkdir minutewright
cd minutewright
git init -b main
python -m venv .venv        # the venv is used locally, never committed
```

Create **.gitignore** — do this *before any code exists*, because one entry
here is a privacy requirement, not a tidiness preference:

```gitignore
# Python
.venv/
__pycache__/
*.pyc

# App data — NEVER commit recordings. They contain other people's voices.
recordings/
*.wav

# Packaging output
build/
dist/
*.spec

# Local machine junk
.env
Thumbs.db
```

> **Why the recordings/ line matters:** one careless `git add .` after a test
> meeting would publish your coworkers' voices to the public internet. The
> ignore rule makes that mistake impossible. Keep it forever.

Create **LICENSE** — pick one deliberately:

| You want | Pick | Effect |
|---|---|---|
| Open source, and nobody may take a modified version closed-source (even as a web service) | **AGPL-3.0** | Anyone distributing or serving a modified version must publish their source under AGPL |
| Maximum adoption; reuse in closed commercial products is acceptable | **Apache-2.0** | Anyone may use/modify/sell it if they keep your copyright + license notices; includes a patent grant |

Easiest way to get the correct text: create the file on GitHub after your
first push (**Add file → Create new file → name it `LICENSE`** → GitHub offers
a license picker), then `git pull`. Or paste the official text now from
choosealicense.com. If you pick Apache-2.0, also add a one-line `NOTICE` file:
`Minutewright — Copyright (c) 2026 <your name>`.

Create **README.md** (stub — it grows every phase):

```markdown
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
```

Create the docs folder and put this guide in it: `docs/BUILD_GUIDE.md`.

### Publish to GitHub

Web route: github.com → **New repository** → name `minutewright` → public →
**do not** initialize with a README (you already have one) → create. Then:

```powershell
git add .
git commit -m "chore: project skeleton - readme, license, gitignore, build guide"
git remote add origin https://github.com/<YOUR-USERNAME>/minutewright.git
git push -u origin main
```

CLI route if you have GitHub CLI: `gh repo create minutewright --public --source . --push`

### Directory now

```
minutewright/
├── .git/
├── .gitignore
├── .venv/              (ignored)
├── LICENSE
├── README.md
└── docs/
    └── BUILD_GUIDE.md
```

**Done when:** the repo is visible on github.com with README, LICENSE, and
.gitignore rendered.

---

## Phase 1 — Prove you can hear what the PC hears

**Goal:** record 5 seconds of system audio to `test.wav` via WASAPI loopback.
This is the hardest platform-specific trick in the app, so it gets its own
phase and its own spike script.

### Steps

```powershell
.venv\Scripts\activate
pip install PyAudioWPatch
```

Create **requirements.txt** (it grows each phase):

```
PyAudioWPatch>=0.2.12.5
```

Create **spikes/record_test.py** — the loopback recorder from the build
conversation. Give it a module docstring explaining the trick:

```python
"""Spike: record what the PC is playing via WASAPI loopback.

Windows hides a 'loopback' twin of every output device. PyAudioWPatch
exposes it, so we can open the default speakers *as an input* and capture
exactly what the user hears - no Teams API, no virtual audio cables.
Run with music playing; produces test.wav (gitignored).
"""
```

### Documentation this phase
- README: add a **How it works** section, first bullet: *"Captures system
  audio through the speakers' WASAPI loopback device — records what you hear,
  so it works with any meeting app."*
- The spike's docstring above.

### Directory now

```
minutewright/
├── docs/
│   └── BUILD_GUIDE.md
├── spikes/
│   └── record_test.py
├── requirements.txt
├── README.md, LICENSE, .gitignore
└── test.wav            (ignored - *.wav rule)
```

**Commit:** `spike: capture system audio via wasapi loopback`

**Done when:** you play a YouTube video, run the spike, and `test.wav` plays
back that exact audio.

---

## Phase 2 — Prove the model transcribes

**Goal:** turn `test.wav` into text on your own machine.

### Steps

```powershell
pip install faster-whisper
```

Append `faster-whisper>=1.0.3` to requirements.txt.

Create **spikes/transcribe_test.py**:

```python
"""Spike: transcribe test.wav with faster-whisper.

First run downloads the model (~100-500 MB) to the Hugging Face cache in
your user profile - NOT into this repo. After that it runs fully offline.
"""
from faster_whisper import WhisperModel

model = WhisperModel("base", device="cpu", compute_type="int8")
segments, info = model.transcribe("test.wav", vad_filter=True)
print(f"Detected language: {info.language}")
for s in segments:
    print(f"[{s.start:6.1f}s] {s.text.strip()}")
```

Record a spike WAV of someone *speaking* (a news clip works) and run it.

### Documentation this phase
- README "How it works" bullet 2: *"Transcribes locally with faster-whisper
  (OpenAI's open-source Whisper, reimplemented for speed). Nothing leaves the
  machine after the one-time model download."*

**Commit:** `spike: transcribe wav locally with faster-whisper`

**Done when:** the console prints a recognizable transcript of the clip.

---

## Phase 3 — Live captions (first real module)

**Goal:** captions print in the console *while* audio plays. The two spikes
merge into the app's first production module.

### Steps

```powershell
pip install numpy scipy
```

Append `numpy>=1.26` and `scipy>=1.11` to requirements.txt.

Create **capture.py** — the engine module. It owns:
- the loopback stream and its callback (bytes go onto a queue)
- a worker thread that drains the queue, converts audio to 16 kHz mono
  float32, and transcribes ~5-second chunks with the VAD filter on
- a `lines` list of `{"t": "03:15", "text": "..."}` that anything (console
  now, web UI later) can read

Create **live_console.py** — a 20-line entry point: load a model, start
capture, print new lines until Ctrl+C. This file exists so the engine can be
tested without any server or browser.

### Documentation this phase
- `capture.py` module docstring: the four-step pipeline (callback → queue →
  resample → chunked transcribe) and *why* chunks: Whisper isn't a streaming
  model, so every live-Whisper app fakes it with chunk-on-pause.
- Inline comments only on the resampling math and the loopback device search.
- README gets a **Try it** section: activate venv, `pip install -r
  requirements.txt`, `python live_console.py`.

### Directory now

```
minutewright/
├── capture.py
├── live_console.py
├── spikes/
│   ├── record_test.py
│   └── transcribe_test.py
├── docs/, requirements.txt, README.md, LICENSE, .gitignore
```

**Commit:** `feat: live captions from system audio (capture engine)`

**Done when:** captions of a playing video appear in the console within
~5-8 seconds of the words being spoken.

---

## Phase 4 — The machine picks its own model

**Goal:** your app's signature install-time behavior — detect CPU/GPU and
choose the largest Whisper model the machine can run in real time.

### Steps

```powershell
pip install psutil
```

Append `psutil>=5.9` to requirements.txt.

Create **hardware.py**:
- `detect_gpu()` — shells out to `nvidia-smi` for name + VRAM; returns None
  if there's no NVIDIA GPU (the command not existing *is* the detection)
- `detect_hardware()` — GPU info + CPU cores + RAM
- `choose_model()` — the tier table (document it in the docstring AND the
  README): 9 GB+ VRAM → large-v3-turbo · 6 GB → medium · 3.5 GB → small ·
  strong CPU → small int8 · 4 cores → base · else tiny
- `cpu_choice()` — the fallback used when a GPU exists but its CUDA
  libraries don't. This makes "not sure if I have a GPU" users safe.

Optional but recommended — your first test, **tests/test_hardware.py**:

```python
"""Model selection is pure logic, so it's the easiest thing to test."""
from hardware import choose_model

def test_big_gpu_gets_turbo():
    hw = {"gpu": {"name": "RTX 4070", "vram_mb": 12000}, "cpu_cores": 8, "ram_gb": 16}
    assert choose_model(hw).model == "large-v3-turbo"

def test_no_gpu_strong_cpu_gets_small():
    hw = {"gpu": None, "cpu_cores": 8, "ram_gb": 16}
    assert choose_model(hw).model == "small"
```

Run with `pip install pytest` then `pytest`.

### Documentation this phase
- README gets the **hardware → model table** verbatim. Users of your app will
  ask "why did it pick X?" — the README answers before they ask.

**Commit:** `feat: auto-select whisper model from detected cpu/gpu`

**Done when:** `python -c "import hardware; print(hardware.choose_model(hardware.detect_hardware()))"`
prints a sensible choice for *your* machine, and pytest passes.

---

## Phase 5 — A backend the UI can talk to

**Goal:** the engine gets an HTTP API. Still no visuals — test with a browser
hitting JSON endpoints.

### Steps

```powershell
pip install fastapi uvicorn
```

Append `fastapi>=0.110` and `uvicorn>=0.29` to requirements.txt.

Create **main.py**: loads the model in a background thread at startup (so the
server comes up instantly and the UI can show "loading model…"), wires up
`capture.py`, and serves:

| Endpoint | Purpose |
|---|---|
| `GET /api/status` | model ready? which model/device and why? recording? |
| `POST /api/record/start` | begin a recording session |
| `POST /api/record/stop` | finalize: write WAV, transcript.txt, meta.json |
| `GET /api/live` | elapsed time + transcript lines so far (UI polls this) |
| `GET /api/recordings` | list saved sessions from `recordings/*/meta.json` |
| `GET /api/recordings/{id}/audio` | the WAV file for playback |
| `GET /api/recordings/{id}/transcript` | the saved transcript text |
| `DELETE /api/recordings/{id}` | remove a session |

Each finished session lands in `recordings/<timestamp>/` as `audio.wav`,
`transcript.txt`, `meta.json`. (Already gitignored since Phase 0.)

### Documentation this phase
- Put the endpoint table above into **docs/API.md**. When you later want a
  mobile app or CLI, this file is the contract.
- `main.py` docstring: how to run, which port, where data lands.

### Directory now

```
minutewright/
├── main.py
├── capture.py
├── hardware.py
├── live_console.py
├── docs/
│   ├── BUILD_GUIDE.md
│   └── API.md
├── recordings/         (ignored, created at runtime)
├── spikes/, tests/, requirements.txt, README.md, LICENSE, .gitignore
```

**Commit:** `feat: fastapi backend - record, live transcript, library endpoints`

**Done when:** `python main.py`, then visiting
`http://127.0.0.1:8737/api/status` in a browser shows live JSON, and a
start → wait → stop sequence via the docs page at `/docs` (FastAPI gives you
this for free) produces a folder in `recordings/`.

---

## Phase 6 — The face

**Goal:** the UI your users actually see: record deck with live transcript,
library with playback.

### Steps

Create **static/index.html** — one file, no build tools: header with the
model badge (surfacing Phase 4's decision to the user), a record deck with
timer and live transcript feed polling `/api/live`, and a library pane that
lists recordings, plays audio with a plain `<audio controls>` tag, and shows
the transcript. Serve it from `GET /` in main.py.

### Documentation this phase
- README gets a screenshot. Save it to **docs/images/ui.png** and embed with
  `![Minutewright UI](docs/images/ui.png)`. A screenshot is the highest-value
  documentation a GitHub project has — it's the first thing visitors judge.
- A short comment block at the top of index.html: what polls what, and that
  there's deliberately no framework or build step.

**Commit:** `feat: web ui - record deck, live transcript, library, playback`

**Done when:** the full loop works in the browser: press record during a
meeting video → watch live captions → stop → play it back → read the
transcript. This is the moment the app exists.

---

## Phase 7 — Summaries, still local

**Goal:** one-click meeting minutes via a local LLM through Ollama —
optional, and graceful when Ollama is absent.

### Steps

```powershell
pip install requests
```

Append `requests>=2.31` to requirements.txt.

Create **summarize.py**: check `http://localhost:11434/api/tags` to find an
installed model; send the transcript with a fixed minutes-format prompt
(Overview / Key points / Decisions / Action items); raise a friendly,
actionable error if Ollama isn't running. Add `POST
/api/recordings/{id}/summarize` to main.py and a Summary tab + button to the
UI. Save results as `summary.md` in the session folder.

### Documentation this phase
- README **Summaries (optional)** section: install Ollama, `ollama pull
  llama3.2:3b`, press the button. State plainly that without Ollama
  everything else still works.
- Add the summarize endpoint to docs/API.md.

**Commit:** `feat: local meeting summaries via ollama (optional)`

**Done when:** with Ollama running you get structured minutes; with Ollama
stopped you get a helpful message instead of a crash.

---

## Phase 8 — Ship v0.1.0

**Goal:** a stranger can clone, double-click, and use it — and the repo has a
tagged release to prove the milestone.

### Steps

1. Create **start_app.bat**: creates `.venv` if missing, installs
   requirements, runs `python main.py`. This is the "installer" for now.
2. Finish **README.md** to its full shape, in this order: title + one-liner,
   screenshot, features, quick start (the .bat), the hardware→model table,
   summaries setup, settings/env vars, **limitations** (own mic not captured
   yet; ~5s caption delay; no speaker labels), and a **consent note**:
   recording meetings can require participant consent depending on location
   and company policy.
3. Create **CHANGELOG.md** with a `## 0.1.0` section listing the features.
4. Tag and release:

```powershell
git add .
git commit -m "release: v0.1.0 - launcher, full readme, changelog"
git tag -a v0.1.0 -m "First working release"
git push && git push --tags
```

On GitHub: **Releases → Draft a new release → choose v0.1.0**, paste the
changelog section, publish.

### Final directory

```
minutewright/
├── main.py              # FastAPI server + endpoints, model loads in background
├── capture.py           # loopback capture + chunked live transcription engine
├── hardware.py          # CPU/GPU detection -> model tier selection
├── summarize.py         # optional local summaries through Ollama
├── live_console.py      # engine demo without the server (kept for debugging)
├── static/
│   └── index.html       # the whole UI, no build step
├── spikes/
│   ├── record_test.py   # minimal WASAPI loopback proof
│   └── transcribe_test.py
├── tests/
│   └── test_hardware.py
├── docs/
│   ├── BUILD_GUIDE.md   # this file
│   ├── API.md           # endpoint contract
│   └── images/ui.png
├── recordings/          # runtime data - gitignored
├── start_app.bat
├── requirements.txt
├── CHANGELOG.md
├── README.md
├── LICENSE              # + NOTICE if Apache-2.0
└── .gitignore
```

**Done when:** you clone the repo fresh into a new folder, double-click
`start_app.bat`, and reach a working app without touching anything else.

---

## After v0.1.0 — working like a maintainer

- **Branch per feature from now on:** `git switch -c feat/mic-mixing`, push,
  open a Pull Request to yourself, merge. It builds the muscle memory and
  keeps `main` always-working for anyone who clones.
- **Use Issues as your roadmap.** Seed it from the limitations list: mix the
  user's own microphone in, speaker labels via pyannote, word-level streaming
  captions, PyInstaller packaging so end users don't need Python, map-reduce
  summaries for long meetings.
- **Add CONTRIBUTING.md** the day a stranger opens their first issue, not
  before.

## Naming note (checked July 2026)

Candidates rejected during the name search: *Earshot* (existing classroom
audio-transcription startup, podcast platform, hearing-aid app), *Susurrus*
(existing Whisper-based transcription GUI on GitHub), *MinuteDeck* (one letter
from MinuteDock, an established time tracker). *Minutewright* surfaced zero
apps, repos, or products. Before publishing widely, re-verify yourself:
GitHub search, Google/Apple app stores, a domain lookup, and — if you ever
commercialize — a proper trademark search (USPTO for the US). None of this
guide is legal advice.
