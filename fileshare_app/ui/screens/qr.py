from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Static

from ...services.qr_manager import QRManager


class QRFullscreenScreen(Screen):
    """Fullscreen QR screen that auto-closes after a short timeout."""
    BINDINGS = [
        Binding("escape", "dismiss", "Dismiss"),
    ]

    def __init__(self, *, url: str | None, qr_manager: QRManager, timeout_seconds: int = 15) -> None:
        super().__init__()
        self.url = url
        self.qr_manager = qr_manager
        self.timeout_seconds = timeout_seconds
        self._started_at = time.time()

    def compose(self) -> ComposeResult:
        yield Static(id="qr-body")

    def on_mount(self) -> None:
        self.set_interval(1.0, self._refresh_countdown)
        self._update_body()

    def _refresh_countdown(self) -> None:
        elapsed = int(time.time() - self._started_at)
        if elapsed >= self.timeout_seconds:
            if self.app.screen is self:
                self.app.pop_screen()
            return
        self._update_body()

    def _update_body(self) -> None:
        elapsed = max(0, int(time.time() - self._started_at))
        remaining = max(0, self.timeout_seconds - elapsed)

        if not self.url:
            qr_ascii = "No URL available for QR display."
            shown_url = "(no URL)"
        else:
            shown_url = self.url
            try:
                qr_ascii = self.qr_manager.render_ascii(self.url, target_width=max(48, self.size.width - 6))
            except Exception as exc:
                qr_ascii = f"QR generation failed: {exc}"

        lines = [
            "[b]QR Fullscreen[/b]",
            "",
            shown_url,
            "",
            qr_ascii,
            "",
            f"Closing in {remaining}s. Press Q again or Esc to return now.",
        ]
        self.query_one("#qr-body", Static).update("\n".join(lines))

    def action_dismiss(self) -> None:
        if self.app.screen is self:
            self.app.pop_screen()
