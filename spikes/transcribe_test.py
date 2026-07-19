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