# Textual Operator Console Architecture

## Goal
Wrap the existing Flask/Waitress backend with a keyboard-first Textual operator console while preserving server behavior and keeping local/LAN operation independent from Cloudflare.

## Layers

### Core backend (existing)
- `fileshare_app/core/server.py`: Flask routes, file listing/download logic, request logging.
- `fileshare_app/core/config.py`: settings model, validation, persistence.
- `fileshare_app/core/metrics.py`: active transfer metrics.
- `fileshare_app/core/tunnel.py`: cloudflared process integration (quick tunnel command).

### Service layer (new)
- `fileshare_app/services/server_manager.py`
  - Starts/stops/restarts Waitress.
  - Exposes runtime toggles (share path, traversal, log verbosity).
  - Produces URL and bind snapshots for UI.
- `fileshare_app/services/cloudflare_manager.py`
  - Cloudflare binary detection (`PATH` + local tools dirs).
  - Explicit lifecycle states:
    - `NOT_INSTALLED`
    - `INSTALLED_NOT_CONFIGURED`
    - `READY`
    - `RUNNING`
    - `ERROR`
  - On-demand public mode start/stop without blocking local/LAN mode.
- `fileshare_app/services/transfer_store.py`
  - Converts raw transfer metrics into active + recent transfer snapshots.
- `fileshare_app/services/log_bridge.py`
  - Rolling in-memory log stream for UI log screen.
- `fileshare_app/services/qr_manager.py`
  - Terminal-friendly ASCII QR rendering.

### UI layer (new)
- `fileshare_app/ui/app.py`: main Textual app, key bindings, screen navigation, refresh loop.
- `fileshare_app/ui/state.py`: central app state store and snapshots.
- `fileshare_app/ui/screens/`
  - `dashboard.py`
  - `transfers.py`
  - `logs.py`
  - `settings.py`
  - `public_access.py`
  - `qr.py` (fullscreen QR with 15s auto-return)

## Runtime model
1. Build settings and logging as before.
2. Initialize services.
3. Start server manager (local HTTP always first).
4. Detect cloudflared only when needed (or when refreshing public screen/status).
5. Optional public mode flow via `p`:
   - Missing cloudflared: explain requirement and install path.
   - Installed but not configured: show setup guidance.
   - Ready: start/stop tunnel.
6. Central state store refreshes on a timer and screens render from that shared snapshot.

## Backward compatibility
- Old non-Textual mode remains available:
  - `--legacy-cli`
  - `--no-ui` (alias)
- If Textual import fails, app prints a clear message and falls back to legacy mode.
