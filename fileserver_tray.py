#!/usr/bin/env python3
"""Tray-mode entry point. Always launches in system tray mode (no console).

This is the entry point for FileServerTray.exe (compiled with console=False).
It injects --tray into sys.argv so the app starts in headless tray mode
without the user needing to pass the flag explicitly.
"""

import sys

if "--tray" not in sys.argv:
    sys.argv.append("--tray")

from fileshare_app.app import main

if __name__ == "__main__":
    raise SystemExit(main())
