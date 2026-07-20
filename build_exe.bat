@echo off
REM Thin wrapper - the real build logic lives in build_exe.py
REM   build_exe.bat                -> Standard edition (CPU), windowed
REM   build_exe.bat debug          -> Standard, console visible
REM   build_exe.bat gpu            -> GPU edition (bundles CUDA DLLs)
REM   build_exe.bat gpu debug      -> GPU, console visible
python build_exe.py %*