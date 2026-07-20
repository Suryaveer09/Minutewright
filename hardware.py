"""Detect this machine's CPU/GPU and choose the best Whisper model it can
handle. Called once at startup; the choice is shown in the UI so the user
always knows what their machine is running and why.

Also owns the Windows CUDA-DLL workaround: pip-installed nvidia libraries
(dev) or bundle-shipped ones (GPU edition of the exe) aren't discoverable
by the OS loader, so we preload them into the process.
"""

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import psutil

from paths import is_frozen, resource_dir


@dataclass
class ModelChoice:
    model: str           # faster-whisper model name, e.g. "small"
    device: str          # "cuda" or "cpu"
    compute_type: str    # "float16", "int8_float16", "int8"
    reason: str          # human-readable explanation shown in the UI


def _nvidia_bin_dirs() -> list:
    """Every nvidia/*/bin folder we can find, in priority order.

    Frozen (packaged) runs look inside the bundle first: the GPU edition
    ships the DLLs at <bundle>/nvidia/<lib>/bin via --add-binary, and
    resource_dir() is exactly the bundle root (sys._MEIPASS). Dev runs
    (and the Standard exe, which finds nothing and falls back) also scan
    site-packages, where pip installs the nvidia wheels.
    """
    roots = []
    if is_frozen():
        roots.append(resource_dir())
    import site
    try:
        roots.extend(site.getsitepackages())
    except Exception:
        pass
    try:
        roots.append(site.getusersitepackages())
    except Exception:
        pass

    found, seen = [], set()
    for root in roots:
        nv = Path(root) / "nvidia"
        if not nv.is_dir():
            continue
        for bin_dir in sorted(nv.glob("*/bin")):
            if bin_dir.is_dir() and str(bin_dir) not in seen:
                seen.add(str(bin_dir))
                found.append(str(bin_dir))
    return found


def enable_cuda_dlls():
    """Make CUDA libraries actually loadable on Windows.

    ctranslate2 delay-loads cublas/cudnn DLLs *by name* from C++ at first
    inference. That lookup only checks modules already loaded into the
    process and the PATH - it ignores os.add_dll_directory. So we do all
    three: register the dirs, prepend them to PATH, and preload every DLL
    with ctypes so by-name lookups resolve to already-loaded modules.

    Returns the list of nvidia bin folders found (useful for diagnostics).
    """
    if sys.platform != "win32":
        return []
    import ctypes

    found = _nvidia_bin_dirs()

    for d in found:
        try:
            os.add_dll_directory(d)
        except OSError:
            pass
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")

    for d in found:
        for dll in sorted(Path(d).glob("*.dll")):
            try:
                ctypes.WinDLL(str(dll))
            except OSError:
                pass  # some DLLs are optional or load-order sensitive; fine

    return found


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