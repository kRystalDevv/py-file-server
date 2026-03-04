from __future__ import annotations

import ipaddress
import threading
from pathlib import Path


def is_loopback_remote(remote_addr: str | None) -> bool:
    if not remote_addr:
        return False
    try:
        ip = ipaddress.ip_address(remote_addr)
        if ip.version == 6 and getattr(ip, "ipv4_mapped", None):
            return ip.ipv4_mapped.is_loopback
        return ip.is_loopback
    except ValueError:
        return remote_addr.lower() == "localhost"


def validate_ip_address(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def safe_resolve_file(shared_root: Path, requested_path: str) -> Path:
    root = shared_root.resolve()
    candidate = (root / requested_path).resolve()
    candidate.relative_to(root)
    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError(str(candidate))
    return candidate


class BlacklistStore:
    def __init__(self, blacklist_file: Path) -> None:
        self.blacklist_file = blacklist_file
        self.blacklist_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.blacklist_file.exists():
            self.blacklist_file.write_text("", encoding="utf-8")
        self._lock = threading.Lock()
        self._entries = self._load()

    def _load(self) -> set[str]:
        data = self.blacklist_file.read_text(encoding="utf-8").splitlines()
        return {line.strip() for line in data if line.strip()}

    def save(self) -> None:
        with self._lock:
            payload = "\n".join(sorted(self._entries))
            self.blacklist_file.write_text(payload, encoding="utf-8")

    def contains(self, ip: str) -> bool:
        with self._lock:
            return ip in self._entries

    def add(self, ip: str) -> None:
        with self._lock:
            self._entries.add(ip)
        self.save()

    def remove(self, ip: str) -> None:
        with self._lock:
            self._entries.discard(ip)
        self.save()

    def entries(self) -> list[str]:
        with self._lock:
            return sorted(self._entries)
