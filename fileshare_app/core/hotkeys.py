from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from typing import Iterator

try:
    import msvcrt  # type: ignore
except Exception:  # pragma: no cover - not available on POSIX
    msvcrt = None  # type: ignore

try:
    import termios
    import tty
    import select
except Exception:  # pragma: no cover - not available on Windows
    termios = None  # type: ignore
    tty = None  # type: ignore
    select = None  # type: ignore


class HotkeyReader:
    """Base/no-op hotkey reader used as a graceful fallback on unsupported platforms."""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def read_nonblocking(self) -> str | None:
        return None

    @contextmanager
    def suspended(self) -> Iterator[None]:
        yield

    def __enter__(self) -> "HotkeyReader":
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()


class WindowsHotkeyReader(HotkeyReader):
    """Non-blocking single-keypress reads via msvcrt (Windows console)."""

    def read_nonblocking(self) -> str | None:
        if msvcrt is None:
            return None
        if not msvcrt.kbhit():
            return None
        key = msvcrt.getwch()
        if key in ("\x00", "\xe0") and msvcrt.kbhit():
            msvcrt.getwch()
            return None
        return key


class PosixHotkeyReader(HotkeyReader):
    """Non-blocking single-keypress reads via termios/tty/select (Linux/macOS terminals)."""

    def __init__(self, stream=None) -> None:
        self._stream = stream if stream is not None else sys.stdin
        self._fd: int | None = None
        self._original_attrs = None
        self._active = False

    def _is_tty(self) -> bool:
        try:
            return os.isatty(self._stream.fileno())
        except Exception:
            return False

    def _supported(self) -> bool:
        return (
            termios is not None
            and tty is not None
            and select is not None
            and hasattr(self._stream, "fileno")
            and self._is_tty()
        )

    def start(self) -> None:
        if not self._supported():
            return
        try:
            fd = self._stream.fileno()
            original_attrs = termios.tcgetattr(fd)
            tty.setcbreak(fd)
        except Exception:
            self._fd = None
            self._original_attrs = None
            self._active = False
            return
        self._fd = fd
        self._original_attrs = original_attrs
        self._active = True

    def stop(self) -> None:
        if self._active and self._fd is not None and self._original_attrs is not None:
            try:
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._original_attrs)
            except Exception:
                pass
        self._active = False

    def read_nonblocking(self) -> str | None:
        if not self._active or self._fd is None:
            return None
        try:
            ready, _, _ = select.select([self._fd], [], [], 0)
        except Exception:
            return None
        if not ready:
            return None
        try:
            data = os.read(self._fd, 1)
        except Exception:
            return None
        if not data:
            return None
        char = data.decode("utf-8", errors="ignore")
        if not char:
            return None
        if char == "\x1b":
            self._drain_escape_sequence()
            return None
        return char

    def _drain_escape_sequence(self) -> None:
        try:
            while True:
                ready, _, _ = select.select([self._fd], [], [], 0)
                if not ready:
                    break
                if not os.read(self._fd, 1):
                    break
        except Exception:
            pass

    @contextmanager
    def suspended(self) -> Iterator[None]:
        if not self._active or self._fd is None or self._original_attrs is None:
            yield
            return
        try:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._original_attrs)
        except Exception:
            pass
        try:
            yield
        finally:
            try:
                tty.setcbreak(self._fd)
            except Exception:
                pass


def create_hotkey_reader() -> HotkeyReader:
    if os.name == "nt":
        return WindowsHotkeyReader()
    if os.name == "posix":
        return PosixHotkeyReader()
    return HotkeyReader()
