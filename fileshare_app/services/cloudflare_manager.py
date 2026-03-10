from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import logging
import os
from pathlib import Path
import platform
import shutil
import subprocess
import threading

from ..core.tunnel import TunnelError, TunnelManager


class CloudflareState(str, Enum):
    NOT_INSTALLED = "NOT_INSTALLED"
    INSTALLED_NOT_CONFIGURED = "INSTALLED_NOT_CONFIGURED"
    READY = "READY"
    RUNNING = "RUNNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class CloudflareSnapshot:
    state: CloudflareState
    installed: bool
    configured: bool
    running: bool
    binary_path: str | None
    version: str | None
    public_url: str | None
    message: str
    quick_tunnel_warning: str | None


class CloudflareManager:
    """Optional Cloudflare controller; never required for local/LAN operation."""

    def __init__(
        self,
        logger: logging.Logger,
        *,
        known_tool_dirs: list[Path] | None = None,
    ) -> None:
        self.logger = logger
        self._lock = threading.RLock()
        self._tunnel = TunnelManager(logger)
        self._known_tool_dirs = [p for p in (known_tool_dirs or []) if p]
        self._binary_path: str | None = None
        self._version_cache: dict[str, str | None] = {}
        self._snapshot = CloudflareSnapshot(
            state=CloudflareState.NOT_INSTALLED,
            installed=False,
            configured=False,
            running=False,
            binary_path=None,
            version=None,
            public_url=None,
            message="cloudflared not detected.",
            quick_tunnel_warning=None,
        )

    def snapshot(self) -> CloudflareSnapshot:
        with self._lock:
            return self._detect_locked()

    def detect(self) -> CloudflareSnapshot:
        with self._lock:
            return self._detect_locked()

    def start_public_mode(self, *, port: int) -> CloudflareSnapshot:
        with self._lock:
            base = self.detect()
            if base.state == CloudflareState.RUNNING:
                return replace(base, message="Public tunnel is already running.")
            if base.state == CloudflareState.NOT_INSTALLED:
                self.logger.warning("event=cloudflare_missing_for_public_mode")
                return base
            if base.state == CloudflareState.INSTALLED_NOT_CONFIGURED:
                self.logger.info("event=cloudflare_setup_required")
                return replace(
                    base,
                    message=(
                        "Setup required: run 'cloudflared tunnel login' and create a named tunnel. "
                        "Local/LAN mode remains available."
                    ),
                )

            try:
                url = self._tunnel.start(enabled=True, port=port)
            except TunnelError as exc:
                self._snapshot = replace(
                    base,
                    state=CloudflareState.ERROR,
                    running=False,
                    public_url=None,
                    message=f"Tunnel start failed: {exc}",
                )
                self.logger.error("event=cloudflare_tunnel_start_failed reason=%s", exc)
                return self._snapshot

            refreshed = self._detect_locked()
            if refreshed.state != CloudflareState.RUNNING:
                self._snapshot = replace(
                    refreshed,
                    state=CloudflareState.ERROR,
                    running=False,
                    public_url=None,
                    message="Tunnel started but did not remain active.",
                )
                return self._snapshot

            self._snapshot = replace(refreshed, public_url=url, message="Public tunnel is active.")
            self.logger.info("event=cloudflare_tunnel_running url=%s", url or "unknown")
            return self._snapshot

    def stop_public_mode(self) -> CloudflareSnapshot:
        with self._lock:
            self._tunnel.stop()
            snapshot = self.detect()
            if snapshot.state == CloudflareState.RUNNING:
                snapshot = replace(snapshot, state=CloudflareState.READY, running=False, public_url=None)
            self._snapshot = replace(snapshot, message="Public tunnel stopped.")
            self.logger.info("event=cloudflare_tunnel_stopped")
            return self._snapshot

    def refresh(self) -> CloudflareSnapshot:
        return self.detect()

    def get_public_url(self) -> str | None:
        return self.snapshot().public_url

    def install_instructions(self) -> list[str]:
        if os.name == "nt":
            return [
                "winget install Cloudflare.cloudflared",
                "or download binary from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/",
                "verify with: cloudflared --version",
            ]
        if platform.system().lower() == "darwin":
            return [
                "brew install cloudflared",
                "verify with: cloudflared --version",
            ]
        return [
            "Install from distro package manager or Cloudflare downloads page.",
            "verify with: cloudflared --version",
        ]

    def setup_instructions(self) -> list[str]:
        return [
            "cloudflared tunnel login",
            "cloudflared tunnel create <NAME>",
            "cloudflared tunnel route dns <NAME> <HOSTNAME>",
            "Use named tunnel config for production deployments.",
        ]

    def _resolve_binary(self) -> str | None:
        if self._binary_path and Path(self._binary_path).exists():
            return self._binary_path

        from_path = shutil.which("cloudflared")
        if from_path:
            self._binary_path = from_path
            return from_path

        executable = "cloudflared.exe" if os.name == "nt" else "cloudflared"
        for root in self._known_tool_dirs:
            candidate = (root / executable).resolve()
            if candidate.exists():
                self._binary_path = str(candidate)
                return self._binary_path
        return None

    def _read_version(self, binary: str) -> str | None:
        if binary in self._version_cache:
            return self._version_cache[binary]
        try:
            result = subprocess.run(
                [binary, "--version"],
                capture_output=True,
                text=True,
                timeout=4,
                check=False,
            )
        except Exception:
            self._version_cache[binary] = None
            return None
        output = (result.stdout or result.stderr or "").strip().splitlines()
        self._version_cache[binary] = output[0] if output else None
        return self._version_cache[binary]

    def _is_configured(self) -> bool:
        home = Path.home()
        cloudflared_dir = home / ".cloudflared"
        cert = cloudflared_dir / "cert.pem"
        config_yml = cloudflared_dir / "config.yml"
        config_yaml = cloudflared_dir / "config.yaml"
        return cert.exists() or config_yml.exists() or config_yaml.exists()

    def _detect_locked(self) -> CloudflareSnapshot:
        binary = self._resolve_binary()
        if not binary:
            self._snapshot = CloudflareSnapshot(
                state=CloudflareState.NOT_INSTALLED,
                installed=False,
                configured=False,
                running=False,
                binary_path=None,
                version=None,
                public_url=None,
                message="Public mode requires cloudflared. Install it to enable tunnel features.",
                quick_tunnel_warning=None,
            )
            return self._snapshot

        configured = self._is_configured()
        version = self._read_version(binary)
        proc = self._tunnel.state.process
        process_running = bool(proc and proc.poll() is None)
        public_url = self._tunnel.get_url() if process_running else None
        if not process_running:
            # Avoid stale URLs after process exits.
            self._tunnel.state.url = None

        if process_running and public_url:
            state = CloudflareState.RUNNING
            message = "Public tunnel is running."
        elif process_running and not public_url:
            state = CloudflareState.ERROR
            message = "Tunnel process is running but no public URL is available yet."
        elif configured:
            state = CloudflareState.READY
            message = "cloudflared is installed and ready."
        else:
            state = CloudflareState.INSTALLED_NOT_CONFIGURED
            message = "cloudflared is installed but not configured. Run setup before enabling public mode."

        previous_state = self._snapshot.state
        exit_code = None
        if proc and not process_running:
            exit_code = proc.poll()
        if previous_state == CloudflareState.RUNNING and not process_running and exit_code is not None:
            message = f"Tunnel process exited with code {exit_code}."

        self._snapshot = CloudflareSnapshot(
            state=state,
            installed=True,
            configured=configured,
            running=(state == CloudflareState.RUNNING),
            binary_path=binary,
            version=version,
            public_url=public_url,
            message=message,
            quick_tunnel_warning=(
                "Quick Tunnel is for development/testing only. Use a named tunnel for production."
                if state in {CloudflareState.RUNNING, CloudflareState.READY, CloudflareState.INSTALLED_NOT_CONFIGURED}
                else None
            ),
        )
        return self._snapshot
