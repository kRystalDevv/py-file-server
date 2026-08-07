import logging
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from fileshare_app.core.config import build_settings
from fileshare_app.core.metrics import TransferMetrics
from fileshare_app.core.security import BlacklistStore
from fileshare_app.services.server_manager import ServerManager


class _DummyServer:
    """Stands in for waitress' server: run() blocks until close() is called."""

    def __init__(self) -> None:
        self._stopped = threading.Event()

    def run(self) -> None:
        self._stopped.wait(timeout=5)

    def close(self) -> None:
        self._stopped.set()


def _build_manager(tmp_path: Path, **overrides) -> ServerManager:
    share = tmp_path / "share"
    share.mkdir(exist_ok=True)
    cfg = tmp_path / "settings.json"
    payload = {
        "mode": "lan",
        "host": "127.0.0.1",
        "port": 0,
        "directory": str(share),
        "tunnel": "off",
        "threads": 4,
        "max_downloads": 1,
    }
    payload.update(overrides)
    settings = build_settings(payload, config_path_override=cfg)
    logger = logging.getLogger("test_server_manager")
    metrics = TransferMetrics()
    blacklist_store = BlacklistStore(settings.app_paths.blacklist_file)
    return ServerManager(settings, logger=logger, metrics=metrics, blacklist_store=blacklist_store)


def _patched_manager(tmp_path: Path, **overrides):
    manager = _build_manager(tmp_path, **overrides)
    patches = [
        patch("fileshare_app.services.server_manager.create_server", return_value=_DummyServer()),
        patch("fileshare_app.services.server_manager._wait_for_local_listener", return_value=True),
        patch("fileshare_app.services.server_manager.resolve_listen_port", side_effect=lambda host, port: port),
    ]
    return manager, patches


class ServerManagerTests(unittest.TestCase):
    def test_start_returns_running_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager, patches = _patched_manager(Path(tmp))
            with patches[0], patches[1], patches[2]:
                snapshot = manager.start()
            try:
                self.assertTrue(snapshot.running)
                self.assertIsNone(snapshot.server_error)
                self.assertEqual(snapshot.bind_port, 0)
            finally:
                manager.stop()

    def test_start_is_idempotent_while_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager, patches = _patched_manager(Path(tmp))
            with patches[0] as create_mock, patches[1], patches[2]:
                manager.start()
                manager.start()
                self.assertEqual(create_mock.call_count, 1)
            manager.stop()

    def test_stop_when_not_started_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = _build_manager(Path(tmp))
            manager.stop()

    def test_restart_on_port_switches_port_and_stops_previous_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager, patches = _patched_manager(Path(tmp))
            first_server = _DummyServer()
            second_server = _DummyServer()
            create_patch = patch(
                "fileshare_app.services.server_manager.create_server",
                side_effect=[first_server, second_server],
            )
            with create_patch, patches[1], patches[2]:
                manager.start()
                snapshot = manager.restart_on_port(9001)
            try:
                self.assertEqual(snapshot.bind_port, 9001)
                self.assertTrue(first_server._stopped.is_set())
            finally:
                manager.stop()

    def test_restart_on_same_port_while_running_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager, patches = _patched_manager(Path(tmp), port=8123)
            with patches[0] as create_mock, patches[1], patches[2]:
                manager.start()
                manager.restart_on_port(8123)
                self.assertEqual(create_mock.call_count, 1)
            manager.stop()

    def test_toggle_subdirectories_delegates_to_runtime_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = _build_manager(Path(tmp))
            enabled = manager.toggle_subdirectories()
            self.assertEqual(enabled, manager.runtime_state.get_allow_subdirectories())
            self.assertFalse(enabled)

    def test_cycle_log_verbosity_delegates_to_runtime_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = _build_manager(Path(tmp))
            level = manager.cycle_log_verbosity()
            self.assertEqual(level, manager.runtime_state.get_log_verbosity())

    def test_set_share_directory_updates_runtime_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = _build_manager(Path(tmp))
            new_dir = Path(tmp) / "other_share"
            updated = manager.set_share_directory(new_dir)
            self.assertEqual(updated, manager.runtime_state.get_share_dir())
            self.assertTrue(new_dir.resolve() == updated)

    def test_concurrent_start_calls_create_server_only_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager, patches = _patched_manager(Path(tmp))
            with patches[0] as create_mock, patches[1], patches[2]:
                threads = [threading.Thread(target=manager.start) for _ in range(8)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join(timeout=5)
                self.assertEqual(create_mock.call_count, 1)
            manager.stop()

    def test_primary_local_url_falls_back_to_browser_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = _build_manager(Path(tmp))
            url = manager.primary_local_url()
            self.assertTrue(url.startswith("http://"))


if __name__ == "__main__":
    unittest.main()
