from __future__ import annotations

import ctypes
import os
import shutil
import sys
import threading
import time
from pathlib import Path


def human_readable_bytes(num: float, suffix: str = "B") -> str:
    for unit in ("", "K", "M", "G", "T", "P"):
        if abs(num) < 1024.0:
            return f"{num:.2f} {unit}{suffix}"
        num /= 1024.0
    return f"{num:.2f} Y{suffix}"


class TransferMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active: dict[str, dict[str, float | str]] = {}
        self.total_uploaded = 0

    def start(self, key: str, filename: str) -> None:
        with self._lock:
            self.active[key] = {"filename": filename, "bytes": 0.0, "start": time.time()}

    def update(self, key: str, byte_count: int) -> None:
        with self._lock:
            if key in self.active:
                self.active[key]["bytes"] = float(self.active[key]["bytes"]) + byte_count
            self.total_uploaded += byte_count

    def stop(self, key: str) -> None:
        with self._lock:
            self.active.pop(key, None)

    def snapshot(self) -> tuple[list[dict[str, float | str]], int]:
        with self._lock:
            rows = [dict(item) for item in self.active.values()]
            return rows, self.total_uploaded


def start_console_monitor(
    metrics: TransferMetrics,
    *,
    log_file: Path,
    tunnel_url_getter,
    interval: float = 1.0,
    tail_lines: int = 10,
    stop_event: threading.Event | None = None,
    status_getter=None,
    controls: list[str] | None = None,
    pause_event: threading.Event | None = None,
) -> threading.Thread:
    event = stop_event or threading.Event()
    paused = pause_event or threading.Event()
    use_color = _enable_ansi_if_supported()
    max_rows = 8
    log_rows = max(3, min(tail_lines, 8))

    def _run() -> None:
        first_frame = True
        while not event.is_set():
            if paused.is_set():
                event.wait(0.2)
                continue
            rows, total_uploaded = metrics.snapshot()
            total_speed = 0.0
            lines: list[str] = []
            width = max(72, shutil.get_terminal_size(fallback=(100, 30)).columns)
            ruler = "=" * width
            divider = "-" * width

            if first_frame:
                lines.append("\n")
                first_frame = False
            lines.append(_paint(ruler, "cyan", use_color))
            lines.append(_paint(" 63xky File Server Monitor", "bold", use_color))
            lines.append(_paint(ruler, "cyan", use_color))
            tunnel_value = tunnel_url_getter() or "disabled/not-ready"
            lines.append(_fit_line(f" Tunnel: {_paint(tunnel_value, 'green' if 'https://' in tunnel_value else 'yellow', use_color)}", width))
            if status_getter:
                status_text = status_getter() or "Ready"
                lines.append(_fit_line(f" Status: {_paint(status_text, 'magenta', use_color)}", width))
            lines.append("")
            lines.append(_paint(" Active Downloads", "blue", use_color))
            lines.append(divider)

            visible_rows = rows[:max_rows]
            if not visible_rows:
                lines.append("  (none)")

            for row in visible_rows:
                elapsed = max(time.time() - float(row["start"]), 0.001)
                speed = float(row["bytes"]) / elapsed
                total_speed += speed
                lines.append(_fit_line(
                    f"  {str(row['filename'])[:36]:36}  "
                    f"{human_readable_bytes(float(row['bytes'])):>10}  "
                    f"{human_readable_bytes(speed):>10}/s"
                , width))

            if len(rows) > max_rows:
                lines.append(_fit_line(f"  ... and {len(rows) - max_rows} more", width))

            lines.append(divider)
            lines.append(
                _fit_line(" "
                + _paint("Summary:", "magenta", use_color)
                + f" active={len(rows)} | speed={human_readable_bytes(total_speed)}/s | total={human_readable_bytes(total_uploaded)}"
                , width)
            )
            lines.append(divider)
            lines.append(_paint(" Recent logs", "blue", use_color))

            if log_file.exists():
                try:
                    tail = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-log_rows:]
                    for line in tail:
                        lines.append(_fit_line(f"  {line}", width))
                except Exception:
                    lines.append("  <log read failed>")
            else:
                lines.append("  <log file not created yet>")

            if controls:
                lines.append(divider)
                lines.append(_paint(" Controls", "blue", use_color))
                for ctl in controls:
                    lines.append(_fit_line(f"  {ctl}", width))

            frame = "\x1b[H\x1b[J" + "\n".join(lines)
            print(frame, end="", flush=True)
            event.wait(interval)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


def _enable_ansi_if_supported() -> bool:
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False
    if os.name != "nt":
        return True
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)) == 0:
            return False
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        if mode.value & ENABLE_VIRTUAL_TERMINAL_PROCESSING:
            return True
        return bool(kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING))
    except Exception:
        return False


def _paint(text: str, color: str, enabled: bool) -> str:
    if not enabled:
        return text
    colors = {
        "bold": "1",
        "blue": "34",
        "cyan": "36",
        "green": "32",
        "yellow": "33",
        "magenta": "35",
    }
    code = colors.get(color)
    if not code:
        return text
    return f"\x1b[{code}m{text}\x1b[0m"


def _fit_line(text: str, width: int) -> str:
    if width < 20:
        return text
    plain = _strip_ansi(text)
    if len(plain) <= width - 1:
        return text
    return plain[: width - 4] + "..."


def _strip_ansi(text: str) -> str:
    out = []
    in_esc = False
    for ch in text:
        if ch == "\x1b":
            in_esc = True
            continue
        if in_esc:
            if ch == "m":
                in_esc = False
            continue
        out.append(ch)
    return "".join(out)
