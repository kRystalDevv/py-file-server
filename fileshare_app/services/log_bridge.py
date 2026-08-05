from __future__ import annotations

from collections import deque
import logging
import threading


class _RollingHandler(logging.Handler):
    def __init__(self, *, max_lines: int) -> None:
        super().__init__()
        self._lines = deque(maxlen=max_lines)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
        except Exception:
            line = record.getMessage()
        with self._lock:
            self._lines.append(line)

    def snapshot(self, limit: int | None = None) -> list[str]:
        with self._lock:
            if limit is None:
                return list(self._lines)
            return list(self._lines)[-limit:]


class LogBridge:
    """Connects Python logging to UI-friendly rolling log snapshots."""

    def __init__(self, *, max_lines: int = 500) -> None:
        self._handler = _RollingHandler(max_lines=max_lines)
        self._handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s",
                "%H:%M:%S",
            )
        )
        self._attached = False

    def attach(self) -> None:
        if self._attached:
            return
        root = logging.getLogger()
        root.addHandler(self._handler)
        self._attached = True

    def detach(self) -> None:
        if not self._attached:
            return
        root = logging.getLogger()
        root.removeHandler(self._handler)
        self._attached = False

    def snapshot(self, *, limit: int | None = None) -> list[str]:
        return self._handler.snapshot(limit=limit)
