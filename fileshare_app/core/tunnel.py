from __future__ import annotations

import logging
import re
import shutil
import socket
import subprocess
import threading
import time
from urllib.parse import urlparse
from dataclasses import dataclass


class TunnelError(RuntimeError):
    """Raised for tunnel start failures."""


@dataclass
class TunnelState:
    url: str | None = None
    process: subprocess.Popen[str] | None = None
    startup_error: str | None = None
    alive: bool = False


class TunnelManager:
    URL_RE = re.compile(r"(https://[\w\.-]+\.trycloudflare\.com)")

    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger
        self.state = TunnelState()
        self._stop_lock = threading.Lock()

    def get_url(self) -> str | None:
        return self.state.url

    def start(self, *, enabled: bool, port: int, timeout_seconds: int = 30) -> str | None:
        if not enabled:
            self.logger.info("Tunnel disabled by settings.")
            return None

        if shutil.which("cloudflared") is None:
            raise TunnelError("cloudflared is not installed or not on PATH.")

        cmd = ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"]
        self.logger.info("Starting cloudflared tunnel.")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.state.process = proc
        self.state.alive = True
        found = threading.Event()
        url_announced = False

        def _reader() -> None:
            nonlocal url_announced
            assert proc.stdout is not None
            for line in proc.stdout:
                message = line.strip()
                if message:
                    self.logger.debug("cloudflared: %s", message)
                match = self.URL_RE.search(message)
                if match and not url_announced:
                    self.state.url = match.group(1)
                    url_announced = True
                    found.set()
            code = proc.wait()
            self.state.alive = False
            if self.state.url is None:
                self.state.startup_error = f"cloudflared exited with code {code}"
                found.set()
            else:
                self.logger.error("cloudflared tunnel process exited with code %s", code)

        threading.Thread(target=_reader, daemon=True).start()
        if not found.wait(timeout_seconds):
            self.stop()
            raise TunnelError(f"Timed out waiting for cloudflared tunnel URL after {timeout_seconds}s.")

        if self.state.url:
            if self._wait_for_dns(self.state.url, timeout_seconds=20):
                self.logger.info("Tunnel URL available: %s", self.state.url)
                return self.state.url
            self.stop()
            raise TunnelError(
                "Tunnel URL was emitted but DNS never resolved. "
                "This is usually network or quick-tunnel instability; retry in a moment."
            )

        error = self.state.startup_error or "cloudflared failed to start tunnel."
        self.stop()
        raise TunnelError(error)

    def stop(self) -> None:
        with self._stop_lock:
            proc = self.state.process
            if not proc:
                return
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            self.state.process = None
            self.state.alive = False

    def _wait_for_dns(self, url: str, *, timeout_seconds: int) -> bool:
        host = urlparse(url).hostname
        if not host:
            return False
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                socket.gethostbyname_ex(host)
                with socket.create_connection((host, 443), timeout=3):
                    pass
                return True
            except OSError:
                time.sleep(1)
        return False
