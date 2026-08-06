import logging
import os
import unittest
from unittest.mock import MagicMock, patch

import fileshare_app.tray as tray
from fileshare_app.services.cloudflare_manager import CloudflareSnapshot, CloudflareState
from fileshare_app.services.server_manager import ServerSnapshot
from fileshare_app.services.transfer_store import TransferSnapshot


def _server_snapshot(**overrides) -> ServerSnapshot:
    defaults = dict(
        running=True,
        bind_host="127.0.0.1",
        bind_port=8080,
        bind_url="http://127.0.0.1:8080",
        browser_url="http://127.0.0.1:8080",
        local_urls=["http://127.0.0.1:8080"],
        share_dir="/tmp/share",
        allow_subdirectories=True,
        log_verbosity="medium",
        server_error=None,
    )
    defaults.update(overrides)
    return ServerSnapshot(**defaults)


def _cloudflare_snapshot(**overrides) -> CloudflareSnapshot:
    defaults = dict(
        state=CloudflareState.NOT_INSTALLED,
        installed=False,
        configured=False,
        running=False,
        binary_path=None,
        version=None,
        public_url=None,
        message="not installed",
        quick_tunnel_warning=None,
    )
    defaults.update(overrides)
    return CloudflareSnapshot(**defaults)


class GuardedImportFallbackTests(unittest.TestCase):
    """Covers the thing most likely to regress: the pystray/PIL import guard.

    pystray probes for a platform backend at import time (e.g. connects to an
    X11 display via Xlib on Linux), so on a headless CI runner the failure is
    not ImportError but something backend-specific. The guard in tray.py must
    catch broadly, not just ImportError, or the whole module blows up on
    import in exactly the environment (headless Linux CI) this repo's own
    tests.yml runs in.
    """

    def test_is_available_false_when_pystray_missing(self) -> None:
        with patch.object(tray, "pystray", None), patch.object(tray, "Image", None):
            self.assertFalse(tray.is_available())

    def test_is_available_true_when_both_present(self) -> None:
        with patch.object(tray, "pystray", MagicMock()), patch.object(tray, "Image", MagicMock()):
            self.assertTrue(tray.is_available())

    def test_is_available_false_when_only_pystray_present(self) -> None:
        with patch.object(tray, "pystray", MagicMock()), patch.object(tray, "Image", None):
            self.assertFalse(tray.is_available())

    def test_module_reload_survives_non_import_error_from_pystray(self) -> None:
        # Reproduces the headless-CI failure mode for real: reload the actual
        # module with __import__ patched to raise a non-ImportError (mirroring
        # Xlib.error.DisplayNameError) specifically for "pystray". If tray.py's
        # guard only caught ImportError, this reload would raise and the test
        # would error out instead of passing.
        import builtins
        import importlib

        real_import = builtins.__import__

        def _raising_import(name, *args, **kwargs):
            if name == "pystray":
                raise RuntimeError("simulated backend probe failure (e.g. no X11 display)")
            return real_import(name, *args, **kwargs)

        try:
            with patch.object(builtins, "__import__", side_effect=_raising_import):
                importlib.reload(tray)
            self.assertIsNone(tray.pystray)
            self.assertIsNone(tray.Image)
            self.assertFalse(tray.is_available())
        finally:
            importlib.reload(tray)  # restore normal module state for later tests


class StartupToggleNonWindowsTests(unittest.TestCase):
    """On non-Windows, winreg is None, so these are a documented no-op."""

    def test_is_startup_enabled_false_without_winreg(self) -> None:
        with patch.object(tray, "winreg", None):
            self.assertFalse(tray._is_startup_enabled())

    def test_set_startup_enabled_false_without_winreg(self) -> None:
        with patch.object(tray, "winreg", None):
            self.assertFalse(tray._set_startup_enabled(True))


