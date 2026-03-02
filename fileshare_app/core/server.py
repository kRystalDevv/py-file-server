from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import re
import socket
import threading
import time
import ipaddress
from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template_string, request, send_from_directory, stream_with_context

from .. import __version__
from .config import Settings, SettingsError
from .metrics import TransferMetrics
from .security import BlacklistStore, is_loopback_remote, safe_resolve_file, validate_ip_address

RANGE_RE = re.compile(r"bytes=(\d+)-(\d*)$")
TRUSTED_LOCAL_PROXIES = {"127.0.0.1", "::1", "::ffff:127.0.0.1"}
LOG_LEVELS = ("no", "basic", "medium", "full")


@dataclass
class RuntimeState:
    share_dir: Path
    allow_subdirectories: bool = True
    current_port: int = 0
    log_verbosity: str = "medium"

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self.share_dir = self.share_dir.resolve()

    def get_share_dir(self) -> Path:
        with self._lock:
            return self.share_dir

    def set_share_dir(self, path: Path) -> None:
        resolved = path.expanduser().resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        if not resolved.is_dir():
            raise SettingsError(f"Invalid share directory: {resolved}")
        with self._lock:
            self.share_dir = resolved

    def toggle_subdirectories(self) -> bool:
        with self._lock:
            self.allow_subdirectories = not self.allow_subdirectories
            return self.allow_subdirectories

    def get_allow_subdirectories(self) -> bool:
        with self._lock:
            return self.allow_subdirectories

    def set_port(self, port: int) -> None:
        with self._lock:
            self.current_port = port

    def get_port(self) -> int:
        with self._lock:
            return self.current_port

    def cycle_log_verbosity(self) -> str:
        with self._lock:
            try:
                idx = LOG_LEVELS.index(self.log_verbosity)
            except ValueError:
                idx = 2
            self.log_verbosity = LOG_LEVELS[(idx + 1) % len(LOG_LEVELS)]
            return self.log_verbosity

    def get_log_verbosity(self) -> str:
        with self._lock:
            return self.log_verbosity


def get_client_context(req) -> dict[str, str | bool]:
    remote_addr = (req.remote_addr or "").strip()
    ua = (req.headers.get("User-Agent") or "").strip()
    is_trusted_proxy = remote_addr in TRUSTED_LOCAL_PROXIES

    client_ip = remote_addr or "Unknown"
    client_country = "Unknown"
    client_ray = ""
    proxied = False
    source = "local" if is_loopback_remote(remote_addr) else "lan"

    # When using cloudflared quick tunnels locally, Flask sees 127.0.0.1/::1
    # as the immediate peer because cloudflared is the local reverse proxy.
    if is_trusted_proxy:
        cf_ip = (req.headers.get("CF-Connecting-IP") or "").strip()
        if cf_ip:
            try:
                ipaddress.ip_address(cf_ip)
                client_ip = cf_ip
                client_country = (req.headers.get("CF-IPCountry") or "Unknown").strip() or "Unknown"
                client_ray = (req.headers.get("CF-Ray") or "").strip()
                proxied = True
                source = "cloudflare"
            except ValueError:
                pass

    return {
        "client_ip": client_ip,
        "client_country": client_country,
        "client_ray": client_ray,
        "proxied": proxied,
        "source": source,
        "user_agent": ua,
    }


def build_request_log_message(
    *,
    mode: str,
    ctx: dict[str, str | bool],
    method: str,
    path: str,
    status: int,
    verbosity: str,
    app_version: str,
) -> str:
    if verbosity == "no":
        return ""

    ip = str(ctx.get("client_ip", "Unknown"))
    source = str(ctx.get("source", "lan"))
    ua = str(ctx.get("user_agent", "")).replace('"', "'")
    country = str(ctx.get("client_country", "Unknown"))
    ray = str(ctx.get("client_ray", ""))
    proxied_flag = bool(ctx.get("proxied", False)) or source == "cloudflare"
    proxied = "true" if proxied_flag else "false"

    if verbosity == "basic":
        return f"client_ip={ip} path={path} status={status}"
    if verbosity == "medium":
        return (
            f"mode={mode} source={source} client_ip={ip} "
            f"method={method} path={path} status={status}"
        )
    return (
        f'event=request_complete version={app_version} mode={mode} source={source} '
        f"client_ip={ip} method={method} path={path} status={status} "
        f"country={country} ray={ray} proxied={proxied} ua=\"{ua}\""
    )


def resolve_listen_port(host: str, requested_port: int) -> int:
    family = socket.AF_INET
    try:
        if ipaddress.ip_address(host).version == 6:
            family = socket.AF_INET6
    except ValueError:
        if ":" in host:
            family = socket.AF_INET6

    if requested_port == 0:
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            sock.bind((host, 0))
            return int(sock.getsockname()[1])

    with socket.socket(family, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, requested_port))
        except OSError as exc:
            raise SettingsError(f"Port {requested_port} is unavailable on host {host}.") from exc
    return requested_port


