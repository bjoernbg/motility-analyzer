"""Locating the ffmpeg and ffprobe executables the app shells out to.

The packaged app ships its own binaries under ``ffmpeg_bin/<platform>/`` so the
target machine needs no system ffmpeg. A source checkout uses those same
vendored binaries when they are present and otherwise falls back to PATH.
"""

import logging
import os
import shutil
import sys
from functools import lru_cache
from pathlib import Path

from .config import FFMPEG_BIN_DIR

logger = logging.getLogger(__name__)

# A Git LFS pointer is ~130 bytes and carries the name of the binary it stands
# in for, so a clone made without git-lfs looks like a valid ffmpeg.exe until it
# is executed. Size is the cheap way to spot one.
_MIN_PLAUSIBLE_BINARY_SIZE = 1024 * 1024


class FFmpegNotFoundError(RuntimeError):
    """Neither a bundled nor a system copy of the tool could be used."""


def _platform_dir() -> str | None:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return None


def _bundled_path(tool: str) -> Path | None:
    """Return the vendored binary for this platform, or None if unusable."""
    platform_dir = _platform_dir()
    if platform_dir is None:
        return None

    name = f"{tool}.exe" if sys.platform == "win32" else tool
    candidate = FFMPEG_BIN_DIR / platform_dir / name
    if not candidate.is_file():
        return None

    size = candidate.stat().st_size
    if size < _MIN_PLAUSIBLE_BINARY_SIZE:
        logger.warning(
            "Ignoring %s: %d bytes is too small to be a real binary, most likely "
            "a Git LFS pointer. Run 'git lfs install && git lfs pull'.",
            candidate,
            size,
        )
        return None

    # PyInstaller does not always preserve the executable bit on bundled data.
    if os.name == "posix" and not os.access(candidate, os.X_OK):
        try:
            candidate.chmod(candidate.stat().st_mode | 0o111)
        except OSError as exc:
            logger.warning("Cannot make %s executable: %s", candidate, exc)
            return None

    return candidate


@lru_cache(maxsize=None)
def _resolve(tool: str) -> str:
    bundled = _bundled_path(tool)
    if bundled is not None:
        logger.info("Using bundled %s: %s", tool, bundled)
        return str(bundled)

    on_path = shutil.which(tool)
    if on_path:
        logger.info("Using %s from PATH: %s", tool, on_path)
        return on_path

    platform_dir = _platform_dir() or "<platform>"
    raise FFmpegNotFoundError(
        f"{tool} is not available. The packaged app ships it at "
        f"{FFMPEG_BIN_DIR / platform_dir}; that file is missing, too small to be "
        f"a real binary, or not executable. Either restore the vendored binaries "
        f"or install ffmpeg and put it on PATH."
    )


def ffmpeg_executable() -> str:
    """Path to the ffmpeg binary to invoke."""
    return _resolve("ffmpeg")


def ffprobe_executable() -> str:
    """Path to the ffprobe binary to invoke."""
    return _resolve("ffprobe")
