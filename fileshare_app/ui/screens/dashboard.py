from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static


class DashboardScreen(Screen):
    """Primary operations overview."""

    def compose(self) -> ComposeResult:
        yield Static(id="dashboard-body")

    def on_show(self) -> None:
        self.refresh_view()

    def refresh_view(self) -> None:
        state = self.app.state_store.snapshot()
        server = state.server
        cloudflare = state.cloudflare

        local_urls = "\n".join(f"  - {url}" for url in server.local_urls) if server.local_urls else "  - unavailable"
        public_url = cloudflare.public_url or "disabled"
        transfer_count = len(state.transfers.active)
        active_users = str(state.active_users_count) if state.active_users_count is not None else "n/a"

        lines = [
            "[b]Dashboard[/b]",
            "",
            f"Server: {'RUNNING' if server.running else 'STOPPED'}",
            f"Bind: {server.bind_host}:{server.bind_port}",
            f"Browse URL: {server.browser_url}",
            "Local/LAN URLs:",
            local_urls,
            f"Public tunnel: {cloudflare.state.value} ({public_url})",
            f"Active transfers: {transfer_count}",
            f"Active users: {active_users}",
            "",
            f"Status: {state.status_message}",
            "",
            "[b]Keys[/b]",
            "1 Dashboard | 2 Transfers | 3 Logs | 4 Settings | 5 Public Access",
            "q QR fullscreen | p Public mode flow | r Refresh | x Shutdown | Esc Close modal/QR",
        ]

        self.query_one("#dashboard-body", Static).update("\n".join(lines))
