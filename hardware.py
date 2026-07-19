"""Detect this machine's CPU/GPU and choose the best Whisper model it can
handle. Called once at startup; the choice is shown in the UI so the user
always knows what their machine is running and why.
"""

import subprocess
from dataclasses import dataclass

import psutil


@dataclass
class ModelChoice:
    model: str          # faster-whisper model name, e.g. "small"
    device: str          # "cuda" or "cpu"
    compute_type: str    # "float16", "int8_float16", "int8"
    reason: str           # human-readable explanation shown in the UI


def detect_gpu():
    """Return {'name', 'vram_mb'} for the first NVIDIA GPU, or None."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            first = out.stdout.strip().splitlines()[0]
            name, mem = [x.strip() for x in first.split(",")]
            return {"name": name, "vram_mb": int(float(mem))}
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, OSError):
        pass
    return None


def detect_hardware():
    return {
        "gpu": detect_gpu(),
        "cpu_cores": psutil.cpu_count(logical=True) or 4,
        "ram_gb": round(psutil.virtual_memory().total / 1_000_000_000, 1),
    }

def choose_model(hw) -> ModelChoice:
    """Pick the largest model this machine can run comfortably in real time."""
    gpu = hw["gpu"]
    if gpu:
        vram = gpu["vram_mb"]
        label = f"{gpu['name']}, {vram} MB VRAM"
        if vram >= 9000:
            return ModelChoice("large-v3-turbo", "cuda", "float16", label)
        if vram >= 6000:
            return ModelChoice("medium", "cuda", "float16", label)
        if vram >= 3500:
            return ModelChoice("small", "cuda", "int8_float16", label)
        # Tiny GPUs aren't worth the CUDA overhead - fall through to CPU.
    return cpu_choice(hw)


def cpu_choice(hw) -> ModelChoice:
    """CPU-only pick. Also used as the fallback when CUDA libs are missing."""
    cores = hw["cpu_cores"]
    ram = hw["ram_gb"]
    label = f"CPU, {cores} cores, {ram} GB RAM"
    if cores >= 8 and ram >= 8:
        return ModelChoice("small", "cpu", "int8", label)
    if cores >= 4 and ram >= 4:
        return ModelChoice("base", "cpu", "int8", label)
    return ModelChoice("tiny", "cpu", "int8", label)