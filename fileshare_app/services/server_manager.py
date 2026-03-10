from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import logging
import socket
import threading
import time
from pathlib import Path

from waitress import create_server

from ..core.config import Settings, SettingsError
from ..core.metrics import TransferMetrics
from ..core.security import BlacklistStore
from ..core.server import RuntimeState, create_app, resolve_listen_port


@dataclass(frozen=True)
class ServerSnapshot:
    running: bool
    bind_host: str
    bind_port: int
    bind_url: str
    browser_url: str
    local_urls: list[str]
    share_dir: str
    allow_subdirectories: bool
    log_verbosity: str
    server_error: str | None


class ServerManager:
    """Owns Waitress runtime and exposes safe, UI-friendly control methods."""

    def __init__(
        self,
        settings: Settings,
        *,
        logger: logging.Logger,
        metrics: TransferMetrics,
        blacklist_store: BlacklistStore,
    ) -> None:
        self.settings = settings
        self.logger = logger
        self.metrics = metrics
        self.runtime_state = RuntimeState(
            share_dir=settings.share_dir,
            allow_subdirectories=True,
            current_port=settings.port,
            log_verbosity="medium",
        )
        self._app = create_app(
            settings,
            logger=logger,
            metrics=metrics,
            blacklist_store=blacklist_store,
            runtime_state=self.runtime_state,
        )
        self._server = None
        self._thread: threading.Thread | None = None
        self._errors: list[Exception] = []
        self._lock = threading.Lock()

    def start(self) -> ServerSnapshot:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return self.snapshot()

            port = resolve_listen_port(self.settings.host, self.settings.port)
            server, thread, errors = _start_waitress(
                self._app,
                host=self.settings.host,
                port=port,
                threads=self.settings.waitress_threads,
            )
            if not _wait_for_local_listener(self.settings.host, port, timeout_seconds=15):
                _stop_waitress(server, thread)
                raise RuntimeError("Waitress did not open listener in time.")

            self._server = server
            self._thread = thread
            self._errors = errors
            self.runtime_state.set_port(port)
            self.logger.info("event=server_started bind_host=%s bind_port=%s", self.settings.host, port)
            return self.snapshot()

    def stop(self) -> None:
        with self._lock:
            if self._server is None or self._thread is None:
                return
            _stop_waitress(self._server, self._thread)
            self.logger.info("event=server_stopped")
            self._server = None
            self._thread = None

    def restart_on_port(self, requested_port: int) -> ServerSnapshot:
        with self._lock:
            new_port = resolve_listen_port(self.settings.host, requested_port)
            current = self.runtime_state.get_port()
            if current == new_port and self._thread and self._thread.is_alive():
                return self.snapshot()

            if self._server is not None and self._thread is not None:
                _stop_waitress(self._server, self._thread)
                self._server = None
                self._thread = None

            self._errors.clear()
            server, thread, errors = _start_waitress(
                self._app,
                host=self.settings.host,
                port=new_port,
                threads=self.settings.waitress_threads,
            )
            if not _wait_for_local_listener(self.settings.host, new_port, timeout_seconds=15):
                _stop_waitress(server, thread)
                raise RuntimeError("Listener was not ready after port restart.")

            self._server = server
            self._thread = thread
            self._errors = errors
            self.runtime_state.set_port(new_port)
            self.settings.port = new_port
            self.logger.info("event=server_port_changed new_port=%s", new_port)
            return self.snapshot()

    def set_share_directory(self, directory: str | Path) -> Path:
        self.runtime_state.set_share_dir(Path(directory))
        updated = self.runtime_state.get_share_dir()
        self.logger.info("event=share_dir_changed share_dir=%s", updated)
        return updated

    def toggle_subdirectories(self) -> bool:
        value = self.runtime_state.toggle_subdirectories()
        self.logger.info("event=subdirectory_toggle enabled=%s", value)
        return value

    def cycle_log_verbosity(self) -> str:
        value = self.runtime_state.cycle_log_verbosity()
        self.logger.info("event=log_verbosity_changed level=%s", value)
        return value

    def snapshot(self) -> ServerSnapshot:
        port = self.runtime_state.get_port()
        running = bool(self._thread and self._thread.is_alive() and not self._errors)
        bind_url = f"http://{self.settings.host}:{port}"
        browser_host = _choose_browser_host(self.settings.host, self.settings.mode)
        browser_url = f"http://{browser_host}:{port}"
        local_urls = _build_local_urls(self.settings.host, port, self.settings.mode)
        server_error = str(self._errors[-1]) if self._errors else None

        return ServerSnapshot(
            running=running,
            bind_host=self.settings.host,
            bind_port=port,
            bind_url=bind_url,
            browser_url=browser_url,
            local_urls=local_urls,
            share_dir=str(self.runtime_state.get_share_dir()),
            allow_subdirectories=self.runtime_state.get_allow_subdirectories(),
            log_verbosity=self.runtime_state.get_log_verbosity(),
            server_error=server_error,
        )

    def primary_local_url(self) -> str:
        snapshot = self.snapshot()
        if snapshot.local_urls:
            return snapshot.local_urls[0]
        return snapshot.browser_url


def _start_waitress(app, *, host: str, port: int, threads: int):
    errors: list[Exception] = []
    server = create_server(
        app,
        host=host,
        port=port,
        threads=threads,
        connection_limit=max(100, threads * 12),
    )

    def _run() -> None:
        try:
            server.run()
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return server, thread, errors


def _stop_waitress(server, thread: threading.Thread) -> None:
    try:
        server.close()
    except Exception:
        pass
    thread.join(timeout=5)


def _wait_for_local_listener(host: str, port: int, *, timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    check_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    while time.time() < deadline:
        try:
            with socket.create_connection((check_host, port), timeout=1.5):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def _choose_browser_host(bind_host: str, mode: str) -> str:
    if bind_host in ("0.0.0.0", "::"):
        if mode == "local":
            return "127.0.0.1"
        detected = _detect_lan_ip()
        return detected or "127.0.0.1"
    if bind_host == "localhost":
        return "127.0.0.1"
    return bind_host


def _build_local_urls(bind_host: str, port: int, mode: str) -> list[str]:
    if port <= 0:
        return []
    urls: list[str] = []
    if bind_host in ("127.0.0.1", "localhost", "::1"):
        urls.append(f"http://127.0.0.1:{port}")
        return urls
    if bind_host in ("0.0.0.0", "::"):
        if mode == "local":
            urls.append(f"http://127.0.0.1:{port}")
            return urls
        lan = _detect_lan_ip()
        if lan:
            urls.append(f"http://{lan}:{port}")
        urls.append(f"http://127.0.0.1:{port}")
        return urls
    urls.append(f"http://{bind_host}:{port}")
    return urls


def _detect_lan_ip() -> str | None:
    candidates: list[str] = []

    for target in ("8.8.8.8", "1.1.1.1"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect((target, 80))
                candidates.append(sock.getsockname()[0])
        except OSError:
            pass

    try:
        hostname = socket.gethostname()
        for item in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM):
            addr = item[4][0]
            candidates.append(addr)
    except OSError:
        pass

    private_ip = None
    public_ip = None
    for addr in candidates:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if ip.is_loopback or ip.is_unspecified:
            continue
        if ip.version == 4 and ip.is_private and private_ip is None:
            private_ip = addr
        elif not ip.is_private and public_ip is None:
            public_ip = addr

    return private_ip or public_ip
