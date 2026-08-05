from __future__ import annotations

from textual.widgets import Static


class StatusBlock(Static):
    """Small helper widget for multiline status text."""

    def set_lines(self, lines: list[str]) -> None:
        self.update("\n".join(lines))
