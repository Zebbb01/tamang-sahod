"""Browser tests (Playwright) against a live server: uv run pytest e2e"""

import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def base_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
                              cwd=Path(__file__).resolve().parent.parent)
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(f"{url}/health")
            break
        except OSError:
            time.sleep(0.1)
    yield url
    server.terminate()
    server.wait()
