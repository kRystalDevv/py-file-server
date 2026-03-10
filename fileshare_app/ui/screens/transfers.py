from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Static

from .base import format_timestamp, human_readable_bytes


class TransfersScreen(Screen):
    """Shows active and recent transfer activity."""

    ACTIVE_COLUMNS = ("Filename", "Sent", "Rate", "Elapsed")
    RECENT_COLUMNS = ("Filename", "Sent", "Completed")

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(id="transfers-summary")
            yield Static("Active Transfers", classes="section-title")
            yield DataTable(id="transfers-active")
            yield Static("Recent Transfers", classes="section-title")
            yield DataTable(id="transfers-recent")

    def on_mount(self) -> None:
        self._ensure_tables()
        self.refresh_view()

    def _ensure_tables(self) -> None:
        active = self.query_one("#transfers-active", DataTable)
        if not active.columns:
            active.add_columns(*self.ACTIVE_COLUMNS)
        active.cursor_type = "row"

        recent = self.query_one("#transfers-recent", DataTable)
        if not recent.columns:
            recent.add_columns(*self.RECENT_COLUMNS)
        recent.cursor_type = "row"

    def on_show(self) -> None:
        self.refresh_view()

    def refresh_view(self) -> None:
        self._ensure_tables()
        state = self.app.state_store.snapshot()
        snapshot = state.transfers
        summary = (
            f"Active: {len(snapshot.active)} | Recent: {len(snapshot.recent)} | "
            f"Total sent: {human_readable_bytes(snapshot.total_uploaded)}"
        )
        self.query_one("#transfers-summary", Static).update(summary)

        active_table = self.query_one("#transfers-active", DataTable)
        active_table.clear()
        if snapshot.active:
            for row in snapshot.active:
                active_table.add_row(
                    row.filename,
                    human_readable_bytes(row.bytes_sent),
                    f"{human_readable_bytes(row.rate_bps)}/s",
                    f"{row.elapsed_seconds:.1f}s",
                )
        else:
            active_table.add_row(*self._placeholder_row(active_table, "No active transfers"))

        recent_table = self.query_one("#transfers-recent", DataTable)
        recent_table.clear()
        if snapshot.recent:
            for row in snapshot.recent[:20]:
                recent_table.add_row(
                    row.filename,
                    human_readable_bytes(row.bytes_sent),
                    format_timestamp(row.completed_at),
                )
        else:
            recent_table.add_row(*self._placeholder_row(recent_table, "No recent transfers yet"))

    def _placeholder_row(self, table: DataTable, label: str) -> tuple[str, ...]:
        column_count = len(table.columns)
        if column_count <= 1:
            return (label,)
        return tuple([label, *["-"] * (column_count - 1)])
