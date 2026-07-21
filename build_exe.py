"""Build Minutewright.exe - wrapper around PyInstaller.

The real reason this is Python and not batch: the GPU edition must locate
the nvidia CUDA 'bin' folders inside site-packages and pass each one as
--add-binary (PyInstaller's --collect-all can't handle the nvidia wheels,
which are data-style packages its import scanner mishandles).

Usage:
  python build_exe.py                 -> Standard edition (CPU), windowed
  python build_exe.py debug           -> Standard, console kept visible
  python build_exe.py gpu             -> GPU edition (bundles CUDA DLLs)
  python build_exe.py gpu debug       -> GPU, console kept visible

Output: dist\\Minutewright\\ or dist\\Minutewright-GPU\\ - distribute the
whole folder, zipped. One-dir instead of one-file on purpose: with ~1 GB
of AI runtime, a single-file exe re-extracts to temp on every launch
(slow starts) and trips antivirus more often.
"""

import site
import sys
from pathlib import Path

import PyInstaller.__main__ as pyinstaller

args = {a.lower() for a in sys.argv[1:]}
GPU = "gpu" in args
DEBUG = "debug" in args

NAME = "Minutewright-GPU" if GPU else "Minutewright"

cmd = [
    "desktop.py",
    "--noconfirm", "--clean", "--onedir",
    "--name", NAME,
    "--icon", "minutewright.ico",
    "--add-data", "static;static",
    "--add-data", "minutewright.ico;.",
    "--collect-all", "llama_cpp",       # llama.cpp native DLLs
    "--collect-all", "faster_whisper",  # bundled Silero VAD assets
    "--collect-all", "ctranslate2",     # whisper engine's native libraries
    "--collect-all", "webview",         # pywebview
    # pythonnet / .NET bridge that pywebview uses for WebView2 on Windows.
    # PyInstaller's scanner misses its runtime DLLs, so collect everything
    # explicitly - without this the app crashes on clean machines with
    # "Failed to resolve Python.Runtime.Loader.Initialize".
    "--collect-all", "pythonnet",
    "--collect-all", "clr_loader",
    "--collect-all", "reportlab",       # PDF export fonts/data
    "--collect-all", "docx",            # python-docx templates
    "--copy-metadata", "pythonnet",
    "--hidden-import", "clr",
]
if not DEBUG:
    cmd.append("--windowed")

if GPU:
    roots = []
    try:
        roots.extend(site.getsitepackages())
    except Exception:
        pass
    try:
        roots.append(site.getusersitepackages())
    except Exception:
        pass

    bins = {}  # dest -> source, deduped across roots
    for root in roots:
        nv = Path(root) / "nvidia"
        if not nv.is_dir():
            continue
        for b in sorted(nv.glob("*/bin")):
            if b.is_dir():
                bins.setdefault(f"nvidia/{b.parent.name}/bin", b)

    if not bins:
        sys.exit(
            "GPU build requested but no nvidia CUDA wheels found in this "
            "environment.\nRun: pip install nvidia-cublas-cu12 nvidia-cudnn-cu12"
        )
    for dest, src in bins.items():
        print(f"bundling {src} -> {dest}")
        cmd += ["--add-binary", f"{src};{dest}"]

print(f"\nBuilding {NAME} ({'debug/console' if DEBUG else 'windowed release'})...\n")
pyinstaller.run(cmd)
print(f"\nDone. Run: dist\\{NAME}\\{NAME}.exe")