def create_app(
    settings: Settings,
    *,
    logger: logging.Logger,
    metrics: TransferMetrics,
    blacklist_store: BlacklistStore,
    runtime_state: RuntimeState,
) -> Flask:
    app = Flask(__name__)

    @app.before_request
    def enforce_blacklist() -> None:
        remote = request.remote_addr or ""
        if remote and blacklist_store.contains(remote) and not request.path.startswith("/admin"):
            abort(403)

    @app.after_request
    def log_request(response):  # type: ignore[no-untyped-def]
        ctx = get_client_context(request)
        message = build_request_log_message(
            mode=settings.mode,
            ctx=ctx,
            method=request.method,
            path=request.path,
            status=response.status_code,
            verbosity=runtime_state.get_log_verbosity(),
            app_version=__version__,
        )
        if message:
            logger.info(message)
        return response

    @app.route("/")
    def index():  # type: ignore[no-untyped-def]
        share_dir = runtime_state.get_share_dir()
        include_subdirs = runtime_state.get_allow_subdirectories()
        requested_dir = (request.args.get("dir") or "").strip().replace("\\", "/")
        if not include_subdirs and requested_dir:
            abort(403)
        try:
            current_dir, current_rel = _resolve_browse_dir(share_dir, requested_dir)
        except ValueError:
            abort(403)
        except FileNotFoundError:
            abort(404)
        entries = _scan_directory(current_dir, share_dir=share_dir, include_subdirs=include_subdirs)
        parent_rel = _parent_relative(current_rel)
        breadcrumbs = _build_breadcrumbs(current_rel)
        html = """
        <!doctype html>
        <html>
            <head>
                <meta charset='utf-8'>
                <title>63xky File Server</title>
                <style>
                    :root {
                        --bg: #f4f7fb;
                        --panel: #ffffff;
                        --text: #1f2a37;
                        --muted: #64748b;
                        --accent: #0b5ed7;
                        --border: #e2e8f0;
                        --shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
                    }
                    body {
                        margin: 0;
                        background: radial-gradient(circle at top, #e8f0ff 0%, var(--bg) 35%);
                        color: var(--text);
                        font-family: "Segoe UI", "Trebuchet MS", sans-serif;
                    }
                    .wrap {
                        width: calc(100vw - 2rem);
                        max-width: 1600px;
                        margin: 1.2rem auto;
                        padding: 0 1rem;
                    }
                    .card {
                        background: var(--panel);
                        border: 1px solid var(--border);
                        border-radius: 16px;
                        box-shadow: var(--shadow);
                        overflow: visible;
                    }
                    .head {
                        padding: 1.1rem 1.2rem;
                        border-bottom: 1px solid var(--border);
                        background: linear-gradient(135deg, #f8fbff, #eef5ff);
                    }
                    h1 { margin: 0 0 .3rem 0; font-size: 1.35rem; }
                    .meta { color: var(--muted); font-size: .92rem; }
                    .table-wrap { overflow-x: auto; width: 100%; }
                    table { width: 100%; border-collapse: collapse; min-width: 980px; }
                    th, td { padding: .72rem 1rem; border-bottom: 1px solid var(--border); text-align: left; }
                    th { font-size: .85rem; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
                    tr:hover { background: #f8fbff; }
                    .name a { color: var(--accent); text-decoration: none; }
                    .name a:hover { text-decoration: underline; }
                    .name {
                        max-width: 0;
                        overflow-wrap: anywhere;
                        word-break: break-word;
                    }
                    .size, .updated { white-space: nowrap; color: var(--muted); font-size: .9rem; }
                    .actions { text-align: right; white-space: nowrap; }
                    .copy-btn {
                        border: 1px solid var(--border);
                        background: #fff;
                        color: #0f172a;
                        border-radius: 10px;
                        padding: .35rem .6rem;
                        margin-left: .35rem;
                        cursor: pointer;
                        font-size: .82rem;
                    }
                    .copy-btn:hover { background: #eef5ff; border-color: #bfd7ff; }
                    .toast {
                        position: fixed;
                        right: 1rem;
                        bottom: 1rem;
                        background: #0f172a;
                        color: #fff;
                        padding: .55rem .8rem;
                        border-radius: 10px;
                        opacity: 0;
                        transition: opacity .2s ease;
                        font-size: .9rem;
                        pointer-events: none;
                    }
                    .toast.show { opacity: .95; }
                    .empty { padding: 1.5rem 1.2rem; color: var(--muted); }
                </style>
            </head>
            <body>
                <div class="wrap">
                    <div class="card">
                        <div class="head">
                            <h1>63xky File Server</h1>
                            <div class="meta">Shared directory: {{ shared_dir }} | Port: {{ port }} | Folder navigation: {{ "On" if include_subdirs else "Off" }}</div>
                            <div class="meta">Current path: /{{ current_rel if current_rel else "" }}</div>
                        </div>
                        <div style="padding:.65rem 1rem; border-bottom:1px solid var(--border); background:#fbfdff;">
                            {% if parent_rel is not none %}
                                <a href="{{ url_for('index', dir=parent_rel) }}" style="margin-right:1rem; color:var(--accent); text-decoration:none;">&larr; Up</a>
                            {% endif %}
                            <span style="color:var(--muted); font-size:.9rem;">
                                {% for crumb in breadcrumbs %}
                                    {% if not loop.first %}/ {% endif %}
                                    {% if crumb.link is not none %}
                                        <a href="{{ url_for('index', dir=crumb.link) }}" style="color:var(--accent); text-decoration:none;">{{ crumb.name }}</a>
                                    {% else %}
                                        {{ crumb.name }}
                                    {% endif %}
                                {% endfor %}
                            </span>
                        </div>
                        {% if entries %}
                            <div class="table-wrap">
                                <table>
                                    <thead>
                                        <tr>
                                            <th>Name</th>
                                            <th>Type</th>
                                            <th>Size</th>
                                            <th>Updated</th>
                                            <th style="text-align:right;">Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {% for item in entries %}
                                            <tr>
                                                <td class="name">
                                                    {% if item.is_dir %}
                                                        <a href='{{ url_for("index", dir=item.path) }}'>{{ item.display_name }}/</a>
                                                    {% else %}
                                                        <a href='{{ url_for("download", filename=item.path) }}'>{{ item.display_name }}</a>
                                                    {% endif %}
                                                </td>
                                                <td class="size">{{ item.kind }}</td>
                                                <td class="size">{{ item.size_human }}</td>
                                                <td class="updated">{{ item.updated }}</td>
                                                <td class="actions">
                                                    {% if not item.is_dir %}
                                                        {% set download_url = request.url_root.rstrip('/') ~ url_for("download", filename=item.path) %}
                                                        <button class="copy-btn" data-url="{{ download_url }}" data-name="{{ item.display_name }}" data-kind="curl" onclick="copyCommand(this)" title="Copy curl command">📋 curl</button>
                                                        <button class="copy-btn" data-url="{{ download_url }}" data-name="{{ item.display_name }}" data-kind="ps" onclick="copyCommand(this)" title="Copy PowerShell command">📋 ps</button>
                                                    {% endif %}
                                                </td>
                                            </tr>
                                        {% endfor %}
                                    </tbody>
                                </table>
                            </div>
                        {% else %}
                            <div class="empty"><em>No files available.</em></div>
                        {% endif %}
                    </div>
                </div>
                <div id="toast" class="toast">Copied</div>
                <script>
                    function copyCommand(btn) {
                        const url = btn.dataset.url;
                        const name = (btn.dataset.name || "download.bin").replace(/"/g, "");
                        const kind = btn.dataset.kind;
                        let cmd = "";
                        if (kind === "ps") {
                            cmd = `Invoke-WebRequest -Uri "${url}" -OutFile "${name}"`;
                        } else {
                            cmd = `curl.exe -L "${url}" -o "${name}"`;
                        }
                        copyText(cmd)
                            .then(() => showToast("Copied " + kind + " command"))
                            .catch(() => {
                                showToast("Clipboard unavailable. Copy manually.");
                                window.prompt("Copy command:", cmd);
                            });
                    }
                    function copyText(text) {
                        if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
                            return navigator.clipboard.writeText(text);
                        }
                        return new Promise((resolve, reject) => {
                            try {
                                const ta = document.createElement("textarea");
                                ta.value = text;
                                ta.setAttribute("readonly", "");
                                ta.style.position = "fixed";
                                ta.style.opacity = "0";
                                ta.style.left = "-9999px";
                                document.body.appendChild(ta);
                                ta.focus();
                                ta.select();
                                const ok = document.execCommand("copy");
                                document.body.removeChild(ta);
                                if (ok) resolve();
                                else reject(new Error("copy failed"));
                            } catch (err) {
                                reject(err);
                            }
                        });
                    }
                    function showToast(text) {
                        const toast = document.getElementById("toast");
                        toast.textContent = text;
                        toast.classList.add("show");
                        setTimeout(() => toast.classList.remove("show"), 1300);
                    }
                </script>
            </body>
        </html>
        """
        return render_template_string(
            html,
            entries=entries,
            shared_dir=str(share_dir),
            include_subdirs=include_subdirs,
            port=runtime_state.get_port(),
            current_rel=current_rel,
            parent_rel=parent_rel,
            breadcrumbs=breadcrumbs,
        )

    @app.route("/files/<path:filename>")
    def download(filename: str):  # type: ignore[no-untyped-def]
        share_dir = runtime_state.get_share_dir()
        if not runtime_state.get_allow_subdirectories() and ("/" in filename or "\\" in filename):
            abort(403)
        try:
            file_path = safe_resolve_file(share_dir, filename)
        except ValueError:
            abort(403)
        except FileNotFoundError:
            abort(404)

        size = file_path.stat().st_size
        start = 0
        end = size - 1
        partial = False
        range_header = request.headers.get("Range")
        if range_header:
            match = RANGE_RE.match(range_header.strip())
            if not match:
                abort(416)
            start = int(match.group(1))
            if match.group(2):
                end = int(match.group(2))
            if start > end or start >= size:
                abort(416)
            partial = True
        length = end - start + 1
        key = f"{threading.get_ident()}:{filename}:{time.time()}"

        def generate():
            metrics.start(key, os.path.basename(filename))
            try:
                with file_path.open("rb") as handle:
                    handle.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = handle.read(min(8192, remaining))
                        if not chunk:
                            break
                        yield chunk
                        metrics.update(key, len(chunk))
                        remaining -= len(chunk)
            finally:
                metrics.stop(key)

        headers = {
            "Content-Disposition": f'attachment; filename="{Path(filename).name}"',
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
        }
        if partial:
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"

        return Response(
            stream_with_context(generate()),
            status=206 if partial else 200,
            headers=headers,
            mimetype="application/octet-stream",
        )

    @app.route("/admin/logs")
    def admin_logs():  # type: ignore[no-untyped-def]
        if not settings.admin_routes_enabled:
            abort(404)
        if not is_loopback_remote(request.remote_addr):
            abort(403)
        return send_from_directory(settings.app_paths.log_file.parent, settings.app_paths.log_file.name, as_attachment=True)

    @app.route("/admin/blacklist", methods=["GET", "POST"])
    def admin_blacklist():  # type: ignore[no-untyped-def]
        if not settings.admin_routes_enabled:
            abort(404)
        if not is_loopback_remote(request.remote_addr):
            abort(403)

        if request.method == "POST":
            payload = request.get_json(silent=True) or {}
            ip = str(payload.get("ip", "")).strip()
            action = str(payload.get("action", "add")).strip().lower()
            if not validate_ip_address(ip):
                return jsonify({"error": "Invalid IP address"}), 400
            if action == "remove":
                blacklist_store.remove(ip)
            else:
                blacklist_store.add(ip)

        return jsonify({"blacklist": blacklist_store.entries()})

    return app


