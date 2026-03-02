#!/usr/bin/env python3
"""Compatibility entrypoint for the refactored file server app."""

from fileshare_app.app import main


if __name__ == "__main__":
    raise SystemExit(main())
