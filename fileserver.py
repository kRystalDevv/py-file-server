#!/usr/bin/env python3
"""
63xky's File Server - Production-ready Flask file sharing application with CLI metrics
Version: 1.1.0
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
import time
from pathlib import Path

import yaml
from flask import (
    Flask,
    abort,
    render_template_string,
    request,
    Response,
    stream_with_context,
)
from logging.handlers import RotatingFileHandler

# Metadata
# --------------------------------------------------------------------------- #
__app_name__ = "63xky's File Server"
__version__ = "1.1.0"

# Default configuration
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = {
    "port": None,
    "files_dir": "files",
    "tunnel_name": "fileshare",
    "listen_host": "127.0.0.1",
    "log_file": "access.log",
    "blacklist_file": "blacklist.txt",
    "max_log_size": 5 * 1024 * 1024,
    "backup_count": 3,
    "config_file": "server_config.yml",
    "monitor_interval": 1  # seconds
}

# Metrics storage
# --------------------------------------------------------------------------- #
active_downloads = {}  # key -> {filename, bytes, start}
active_lock = threading.Lock()
total_uploaded = 0

# Utility: pick a free port
# --------------------------------------------------------------------------- #
COMMON_PORTS = {20,21,22,23,25,53,80,110,143,443,465,587,995,3306,5432,6379,8080,27017,5000,8000,9000,22222}
PORT_RANGE = (15000, 29999)

def pick_free_port() -> int:
    while True:
        p = random.randint(*PORT_RANGE)
        if p in COMMON_PORTS:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(('127.0.0.1', p)) != 0:
                return p

# Configuration loader
# --------------------------------------------------------------------------- #
def load_config() -> dict:
    cfg = DEFAULT_CONFIG.copy()
    path = BASE_DIR / cfg['config_file']
    if path.exists():
        try:
            user_cfg = yaml.safe_load(path.read_text()) or {}
            cfg.update({k: v for k, v in user_cfg.items() if v is not None})
            logging.info(f"Loaded config from {path}")
        except Exception as e:
            logging.warning(f"Failed to read config: {e}")
    if not cfg['port']:
        cfg['port'] = pick_free_port()
    cfg['files_dir'] = (BASE_DIR / cfg['files_dir']).resolve()
    cfg['files_dir'].mkdir(exist_ok=True)
    cfg['log_file'] = BASE_DIR / cfg['log_file']
    cfg['blacklist_file'] = BASE_DIR / cfg['blacklist_file']
    return cfg

# Logging setup
# --------------------------------------------------------------------------- #
def setup_logging(cfg):
    handler = RotatingFileHandler(cfg['log_file'], maxBytes=cfg['max_log_size'], backupCount=cfg['backup_count'])
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(message)s', '%Y-%m-%d %H:%M:%S')
    handler.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

# Metrics monitor thread
# --------------------------------------------------------------------------- #
def monitor_thread(cfg):
    interval = cfg.get('monitor_interval', 1)
    while True:
        if os.name == 'nt':
            subprocess.run(['cls'], shell=True)
        else:
            subprocess.run(['clear'])
        print(f"{__app_name__} v{__version__} - Active Downloads")
        print('-'*50)
        total_speed = 0.0
        with active_lock:
            for key, data in list(active_downloads.items()):
                elapsed = time.time() - data['start']
                speed = data['bytes'] / elapsed if elapsed > 0 else 0
                total_speed += speed
                print(f"{data['filename']} | {data['bytes']} B sent | {speed:.2f} B/s")
        print('-'*50)
        print(f"Global Upload Speed: {total_speed:.2f} B/s")
        print(f"Total Uploaded: {total_uploaded} B")
        time.sleep(interval)

# Flask application factory
# --------------------------------------------------------------------------- #
def create_app(cfg):
    app = Flask(__name__)
    if not cfg['blacklist_file'].exists():
        cfg['blacklist_file'].write_text('')
    blacklist = set(cfg['blacklist_file'].read_text().split())

    @app.before_request
    def block_blacklisted():
        if request.remote_addr in blacklist and not request.path.startswith('/admin'):
            abort(403)

    @app.after_request
    def log_request(resp):
        logging.info(f"{request.remote_addr} | {request.method} {request.path} | {resp.status_code}")
        return resp

    @app.route('/')
    def index():
        files = sorted(os.listdir(cfg['files_dir']))
        html = f"""
        <!doctype html><html><head><meta charset='utf-8'><title>{__app_name__}</title>
        <style>body{{font-family:system-ui,sans-serif;max-width:800px;margin:2rem auto}}h1{{color:#2c3e50}}.file{{margin:.5rem 0}}a{{color:#1abc9c;text-decoration:none}}a:hover{{text-decoration:underline}}</style>
        </head><body><h1>{__app_name__}</h1><p>Version: {__version__}</p><h2>Files</h2>
        {{% if files %}}{{% for f in files %}}<div class='file'><a href='{{{{ url_for('download', filename=f) }}}}'>{{{{ f }}}}</a></div>{{% endfor %}}{{% else %}}<p><em>No files available.</em></p>{{% endif %}}
        </body></html>
        """
        return render_template_string(html, files=files)

    @app.route('/files/<path:filename>')
    def download(filename):
        filepath = cfg['files_dir'] / filename
        if not filepath.exists() or not filepath.is_file():
            abort(404)
        def generate():
            global total_uploaded
            key = f"{threading.get_ident()}:{filename}"
            with active_lock:
                active_downloads[key] = {'filename': filename, 'bytes': 0, 'start': time.time()}
            with open(filepath, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    yield chunk
                    with active_lock:
                        active_downloads[key]['bytes'] += len(chunk)
                        total_uploaded += len(chunk)
            with active_lock:
                del active_downloads[key]
        headers = {'Content-Disposition': f'attachment; filename="{filename}"'}
        return Response(stream_with_context(generate()), headers=headers, mimetype='application/octet-stream')

    @app.route('/admin/logs')
    def get_logs():
        if request.remote_addr not in ('127.0.0.1','::1'):
            abort(403)
        return send_from_directory(BASE_DIR, cfg['log_file'].name, as_attachment=True)

    @app.route('/admin/blacklist')
    def manage_blacklist():
        if request.remote_addr not in ('127.0.0.1','::1'):
            abort(403)
        ip = request.args.get('ip')
        action = request.args.get('action','add')
        if ip:
            if action=='remove': blacklist.discard(ip)
            else: blacklist.add(ip)
            with open(cfg['blacklist_file'],'w') as bf:
                bf.write("\n".join(sorted(blacklist)))
        return {'blacklist': sorted(blacklist)}

    return app

# Tunnel helper
# --------------------------------------------------------------------------- #
def start_tunnel(cfg):
    cmd = ['cloudflared','tunnel','--url',f"http://localhost:{cfg['port']}"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    def read_url():
        for line in proc.stdout:
            if line.strip().startswith('https://'):
                logging.info(f"Tunnel URL: {line.strip()}")
                break
    threading.Thread(target=read_url,daemon=True).start()
    atexit.register(proc.terminate)
    return proc

# Entrypoint
# --------------------------------------------------------------------------- #
if __name__=='__main__':
    cfg = load_config()
    setup_logging(cfg)
    logging.info(f"Starting {__app_name__} (v{__version__})")
    monitor = threading.Thread(target=monitor_thread, args=(cfg,), daemon=True)
    monitor.start()
    cf_proc = start_tunnel(cfg)
    app = create_app(cfg)
    from waitress import serve
    serve(app, host=cfg['listen_host'], port=cfg['port'])
    cf_proc.terminate()
