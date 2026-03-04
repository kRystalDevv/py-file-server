# py-file-server (63xky's File Server)

Refactored lightweight file sharing server with explicit runtime modes and optional Cloudflare tunnel.

## Runtime modes

- `local`: bind to loopback only, tunnel disabled.
- `lan`: bind to LAN interface (`0.0.0.0` by default), tunnel disabled by default.
- `public`: tunnel enabled by default.

## Configuration model

User settings are now persisted as JSON (not YAML).

- Default settings path on Windows:
  - `%APPDATA%\63xkyFileServer\settings.json`
- Override settings path:
  - `--config C:\path\to\settings.json`

CLI arguments override persisted settings for the current run.  
Use `--save` to write current effective settings back to JSON.

## Run

```powershell
python fileserver.py --mode local
```

Or:

```powershell
python -m fileshare_app.app --mode lan --host 0.0.0.0 --port 8080 --directory .\files
```

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

Defaults:
- `threads=16`
- `max_downloads=12`
- `max_downloads` must be lower than `threads` so lightweight web requests retain worker capacity during large downloads.

## Notes

- Admin routes are disabled by default and only allowed from loopback when enabled.
- Download path resolution is locked to the shared root to prevent path traversal.
- Cloudflare tunnel startup has explicit timeout/failure handling.
- In monitor mode, hotkeys are available:
  - `Q` quit (with Y/N confirmation)
  - `P` change shared folder path live
  - `T` toggle subdirectory traversal
  - `O` switch server port live (in-process restart)
  - `L` cycle request logging verbosity: `no` -> `basic` -> `medium` -> `full`
- Web file list includes one-click command copy buttons per file:
  - `curl.exe -L "<url>" -o "<filename>"`
  - `Invoke-WebRequest -Uri "<url>" -OutFile "<filename>"`

## Tests

```powershell
python -m unittest discover -s tests -v
```
