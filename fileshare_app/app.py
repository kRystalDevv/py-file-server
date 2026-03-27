from __future__ import annotations

import atexit
from dataclasses import dataclass
import ipaddress
import logging
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from waitress import create_server

from .cli import namespace_to_overrides, parse_args
from .core.config import Settings, SettingsError, build_settings
from .core.logging_utils import configure_logging
from .core.metrics import TransferMetrics, start_console_monitor
from .core.security import BlacklistStore
from .services import CloudflareManager, LogBridge, QRManager, ServerManager, TransferStore


def _get_bundle_dir() -> Path:
    """Return the base directory for bundled resources (PyInstaller or source)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent

try:
    import msvcrt  # type: ignore
except Exception:  # pragma: no cover
    msvcrt = None  # type: ignore

try:
    import tkinter as tk  # type: ignore
    from tkinter import filedialog  # type: ignore
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    filedialog = None  # type: ignore

_GOODBYE_PANEL_PRINTED = False


@dataclass
class RuntimeBootstrap:
    args: object
    settings: Settings
    logger: logging.Logger
    metrics: TransferMetrics
    blacklist_store: BlacklistStore


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        settings = build_settings(
            namespace_to_overrides(args),
            config_path_override=args.config,
            persist_overrides=args.save,
        )
    except SettingsError as exc:
        print(f"[ERROR] Invalid configuration: {exc}")
        return 2

    console_level = logging.WARNING if settings.monitor_enabled else logging.INFO
    logger = configure_logging(settings.app_paths.log_file, console_level=console_level)
    logger.info("event=startup mode=%s host=%s configured_port=%s", settings.mode, settings.host, settings.port)
    logger.info("event=paths share_dir=%s settings=%s", settings.share_dir, settings.app_paths.settings_file)
    logger.info("event=paths log_file=%s", settings.app_paths.log_file)
    logger.info(
        "event=server_tuning threads=%s max_downloads=%s",
        settings.waitress_threads,
        settings.max_concurrent_downloads,
    )

    bootstrap = RuntimeBootstrap(
        args=args,
        settings=settings,
        logger=logger,
        metrics=TransferMetrics(),
        blacklist_store=BlacklistStore(settings.app_paths.blacklist_file),
    )

    if getattr(args, "tray", False):
        from .tray import run_tray
        return run_tray(bootstrap)

    if getattr(args, "legacy_cli", False) or getattr(args, "no_ui", False):
        return run_legacy_cli(bootstrap)
    return run_textual_ui(bootstrap)


def run_textual_ui(bootstrap: RuntimeBootstrap) -> int:
    settings = bootstrap.settings
    logger = bootstrap.logger

    try:
        from .ui.app import OperatorConsoleApp
    except Exception as exc:
        print("[WARN] Textual UI is unavailable, falling back to legacy CLI mode.")
        print("[INFO] Install UI deps with: pip install textual qrcode")
        logger.warning("event=textual_import_failed reason=%s fallback=legacy_cli", exc)
        return run_legacy_cli(bootstrap)

    server_manager, cloudflare_manager, transfer_store, log_bridge, qr_manager = _create_services(bootstrap)
    app = OperatorConsoleApp(
        settings=settings,
        server_manager=server_manager,
        cloudflare_manager=cloudflare_manager,
        transfer_store=transfer_store,
        log_bridge=log_bridge,
        qr_manager=qr_manager,
    )

    try:
        app.run()
        return 0
    except KeyboardInterrupt:
        logger.info("event=shutdown signal=keyboard_interrupt")
        return 0
    except Exception as exc:
        logger.error("event=textual_runtime_failed reason=%s", exc)
        print(f"[ERROR] Textual runtime failed: {exc}")
        return 1
    finally:
        try:
            app.shutdown_services()
        except Exception:
            pass
        logging.shutdown()
        _print_goodbye_panel_once()


def run_legacy_cli(bootstrap: RuntimeBootstrap) -> int:
    settings = bootstrap.settings
    logger = bootstrap.logger

    server_manager, cloudflare_manager, transfer_store, log_bridge, _ = _create_services(bootstrap)

    ui_pause_event = threading.Event()
    stop_event = threading.Event()
    status_line = {"value": "Ready"}

    def _set_status(message: str) -> None:
        status_line["value"] = message
        logger.info("event=ui_status msg=%s", message)

    controls = [
        "Q: quit",
        "P: change shared folder path",
        "T: toggle subdirectory traversal",
        "O: change port (restarts server)",
        "L: cycle request logs (no/basic/medium/full)",
    ]

    if settings.monitor_enabled:
        start_console_monitor(
            bootstrap.metrics,
            log_file=settings.app_paths.log_file,
            tunnel_url_getter=cloudflare_manager.get_public_url,
            interval=1.0,
            tail_lines=10,
            stop_event=stop_event,
            status_getter=lambda: status_line["value"],
            controls=controls,
            pause_event=ui_pause_event,
        )

    try:
        snapshot = server_manager.start()
    except Exception as exc:
        logger.error("event=server_start_failed reason=%s", exc)
        return 1

    cloudflare = cloudflare_manager.detect()
    if settings.tunnel_enabled:
        cloudflare = cloudflare_manager.start_public_mode(port=snapshot.bind_port)
        if cloudflare.public_url and not _wait_for_public_http_ok(cloudflare.public_url, timeout_seconds=25):
            logger.error("event=tunnel_unreachable url=%s", cloudflare.public_url)
            _set_status("Public URL is unreachable. Local/LAN mode continues.")
            cloudflare = cloudflare_manager.stop_public_mode()

    logger.info(
        "event=server_ready listen_url=%s browse_url=%s public_url=%s",
        snapshot.bind_url,
        snapshot.browser_url,
        cloudflare.public_url or "disabled",
    )

    _set_status(f"Serving {snapshot.browser_url}")
    if settings.open_browser:
        try:
            webbrowser.open(cloudflare.public_url or snapshot.browser_url)
        except Exception:
            logger.warning("event=browser_open_failed url=%s", cloudflare.public_url or snapshot.browser_url)

    atexit.register(cloudflare_manager.stop_public_mode)

    exit_code = 0
    try:
        while True:
            current = server_manager.snapshot()
            if current.server_error:
                logger.error("event=server_crashed error=%s", current.server_error)
                exit_code = 1
                break
            if not current.running:
                break

            transfer_store.refresh()
            action = _read_hotkey_nonblocking()
            if action:
                action = action.lower()
                if action == "q":
                    if _prompt_yes_no(ui_pause_event, "Quit server? [Y/N]: "):
                        _set_status("Shutting down...")
                        break
                    _set_status("Quit canceled.")
                elif action == "p":
                    new_path = _pick_folder_path()
                    if new_path is None:
                        new_path = _prompt_text(ui_pause_event, "Enter new shared folder path (blank cancels): ")
                    if not new_path:
                        _set_status("Path change canceled.")
                    else:
                        try:
                            updated = server_manager.set_share_directory(new_path)
                            _set_status(f"Shared path updated: {updated}")
                        except Exception as exc:
                            _set_status(f"Invalid path: {exc}")
                elif action == "t":
                    enabled = server_manager.toggle_subdirectories()
                    state = "enabled" if enabled else "disabled"
                    _set_status(f"Subdirectory traversal {state}.")
                elif action == "o":
                    new_port_text = _prompt_text(ui_pause_event, "Enter new port (1-65535, 0=auto, blank cancels): ")
                    if not new_port_text:
                        _set_status("Port change canceled.")
                    else:
                        try:
                            requested_port = int(new_port_text)
                            snapshot = server_manager.restart_on_port(requested_port)
                            cloudflare_manager.stop_public_mode()
                            if settings.tunnel_enabled:
                                cloudflare = cloudflare_manager.start_public_mode(port=snapshot.bind_port)
                            else:
                                cloudflare = cloudflare_manager.snapshot()

                            browse_url = cloudflare.public_url or snapshot.browser_url
                            try:
                                webbrowser.open(browse_url)
                            except Exception:
                                logger.warning("event=browser_open_failed url=%s", browse_url)
                            _set_status(f"Now serving {snapshot.browser_url}")
                        except Exception as exc:
                            _set_status(f"Port switch failed: {exc}")
                elif action == "l":
                    level = server_manager.cycle_log_verbosity()
                    _set_status(f"Request log verbosity: {level}")

            time.sleep(0.1)
    except KeyboardInterrupt:
        logger.info("event=shutdown signal=keyboard_interrupt")
        exit_code = 0
    finally:
        stop_event.set()
        cloudflare_manager.stop_public_mode()
        server_manager.stop()
        log_bridge.detach()
        logging.shutdown()

    return exit_code


def main() -> int:
    return run()


def _create_services(bootstrap: RuntimeBootstrap):
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
    return server_manager, cloudflare_manager, transfer_store, log_bridge, qr_manager


def _print_goodbye_panel_once() -> None:
    global _GOODBYE_PANEL_PRINTED
    if _GOODBYE_PANEL_PRINTED:
        return
    _GOODBYE_PANEL_PRINTED = True

    title = "Latest version and feedback"
    body_lines = [
        "Thanks for using py-file-server.",
        "",
        "For the latest version, visit:",
        "https://github.com/kRystalDevv/py-file-server",
        "",
        "You can also send bug reports, feature requests, or suggestions there.",
        "",
        "Thanks for trying py-file-server.",
    ]
    body = "\n".join(body_lines)

    try:
        from rich import box
        from rich.console import Console
        from rich.panel import Panel

        Console().print(
            Panel(
                body,
                title=title,
                border_style="cyan",
                box=box.ROUNDED,
                expand=False,
            )
        )
    except Exception:
        width = max(len(title), *(len(line) for line in body_lines))
        border = "+" + "-" * (width + 2) + "+"
        print(border)
        print(f"| {title.ljust(width)} |")
        print(border)
        for line in body_lines:
            print(f"| {line.ljust(width)} |")
        print(border)


def _start_waitress(app, *, host: str, port: int, threads: int):
    errors: list[Exception] = []
    server = create_server(
        app,
        host=host,
        port=port,
        threads=threads,
        connection_limit=max(100, threads * 12),
    )

    def _run() -> None:
        try:
            server.run()
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return server, thread, errors


def _stop_waitress(server, thread: threading.Thread) -> None:
    try:
        server.close()
    except Exception:
        pass
    thread.join(timeout=5)


def _read_hotkey_nonblocking() -> str | None:
    if msvcrt is None:
        return None
    if not msvcrt.kbhit():
        return None
    key = msvcrt.getwch()
    if key in ("\x00", "\xe0") and msvcrt.kbhit():
        msvcrt.getwch()
        return None
    return key


def _prompt_yes_no(pause_event: threading.Event, prompt: str) -> bool:
    pause_event.set()
    try:
        answer = input(f"\n{prompt}").strip().lower()
        return answer == "y"
    finally:
        pause_event.clear()


def _prompt_text(pause_event: threading.Event, prompt: str) -> str:
    pause_event.set()
    try:
        return input(f"\n{prompt}").strip().strip('"')
    finally:
        pause_event.clear()


def _pick_folder_path() -> str | None:
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


def _wait_for_local_listener(host: str, port: int, *, timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    check_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    while time.time() < deadline:
        try:
            with socket.create_connection((check_host, port), timeout=1.5):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def _wait_for_public_http_ok(url: str, *, timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status < 400:
                    return True
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                time.sleep(1)
                continue
        except Exception:
            time.sleep(1)
            continue
        time.sleep(1)
    return False


def _choose_browser_host(bind_host: str, mode: str) -> str:
    if bind_host in ("0.0.0.0", "::"):
        if mode == "local":
            return "127.0.0.1"
        detected = _detect_lan_ip()
        return detected or "127.0.0.1"
    if bind_host == "localhost":
        return "127.0.0.1"
    return bind_host


def _detect_lan_ip() -> str | None:
    candidates: list[str] = []

    for target in ("8.8.8.8", "1.1.1.1"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect((target, 80))
                candidates.append(sock.getsockname()[0])
        except OSError:
            pass

    try:
        hostname = socket.gethostname()
        for item in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM):
            addr = item[4][0]
            candidates.append(addr)
    except OSError:
        pass

    private_ip = None
    public_ip = None
    for addr in candidates:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if ip.is_loopback or ip.is_unspecified:
            continue
        if ip.version == 4 and ip.is_private and private_ip is None:
            private_ip = addr
        elif not ip.is_private and public_ip is None:
            public_ip = addr

    return private_ip or public_ip


if __name__ == "__main__":
    raise SystemExit(main())
