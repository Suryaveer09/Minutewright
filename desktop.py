"""Desktop entry point for Minutewright.

Runs the FastAPI engine in a background thread and opens the UI in a
native window (pywebview -> Edge WebView2 on Windows). No browser, no
tabs - this is what gets packaged into Minutewright.exe later.
"""

import asyncio
import logging
import threading
import time

import uvicorn
import webview

from main import app, load_model_background

PORT = 8737


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

    webview.create_window(
        "Minutewright",
        f"http://127.0.0.1:{PORT}",
        width=1100,
        height=760,
        min_size=(800, 560),
    )
    webview.start()
    # webview.start() blocks until the window closes; the daemon threads
    # (server + model) die with the process - closing the window exits the app.