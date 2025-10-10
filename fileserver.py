#!/usr/bin/env python3
"""
63xky's File Server - Local + Tunnel-based File Sharing Application
Version: 1.0.0
"""
import os
import sys
import socket
import random
import logging
import atexit
import subprocess
import tempfile
import threading
from pathlib import Path

import yaml
from flask import (
    Flask,
    abort,
    render_template_string,
    request,
    send_from_directory,
)
from logging.handlers import RotatingFileHandler

# Metadata
# --------------------------------------------------------------------------- #
__app_name__ = "63xky's File Server"
__version__ = "1.0.0"

# Default configuration
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = {
    "port": None,
    "files_dir": "files",
    "tunnel_name": "fileshare",
    "listen_host": "127.0.0.1",  # Change to 0.0.0.0 to expose to LAN
    "log_file": "access.log",
    "blacklist_file": "blacklist.txt",
    "max_log_size": 5 * 1024 * 1024,   # 5MB
    "backup_count": 3,
    "config_file": "server_config.yml",
}

# Utility: pick a free port
# --------------------------------------------------------------------------- #
COMMON_PORTS = {20,21,22,23,25,53,80,110,143,443,465,587,995,3306,5432,6379,8080,27017,5000,8000,9000,22222}
PORT_RANGE = (15000, 29999)

def pick_free_port() -> int:
    """Pick an uncommon free port."""
    while True:
        p = random.randint(*PORT_RANGE)
        if p in COMMON_PORTS:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(('127.0.0.1', p)) != 0:
                return p

# Load configuration
# --------------------------------------------------------------------------- #
def load_config() -> dict:
    cfg = DEFAULT_CONFIG.copy()
    cfg_path = BASE_DIR / cfg['config_file']
    if cfg_path.exists():
        try:
            user_cfg = yaml.safe_load(cfg_path.read_text()) or {}
            cfg.update({k: v for k, v in user_cfg.items() if v is not None})
            logging.info(f"Loaded config from {cfg_path}")
        except Exception as e:
            logging.warning(f"Failed to parse {cfg_path}: {e}")
    if not cfg['port']:
        cfg['port'] = pick_free_port()
    cfg['files_dir'] = (BASE_DIR / cfg['files_dir']).resolve()
    cfg['files_dir'].mkdir(exist_ok=True)
    cfg['log_file'] = (BASE_DIR / cfg['log_file']).resolve()
    cfg['blacklist_file'] = (BASE_DIR / cfg['blacklist_file']).resolve()
    return cfg

# Setup logging
# --------------------------------------------------------------------------- #
def setup_logging(cfg: dict):
    handler = RotatingFileHandler(
        cfg['log_file'], maxBytes=cfg['max_log_size'], backupCount=cfg['backup_count']
    )
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    handler.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

# Flask application factory
# --------------------------------------------------------------------------- #
def create_app(cfg: dict) -> Flask:
    app = Flask(__name__)
    if not cfg['blacklist_file'].exists():
        cfg['blacklist_file'].write_text('')
    blacklist = set(cfg['blacklist_file'].read_text().split())

    @app.before_request
    def block_blacklisted():
        if request.remote_addr in blacklist and not request.path.startswith('/admin'):
            logging.warning(f"Blocked blacklisted IP: {request.remote_addr}")
            abort(403)

    @app.after_request
    def log_request(response):
        logging.info(f"{request.remote_addr} | {request.method} {request.path} | {response.status_code}")
        return response

    @app.route('/')
    def index():
        files = sorted(os.listdir(cfg['files_dir']))
        html = f"""
        <!doctype html>
        <html><head><meta charset='utf-8'><title>{__app_name__}</title>
        <style>body{{font-family:system-ui,sans-serif;max-width:800px;margin:2rem auto}} h1{{color:#2c3e50}} .file{{margin:.5rem 0}} a{{color:#1abc9c;text-decoration:none}} a:hover{{text-decoration:underline}}</style>
        </head><body>
        <h1>{__app_name__}</h1><p>Version: {__version__}</p><h2>Available Files</h2>
        {{% if files %}}{{% for f in files %}}<div class='file'><a href='{{{{ url_for('download', filename=f) }}}}'>{{{{ f }}}}</a></div>{{% endfor %}}{{% else %}}<p><em>No files found. Drop them in the '{cfg['files_dir'].name}' folder.</em></p>{{% endif %}}
        </body></html>
        """
        return render_template_string(html, files=files)

    @app.route('/files/<path:filename>')
    def download(filename):
        return send_from_directory(cfg['files_dir'], filename, as_attachment=True)

    # Admin endpoints (localhost only)
    def local_only():
        if request.remote_addr not in ('127.0.0.1', '::1'):
            abort(403)

    @app.route('/admin/logs')
    def get_logs():
        local_only()
        return send_from_directory(BASE_DIR, Path(cfg['log_file']).name, as_attachment=True)

    @app.route('/admin/blacklist')
    def manage_blacklist():
        local_only()
        ip = request.args.get('ip')
        action = request.args.get('action', 'add')
        if ip:
            if action == 'remove':
                blacklist.discard(ip)
            else:
                blacklist.add(ip)
            with open(cfg['blacklist_file'], 'w') as bf:
                bf.write("\n".join(sorted(blacklist)))
        return {'blacklist': sorted(blacklist)}

    return app

# Tunnel helper
# --------------------------------------------------------------------------- #
def start_tunnel(cfg: dict) -> subprocess.Popen:
    cmd = ['cloudflared', 'tunnel', '--url', f"http://localhost:{cfg['port']}"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    def read_url():
        for line in proc.stdout:
            if line.strip().startswith('https://'):
                logging.info(f"Tunnel URL: {line.strip()}")
                break
    threading.Thread(target=read_url, daemon=True).start()
    atexit.register(proc.terminate)
    return proc

# Entrypoint
# --------------------------------------------------------------------------- #
if __name__ == '__main__':
    cfg = load_config()
    setup_logging(cfg)
    logging.info(f"Starting {__app_name__} (v{__version__})")
    cf_proc = start_tunnel(cfg)
    app = create_app(cfg)

    try:
        from waitress import serve
        serve(app, host=cfg['listen_host'], port=cfg['port'])
    except KeyboardInterrupt:
        logging.info("Shutdown requested, exiting...")
    finally:
        cf_proc.terminate()
        logging.info("Server stopped.")
