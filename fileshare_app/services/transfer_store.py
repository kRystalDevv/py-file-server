from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import threading
import time

from ..core.metrics import TransferMetrics


@dataclass(frozen=True)
class TransferRecord:
    filename: str
    bytes_sent: int
    elapsed_seconds: float
    rate_bps: float
    started_at: float
    completed_at: float | None = None


@dataclass(frozen=True)
class TransferSnapshot:
    active: list[TransferRecord]
    recent: list[TransferRecord]
    total_uploaded: int


class TransferStore:
    """Turns low-level transfer metrics into active and recent transfer snapshots."""

    def __init__(self, metrics: TransferMetrics, *, max_recent: int = 30) -> None:
        self._metrics = metrics
        self._lock = threading.Lock()
        self._active_index: dict[str, TransferRecord] = {}
        self._recent = deque(maxlen=max_recent)
        self._last_total = 0

    def refresh(self) -> TransferSnapshot:
        rows, total_uploaded = self._metrics.snapshot()
        now = time.time()
        current: dict[str, TransferRecord] = {}

        for row in rows:
            filename = str(row.get("filename", "unknown"))
            started = float(row.get("start", now))
            bytes_sent = int(float(row.get("bytes", 0.0)))
            elapsed = max(now - started, 0.001)
            key = f"{filename}|{started}"
            current[key] = TransferRecord(
                filename=filename,
                bytes_sent=bytes_sent,
                elapsed_seconds=elapsed,
                rate_bps=bytes_sent / elapsed,
                started_at=started,
            )

        with self._lock:
            finished = [key for key in self._active_index if key not in current]
            for key in finished:
                done = self._active_index[key]
                self._recent.appendleft(
                    TransferRecord(
                        filename=done.filename,
                        bytes_sent=done.bytes_sent,
                        elapsed_seconds=done.elapsed_seconds,
                        rate_bps=done.rate_bps,
                        started_at=done.started_at,
                        completed_at=now,
                    )
                )
            self._active_index = current
            self._last_total = total_uploaded
            return TransferSnapshot(
                active=sorted(current.values(), key=lambda item: item.started_at, reverse=True),
                recent=list(self._recent),
                total_uploaded=total_uploaded,
            )

    def snapshot(self) -> TransferSnapshot:
        with self._lock:
            return TransferSnapshot(
                active=sorted(self._active_index.values(), key=lambda item: item.started_at, reverse=True),
                recent=list(self._recent),
                total_uploaded=self._last_total,
            )
