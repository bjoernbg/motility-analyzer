# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Motility Analyzer desktop build.

One-folder by design: a one-file build unpacks ~half a gigabyte to a temp
directory on every launch, which reads as a hang. Build with::

    cd server && uv run pyinstaller motility-analyzer.spec

The built client must already be in server/static/ (see client's
`npm run build-bundled`), and the vendored ffmpeg binaries must be real
binaries rather than Git LFS pointers.
"""

import sys
from pathlib import Path

SPEC_DIR = Path(SPECPATH).resolve()

if sys.platform == "win32":
    FFMPEG_PLATFORM = "windows"
elif sys.platform == "darwin":
    FFMPEG_PLATFORM = "macos"
else:
    FFMPEG_PLATFORM = "linux"

# A Git LFS pointer is ~130 bytes and named exactly like the binary it replaces,
# so it would be bundled without complaint and fail only at runtime.
MIN_BINARY_SIZE = 1024 * 1024

static_dir = SPEC_DIR / "static"
if not (static_dir / "index.html").is_file():
    raise SystemExit(
        f"{static_dir / 'index.html'} is missing. Build the client first:\n"
        "  cd client && npm ci && npm run build-bundled"
    )

ffmpeg_dir = SPEC_DIR / "ffmpeg_bin" / FFMPEG_PLATFORM
suffix = ".exe" if sys.platform == "win32" else ""
for tool in ("ffmpeg", "ffprobe"):
    binary = ffmpeg_dir / f"{tool}{suffix}"
    if not binary.is_file():
        raise SystemExit(f"Vendored binary missing: {binary}")
    if binary.stat().st_size < MIN_BINARY_SIZE:
        raise SystemExit(
            f"{binary} is only {binary.stat().st_size} bytes — that is a Git LFS "
            "pointer, not a binary. Run 'git lfs install && git lfs pull'."
        )

# The ffmpeg binaries go in as data, not as `binaries`: they are self-contained
# static builds and must not be run through PyInstaller's dependency scanner.
datas = [
    (str(static_dir), "static"),
    (str(ffmpeg_dir), f"ffmpeg_bin/{FFMPEG_PLATFORM}"),
]

# uvicorn picks its protocol and loop implementations by string at runtime, so
# none of them are reachable by static analysis.
hiddenimports = [
    "uvicorn.lifespan.off",
    "uvicorn.lifespan.on",
    "uvicorn.logging",
    "uvicorn.loops.asyncio",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
]

excludes = [
    "IPython",
    "matplotlib",
    "pytest",
    "tkinter",
]

a = Analysis(
    [str(SPEC_DIR / "run.py")],
    pathex=[str(SPEC_DIR.parent)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="motility-analyzer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="motility-analyzer",
)
