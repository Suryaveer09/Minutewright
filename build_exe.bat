@echo off
REM Build Minutewright.exe
REM   build_exe.bat          -> release build (no console window)
REM   build_exe.bat debug    -> keeps the console so errors are visible
REM
REM Output: dist\Minutewright\Minutewright.exe  (distribute the whole
REM folder, zipped). One-dir instead of one-file on purpose: with ~1 GB
REM of AI runtime, a single-file exe re-extracts everything to temp on
REM every launch (slow starts) and trips antivirus more often.

setlocal
set WINFLAG=--windowed
if /I "%1"=="debug" set WINFLAG=

pyinstaller --noconfirm --clean --onedir --name Minutewright ^
  --add-data "static;static" ^
  --collect-all llama_cpp ^
  --collect-all faster_whisper ^
  --collect-all ctranslate2 ^
  --collect-all webview ^
  %WINFLAG% ^
  desktop.py

echo.
echo Done. Run: dist\Minutewright\Minutewright.exe
endlocal