def _scan_directory(current_dir: Path, *, share_dir: Path, include_subdirs: bool) -> list[dict[str, str | bool]]:
    rows: list[dict[str, str | bool]] = []
    candidates = list(current_dir.iterdir())
    for path in sorted(candidates, key=lambda p: (not p.is_dir(), p.name.lower())):
        if path.is_dir() and not include_subdirs and path != share_dir:
            continue
        stat = path.stat()
        rel = str(path.relative_to(share_dir)).replace("\\", "/")
        is_dir = path.is_dir()
        rows.append(
            {
                "path": rel,
                "display_name": path.name,
                "kind": "Folder" if is_dir else "File",
                "size_human": "-" if is_dir else _human_size(stat.st_size),
                "updated": time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)),
                "is_dir": is_dir,
            }
        )
    return rows


def _human_size(num: int) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0:
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{value:.2f} PB"


def _resolve_browse_dir(share_dir: Path, requested_rel: str) -> tuple[Path, str]:
    rel = requested_rel.strip().strip("/")
    if not rel:
        return share_dir, ""
    candidate = (share_dir / rel).resolve()
    candidate.relative_to(share_dir)
    if not candidate.exists() or not candidate.is_dir():
        raise FileNotFoundError(str(candidate))
    return candidate, rel.replace("\\", "/")


def _parent_relative(current_rel: str) -> str | None:
    if not current_rel:
        return None
    parent = Path(current_rel).parent
    if str(parent) == ".":
        return ""
    return str(parent).replace("\\", "/")


def _build_breadcrumbs(current_rel: str) -> list[dict[str, str | None]]:
    crumbs: list[dict[str, str | None]] = [{"name": "root", "link": "" if current_rel else None}]
    if not current_rel:
        return crumbs
    parts = [p for p in current_rel.split("/") if p]
    accum: list[str] = []
    for i, part in enumerate(parts):
        accum.append(part)
        link = "/".join(accum)
        crumbs.append({"name": part, "link": None if i == len(parts) - 1 else link})
    return crumbs
