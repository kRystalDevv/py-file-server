import logging
import subprocess
import threading
import unittest
from unittest.mock import MagicMock, patch

from fileshare_app.services.cloudflare_manager import CloudflareManager, CloudflareState
from fileshare_app.core.tunnel import TunnelError


def _manager() -> CloudflareManager:
    return CloudflareManager(logging.getLogger("test_cloudflare_manager"))


class CloudflareManagerNotInstalledTests(unittest.TestCase):
    def test_detect_reports_not_installed_when_binary_missing(self) -> None:
        manager = _manager()
        with patch("fileshare_app.services.cloudflare_manager.shutil.which", return_value=None):
            snapshot = manager.detect()
        self.assertEqual(snapshot.state, CloudflareState.NOT_INSTALLED)
        self.assertFalse(snapshot.installed)

    def test_start_public_mode_is_noop_when_not_installed(self) -> None:
        manager = _manager()
        with patch("fileshare_app.services.cloudflare_manager.shutil.which", return_value=None):
            snapshot = manager.start_public_mode(port=8080)
        self.assertEqual(snapshot.state, CloudflareState.NOT_INSTALLED)


class CloudflareManagerInstalledTests(unittest.TestCase):
    def setUp(self) -> None:
        self._which_patch = patch(
            "fileshare_app.services.cloudflare_manager.shutil.which", return_value="/usr/bin/cloudflared"
        )
        self._which_patch.start()
        self.addCleanup(self._which_patch.stop)

        self._version_patch = patch.object(CloudflareManager, "_read_version", return_value="cloudflared v1.0")
        self._version_patch.start()
        self.addCleanup(self._version_patch.stop)

    def test_detect_reports_installed_not_configured_when_no_cert(self) -> None:
        manager = _manager()
        with patch.object(CloudflareManager, "_is_configured", return_value=False):
            snapshot = manager.detect()
        self.assertEqual(snapshot.state, CloudflareState.INSTALLED_NOT_CONFIGURED)
        self.assertTrue(snapshot.installed)
        self.assertFalse(snapshot.configured)

    def test_detect_reports_ready_when_configured(self) -> None:
        manager = _manager()
        with patch.object(CloudflareManager, "_is_configured", return_value=True):
            snapshot = manager.detect()
        self.assertEqual(snapshot.state, CloudflareState.READY)

    def test_start_public_mode_requires_setup_first(self) -> None:
        manager = _manager()
        with patch.object(CloudflareManager, "_is_configured", return_value=False):
            snapshot = manager.start_public_mode(port=8080)
        self.assertEqual(snapshot.state, CloudflareState.INSTALLED_NOT_CONFIGURED)
        self.assertIn("Setup required", snapshot.message)

    def test_start_public_mode_delegates_to_tunnel_manager_and_reports_running(self) -> None:
        manager = _manager()
        fake_process = MagicMock()
        fake_process.poll.return_value = None

        def _fake_start(*, enabled: bool, port: int) -> str:
            manager._tunnel.state.process = fake_process
            manager._tunnel.state.url = "https://example.trycloudflare.com"
            return "https://example.trycloudflare.com"

        manager._tunnel.start = MagicMock(side_effect=_fake_start)

        with patch.object(CloudflareManager, "_is_configured", return_value=True):
            snapshot = manager.start_public_mode(port=8080)

        manager._tunnel.start.assert_called_once_with(enabled=True, port=8080)
        self.assertEqual(snapshot.state, CloudflareState.RUNNING)
        self.assertEqual(snapshot.public_url, "https://example.trycloudflare.com")

    def test_start_public_mode_reports_error_on_tunnel_failure(self) -> None:
        manager = _manager()
        manager._tunnel.start = MagicMock(side_effect=TunnelError("boom"))

        with patch.object(CloudflareManager, "_is_configured", return_value=True):
            snapshot = manager.start_public_mode(port=8080)

        self.assertEqual(snapshot.state, CloudflareState.ERROR)
        self.assertIn("boom", snapshot.message)

    def test_start_public_mode_is_idempotent_when_already_running(self) -> None:
        manager = _manager()
        fake_process = MagicMock()
        fake_process.poll.return_value = None

        def _fake_start(*, enabled: bool, port: int) -> str:
            manager._tunnel.state.process = fake_process
            manager._tunnel.state.url = "https://example.trycloudflare.com"
            return "https://example.trycloudflare.com"

        manager._tunnel.start = MagicMock(side_effect=_fake_start)

        with patch.object(CloudflareManager, "_is_configured", return_value=True):
            manager.start_public_mode(port=8080)
            manager._tunnel.start.reset_mock()
            snapshot = manager.start_public_mode(port=8080)

        manager._tunnel.start.assert_not_called()
        self.assertEqual(snapshot.state, CloudflareState.RUNNING)
        self.assertIn("already running", snapshot.message)

    def test_stop_public_mode_delegates_to_tunnel_manager(self) -> None:
        manager = _manager()
        manager._tunnel.stop = MagicMock()
        with patch.object(CloudflareManager, "_is_configured", return_value=True):
            snapshot = manager.stop_public_mode()
        manager._tunnel.stop.assert_called_once()
        self.assertEqual(snapshot.state, CloudflareState.READY)
        self.assertIsNone(snapshot.public_url)

    def test_get_public_url_reads_through_snapshot(self) -> None:
        manager = _manager()
        fake_process = MagicMock()
        fake_process.poll.return_value = None
        manager._tunnel.state.process = fake_process
        manager._tunnel.state.url = "https://example.trycloudflare.com"
        with patch.object(CloudflareManager, "_is_configured", return_value=True):
            url = manager.get_public_url()
        self.assertEqual(url, "https://example.trycloudflare.com")


class CloudflareManagerThreadSafetyTests(unittest.TestCase):
    def test_concurrent_detect_calls_do_not_raise(self) -> None:
        manager = _manager()
        errors: list[Exception] = []

        def _detect() -> None:
            try:
                with patch("fileshare_app.services.cloudflare_manager.shutil.which", return_value=None):
                    manager.detect()
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [threading.Thread(target=_detect) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
