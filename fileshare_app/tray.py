"""System tray mode: runs the file server headless with a pystray tray icon."""

from __future__ import annotations

import atexit
import logging
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    pystray = None  # type: ignore
    Image = None  # type: ignore
    ImageDraw = None  # type: ignore
    ImageFont = None  # type: ignore

try:
    import tkinter as tk  # type: ignore
    from tkinter import Label as TkLabel  # type: ignore
except Exception:  # pragma: no cover
    tk = None  # type: ignore

try:
    import winreg  # type: ignore
except ImportError:
    winreg = None  # type: ignore


def is_available() -> bool:
    """Return True if pystray and Pillow are importable."""
    return pystray is not None and Image is not None


def _create_icon_image(size: int = 64) -> "Image.Image":
    """Generate a simple tray icon with 'FS' text."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Draw a rounded-ish colored background
    draw.rounded_rectangle(
        [2, 2, size - 2, size - 2],
        radius=size // 6,
        fill=(41, 128, 185),
        outline=(52, 152, 219),
        width=2,
    )

    # Draw "FS" text centered
    try:
        font = ImageFont.truetype("arial.ttf", size // 3)
    except (OSError, IOError):
        font = ImageFont.load_default()

    text = "FS"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (size - text_w) // 2
    y = (size - text_h) // 2 - bbox[1]
    draw.text((x, y), text, fill="white", font=font)

    return image


def _load_icon_image() -> "Image.Image":
    """Load icon from assets/icon.ico or generate one."""
    icon_candidates = [
        Path(__file__).parent.parent / "assets" / "icon.ico",
        Path(getattr(sys, "_MEIPASS", "")) / "assets" / "icon.ico",
    ]
    for path in icon_candidates:
        if path.exists():
            try:
                return Image.open(path)
            except Exception:
                pass
    return _create_icon_image()


def _human_bytes(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0:
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} PB"


def _get_startup_registry_key() -> str:
    return r"Software\Microsoft\Windows\CurrentVersion\Run"


def _get_startup_value_name() -> str:
    return "63xkyFileServer"


def _is_startup_enabled() -> bool:
    """Check if the app is registered to start at login."""
    if winreg is None:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _get_startup_registry_key(), 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, _get_startup_value_name())
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except OSError:
        return False


def _set_startup_enabled(enabled: bool) -> bool:
    """Add or remove the app from Windows startup. Returns True on success."""
    if winreg is None:
        return False
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _get_startup_registry_key(),
            0,
            winreg.KEY_SET_VALUE,
        )
        try:
            if enabled:
                if getattr(sys, "frozen", False):
                    # Prefer FileServerTray.exe (console=False) when running as installed app
                    tray_exe = Path(sys.executable).parent / "FileServerTray.exe"
                    exe_path = str(tray_exe) if tray_exe.exists() else sys.executable
                    startup_value = f'"{exe_path}"'
                else:
                    exe_path = sys.executable
                    startup_value = f'"{exe_path}" --tray'
                winreg.SetValueEx(key, _get_startup_value_name(), 0, winreg.REG_SZ, startup_value)
            else:
                try:
                    winreg.DeleteValue(key, _get_startup_value_name())
                except FileNotFoundError:
                    pass
            return True
        finally:
            winreg.CloseKey(key)
    except OSError:
        return False


def _show_qr_popup(url: str, qr_manager) -> None:
    """Show a small Tkinter popup with the QR code."""
    if tk is None or not url:
        return

    try:
        import qrcode
        from io import BytesIO

        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        qr_image = qr.make_image(fill_color="black", back_color="white")

        root = tk.Tk()
        root.title("63xky FileServer - QR Code")
        root.resizable(False, False)
        root.attributes("-topmost", True)

        # Convert PIL image to Tkinter PhotoImage
        from PIL import ImageTk

        photo = ImageTk.PhotoImage(qr_image)
        label = TkLabel(root, image=photo)
        label.image = photo  # type: ignore[attr-defined]
        label.pack(padx=10, pady=5)

        url_label = TkLabel(root, text=url, fg="blue")
        url_label.pack(padx=10, pady=(0, 10))

        root.mainloop()
    except Exception:
        pass


class TrayApp:
    """Manages the system tray icon and its context menu."""

    def __init__(
        self,
        *,
        settings,
        server_manager,
        cloudflare_manager,
        transfer_store,
        log_bridge,
        qr_manager,
        logger: logging.Logger,
    ) -> None:
        self.settings = settings
        self.server_manager = server_manager
        self.cloudflare_manager = cloudflare_manager
        self.transfer_store = transfer_store
        self.log_bridge = log_bridge
        self.qr_manager = qr_manager
        self.logger = logger
        self._icon: pystray.Icon | None = None
        self._started_at = time.time()
        self._refresh_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def run(self) -> int:
        """Start the server and tray icon. Blocks until exit."""
        # Start the server
        try:
            snapshot = self.server_manager.start()
            self.logger.info("event=tray_server_started bind=%s:%s", snapshot.bind_host, snapshot.bind_port)
        except Exception as exc:
            self.logger.error("event=tray_server_start_failed reason=%s", exc)
            print(f"[ERROR] Server failed to start: {exc}")
            return 1

        # Start cloudflare tunnel if configured
        cloudflare = self.cloudflare_manager.detect()
        if self.settings.tunnel_enabled:
            cloudflare = self.cloudflare_manager.start_public_mode(port=snapshot.bind_port)

        atexit.register(self._cleanup)

        # Start periodic refresh thread
        self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._refresh_thread.start()

        # Open browser if configured
        if self.settings.open_browser:
            url = cloudflare.public_url or snapshot.browser_url
            try:
                webbrowser.open(url)
            except Exception:
                pass

        # Create and run tray icon
        icon_image = _load_icon_image()
        self._icon = pystray.Icon(
            name="63xky FileServer",
            icon=icon_image,
            title="63xky FileServer",
            menu=pystray.Menu(self._build_menu),
        )

        try:
            self._icon.run()
            return 0
        except KeyboardInterrupt:
            return 0
        finally:
            self._cleanup()

    def _build_menu(self) -> list:
        """Build the dynamic tray context menu."""
        server = self.server_manager.snapshot()
        cloudflare = self.cloudflare_manager.snapshot()
        transfers = self.transfer_store.refresh()

        # Uptime
        uptime_secs = int(time.time() - self._started_at)
        if uptime_secs < 60:
            uptime_str = f"{uptime_secs}s"
        elif uptime_secs < 3600:
            uptime_str = f"{uptime_secs // 60}m {uptime_secs % 60}s"
        else:
            uptime_str = f"{uptime_secs // 3600}h {(uptime_secs % 3600) // 60}m"

        # Server status submenu
        server_items = [
            pystray.MenuItem(f"Mode: {self.settings.mode}", None, enabled=False),
            pystray.MenuItem(f"Port: {server.bind_port}", None, enabled=False),
            pystray.MenuItem(f"URL: {server.browser_url}", None, enabled=False),
            pystray.MenuItem(f"Uptime: {uptime_str}", None, enabled=False),
            pystray.MenuItem(f"Share: {server.share_dir}", None, enabled=False),
        ]
        if cloudflare.public_url:
            server_items.append(pystray.MenuItem(f"Public: {cloudflare.public_url}", None, enabled=False))

        # Transfer info
        active_count = len(transfers.active)
        active_label = f"Active: {active_count} transfer{'s' if active_count != 1 else ''}"
        transfer_items = [
            pystray.MenuItem(active_label, None, enabled=False),
            pystray.MenuItem(f"Total sent: {_human_bytes(transfers.total_uploaded)}", None, enabled=False),
        ]
        for record in transfers.active[:5]:
            transfer_items.append(
                pystray.MenuItem(
                    f"  {record.filename} ({_human_bytes(record.bytes_sent)}, {_human_bytes(record.rate_bps)}/s)",
                    None,
                    enabled=False,
                )
            )

        # Startup toggle
        startup_enabled = _is_startup_enabled()
        startup_label = "Start at Login"

        menu_items = [
            pystray.MenuItem(
                "Server Status",
                pystray.Menu(*server_items),
            ),
            pystray.MenuItem(
                "Transfers",
                pystray.Menu(*transfer_items),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open in Browser", self._on_open_browser),
            pystray.MenuItem("Show QR Code", self._on_show_qr),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                startup_label,
                self._on_toggle_startup,
                checked=lambda _: _is_startup_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._on_exit),
        ]

        return menu_items

    def _on_open_browser(self, icon, item) -> None:
        cloudflare = self.cloudflare_manager.snapshot()
        server = self.server_manager.snapshot()
        url = cloudflare.public_url or server.browser_url
        try:
            webbrowser.open(url)
        except Exception as exc:
            self.logger.warning("event=tray_browser_failed reason=%s", exc)

    def _on_show_qr(self, icon, item) -> None:
        cloudflare = self.cloudflare_manager.snapshot()
        server = self.server_manager.snapshot()
        url = cloudflare.public_url or (server.local_urls[0] if server.local_urls else server.browser_url)
        # Run QR popup in a separate thread to avoid blocking pystray
        threading.Thread(target=_show_qr_popup, args=(url, self.qr_manager), daemon=True).start()

    def _on_toggle_startup(self, icon, item) -> None:
        current = _is_startup_enabled()
        success = _set_startup_enabled(not current)
        if not success:
            self.logger.warning("event=tray_startup_toggle_failed")

    def _on_exit(self, icon, item) -> None:
        self._stop_event.set()
        if self._icon:
            self._icon.stop()

    def _refresh_loop(self) -> None:
        """Periodically refresh transfer store in the background."""
        while not self._stop_event.wait(2.0):
            try:
                self.transfer_store.refresh()
            except Exception:
                pass

    def _cleanup(self) -> None:
        self._stop_event.set()
        try:
            self.cloudflare_manager.stop_public_mode()
        except Exception:
            pass
        try:
            self.server_manager.stop()
        except Exception:
            pass
        try:
            self.log_bridge.detach()
        except Exception:
            pass


def _ensure_detached() -> None:
    """On Windows, if attached to a console, re-launch as a detached process and exit parent.

    This ensures that closing the terminal that started ``--tray`` mode does not kill
    the tray icon.  The child process inherits the same sys.argv so it re-enters tray
    mode, but ``GetConsoleWindow()`` will return 0 for the detached child, so the
    function returns early and the tray starts normally.
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        if ctypes.windll.kernel32.GetConsoleWindow() == 0:
            return  # already detached (e.g. launched via FileServerTray.exe)
    except Exception:
        return

    # Re-launch this exact invocation as a detached Windows process.
    subprocess.Popen(
        [sys.executable] + sys.argv,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    sys.exit(0)


def run_tray(bootstrap) -> int:
    """Entry point for tray mode. Takes a RuntimeBootstrap from app.py."""
    _ensure_detached()

    if not is_available():
        print("[ERROR] System tray mode requires pystray and Pillow.")
        print("[INFO]  Install with: pip install pystray Pillow")
        return 2

    from .services import CloudflareManager, LogBridge, QRManager, ServerManager, TransferStore

    settings = bootstrap.settings
    logger = bootstrap.logger

    server_manager = ServerManager(
        settings,
        logger=logger,
        metrics=bootstrap.metrics,
        blacklist_store=bootstrap.blacklist_store,
    )
    known_tools = [
        settings.app_paths.app_dir / "tools",
        Path.cwd() / "tools",
    ]
    cloudflare_manager = CloudflareManager(logger, known_tool_dirs=known_tools)
    transfer_store = TransferStore(bootstrap.metrics)
    log_bridge = LogBridge(max_lines=500)
    qr_manager = QRManager()

    app = TrayApp(
        settings=settings,
        server_manager=server_manager,
        cloudflare_manager=cloudflare_manager,
        transfer_store=transfer_store,
        log_bridge=log_bridge,
        qr_manager=qr_manager,
        logger=logger,
    )

    return app.run()
