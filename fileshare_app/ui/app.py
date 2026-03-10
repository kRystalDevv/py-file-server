from __future__ import annotations

import time
import webbrowser

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual import events
from textual.widgets import Button, DataTable, Input, Label, Markdown, RichLog, Select, Static, TabbedContent, TabPane

from ..core.config import Settings
from ..services.cloudflare_manager import CloudflareManager
from ..services.log_bridge import LogBridge
from ..services.qr_manager import QRManager
from ..services.server_manager import ServerManager
from ..services.transfer_store import TransferStore
from .screens import ConfirmShutdownScreen, QRFullscreenScreen
from .state import OperatorStateStore

try:
    import tkinter as tk  # type: ignore
    from tkinter import filedialog  # type: ignore
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    filedialog = None  # type: ignore


class OperatorConsoleApp(App[None]):
    TITLE = "63xky File Server Operator Console"
    CSS_PATH = "operator_console.tcss"

    KEY_ACTIONS: list[tuple[str, str, str, str]] = [
        ("dashboard", "show_dashboard", "Dashboard", "1"),
        ("transfers", "show_transfers", "Transfers", "2"),
        ("logs", "show_logs", "Logs", "3"),
        ("settings", "show_settings", "Settings", "4"),
        ("public", "show_public_access", "Public", "5"),
        ("qr", "toggle_qr", "QR", "q"),
        ("refresh", "refresh_current", "Refresh", "r"),
        ("public_flow", "public_mode_flow", "Public Flow", "p"),
        ("folder_picker", "pick_folder", "Pick Folder", "f"),
        ("shutdown", "shutdown_flow", "Shutdown", "x"),
        ("dismiss", "escape_action", "Dismiss", "escape"),
    ]

    def __init__(
        self,
        *,
        settings: Settings,
        server_manager: ServerManager,
        cloudflare_manager: CloudflareManager,
        transfer_store: TransferStore,
        log_bridge: LogBridge,
        qr_manager: QRManager,
    ) -> None:
        super().__init__()
        self.runtime_settings = settings
        self.server_manager = server_manager
        self.cloudflare_manager = cloudflare_manager
        self.transfer_store = transfer_store
        self.log_bridge = log_bridge
        self.qr_manager = qr_manager
        self.state_store = OperatorStateStore()
        self._services_shutdown = False
        self._log_cursor = 0
        self._active_keymap = {item[0]: item[3] for item in self.KEY_ACTIONS}
        self._qr_source_preference = "auto"
        self._qr_last_source = "auto"

    def compose(self) -> ComposeResult:
        yield Static("63xky File Server", id="header-strip")
        yield Static("Starting...", id="status-line")

        with TabbedContent(initial="dashboard", id="main-tabs"):
            with TabPane("Dashboard", id="dashboard"):
                with Vertical(classes="pane-body"):
                    with Horizontal(classes="card-row"):
                        with Vertical(id="dash-server", classes="card"):
                            yield Static("Server", classes="card-title")
                            yield Static("", classes="card-body")
                        with Vertical(id="dash-local", classes="card"):
                            yield Static("Local Access", classes="card-title")
                            yield Static("", classes="card-body")
                        with Vertical(id="dash-public", classes="card"):
                            yield Static("Public Access", classes="card-title")
                            yield Static("", classes="card-body")
                    with Horizontal(classes="card-row"):
                        with Vertical(id="dash-transfers", classes="card"):
                            yield Static("Transfers", classes="card-title")
                            yield Static("", classes="card-body")
                        with Vertical(id="dash-activity", classes="card"):
                            yield Static("Activity", classes="card-title")
                            yield Static("", classes="card-body")
                        with Vertical(id="dash-health", classes="card"):
                            yield Static("Health", classes="card-title")
                            yield Static("", classes="card-body")
                    with Horizontal(id="dashboard-actions", classes="action-row"):
                        yield Button("LAN QR", id="btn-dashboard-qr-lan", variant="primary")
                        yield Button("Public QR", id="btn-dashboard-qr-public")
                        yield Button("Open URL", id="btn-open-url")
                        yield Button("Refresh", id="btn-dashboard-refresh")
                        yield Button("Start/Stop Public", id="btn-dashboard-public")
                        yield Button("Pick Folder", id="btn-dashboard-folder")
                        yield Button("Shutdown", id="btn-dashboard-shutdown", variant="error")

            with TabPane("Transfers", id="transfers"):
                with Vertical(classes="pane-body"):
                    yield Static("", id="transfers-summary", classes="summary")
                    with Horizontal(classes="table-row"):
                        with Vertical(classes="table-card"):
                            yield Static("Active Transfers", classes="card-title")
                            yield DataTable(id="transfers-active")
                        with Vertical(classes="table-card"):
                            yield Static("Recent Transfers", classes="card-title")
                            yield DataTable(id="transfers-recent")

            with TabPane("Logs", id="logs"):
                with Vertical(classes="pane-body"):
                    with Horizontal(classes="action-row"):
                        yield Button("Refresh", id="btn-logs-refresh")
                        yield Button("Clear View", id="btn-logs-clear")
                    yield Static("", id="logs-summary", classes="summary")
                    yield RichLog(id="logs-pane", wrap=True, highlight=False, markup=False, auto_scroll=True)

            with TabPane("Settings", id="settings"):
                with Vertical(classes="pane-body"):
                    yield Static("Edit server/runtime settings", classes="summary")
                    with Horizontal(classes="settings-row"):
                        with Vertical(classes="table-card"):
                            yield Static("Server", classes="card-title")
                            yield Label("Shared folder")
                            yield Input(placeholder="Shared folder path", id="setting-share-path")
                            yield Label("Port")
                            yield Input(placeholder="Port (1-65535 or 0)", id="setting-port")
                            with Horizontal(classes="action-row"):
                                yield Button("Browse Folder", id="btn-settings-browse")
                                yield Button("Apply Server", id="btn-settings-apply-server", variant="primary")
                            yield Static("", id="settings-runtime-note", classes="summary")
                        with Vertical(classes="table-card"):
                            yield Static("QR", classes="card-title")
                            yield Label("Default QR source")
                            yield Select(
                                options=[("Auto", "auto"), ("LAN", "lan"), ("Public", "public")],
                                value="auto",
                                id="setting-qr-source",
                            )
                            with Horizontal(classes="action-row"):
                                yield Button("Show LAN QR", id="btn-settings-qr-lan")
                                yield Button("Show Public QR", id="btn-settings-qr-public")
                    with Vertical(classes="table-card"):
                        yield Static("Key Bindings", classes="card-title")
                        with Horizontal(classes="settings-row"):
                            with Vertical(classes="key-col"):
                                yield Label("Dashboard")
                                yield Input(value="1", id="key-dashboard")
                                yield Label("Transfers")
                                yield Input(value="2", id="key-transfers")
                                yield Label("Logs")
                                yield Input(value="3", id="key-logs")
                                yield Label("Settings")
                                yield Input(value="4", id="key-settings")
                            with Vertical(classes="key-col"):
                                yield Label("Public")
                                yield Input(value="5", id="key-public")
                                yield Label("QR")
                                yield Input(value="q", id="key-qr")
                                yield Label("Refresh")
                                yield Input(value="r", id="key-refresh")
                                yield Label("Public Flow")
                                yield Input(value="p", id="key-public_flow")
                            with Vertical(classes="key-col"):
                                yield Label("Folder Picker")
                                yield Input(value="f", id="key-folder_picker")
                                yield Label("Shutdown")
                                yield Input(value="x", id="key-shutdown")
                                yield Label("Dismiss")
                                yield Input(value="escape", id="key-dismiss")
                        with Horizontal(classes="action-row"):
                            yield Button("Apply Keys", id="btn-settings-apply-keys", variant="primary")
                            yield Button("Reset Keys", id="btn-settings-reset-keys")

            with TabPane("Public Access", id="public"):
                with Vertical(classes="pane-body"):
                    with Horizontal(classes="card-row"):
                        with Vertical(id="public-status", classes="card"):
                            yield Static("Tunnel Status", classes="card-title")
                            yield Static("", classes="card-body")
                        with Vertical(id="public-runtime", classes="card"):
                            yield Static("Runtime", classes="card-title")
                            yield Static("", classes="card-body")
                    with Horizontal(classes="action-row"):
                        yield Button("Start Public", id="btn-public-toggle", variant="primary")
                        yield Button("Refresh", id="btn-public-refresh")
                        yield Button("LAN QR", id="btn-public-qr-lan")
                        yield Button("Public QR", id="btn-public-qr-public")
                        yield Button("Open Public URL", id="btn-public-open")
                    yield Markdown("", id="public-hints")

        yield Static("", id="key-footer")

    def on_mount(self) -> None:
        self._ensure_tables()
        self.log_bridge.attach()
        self._boot_services()
        self._load_settings_form_from_runtime()
        self._sync_key_inputs()
        self._update_key_footer()
        self.set_interval(1.0, self._refresh_tick)

    def on_unmount(self) -> None:
        self.shutdown_services()

    def shutdown_services(self) -> None:
        if self._services_shutdown:
            return
        self.cloudflare_manager.stop_public_mode()
        self.server_manager.stop()
        self.log_bridge.detach()
        self._services_shutdown = True

    def _boot_services(self) -> None:
        try:
            server = self.server_manager.start()
            cloudflare = self.cloudflare_manager.detect()
            if self.runtime_settings.tunnel_enabled and server.bind_port > 0:
                cloudflare = self.cloudflare_manager.start_public_mode(port=server.bind_port)
            self.state_store.update(
                server=server,
                cloudflare=cloudflare,
                transfers=self.transfer_store.refresh(),
                logs=self.log_bridge.snapshot(limit=250),
                qr_target_url=self._resolve_qr_target(cloudflare.public_url, server.local_urls, preferred=self._qr_source_preference),
                status_message="Server ready",
            )
            self._refresh_visible_screen(force=True)
        except Exception as exc:
            self.state_store.set_status(f"Startup failed: {exc}")
            self._update_status_line()

    def _refresh_tick(self) -> None:
        self._refresh_state()
        self._refresh_visible_screen()

    def _refresh_state(self) -> None:
        server = self.server_manager.snapshot()
        cloudflare = self.cloudflare_manager.refresh()
        self.state_store.update(
            server=server,
            cloudflare=cloudflare,
            transfers=self.transfer_store.refresh(),
            logs=self.log_bridge.snapshot(limit=250),
            qr_target_url=self._resolve_qr_target(cloudflare.public_url, server.local_urls, preferred=self._qr_source_preference),
        )
        self._update_status_line()

    def _refresh_visible_screen(self, force: bool = False, *_args) -> None:
        self._update_status_line()
        self._refresh_dashboard()
        self._refresh_transfers()
        self._refresh_logs(force=force)
        self._refresh_settings_runtime_only()
        self._refresh_public_access()

    def _refresh_dashboard(self) -> None:
        state = self.state_store.snapshot()
        server = state.server
        cf = state.cloudflare
        self.query_one("#dash-server .card-body", Static).update(
            f"State: {'Running' if server.running else 'Stopped'}\nBind: {server.bind_host}:{server.bind_port}\nBrowse: {server.browser_url}"
        )
        self.query_one("#dash-local .card-body", Static).update("\n".join(server.local_urls or ["No local URL available"]))
        self.query_one("#dash-public .card-body", Static).update(f"State: {cf.state.value}\nURL: {cf.public_url or 'Not active'}")
        self.query_one("#dash-transfers .card-body", Static).update(
            f"Active: {len(state.transfers.active)}\nRecent: {len(state.transfers.recent)}\nTotal sent: {self._human_bytes(state.transfers.total_uploaded)}"
        )
        self.query_one("#dash-activity .card-body", Static).update(
            f"Active users: {state.active_users_count if state.active_users_count is not None else 'n/a'}\nShare dir: {server.share_dir}"
        )
        self.query_one("#dash-health .card-body", Static).update(
            f"Status: {state.status_message}\nUpdated: {self._time_ago_label(state.updated_at)}"
        )

    def _refresh_transfers(self) -> None:
        state = self.state_store.snapshot()
        snapshot = state.transfers
        self.query_one("#transfers-summary", Static).update(
            f"Active {len(snapshot.active)}  |  Recent {len(snapshot.recent)}  |  Total {self._human_bytes(snapshot.total_uploaded)}"
        )
        active_table = self.query_one("#transfers-active", DataTable)
        active_table.clear()
        if snapshot.active:
            for row in snapshot.active:
                active_table.add_row(row.filename, self._human_bytes(row.bytes_sent), f"{self._human_bytes(row.rate_bps)}/s", f"{row.elapsed_seconds:.1f}s")
        else:
            active_table.add_row(*self._placeholder_row(active_table, "No active transfers"))
        recent_table = self.query_one("#transfers-recent", DataTable)
        recent_table.clear()
        if snapshot.recent:
            for row in snapshot.recent[:20]:
                recent_table.add_row(row.filename, self._human_bytes(row.bytes_sent), self._format_timestamp(row.completed_at))
        else:
            recent_table.add_row(*self._placeholder_row(recent_table, "No recent transfers"))

    def _refresh_logs(self, *, force: bool = False) -> None:
        state = self.state_store.snapshot()
        pane = self.query_one("#logs-pane", RichLog)
        lines = state.logs
        if force or self._log_cursor > len(lines):
            pane.clear()
            self._log_cursor = 0
        for line in lines[self._log_cursor :]:
            pane.write(line)
            self._log_cursor += 1
        self.query_one("#logs-summary", Static).update(f"Showing {min(len(lines), 250)} buffered lines")

    def _refresh_settings_runtime_only(self) -> None:
        state = self.state_store.snapshot()
        server = state.server
        self.query_one("#settings-runtime-note", Static).update(
            " | ".join(
                [
                    f"Current bind: {server.bind_host}:{server.bind_port}",
                    f"Cloudflare: {state.cloudflare.state.value}",
                    f"Share: {server.share_dir}",
                    "Tip: while typing in inputs, use Ctrl+<shortcut> for global actions",
                ]
            )
        )

    def _refresh_public_access(self) -> None:
        state = self.state_store.snapshot()
        cf = state.cloudflare
        self.query_one("#public-status .card-body", Static).update(
            f"State: {cf.state.value}\nInstalled: {'Yes' if cf.installed else 'No'}\nConfigured: {'Yes' if cf.configured else 'No'}\nVersion: {cf.version or 'Unknown'}"
        )
        self.query_one("#public-runtime .card-body", Static).update(
            f"Tunnel URL: {cf.public_url or 'Not active'}\nBinary: {cf.binary_path or 'Not found'}\n{cf.message}"
        )
        hints: list[str] = []
        if not cf.installed:
            hints.append("### Install required")
            hints.extend([f"- {item}" for item in self.cloudflare_manager.install_instructions()])
        elif not cf.configured:
            hints.append("### Setup required")
            hints.extend([f"- {item}" for item in self.cloudflare_manager.setup_instructions()])
        elif cf.quick_tunnel_warning:
            hints.append(f"> {cf.quick_tunnel_warning}")
        else:
            hints.append("Public access is ready. Use Start Public to bring tunnel online.")
        self.query_one("#public-hints", Markdown).update("\n".join(hints))
        toggle = self.query_one("#btn-public-toggle", Button)
        toggle.label = "Stop Public" if cf.running else "Start Public"
        toggle.variant = "warning" if cf.running else "primary"
        public_available = bool(cf.public_url)
        self.query_one("#btn-public-open", Button).disabled = not public_available
        self.query_one("#btn-dashboard-qr-public", Button).disabled = not public_available
        self.query_one("#btn-public-qr-public", Button).disabled = not public_available

    def _ensure_tables(self) -> None:
        active = self.query_one("#transfers-active", DataTable)
        if not active.columns:
            active.add_columns("Filename", "Sent", "Rate", "Elapsed")
        recent = self.query_one("#transfers-recent", DataTable)
        if not recent.columns:
            recent.add_columns("Filename", "Sent", "Completed")

    def _placeholder_row(self, table: DataTable, label: str) -> tuple[str, ...]:
        count = len(table.columns)
        return (label,) if count <= 1 else tuple([label, *["-"] * (count - 1)])

    def _load_settings_form_from_runtime(self) -> None:
        state = self.state_store.snapshot()
        self.query_one("#setting-share-path", Input).value = state.server.share_dir
        self.query_one("#setting-port", Input).value = str(state.server.bind_port)
        self.query_one("#setting-qr-source", Select).value = self._qr_source_preference

    def _sync_key_inputs(self) -> None:
        for action_id, _, _, default in self.KEY_ACTIONS:
            self.query_one(f"#key-{action_id}", Input).value = self._active_keymap.get(action_id, default)

    def _apply_server_settings(self) -> None:
        path_value = self.query_one("#setting-share-path", Input).value.strip().strip('"')
        port_text = self.query_one("#setting-port", Input).value.strip()
        if not path_value:
            self.state_store.set_status("Shared folder path cannot be empty")
            return
        try:
            self.server_manager.set_share_directory(path_value)
        except Exception as exc:
            self.state_store.set_status(f"Folder update failed: {exc}")
            return
        current_port = self.server_manager.snapshot().bind_port
        requested_port = current_port
        if port_text:
            try:
                requested_port = int(port_text)
            except ValueError:
                self.state_store.set_status("Port must be an integer")
                return
        was_public = self.state_store.snapshot().cloudflare.running
        if requested_port != current_port:
            try:
                snap = self.server_manager.restart_on_port(requested_port)
                if was_public:
                    self.cloudflare_manager.stop_public_mode()
                    self.state_store.update(cloudflare=self.cloudflare_manager.start_public_mode(port=snap.bind_port))
            except Exception as exc:
                self.state_store.set_status(f"Port update failed: {exc}")
                return
        self.state_store.set_status("Server settings applied")

    def _apply_keymap(self) -> None:
        updated: dict[str, str] = {}
        seen: set[str] = set()
        for action_id, _, _, _ in self.KEY_ACTIONS:
            key = self.query_one(f"#key-{action_id}", Input).value.strip().lower()
            if not key:
                self.state_store.set_status(f"Key for {action_id} cannot be empty")
                return
            if key in seen:
                self.state_store.set_status(f"Duplicate key: {key}")
                return
            seen.add(key)
            updated[action_id] = key
        self._active_keymap = updated
        self._update_key_footer()
        self.state_store.set_status("Key bindings updated")

    def _reset_keymap(self) -> None:
        self._active_keymap = {item[0]: item[3] for item in self.KEY_ACTIONS}
        self._sync_key_inputs()
        self._update_key_footer()
        self.state_store.set_status("Key bindings reset")

    def _update_key_footer(self) -> None:
        labels = []
        for action_id, _, description, default in self.KEY_ACTIONS:
            labels.append(f"{self._active_keymap.get(action_id, default).upper()}: {description}")
        self.query_one("#key-footer", Static).update("   |   ".join(labels))

    def _update_status_line(self) -> None:
        state = self.state_store.snapshot()
        server = state.server
        cf = state.cloudflare
        public_text = cf.public_url if cf.running else cf.state.value
        self.query_one("#status-line", Static).update(
            f"{state.status_message}  |  {server.bind_host}:{server.bind_port}  |  Public: {public_text}  |  Active transfers: {len(state.transfers.active)}"
        )

    def _resolve_qr_target(self, public_url: str | None, local_urls: list[str], *, preferred: str = "auto") -> str | None:
        if preferred == "public":
            return public_url
        if preferred == "lan":
            return local_urls[0] if local_urls else None
        if public_url:
            return public_url
        return local_urls[0] if local_urls else None

    def _show_qr_for_source(self, source: str) -> None:
        state = self.state_store.snapshot()
        url = self._resolve_qr_target(state.cloudflare.public_url, state.server.local_urls, preferred=source)
        if source == "public" and not url:
            self.state_store.set_status("Public URL is not available yet")
            self._refresh_visible_screen()
        self._qr_last_source = source
        self.push_screen(QRFullscreenScreen(url=url, qr_manager=self.qr_manager, timeout_seconds=15))

    def _open_primary_url(self) -> None:
        state = self.state_store.snapshot()
        url = state.cloudflare.public_url or state.server.browser_url
        try:
            webbrowser.open(url)
            self.state_store.set_status(f"Opened {url}")
        except Exception as exc:
            self.state_store.set_status(f"Browser open failed: {exc}")
        self._refresh_visible_screen()

    def _set_active_tab(self, tab_id: str) -> None:
        self.query_one("#main-tabs", TabbedContent).active = tab_id

    def action_show_dashboard(self) -> None:
        self._set_active_tab("dashboard")

    def action_show_transfers(self) -> None:
        self._set_active_tab("transfers")

    def action_show_logs(self) -> None:
        self._set_active_tab("logs")

    def action_show_settings(self) -> None:
        self._set_active_tab("settings")

    def action_show_public_access(self) -> None:
        self._set_active_tab("public")

    def action_toggle_qr(self) -> None:
        if isinstance(self.screen, QRFullscreenScreen):
            self.pop_screen()
            return
        source = self._qr_last_source if self._qr_last_source in {"lan", "public"} else self._qr_source_preference
        if source not in {"lan", "public"}:
            source = "public" if self.state_store.snapshot().cloudflare.public_url else "lan"
        self._show_qr_for_source(source)

    def action_refresh_current(self) -> None:
        self._refresh_state()
        self._refresh_visible_screen(force=True)

    def action_public_mode_flow(self) -> None:
        state = self.state_store.snapshot()
        if state.cloudflare.running:
            self.state_store.update(cloudflare=self.cloudflare_manager.stop_public_mode(), status_message="Public mode stopped")
            self._refresh_visible_screen(force=True)
            return
        if not state.server.running:
            self.state_store.set_status("Cannot start public mode while server is stopped")
            self._refresh_visible_screen()
            return
        cf = self.cloudflare_manager.start_public_mode(port=state.server.bind_port)
        if cf.running:
            self.state_store.update(cloudflare=cf, status_message=f"Public mode active: {cf.public_url}")
        else:
            self.state_store.update(cloudflare=cf, status_message=cf.message)
            self._set_active_tab("public")
        self._refresh_visible_screen(force=True)

    def action_pick_folder(self) -> None:
        selected = self._pick_folder_path()
        if selected is None:
            self.state_store.set_status("Folder picker unavailable")
            return
        if not selected:
            self.state_store.set_status("Folder selection canceled")
            return
        self.query_one("#setting-share-path", Input).value = selected
        self.state_store.set_status(f"Selected folder: {selected}")
        self._set_active_tab("settings")
        self._refresh_visible_screen()

    def action_shutdown_flow(self) -> None:
        self.push_screen(ConfirmShutdownScreen(), self._on_shutdown_confirmed)

    def _on_shutdown_confirmed(self, confirmed: bool | None) -> None:
        if confirmed:
            self.shutdown_services()
            self.exit()
            return
        self.state_store.set_status("Shutdown canceled")
        self._refresh_visible_screen()

    def action_escape_action(self) -> None:
        if isinstance(self.screen, QRFullscreenScreen):
            self.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid in {"btn-dashboard-qr-lan", "btn-public-qr-lan", "btn-settings-qr-lan"}:
            self._show_qr_for_source("lan")
        elif bid in {"btn-dashboard-qr-public", "btn-public-qr-public", "btn-settings-qr-public"}:
            self._show_qr_for_source("public")
        elif bid in {"btn-dashboard-refresh", "btn-public-refresh", "btn-logs-refresh"}:
            self.action_refresh_current()
        elif bid in {"btn-dashboard-public", "btn-public-toggle"}:
            self.action_public_mode_flow()
        elif bid in {"btn-dashboard-folder", "btn-settings-browse"}:
            self.action_pick_folder()
        elif bid == "btn-settings-apply-server":
            self._apply_server_settings()
            self.action_refresh_current()
        elif bid == "btn-settings-apply-keys":
            self._apply_keymap()
        elif bid == "btn-settings-reset-keys":
            self._reset_keymap()
        elif bid == "btn-dashboard-shutdown":
            self.action_shutdown_flow()
        elif bid in {"btn-open-url", "btn-public-open"}:
            self._open_primary_url()
        elif bid == "btn-logs-clear":
            pane = self.query_one("#logs-pane", RichLog)
            pane.clear()
            self._log_cursor = len(self.state_store.snapshot().logs)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "setting-qr-source":
            value = str(event.value)
            if value in {"auto", "lan", "public"}:
                self._qr_source_preference = value
                self._qr_last_source = value
                self.state_store.set_status(f"Default QR source set: {value}")

    async def on_key(self, event: events.Key) -> None:
        if self._should_defer_to_focused_input(event):
            return
        action_lookup = {action_id: action for action_id, action, _, _ in self.KEY_ACTIONS}
        candidates = self._key_candidates(event)
        for action_id, key in self._active_keymap.items():
            if key in candidates:
                event.stop()
                await self.run_action(action_lookup[action_id])
                return

    def _should_defer_to_focused_input(self, event: events.Key) -> bool:
        if isinstance(self.screen, QRFullscreenScreen):
            return False
        focused = self.focused
        if not isinstance(focused, Input):
            return False
        if event.key == "escape":
            return False
        if event.key.startswith("ctrl+"):
            return False
        # Limit input capture to the visible Settings tab so hidden Inputs don't block shortcuts.
        try:
            active_tab = self.query_one("#main-tabs", TabbedContent).active
        except Exception:
            return False
        return active_tab == "settings"

    def _key_candidates(self, event: events.Key) -> set[str]:
        candidates: set[str] = set()
        key = event.key.lower()
        candidates.add(key)
        if "+" in key:
            candidates.add(key.rsplit("+", 1)[-1])
        if key.startswith("kp_") and len(key) > 3:
            candidates.add(key[3:])
        if len(key) == 1:
            candidates.add(key)
        char = (event.character or "").lower()
        if char:
            candidates.add(char)
        return candidates

    def _pick_folder_path(self) -> str | None:
        if tk is None or filedialog is None:
            return None
        root = None
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            selected = filedialog.askdirectory(mustexist=True, title="Choose shared folder")
            return selected.strip() if selected else ""
        except Exception:
            return None
        finally:
            if root is not None:
                try:
                    root.destroy()
                except Exception:
                    pass

    def _format_timestamp(self, ts: float | None) -> str:
        if not ts:
            return "-"
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))

    def _human_bytes(self, num: float) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if abs(num) < 1024.0:
                return f"{num:.2f} {unit}"
            num /= 1024.0
        return f"{num:.2f} PB"

    def _time_ago_label(self, ts: float) -> str:
        delta = max(0, int(time.time() - ts))
        if delta < 60:
            return f"{delta}s ago"
        if delta < 3600:
            return f"{delta // 60}m ago"
        return f"{delta // 3600}h ago"
