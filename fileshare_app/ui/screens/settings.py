from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Static


class SettingsScreen(Screen):
    """Runtime settings and extension placeholders."""

    def compose(self) -> ComposeResult:
        yield Static(id="settings-body")

    def on_show(self) -> None:
        self.refresh_view()

    def refresh_view(self) -> None:
        state = self.app.state_store.snapshot()
        server = state.server
        settings = self.app.runtime_settings

        lines = [
            "[b]Settings[/b]",
            "",
            "[b]Runtime[/b]",
            f"Mode: {settings.mode}",
            f"Host: {settings.host}",
            f"Port: {server.bind_port}",
            f"Shared directory: {server.share_dir}",
            f"Subdirectory traversal: {'enabled' if server.allow_subdirectories else 'disabled'}",
            f"Request log verbosity: {server.log_verbosity}",
            f"Open browser on start: {settings.open_browser}",
            f"Monitor enabled: {settings.monitor_enabled}",
            f"Admin routes enabled: {settings.admin_routes_enabled}",
            f"Threads: {settings.waitress_threads}",
            f"Max downloads: {settings.max_concurrent_downloads}",
            "",
            "[b]Public Mode[/b]",
            f"Tunnel configured in settings: {settings.tunnel_enabled}",
            f"Cloudflared state: {state.cloudflare.state.value}",
            "",
            "[b]QR Preferences[/b]",
            "QR target priority: public URL first, otherwise local/LAN URL",
            "Fullscreen timeout: 15s",
            "",
            "[b]Future Placeholders[/b]",
            "- Per-operator profile presets",
            "- Named tunnel profile picker",
        ]
        self.query_one("#settings-body", Static).update("\n".join(lines))
