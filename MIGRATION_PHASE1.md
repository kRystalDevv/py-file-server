# Phase 1 Migration Notes

## Old behavior

- Single `fileserver.py` script handled config, server, tunnel, logging, and monitoring together.
- User config used `server_config.yml`.
- Cloudflare tunnel startup was effectively mandatory.
- Host/port behavior required editing script/config.

## New behavior

- App split into modules under `fileshare_app/`:
  - `core/config.py`
  - `core/server.py`
  - `core/tunnel.py`
  - `core/metrics.py`
  - `core/security.py`
  - `cli.py`
  - `app.py`
- User config is JSON at `%APPDATA%\63xkyFileServer\settings.json` by default.
- CLI args override saved settings for one run.
- `--save` persists current effective settings.
- Tunnel is mode-driven and optional.

## How to run now

1. Install requirements:
   - `python -m pip install -r requirements.txt`
2. Start with compatibility script:
   - `   `
3. Or start module directly:
   - `python -m fileshare_app.app --mode public --port 8080`

## Compatibility

- `fileserver.py` remains as a thin wrapper entrypoint.
- Existing launchers calling `python fileserver.py` still work.
