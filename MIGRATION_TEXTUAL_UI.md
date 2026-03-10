# Migration Note: Legacy CLI -> Textual Console

## Startup behavior
- New default: Textual operator console.
- Legacy mode remains available via:
  - `--legacy-cli`
  - `--no-ui`
- If Textual is missing, startup falls back to legacy CLI automatically.

## Server behavior
- Flask routes, download handling, path safety, and concurrency limits remain in `core/`.
- Waitress startup and runtime toggles are preserved and wrapped by `ServerManager`.

## Public mode behavior
- Public mode is optional and on-demand.
- Local/LAN mode does not depend on cloudflared.
- If public mode is requested and cloudflared is missing:
  - UI shows explicit requirement and install hints.
  - Local/LAN mode continues normally.
- If installed but not configured:
  - UI shows setup guidance.

## Key map migration
- New app-level keys:
  - `1` Dashboard
  - `2` Transfers
  - `3` Logs
  - `4` Settings
  - `5` Public Access
  - `q` Toggle fullscreen QR (15s auto-return, `q`/`Esc` to exit early)
  - `p` Public mode flow
  - `r` Refresh
  - `x` Stop/shutdown with confirmation
  - `Esc` Dismiss QR/modal

## Legacy controls (when `--legacy-cli` is used)
- Existing hotkeys are unchanged:
  - `Q` quit
  - `P` change shared folder
  - `T` toggle subdirectory traversal
  - `O` change port
  - `L` cycle request log verbosity