class StartupToggleWindowsTests(unittest.TestCase):
    """Simulates winreg on a Windows-like environment via a mock module."""

    def setUp(self) -> None:
        self.fake_winreg = MagicMock()
        self.fake_winreg.HKEY_CURRENT_USER = "HKCU"
        self.fake_winreg.KEY_READ = "READ"
        self.fake_winreg.KEY_SET_VALUE = "SET_VALUE"
        self.fake_winreg.REG_SZ = "REG_SZ"
        self._patch = patch.object(tray, "winreg", self.fake_winreg)
        self._patch.start()
        self.addCleanup(self._patch.stop)

    def test_is_startup_enabled_true_when_value_present(self) -> None:
        fake_key = MagicMock()
        self.fake_winreg.OpenKey.return_value = fake_key
        self.fake_winreg.QueryValueEx.return_value = ("value", 1)
        self.assertTrue(tray._is_startup_enabled())
        self.fake_winreg.CloseKey.assert_called_once_with(fake_key)

    def test_is_startup_enabled_false_when_value_missing(self) -> None:
        fake_key = MagicMock()
        self.fake_winreg.OpenKey.return_value = fake_key
        self.fake_winreg.QueryValueEx.side_effect = FileNotFoundError
        self.assertFalse(tray._is_startup_enabled())

    def test_is_startup_enabled_false_when_key_cannot_open(self) -> None:
        self.fake_winreg.OpenKey.side_effect = OSError
        self.assertFalse(tray._is_startup_enabled())

    def test_set_startup_enabled_true_writes_value(self) -> None:
        fake_key = MagicMock()
        self.fake_winreg.OpenKey.return_value = fake_key
        with patch("sys.frozen", False, create=True):
            result = tray._set_startup_enabled(True)
        self.assertTrue(result)
        self.fake_winreg.SetValueEx.assert_called_once()

    def test_set_startup_enabled_false_deletes_value(self) -> None:
        fake_key = MagicMock()
        self.fake_winreg.OpenKey.return_value = fake_key
        result = tray._set_startup_enabled(False)
        self.assertTrue(result)
        self.fake_winreg.DeleteValue.assert_called_once()

    def test_set_startup_enabled_missing_value_on_delete_is_not_an_error(self) -> None:
        fake_key = MagicMock()
        self.fake_winreg.OpenKey.return_value = fake_key
        self.fake_winreg.DeleteValue.side_effect = FileNotFoundError
        result = tray._set_startup_enabled(False)
        self.assertTrue(result)

    def test_set_startup_enabled_returns_false_on_oserror(self) -> None:
        self.fake_winreg.OpenKey.side_effect = OSError
        self.assertFalse(tray._set_startup_enabled(True))


class RunTrayUnavailableTests(unittest.TestCase):
    def test_run_tray_returns_error_code_when_dependencies_missing(self) -> None:
        bootstrap = MagicMock()
        with patch.object(tray, "is_available", return_value=False), patch.object(
            tray, "_ensure_detached"
        ):
            rc = tray.run_tray(bootstrap)
        self.assertEqual(rc, 2)


class _FakeMenuItem:
    def __init__(self, text=None, action=None, *submenu, enabled=True, checked=None, **kwargs):
        self.text = text
        self.action = action
        self.submenu = submenu
        self.enabled = enabled
        self.checked = checked


class _FakeMenu(list):
    SEPARATOR = "__SEPARATOR__"

    def __init__(self, *items):
        super().__init__(items)


class _FakePystrayModule:
    MenuItem = _FakeMenuItem
    Menu = _FakeMenu
    Icon = MagicMock


