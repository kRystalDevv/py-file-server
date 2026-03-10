from __future__ import annotations

from dataclasses import dataclass, replace
import threading
import time

from ..services.cloudflare_manager import CloudflareSnapshot, CloudflareState
from ..services.server_manager import ServerSnapshot
from ..services.transfer_store import TransferSnapshot

_UNSET = object()


def default_server_snapshot() -> ServerSnapshot:
    return ServerSnapshot(
        running=False,
        bind_host="127.0.0.1",
        bind_port=0,
        bind_url="http://127.0.0.1:0",
        browser_url="http://127.0.0.1:0",
        local_urls=[],
        share_dir="",
        allow_subdirectories=True,
        log_verbosity="medium",
        server_error=None,
    )


def default_cloudflare_snapshot() -> CloudflareSnapshot:
    return CloudflareSnapshot(
        state=CloudflareState.NOT_INSTALLED,
        installed=False,
        configured=False,
        running=False,
        binary_path=None,
        version=None,
        public_url=None,
        message="Cloudflare public mode is optional.",
        quick_tunnel_warning=None,
    )


def default_transfer_snapshot() -> TransferSnapshot:
    return TransferSnapshot(active=[], recent=[], total_uploaded=0)


@dataclass(frozen=True)
class OperatorState:
    server: ServerSnapshot
    cloudflare: CloudflareSnapshot
    transfers: TransferSnapshot
    logs: list[str]
    status_message: str
    active_users_count: int | None
    qr_target_url: str | None
    updated_at: float


class OperatorStateStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = OperatorState(
            server=default_server_snapshot(),
            cloudflare=default_cloudflare_snapshot(),
            transfers=default_transfer_snapshot(),
            logs=[],
            status_message="Starting...",
            active_users_count=None,
            qr_target_url=None,
            updated_at=time.time(),
        )

    def snapshot(self) -> OperatorState:
        with self._lock:
            return self._state

    def update(
        self,
        *,
        server: ServerSnapshot | None = None,
        cloudflare: CloudflareSnapshot | None = None,
        transfers: TransferSnapshot | None = None,
        logs: list[str] | None = None,
        status_message: str | None = None,
        active_users_count: int | None | object = _UNSET,
        qr_target_url: str | None | object = _UNSET,
    ) -> OperatorState:
        with self._lock:
            data = {
                "server": server or self._state.server,
                "cloudflare": cloudflare or self._state.cloudflare,
                "transfers": transfers or self._state.transfers,
                "logs": logs if logs is not None else self._state.logs,
                "status_message": status_message if status_message is not None else self._state.status_message,
                "active_users_count": (
                    self._state.active_users_count if active_users_count is _UNSET else active_users_count
                ),
                "qr_target_url": self._state.qr_target_url if qr_target_url is _UNSET else qr_target_url,
                "updated_at": time.time(),
            }
            self._state = OperatorState(**data)
            return self._state

    def set_status(self, message: str) -> OperatorState:
        with self._lock:
            self._state = replace(self._state, status_message=message, updated_at=time.time())
            return self._state
