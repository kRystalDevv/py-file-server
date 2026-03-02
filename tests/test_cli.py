import unittest

from fileshare_app.cli import namespace_to_overrides, parse_args


class CliTests(unittest.TestCase):
    def test_cli_overrides_mapping(self) -> None:
        ns = parse_args(
            [
                "--mode",
                "public",
                "--host",
                "0.0.0.0",
                "--port",
                "5050",
                "--directory",
                "files",
                "--tunnel",
                "on",
                "--no-browser",
                "--admin-routes",
                "--no-monitor",
            ]
        )
        overrides = namespace_to_overrides(ns)
        self.assertEqual(overrides["mode"], "public")
        self.assertEqual(overrides["host"], "0.0.0.0")
        self.assertEqual(overrides["port"], 5050)
        self.assertEqual(overrides["directory"], "files")
        self.assertEqual(overrides["tunnel"], "on")
        self.assertIs(overrides["open_browser"], False)
        self.assertIs(overrides["admin_routes"], True)
        self.assertIs(overrides["monitor"], False)


if __name__ == "__main__":
    unittest.main()
