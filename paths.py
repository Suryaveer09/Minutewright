"""Central path resolution for dev vs packaged (frozen) runs.

Two kinds of paths, deliberately separated:

- resource_dir(): read-only assets that ship INSIDE the app (static/).
  In dev that's the project folder; in a PyInstaller build it's the
  bundle's extraction dir (sys._MEIPASS).

- data_dir(): user-writable data (recordings, AI models, settings).
  In dev: the project folder, same as always. In a packaged exe:
  %LOCALAPPDATA%\\Minutewright - NEVER next to the executable, because
  a one-file exe unpacks to a temp folder that Windows deletes on exit
  (recordings would vanish), and Program Files isn't writable anyway.

This split is also what guarantees users get a CLEAN app: the exe
contains program only; their machine grows its own data folder.
"""

import os
import sys
from pathlib import Path

APP_NAME = "Minutewright"


def is_frozen() -> bool:
    """True when running as a PyInstaller-packaged executable."""
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Where bundled read-only assets live (static/)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    """Where user data lives (recordings/, models/, settings.json)."""
    if is_frozen():
        base = Path(os.environ.get("LOCALAPPDATA",
                                   Path.home() / "AppData" / "Local"))
        d = base / APP_NAME
    else:
        d = Path(__file__).resolve().parent
    d.mkdir(parents=True, exist_ok=True)
    return d