# python-fs (63xky's File Server)

Simple, lightweight file server with live monitoring, resumable downloads, rotating logs, a local IP blacklist, and optional Cloudflare Tunnel for easy sharing.

Current version: v1.2.1

## Features

- Zero-config startup (auto-picks a free port if none provided)
- Clean HTML index listing with direct links to files
- Resumable/partial downloads (HTTP Range support)
- Live console monitor: per-download speed, global upload speed, total uploaded, and recent log tail
- Rotating access logs (size-based with backups)
- Simple IP blacklist with localhost-only admin endpoints
	- GET `/admin/blacklist?action=add&ip=1.2.3.4` (or `action=remove`) from 127.0.0.1 only
	- GET `/admin/logs` to download `access.log` from 127.0.0.1 only
- YAML configuration file (`server_config.yml`)
- Built-in helper to start a Cloudflare Tunnel and print the public HTTPS URL

## Requirements

- Python 3.8+
- Cloudflare Tunnel (cloudflared) installed and on PATH
	- Install guide: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install/

## Install dependencies

### Windows quickstart

Run `setup.bat` to automatically install `cloudflared` and Python dependencies.

### Manual

```bash
pip install -r requirements.txt
```

## Usage

1) Put the files you want to share into the `files/` folder.
2) Start the server:

```bash
python fileserver.py
```

On Windows you can also double-click `run_server.bat`.

When the server starts, the console monitor will appear and, if `cloudflared` is available, a public tunnel URL (https://...) will be logged.

By default the server listens on `127.0.0.1` and chooses a free port. Open the printed URL or visit `http://127.0.0.1:<port>/` locally. Use Cloudflare Tunnel to share externally.

## Configuration (server_config.yml)

Place a `server_config.yml` next to `fileserver.py` to customize settings. All fields are optional; sensible defaults are used if missing.

Example:

```yaml
# Pick a specific port (set to null or remove to auto-pick a free one)
port: null

# Bind address
listen_host: 127.0.0.1

# Where to read files from
files_dir: files

# Logging
log_file: access.log
max_log_size: 5242880      # 5 MB
backup_count: 3

# Blacklist storage
blacklist_file: blacklist.txt

# Monitor behavior
monitor_interval: 1        # seconds
log_tail_lines: 10

# Cloudflare tunnel name (optional label)
tunnel_name: fileshare
```

Notes:
- The server writes rotating logs to `access.log` and shows the tail in the console monitor.
- Admin endpoints are restricted to localhost for safety.
- To serve over your LAN, set `listen_host: 0.0.0.0` and ensure your firewall allows inbound traffic.

## Admin endpoints (localhost only)

- GET `http://127.0.0.1:<port>/admin/blacklist?action=add&ip=1.2.3.4`
	- Use `action=remove` to unblock an IP.
- GET `http://127.0.0.1:<port>/admin/logs` to download the log file.

## Troubleshooting

- Cloudflared not found / tunnel doesn’t start: install `cloudflared` and ensure it’s on PATH, then try again.
- 403 on admin routes: they are only accessible from 127.0.0.1/::1.
- Can’t reach the server externally: the default bind is localhost. Use Cloudflare Tunnel or change `listen_host` to `0.0.0.0` and expose the chosen port.

