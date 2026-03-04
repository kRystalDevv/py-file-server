import json
import tempfile
import unittest
from pathlib import Path

from fileshare_app.core.config import SettingsError, build_settings


class ConfigTests(unittest.TestCase):
    def test_invalid_host_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "settings.json"
            with self.assertRaises(SettingsError):
                build_settings(
                    {"host": "not-a-host", "mode": "lan", "directory": str(Path(tmp) / "share")},
                    config_path_override=cfg,
                )

    def test_invalid_port_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "settings.json"
            with self.assertRaises(SettingsError):
                build_settings(
                    {"port": 70000, "mode": "lan", "directory": str(Path(tmp) / "share")},
                    config_path_override=cfg,
                )

    def test_invalid_directory_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "settings.json"
            fake_dir = Path(tmp) / "not_a_dir"
            fake_dir.write_text("x", encoding="utf-8")
            with self.assertRaises(SettingsError):
                build_settings({"directory": str(fake_dir)}, config_path_override=cfg)

    def test_cli_overrides_do_not_persist_without_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cfg = tmp_path / "settings.json"
            share = tmp_path / "share"
            share.mkdir()
            payload = {
                "mode": "lan",
                "host": "0.0.0.0",
                "port": 8080,
                "directory": str(share),
                "tunnel": "off",
            }
            cfg.write_text(json.dumps(payload), encoding="utf-8")

            settings = build_settings(
                {"port": 9090, "mode": "local", "host": "127.0.0.1", "tunnel": "off"},
                config_path_override=cfg,
                persist_overrides=False,
            )
            self.assertEqual(settings.port, 9090)
            self.assertEqual(settings.mode, "local")

            reloaded = json.loads(cfg.read_text(encoding="utf-8"))
            self.assertEqual(reloaded["port"], 8080)
            self.assertEqual(reloaded["mode"], "lan")

    def test_public_mode_forces_tunnel_on(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "settings.json"
            share = Path(tmp) / "share"
            share.mkdir()
            cfg.write_text(
                json.dumps(
                    {
                        "mode": "public",
                        "host": "0.0.0.0",
                        "port": 8080,
                        "directory": str(share),
                        "tunnel": "off",
                    }
                ),
                encoding="utf-8",
            )
            settings = build_settings({}, config_path_override=cfg)
            self.assertTrue(settings.tunnel_enabled)

    def test_public_mode_rejects_explicit_tunnel_off(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "settings.json"
            with self.assertRaises(SettingsError):
                build_settings(
                    {"mode": "public", "host": "0.0.0.0", "directory": str(Path(tmp) / "share"), "tunnel": "off"},
                    config_path_override=cfg,
                )

    def test_lan_mode_uses_lan_host_and_port_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cfg = tmp_path / "settings.json"
            share = tmp_path / "share"
            share.mkdir()
            cfg.write_text(
                json.dumps(
                    {
                        "mode": "local",
                        "host": "127.0.0.1",
                        "port": 0,
                        "directory": str(share),
                        "tunnel": "off",
                    }
                ),
                encoding="utf-8",
            )
            settings = build_settings({"mode": "lan"}, config_path_override=cfg)
            self.assertEqual(settings.host, "0.0.0.0")
            self.assertEqual(settings.port, 63)

    def test_rejects_download_limit_that_can_starve_ui(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "settings.json"
            with self.assertRaises(SettingsError):
                build_settings(
                    {
                        "mode": "lan",
                        "host": "0.0.0.0",
                        "directory": str(Path(tmp) / "share"),
                        "threads": 8,
                        "max_downloads": 8,
                    },
                    config_path_override=cfg,
                )


if __name__ == "__main__":
    unittest.main()
