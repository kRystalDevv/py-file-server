from __future__ import annotations

import ipaddress
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

APP_DIR_NAME = "63xkyFileServer"
VALID_MODES = {"local", "lan", "public"}
VALID_TUNNEL_VALUES = {"on", "off", "auto"}


class SettingsError(ValueError):
    """Raised when runtime settings are invalid."""


@dataclass(frozen=True)
class AppPaths:
    app_dir: Path
    settings_file: Path
    log_file: Path
    blacklist_file: Path
    default_share_dir: Path


@dataclass
class Settings:
    mode: str
    host: str
    port: int
    share_dir: Path
    tunnel_enabled: bool
    open_browser: bool
    monitor_enabled: bool
    admin_routes_enabled: bool
    app_paths: AppPaths

    def validate(self) -> None:
        if self.mode not in VALID_MODES:
            raise SettingsError(f"Unsupported mode '{self.mode}'. Valid modes: local, lan, public.")

        validate_host(self.host)

        if not isinstance(self.port, int):
            raise SettingsError("Port must be an integer.")
        if not (0 <= self.port <= 65535):
            raise SettingsError("Port must be between 0 and 65535.")

        self.share_dir = self.share_dir.expanduser().resolve()
        try:
            self.share_dir.mkdir(parents=True, exist_ok=True)
        except FileExistsError as exc:
            raise SettingsError(f"Shared directory is invalid: {self.share_dir}") from exc
        if not self.share_dir.exists() or not self.share_dir.is_dir():
            raise SettingsError(f"Shared directory is invalid: {self.share_dir}")

        if self.mode == "local":
            if not is_loopback_host(self.host):
                raise SettingsError("Local mode requires a loopback host (127.0.0.1, ::1, or localhost).")
            if self.tunnel_enabled:
                raise SettingsError("Tunnel cannot be enabled in local mode.")

        if self.mode == "public" and not self.tunnel_enabled:
            raise SettingsError("Public mode requires tunnel to be enabled.")

    def to_persisted_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "host": self.host,
            "port": self.port,
            "directory": str(self.share_dir),
            "tunnel": "on" if self.tunnel_enabled else "off",
            "open_browser": self.open_browser,
            "monitor": self.monitor_enabled,
            "admin_routes": self.admin_routes_enabled,
        }


def resolve_app_paths(config_path_override: str | Path | None = None) -> AppPaths:
    if config_path_override:
        settings_file = Path(config_path_override).expanduser().resolve()
        app_dir = settings_file.parent
    else:
        if os.name == "nt":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        else:
            base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        app_dir = base / APP_DIR_NAME
        settings_file = app_dir / "settings.json"

    app_dir.mkdir(parents=True, exist_ok=True)
    docs = Path.home() / "Documents" / APP_DIR_NAME
    default_share_dir = docs / "files"
    return AppPaths(
        app_dir=app_dir,
        settings_file=settings_file,
        log_file=app_dir / "access.log",
        blacklist_file=app_dir / "blacklist.txt",
        default_share_dir=default_share_dir,
    )


def load_settings_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SettingsError(f"Invalid JSON settings file: {path}") from exc
    if not isinstance(data, dict):
        raise SettingsError(f"Settings file must contain a JSON object: {path}")
    return data


def save_settings_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def default_persisted_settings(paths: AppPaths) -> dict[str, Any]:
    return {
        "mode": "local",
        "host": "127.0.0.1",
        "port": 0,
        "directory": str(paths.default_share_dir),
        "tunnel": "off",
        "open_browser": True,
        "monitor": True,
        "admin_routes": False,
    }


def validate_host(host: str) -> None:
    if host.lower() == "localhost":
        return
    try:
        ipaddress.ip_address(host)
    except ValueError as exc:
        raise SettingsError(f"Invalid host value '{host}'. Use localhost or a valid IP address.") from exc


def is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def tunnel_flag_to_bool(value: str | bool | None, *, mode: str) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return mode == "public"
    if not isinstance(value, str):
        raise SettingsError("Tunnel setting must be one of: on, off, auto.")
    normalized = value.strip().lower()
    if normalized not in VALID_TUNNEL_VALUES:
        raise SettingsError("Tunnel setting must be one of: on, off, auto.")
    if normalized == "auto":
        return mode == "public"
    return normalized == "on"


def build_settings(
    cli_overrides: Mapping[str, Any],
    *,
    config_path_override: str | Path | None = None,
    persist_overrides: bool = False,
) -> Settings:
    paths = resolve_app_paths(config_path_override)
    persisted = load_settings_json(paths.settings_file)
    if not persisted:
        persisted = default_persisted_settings(paths)
        save_settings_json(paths.settings_file, persisted)

    merged = dict(default_persisted_settings(paths))
    merged.update(persisted)
    for key, value in cli_overrides.items():
        if value is not None:
            merged[key] = value

    mode = str(merged.get("mode", "local")).lower()
    if mode not in VALID_MODES:
        raise SettingsError(f"Unsupported mode '{mode}'. Valid modes: local, lan, public.")

    cli_host = cli_overrides.get("host")
    if cli_host is not None:
        host = cli_host
    elif mode == "lan":
        host = "0.0.0.0"
    else:
        host = merged.get("host")
        if not host:
            host = "127.0.0.1" if mode == "local" else "0.0.0.0"

    cli_port = cli_overrides.get("port")
    if cli_port is not None:
        port = cli_port
    elif mode == "lan":
        port = 63
    else:
        port = merged.get("port", 63)
    try:
        port = int(port)
    except (TypeError, ValueError) as exc:
        raise SettingsError("Port must be an integer between 0 and 65535.") from exc

    directory = Path(str(merged.get("directory", paths.default_share_dir)))
    cli_tunnel = cli_overrides.get("tunnel")
    persisted_tunnel = merged.get("tunnel")
    if mode == "public":
        if isinstance(cli_tunnel, str) and cli_tunnel.strip().lower() == "off":
            raise SettingsError("Public mode cannot be used with '--tunnel off'. Use mode 'lan' instead.")
        tunnel_enabled = True
    elif mode == "local":
        if isinstance(cli_tunnel, str) and cli_tunnel.strip().lower() == "on":
            raise SettingsError("Local mode cannot be used with '--tunnel on'.")
        tunnel_enabled = False
    else:
        tunnel_enabled = tunnel_flag_to_bool(cli_tunnel if cli_tunnel is not None else persisted_tunnel, mode=mode)
    open_browser = bool(merged.get("open_browser", True))
    monitor_enabled = bool(merged.get("monitor", True))
    admin_routes_enabled = bool(merged.get("admin_routes", False))

    settings = Settings(
        mode=mode,
        host=str(host),
        port=port,
        share_dir=directory,
        tunnel_enabled=tunnel_enabled,
        open_browser=open_browser,
        monitor_enabled=monitor_enabled,
        admin_routes_enabled=admin_routes_enabled,
        app_paths=paths,
    )
    settings.validate()

    if persist_overrides:
        save_settings_json(paths.settings_file, settings.to_persisted_dict())

    return settings
