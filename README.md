# py-file-server (63xky's File Server)

Refactored lightweight file sharing server with explicit runtime modes and optional Cloudflare tunnel.

Runs on Windows and on Ubuntu/Debian-based Linux.

## Runtime modes

- `local`: bind to loopback only, tunnel disabled.
- `lan`: bind to LAN interface (`0.0.0.0` by default), tunnel disabled by default.
- `public`: tunnel enabled by default.

## Configuration model

User settings are now persisted as JSON (not YAML).

- Default settings path:
  - Windows: `%APPDATA%\63xkyFileServer\settings.json`
  - Linux: `~/.config/63xkyFileServer/settings.json` (or `$XDG_CONFIG_HOME/63xkyFileServer/settings.json` if set)
- Override settings path:
  - Windows: `--config C:\path\to\settings.json`
  - Linux: `--config ~/path/to/settings.json`

CLI arguments override persisted settings for the current run.  
Use `--save` to write current effective settings back to JSON.

## Setup (install dependencies)

### Windows

Run `setup.bat`. It installs Python and `cloudflared` if missing (via winget/Chocolatey/direct
download) and installs the packages from `requirements.txt`.

### Ubuntu / Debian-based Linux

Run `./setup.sh`. It installs `python3`, `python3-venv`, `python3-pip`, and `cloudflared` (via
Cloudflare's apt repository, falling back to a direct `.deb` download) using `sudo` where needed,
then creates a local `.venv` and installs `requirements.txt` into it. A virtual environment is used
because recent Ubuntu/Debian releases block `pip install` directly into the system Python
(PEP 668 "externally managed environment"). `run_server.sh` automatically uses `.venv` if present.

If you'd rather manage the environment yourself:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

### Windows

```powershell
run_server.bat
```

Or directly:

```powershell
python fileserver.py --mode local
python -m fileshare_app.app --mode lan --host 0.0.0.0 --port 8080 --directory .\files
```

### Linux (Ubuntu)

```bash
./run_server.sh
```

Or directly:

```bash
python3 fileserver.py --mode local
python3 -m fileshare_app.app --mode lan --host 0.0.0.0 --port 8080 --directory ./files
```

`run_server.sh` uses `.venv/bin/python3` automatically if `setup.sh` created one, otherwise it
falls back to the system `python3`.

By default the app launches a Textual-based operator console. Pass `--legacy-cli` (or its alias
`--no-ui`) to run the plain console mode instead. If `textual`/`qrcode` aren't installed, the app
automatically falls back to the plain console mode with a warning.

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
- `--legacy-cli` (run the plain console mode instead of the Textual UI)
- `--no-ui` (alias for `--legacy-cli`)
- `--tray` (run headless with a system tray icon; requires `pystray`/`Pillow`; takes priority over `--legacy-cli`/`--no-ui`)

Defaults:
- `threads=16`
- `max_downloads=12`
- `max_downloads` must be lower than `threads` so lightweight web requests retain worker capacity during large downloads.

## Notes

- Admin routes are disabled by default and only allowed from loopback when enabled.
- Download path resolution is locked to the shared root to prevent path traversal.
- Cloudflare tunnel startup has explicit timeout/failure handling.
- In monitor mode, hotkeys are available on both Windows and Linux terminals (Windows via
  `msvcrt`, Linux via `termios`/`tty`; hotkeys are a no-op if stdin isn't an interactive
  terminal, e.g. when run under a service):
  - `Q` quit (with Y/N confirmation)
  - `P` change shared folder path live
  - `T` toggle subdirectory traversal
  - `O` switch server port live (in-process restart)
  - `L` cycle request logging verbosity: `no` -> `basic` -> `medium` -> `full`
- Web file list includes one-click command copy buttons per file:
  - `curl -L "<url>" -o "<filename>"` (Linux/macOS/WSL/`cmd.exe`)
  - `Invoke-WebRequest -Uri "<url>" -OutFile "<filename>"` (Windows PowerShell)

## Building a Windows installer

`build.bat` builds two PyInstaller executables (`FileServer.exe`, the console/Textual UI
build, and `FileServerTray.exe`, the headless tray build) via `fileserver.spec`, then compiles
`installer/fileserver.iss` into a Windows installer with Inno Setup 6, if it's installed
(download from https://jrsoftware.org/isdl.php). The installer version is read directly from
`fileshare_app/__init__.py`'s `__version__`. Output: `installer/Output/FileServerSetup-<version>.exe`.

```powershell
build.bat
```

The `Release` GitHub Actions workflow (manual, `workflow_dispatch`) builds this installer
automatically alongside the plain Windows/Linux binaries as part of every release.

## Tests

Windows:

```powershell
python -m unittest discover -s tests -v
```

Linux:

```bash
python3 -m unittest discover -s tests -v
```
