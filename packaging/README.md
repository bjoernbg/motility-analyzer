# Packaging

The goal is one Windows artifact a lab user double-clicks: no Python, no Node,
no ffmpeg install, no terminal. The server starts, serves the UI on a single
port, and opens the browser itself.

## Build

Both steps run from a clone with Git LFS set up (`git lfs install && git lfs
pull`) — without it the vendored ffmpeg binaries are 130-byte pointer files
named `ffmpeg.exe`, and both the spec and the CI workflow refuse to continue.

```bash
# 1. Build the client into server/static/ with a relative API base
cd client && npm ci && npm run build-bundled

# 2. Build the one-folder bundle
cd ../server && uv sync && uv run pyinstaller --noconfirm motility-analyzer.spec
```

The result is `server/dist/motility-analyzer/`, launched via
`motility-analyzer.exe` (or `motility-analyzer` on macOS/Linux).

To wrap it as an installer on Windows:

```pwsh
iscc /DAppVersion=1.0.0 packaging/motility-analyzer.iss
```

PyInstaller does not cross-compile, so the Windows executable must be built on
Windows. `.github/workflows/windows-build.yml` does all of the above on a
`windows-latest` runner, on a `v*` tag or on demand, and uploads both the
installer and the portable folder.

## Verify the build without packaging

Steps 1 and 2 of the app's runtime behaviour are checkable from a source
checkout on any platform:

```bash
cd client && npm run build-bundled
cd ../server && uv run python run.py
```

That serves the whole app on one port with no Vite process running.

## How the pieces fit

| Concern | Where |
| --- | --- |
| Entry point (port, browser, uvicorn) | `server/run.py` |
| PyInstaller build definition | `server/motility-analyzer.spec` |
| Bundled vs. writable paths | `server/paths.py`, `server/config.py` |
| ffmpeg/ffprobe lookup | `server/ffmpeg_tools.py` |
| Static client + SPA fallback | end of `server/main.py` |
| Relative API base for the bundle | `client/.env.bundled` |

### Paths

A PyInstaller bundle's own directory is read-only in practice — under a
one-file build it is a temp directory deleted when the process exits. So the
two kinds of path are separated:

- **Bundled resources** (`RESOURCE_DIR`): the built client and the ffmpeg
  binaries, resolved from `sys._MEIPASS`.
- **User data** (`DATA_DIR`): videos, `analyses.db`, results. In a frozen build
  this is `%LOCALAPPDATA%\MotilityAnalyzer` on Windows,
  `~/Library/Application Support/MotilityAnalyzer` on macOS, and
  `$XDG_DATA_HOME/MotilityAnalyzer` on Linux. Override with
  `MOTILITY_ANALYZER_DATA_DIR`.

In a source checkout both resolve to `server/`, so development is unchanged.

## Verification on a clean Windows machine

A developer machine masks the ffmpeg and LFS problems because ffmpeg is already
on PATH. Test on a machine with no Python, Node or ffmpeg installed:

- [ ] `ffmpeg.exe` in the build output is a real binary, not a 130-byte pointer
- [ ] App launches by double-click and opens a browser unprompted
- [ ] Upload a video — exercises the ffprobe path
- [ ] Metadata shows correct FPS, frame count and duration
- [ ] Run an analysis to completion, confirm the heatmap renders
- [ ] Contraction detection produces events
- [ ] Re-encode a non-H.264 video — exercises the ffmpeg path
- [ ] **Close the app, reopen it, confirm the previous analysis is still
      listed** — the one failure that loses work quietly
- [ ] `%LOCALAPPDATA%\MotilityAnalyzer` exists and holds `analyses.db`
- [ ] Open via `127.0.0.1:8000` as well as `localhost:8000`
- [ ] No Windows Firewall prompt (the app binds to loopback only)
