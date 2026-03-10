# py-file-server (63xky's File Server)

Refactored lightweight file sharing server with a Textual operator console and preserved backend/server behavior.

## Runtime modes

- `local`: bind to loopback only, tunnel disabled.
- `lan`: bind to LAN interface (`0.0.0.0` by default), tunnel disabled by default.
- `public`: tunnel intent enabled, but cloudflared remains optional and handled on-demand.

## Textual operator console

Default startup launches the Textual UI with screen navigation:

- `1` Dashboard
- `2` Transfers
- `3` Logs
- `4` Settings
- `5` Public Access
- `q` fullscreen QR (auto-return after 15s, or exit with `q`/`Esc`)
- `p` public mode flow (start/stop/setup guidance)
- `r` refresh
- `x` shutdown with confirmation
- `Esc` dismiss QR/modal

Notes:
- When a Settings text input is focused, plain letter/number keys are used for typing.
- In that case, use `Ctrl+<shortcut>` for global actions (example: `Ctrl+1`, `Ctrl+q`, `Ctrl+r`).

## Public mode and cloudflared

- Local/LAN mode works fully without cloudflared installed.
- Public mode is optional.
- If public mode is requested and cloudflared is missing, the UI clearly explains the dependency and shows install/setup hints.
- Quick tunnels are treated as development/testing only.

## Configuration model

User settings are persisted as JSON.

- Default settings path on Windows:
  - `%APPDATA%\63xkyFileServer\settings.json`
- Override settings path:
  - `--config C:\path\to\settings.json`

CLI arguments override persisted settings for the current run.
Use `--save` to write current effective settings back to JSON.

## Run

Default (Textual UI):

```powershell
python fileserver.py --mode lan
```

Legacy non-Textual mode (bypasses Textual UI):

```powershell
python fileserver.py --legacy-cli
```

Or equivalent alias:

```powershell
python fileserver.py --no-ui
```

## Troubleshooting

- If shortcuts seem unresponsive, check if a Settings input field is focused.
- Use `Ctrl+<shortcut>` while typing in inputs to trigger global actions.

## CLI options

- `--mode {local,lan,public}`
- `--host <ip-or-localhost>`
- `--port <0-65535>`
- `--directory <path>`
- `--tunnel {on,off,auto}`
- `--no-browser`
- `--config <path-to-settings-json>`
- `--save`
- `--admin-routes`
- `--no-monitor`
- `--threads <int>`
- `--max-downloads <int>`
- `--legacy-cli`
- `--no-ui`

Defaults:
- `threads=16`
- `max_downloads=12`
- `max_downloads` must be lower than `threads` so lightweight web requests retain worker capacity during large downloads.

## Docs

- Architecture note: `ARCHITECTURE_TEXTUAL_CONSOLE.md`
- Migration note: `MIGRATION_TEXTUAL_UI.md`

## Tests

```powershell
python -m unittest discover -s tests -v
```
