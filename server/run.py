"""Desktop entry point: start the API, serve the client, open a browser.

Used both by the PyInstaller build and, for verification, directly from a source
checkout::

    cd server && uv run python run.py

Binding to loopback is deliberate: it keeps the app off the network and avoids
the Windows Firewall prompt on first run.
"""

import argparse
import logging
import multiprocessing
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Running as a script (rather than `python -m server.run`) leaves the repo root
# off sys.path, so the `server` package would not import. Harmless when frozen.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import uvicorn  # noqa: E402

from server.config import DATA_DIR  # noqa: E402
from server.main import app  # noqa: E402

logger = logging.getLogger("motility-analyzer")

DEFAULT_HOST = "127.0.0.1"
PREFERRED_PORT = 8000
BROWSER_TIMEOUT_SECONDS = 30.0


def find_free_port(host: str, preferred: int = PREFERRED_PORT) -> int:
    """Return the preferred port if it is free, otherwise any free port."""
    for candidate in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, candidate))
            except OSError:
                continue
            return sock.getsockname()[1]
    raise RuntimeError(f"No free port available on {host}")


def _open_browser_when_ready(server: uvicorn.Server, url: str) -> None:
    """Wait for uvicorn to accept connections, then open the default browser."""
    deadline = time.monotonic() + BROWSER_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if server.started:
            webbrowser.open(url)
            return
        if server.should_exit:
            return
        time.sleep(0.1)
    logger.warning(
        "Server did not start within %ss; open %s manually",
        BROWSER_TIMEOUT_SECONDS,
        url,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Motility Analyzer app.")
    parser.add_argument(
        "--host", default=DEFAULT_HOST, help="Interface to bind (default: loopback)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Port to bind (default: {PREFERRED_PORT}, or any free port if taken)",
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="Do not open a browser"
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    port = args.port if args.port is not None else find_free_port(args.host)
    url = f"http://{args.host}:{port}"

    print(f"Motility Analyzer is starting at {url}")
    print(f"Data directory: {DATA_DIR}")
    print("Close this window to stop the app.")

    server = uvicorn.Server(
        uvicorn.Config(app, host=args.host, port=port, log_level="info")
    )

    if not args.no_browser:
        threading.Thread(
            target=_open_browser_when_ready, args=(server, url), daemon=True
        ).start()

    server.run()
    return 0


if __name__ == "__main__":
    # Required before any process spawning in a frozen Windows build.
    multiprocessing.freeze_support()
    sys.exit(main())
