"""Filesystem locations, resolved for both a source checkout and a frozen build.

PyInstaller unpacks a one-file bundle into a temp directory that it deletes when
the process exits, so ``Path(__file__).parent`` is safe to read from but must
never be written to. Everything the app persists therefore goes to a per-user
data directory instead, and only read-only resources resolve from the bundle.

In a source checkout both kinds of path stay where they always were, inside
``server/``, so development behaviour is unchanged.
"""

import os
import sys
from pathlib import Path

APP_NAME = "MotilityAnalyzer"

#: Overrides the writable data directory. Useful for tests and for lab machines
#: that keep their data on a shared drive.
DATA_DIR_ENV_VAR = "MOTILITY_ANALYZER_DATA_DIR"

_SOURCE_DIR = Path(__file__).resolve().parent


def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def resource_dir() -> Path:
    """Read-only files shipped with the app (ffmpeg binaries, built client)."""
    if is_frozen():
        # One-file sets _MEIPASS to the temp extraction dir; one-folder sets it
        # to the bundle's own directory. Neither is writable in any useful way.
        meipass = getattr(sys, "_MEIPASS", None)
        return Path(meipass) if meipass else Path(sys.executable).resolve().parent
    return _SOURCE_DIR


def _platform_data_dir() -> Path:
    if sys.platform == "win32":
        local_appdata = os.getenv("LOCALAPPDATA")
        root = (
            Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
        )
        return root / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    xdg_data_home = os.getenv("XDG_DATA_HOME")
    root = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
    return root / APP_NAME


def data_dir() -> Path:
    """Writable user data (videos, database, results) — never inside the bundle."""
    override = os.getenv(DATA_DIR_ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    if is_frozen():
        return _platform_data_dir()
    return _SOURCE_DIR
