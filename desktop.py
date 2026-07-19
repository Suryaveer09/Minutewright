"""Desktop entry point for Minutewright.

Runs the FastAPI engine in a background thread and opens the UI in a
native window (pywebview -> Edge WebView2 on Windows). No browser, no
tabs - this is what gets packaged into Minutewright.exe later.
"""

import threading
import time

import uvicorn
import webview

from main import app, load_model_background

PORT = 8737


def run_server():
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
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