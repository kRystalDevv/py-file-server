import logging
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fileshare_app.app import RuntimeBootstrap, run, run_textual_ui
from fileshare_app.core.config import build_settings
from fileshare_app.core.metrics import TransferMetrics
from fileshare_app.core.security import BlacklistStore


def _run_with_flags(*flags: str) -> tuple:
    with tempfile.TemporaryDirectory() as tmp:
        with patch("fileshare_app.app.run_textual_ui", return_value=0) as textual_mock, patch(
            "fileshare_app.app.run_legacy_cli", return_value=0
        ) as legacy_mock:
            run(
                [
                    "--mode",
                    "local",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "0",
                    "--directory",
                    tmp,
                    "--tunnel",
                    "off",
                    *flags,
                ]
            )
        return textual_mock, legacy_mock


class RunDispatchTests(unittest.TestCase):
    def test_no_flags_launches_textual_ui(self) -> None:
        textual_mock, legacy_mock = _run_with_flags()
        self.assertTrue(textual_mock.called)
        self.assertFalse(legacy_mock.called)

    def test_legacy_cli_flag_launches_legacy_cli(self) -> None:
        textual_mock, legacy_mock = _run_with_flags("--legacy-cli")
        self.assertFalse(textual_mock.called)
        self.assertTrue(legacy_mock.called)

    def test_no_ui_flag_launches_legacy_cli(self) -> None:
        textual_mock, legacy_mock = _run_with_flags("--no-ui")
        self.assertFalse(textual_mock.called)
        self.assertTrue(legacy_mock.called)

    def test_tray_flag_launches_tray_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("fileshare_app.app.run_textual_ui", return_value=0) as textual_mock, patch(
                "fileshare_app.app.run_legacy_cli", return_value=0
            ) as legacy_mock, patch("fileshare_app.tray.run_tray", return_value=0) as tray_mock:
                run(
                    [
                        "--mode",
                        "local",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "0",
                        "--directory",
                        tmp,
                        "--tunnel",
                        "off",
                        "--tray",
                    ]
                )
        self.assertTrue(tray_mock.called)
        self.assertFalse(textual_mock.called)
        self.assertFalse(legacy_mock.called)

    def test_tray_flag_takes_priority_over_legacy_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("fileshare_app.app.run_legacy_cli", return_value=0) as legacy_mock, patch(
                "fileshare_app.tray.run_tray", return_value=0
            ) as tray_mock:
                run(
                    [
                        "--mode",
                        "local",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "0",
                        "--directory",
                        tmp,
                        "--tunnel",
                        "off",
                        "--tray",
                        "--legacy-cli",
                    ]
                )
        self.assertTrue(tray_mock.called)
        self.assertFalse(legacy_mock.called)


def _build_bootstrap(tmp_path: Path) -> RuntimeBootstrap:
    share = tmp_path / "share"
    share.mkdir()
    cfg = tmp_path / "settings.json"
    settings = build_settings(
        {"mode": "local", "host": "127.0.0.1", "port": 0, "directory": str(share), "tunnel": "off"},
        config_path_override=cfg,
    )
    return RuntimeBootstrap(
        args=None,
        settings=settings,
        logger=logging.getLogger("test_app_dispatch"),
        metrics=TransferMetrics(),
        blacklist_store=BlacklistStore(settings.app_paths.blacklist_file),
    )


class TextualFallbackTests(unittest.TestCase):
    def test_textual_import_error_falls_back_to_legacy_cli(self) -> None:
        # Simulate "textual not installed": fileshare_app.ui.app itself imports
        # `from textual.app import App` at module level, so in reality the
        # ImportError happens right at `from .ui.app import OperatorConsoleApp`
        # in run_textual_ui, before any OperatorConsoleApp is ever constructed.
        # Blocking the module in sys.modules reproduces exactly that failure
        # point rather than a deeper, unrealistic one.
        with tempfile.TemporaryDirectory() as tmp:
            bootstrap = _build_bootstrap(Path(tmp))
            with patch("fileshare_app.app.run_legacy_cli", return_value=42) as legacy_mock, patch.dict(
                sys.modules, {"fileshare_app.ui.app": None, "fileshare_app.ui": None}
            ):
                rc = run_textual_ui(bootstrap)

        self.assertTrue(legacy_mock.called)
        self.assertEqual(rc, 42)


if __name__ == "__main__":
    unittest.main()
