"""Desktop entry point for Minutewright.

Runs the FastAPI engine in a background thread and opens the UI in a
native window (pywebview -> Edge WebView2 on Windows). No browser, no
tabs - this is what gets packaged into Minutewright.exe.

Also home to DesktopApi, the js_api bridge: Python methods the UI can
call directly (window.pywebview.api.*): the native Save As dialog, and
a clipboard reader that powers Paste in the app's own right-click menu.

Hard-won pywebview lessons encoded here:
1. js_api objects are INTROSPECTED - pywebview walks public attributes to
   build nested JS APIs. A public self.window on a js_api object makes it
   try to expose the entire native object graph to JS (infinite recursion
   on .NET's Rectangle.Empty, cross-thread COM errors). Native refs on a
   js_api object must be underscore-private.
2. On Windows, pywebview ties the native right-click menu to debug mode -
   there is NO supported way to enable it in a release window, and JS can
   only suppress menus, never create them. So the app draws its OWN
   context menu in the UI (like VS Code/Discord do). Clipboard READ is
   permission-gated inside the webview, so Paste is served from Python:
   .NET's Clipboard.GetText() on a proper STA thread (WinForms requires
   one), via pythonnet - which the app already ships for pywebview.
"""

import os
import sys

# CRITICAL - must run before any other imports that touch the filesystem.
# When a packaged exe is launched by double-clicking in File Explorer,
# Windows may set the working directory to somewhere unrelated (often
# System32), not the exe's folder. Any cwd-relative path then resolves
# wrong, startup throws, and a windowless exe dies silently before the
# window appears. Anchoring cwd to the exe's own directory up front
# removes the whole class of bug.
if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))

import asyncio
import logging
import threading
import time

import uvicorn
import webview

import exporters
from main import app, load_model_background, load_session, _safe_filename
from paths import resource_dir

PORT = 8737


def _read_clipboard_text():
    """Read text from the Windows clipboard.

    Uses .NET's Clipboard via pythonnet (already shipped for pywebview)
    instead of hand-rolled Win32 ctypes - GetText() handles clipboard
    format-synthesis quirks. WinForms Clipboard requires an STA thread,
    so the read runs on a real .NET STA thread.
    """
    try:
        import clr
        clr.AddReference("System.Windows.Forms")
        from System.Threading import ApartmentState, Thread, ThreadStart
        from System.Windows.Forms import Clipboard

        result = {"text": None}

        def read():
            try:
                if Clipboard.ContainsText():
                    result["text"] = Clipboard.GetText()
            except Exception:
                result["text"] = None

        t = Thread(ThreadStart(read))
        t.SetApartmentState(ApartmentState.STA)
        t.Start()
        t.Join(2000)   # milliseconds
        return result["text"]
    except Exception:
        return None


class DesktopApi:
    """Python methods exposed to the UI as window.pywebview.api."""

    def __init__(self):
        # PRIVATE on purpose - see module docstring, lesson 1.
        self._window = None

    def get_clipboard_text(self):
        """Paste support for the app's own context menu."""
        try:
            text = _read_clipboard_text()
        except Exception:
            text = None
        return {"ok": text is not None, "text": text or ""}

    def save_export(self, rec_id: str, fmt: str):
        try:
            session = load_session(rec_id)
        except Exception as exc:
            # load_session raises FastAPI's HTTPException for bad/missing
            # ids; its .detail is the user-facing message.
            return {"ok": False, "error": getattr(exc, "detail", None) or str(exc)}
        if not session["lines"]:
            return {"ok": False, "error": "This recording has no transcript to export."}

        try:
            data, _media, ext = exporters.export(session, fmt)
        except Exception as exc:
            return {"ok": False, "error": f"Export failed: {exc}"}

        result = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=_safe_filename(session["title"], ext),
            file_types=(f"{ext.upper()} file (*.{ext})", "All files (*.*)"),
        )
        if not result:
            return {"ok": False, "cancelled": True}   # user closed the dialog

        # SAVE_DIALOG returns a plain string on Windows but a tuple on some
        # platforms/versions - accept both.
        path = result[0] if isinstance(result, (tuple, list)) else result
        if not path.lower().endswith("." + ext):
            path += "." + ext
        try:
            with open(path, "wb") as f:
                f.write(data)
        except OSError as exc:
            return {"ok": False, "error": f"Couldn't save the file: {exc}"}
        return {"ok": True, "path": path}


def _silence_benign_disconnects():
    """Windows Proactor loop logs ConnectionResetError(10054) tracebacks
    whenever a client drops an HTTP connection mid-flight - which polling
    UIs do constantly (abandoned polls, cancelled audio range requests).
    Harmless, but noisy enough to scare users and bury real errors, so
    filter exactly that error and nothing else."""

    class _Filter(logging.Filter):
        def filter(self, record):
            exc = record.exc_info[1] if record.exc_info else None
            if isinstance(exc, ConnectionResetError):
                return False
            return "ConnectionResetError" not in record.getMessage()

    logging.getLogger("asyncio").addFilter(_Filter())


def run_server():
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    _silence_benign_disconnects()
    threading.Thread(target=load_model_background, daemon=True).start()
    threading.Thread(target=run_server, daemon=True).start()
    time.sleep(1.0)  # small grace period so the first page load hits a live server

    desktop_api = DesktopApi()
    window = webview.create_window(
        "Minutewright",
        f"http://127.0.0.1:{PORT}",
        width=1100,
        height=760,
        min_size=(800, 560),
        js_api=desktop_api,
    )
    desktop_api._window = window

    _icon = resource_dir() / "minutewright.ico"
    webview.start(icon=str(_icon) if _icon.exists() else None)
    # webview.start() blocks until the window closes; the daemon threads
    # (server + model) die with the process - closing the window exits the app.