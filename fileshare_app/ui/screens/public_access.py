from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static


class PublicAccessScreen(Screen):
    """Cloudflare/public access status and operator actions."""

    def compose(self) -> ComposeResult:
        yield Static(id="public-body")

    def on_show(self) -> None:
        self.refresh_view()

    def refresh_view(self) -> None:
        state = self.app.state_store.snapshot()
        cf = state.cloudflare
        manager = self.app.cloudflare_manager

        lines = [
            "[b]Public Access[/b]",
            "",
            f"Cloudflared installed: {'yes' if cf.installed else 'no'}",
            f"Cloudflared configured: {'yes' if cf.configured else 'no'}",
            f"State: {cf.state.value}",
            f"Version: {cf.version or 'unknown'}",
            f"Binary: {cf.binary_path or 'not found'}",
            f"Tunnel URL: {cf.public_url or 'not running'}",
            "",
            f"Status: {cf.message}",
        ]
        if cf.quick_tunnel_warning:
            lines.extend(["", f"Note: {cf.quick_tunnel_warning}"])

        lines.extend(["", "[b]Actions[/b]", "p Start/stop public mode flow", "r Refresh status", "1-5 Navigate screens"])

        if not cf.installed:
            lines.extend(["", "[b]Install hints[/b]"])
            lines.extend(f"- {item}" for item in manager.install_instructions())
        elif not cf.configured:
            lines.extend(["", "[b]Setup hints[/b]"])
            lines.extend(f"- {item}" for item in manager.setup_instructions())

        self.query_one("#public-body", Static).update("\n".join(lines))
