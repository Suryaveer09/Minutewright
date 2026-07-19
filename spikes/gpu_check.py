"""Spike: verify CUDA inference actually works for faster-whisper on Windows.

Run:  python spikes/gpu_check.py
Prints which nvidia DLL folders were found, then attempts a real (tiny)
model inference on the GPU and reports SUCCESS or the full error traceback.
"""

import sys
import traceback
from pathlib import Path

# Make project-root imports work when run as "python spikes/gpu_check.py"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hardware import enable_cuda_dlls

dirs = enable_cuda_dlls()
print("nvidia DLL folders found:")
if dirs:
    for d in dirs:
        print("  ", d)
else:
    print("   (none - CUDA pip packages missing or not where expected)")

import numpy as np
from faster_whisper import WhisperModel

try:
    print("\nLoading tiny model on cuda...")
    m = WhisperModel("tiny", device="cuda", compute_type="float16")
    segments, _ = m.transcribe(np.zeros(16000, dtype=np.float32), language="en")
    list(segments)  # force the generator - this is what actually hits cuBLAS
    print("SUCCESS: GPU inference works.")
except Exception:
    print("FAILED: GPU inference raised:\n")
    traceback.print_exc()