class TrayAppMenuTests(unittest.TestCase):
    def setUp(self) -> None:
        self._patch = patch.object(tray, "pystray", _FakePystrayModule)
        self._patch.start()
        self.addCleanup(self._patch.stop)

        self.settings = MagicMock(mode="lan")
        self.server_manager = MagicMock()
        self.server_manager.snapshot.return_value = _server_snapshot()
        self.cloudflare_manager = MagicMock()
        self.cloudflare_manager.snapshot.return_value = _cloudflare_snapshot()
        self.transfer_store = MagicMock()
        self.transfer_store.refresh.return_value = TransferSnapshot(active=[], recent=[], total_uploaded=0)
        self.log_bridge = MagicMock()
        self.qr_manager = MagicMock()

        self.app = tray.TrayApp(
            settings=self.settings,
            server_manager=self.server_manager,
            cloudflare_manager=self.cloudflare_manager,
            transfer_store=self.transfer_store,
            log_bridge=self.log_bridge,
            qr_manager=self.qr_manager,
            logger=logging.getLogger("test_tray"),
        )

    def test_build_menu_includes_core_sections(self) -> None:
        with patch.object(tray, "_is_startup_enabled", return_value=False):
            menu = self.app._build_menu()
        labels = [item.text for item in menu if isinstance(item, _FakeMenuItem)]
        self.assertIn("Server Status", labels)
        self.assertIn("Transfers", labels)
        self.assertIn("Open in Browser", labels)
        self.assertIn("Show QR Code", labels)
        self.assertIn("Start at Login", labels)
        self.assertIn("Exit", labels)

    def test_build_menu_omits_public_url_when_not_running(self) -> None:
        with patch.object(tray, "_is_startup_enabled", return_value=False):
            menu = self.app._build_menu()
        server_status = next(item for item in menu if item.text == "Server Status")
        server_lines = [sub.text for sub in server_status.action]
        self.assertFalse(any(line.startswith("Public:") for line in server_lines))

    def test_build_menu_includes_public_url_when_running(self) -> None:
        self.cloudflare_manager.snapshot.return_value = _cloudflare_snapshot(
            state=CloudflareState.RUNNING, running=True, public_url="https://example.trycloudflare.com"
        )
        with patch.object(tray, "_is_startup_enabled", return_value=False):
            menu = self.app._build_menu()
        server_status = next(item for item in menu if item.text == "Server Status")
        server_lines = [sub.text for sub in server_status.action]
        self.assertTrue(any("https://example.trycloudflare.com" in line for line in server_lines))

    def test_build_menu_lists_active_transfers(self) -> None:
        from fileshare_app.services.transfer_store import TransferRecord

        self.transfer_store.refresh.return_value = TransferSnapshot(
            active=[
                TransferRecord(
                    filename="file.bin",
                    bytes_sent=1024,
                    elapsed_seconds=2.0,
                    rate_bps=512.0,
                    started_at=0.0,
                )
            ],
            recent=[],
            total_uploaded=1024,
        )
        with patch.object(tray, "_is_startup_enabled", return_value=False):
            menu = self.app._build_menu()
        transfers = next(item for item in menu if item.text == "Transfers")
        transfer_lines = [sub.text for sub in transfers.action]
        self.assertTrue(any("file.bin" in line for line in transfer_lines))
        self.assertTrue(any(line.startswith("Active: 1 transfer") for line in transfer_lines))

    def test_on_open_browser_prefers_public_url(self) -> None:
        self.cloudflare_manager.snapshot.return_value = _cloudflare_snapshot(
            state=CloudflareState.RUNNING, running=True, public_url="https://example.trycloudflare.com"
        )
        with patch("fileshare_app.tray.webbrowser.open") as open_mock:
            self.app._on_open_browser(None, None)
        open_mock.assert_called_once_with("https://example.trycloudflare.com")

    def test_on_open_browser_falls_back_to_local_url(self) -> None:
        with patch("fileshare_app.tray.webbrowser.open") as open_mock:
            self.app._on_open_browser(None, None)
        open_mock.assert_called_once_with(self.server_manager.snapshot.return_value.browser_url)

    def test_on_toggle_startup_flips_current_state(self) -> None:
        with patch.object(tray, "_is_startup_enabled", return_value=False), patch.object(
            tray, "_set_startup_enabled"
        ) as set_mock:
            self.app._on_toggle_startup(None, None)
        set_mock.assert_called_once_with(True)

    def test_on_exit_stops_icon_and_sets_stop_event(self) -> None:
        fake_icon = MagicMock()
        self.app._icon = fake_icon
        self.app._on_exit(None, None)
        self.assertTrue(self.app._stop_event.is_set())
        fake_icon.stop.assert_called_once()

    def test_cleanup_stops_services_even_if_one_raises(self) -> None:
        self.cloudflare_manager.stop_public_mode.side_effect = RuntimeError("boom")
        self.app._cleanup()
        self.server_manager.stop.assert_called_once()
        self.log_bridge.detach.assert_called_once()


class EnsureDetachedTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "this exercises the non-Windows no-op path")
    def test_ensure_detached_is_noop_on_non_windows(self) -> None:
        # Should return immediately without touching subprocess.
        with patch("fileshare_app.tray.subprocess.Popen") as popen_mock:
            tray._ensure_detached()
        popen_mock.assert_not_called()


class HumanBytesTests(unittest.TestCase):
    def test_human_bytes_formats_units(self) -> None:
        self.assertEqual(tray._human_bytes(512), "512.0 B")
        self.assertEqual(tray._human_bytes(2048), "2.0 KB")
        self.assertEqual(tray._human_bytes(1024 * 1024 * 3), "3.0 MB")


if __name__ == "__main__":
    unittest.main()
