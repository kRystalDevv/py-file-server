from __future__ import annotations

import argparse
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fileserver",
        description="63xky File Server with optional Cloudflare tunnel.",
    )
    parser.add_argument("--mode", choices=["local", "lan", "public"], help="Runtime mode.")
    parser.add_argument("--host", help="Host/IP to bind (localhost, 127.0.0.1, 0.0.0.0, ::1).")
    parser.add_argument("--port", type=int, help="Port number (0 for automatic).")
    parser.add_argument("--directory", help="Directory to share.")
    parser.add_argument("--tunnel", choices=["on", "off", "auto"], help="Tunnel behavior.")
    parser.add_argument("--no-browser", action="store_true", help="Disable auto-opening browser.")
    parser.add_argument("--config", help="Path to JSON settings file.")
    parser.add_argument("--save", action="store_true", help="Persist effective settings to settings JSON.")
    parser.add_argument("--admin-routes", action="store_true", help="Enable localhost-only admin routes.")
    parser.add_argument("--no-monitor", action="store_true", help="Disable console monitor output.")
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    return parser.parse_args(argv)


def namespace_to_overrides(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "mode": args.mode,
        "host": args.host,
        "port": args.port,
        "directory": args.directory,
        "tunnel": args.tunnel,
        "open_browser": False if args.no_browser else None,
        "admin_routes": True if args.admin_routes else None,
        "monitor": False if args.no_monitor else None,
    }
