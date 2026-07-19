"""Entry point: live captions in the console, no server or UI needed.

Loads the model, starts capturing system audio, prints new caption lines
as they arrive, and stops cleanly on Ctrl+C.
"""

import time

from faster_whisper import WhisperModel

from capture import LiveCapture

print("Loading model...")
model = WhisperModel("base", device="cpu", compute_type="int8")

cap = LiveCapture(model)
cap.start()

print("Listening. Press Ctrl+C to stop.\n")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping...")
    cap.stop()
    print(f"Captured {len(cap.lines)} lines.")