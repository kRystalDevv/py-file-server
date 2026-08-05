from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import RichLog, Static


class LogsScreen(Screen):
    """Displays rolling application logs."""

    def __init__(self) -> None:
        super().__init__()
        self._cursor = 0

    def compose(self) -> ComposeResult:
        yield Static("Recent application logs", id="logs-summary")
        yield RichLog(id="logs-pane", wrap=True, highlight=False, markup=False, auto_scroll=True)

    def on_show(self) -> None:
        self.refresh_view(force=True)

    def refresh_view(self, *, force: bool = False) -> None:
        state = self.app.state_store.snapshot()
        lines = state.logs
        pane = self.query_one("#logs-pane", RichLog)

        if force or self._cursor > len(lines):
            pane.clear()
            self._cursor = 0

        for line in lines[self._cursor :]:
            pane.write(line)
            self._cursor += 1

        self.query_one("#logs-summary", Static).update(
            f"Recent application logs | showing {min(len(lines), 250)} buffered lines"
        )
