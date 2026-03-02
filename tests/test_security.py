import tempfile
import unittest
from pathlib import Path

from fileshare_app.core.security import safe_resolve_file


class SecurityTests(unittest.TestCase):
    def test_safe_resolve_file_allows_in_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "hello.txt"
            target.write_text("ok", encoding="utf-8")
            resolved = safe_resolve_file(root, "hello.txt")
            self.assertEqual(resolved, target.resolve())

    def test_safe_resolve_file_blocks_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            root.mkdir(parents=True)
            outside = Path(tmp) / "secret.txt"
            outside.write_text("secret", encoding="utf-8")
            with self.assertRaises(ValueError):
                safe_resolve_file(root, "../secret.txt")


if __name__ == "__main__":
    unittest.main()
