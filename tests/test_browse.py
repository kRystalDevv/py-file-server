import tempfile
import unittest
from pathlib import Path

from fileshare_app.core.server import _parent_relative, _resolve_browse_dir


class BrowseTests(unittest.TestCase):
    def test_resolve_browse_dir_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            cur, rel = _resolve_browse_dir(root, "")
            self.assertEqual(cur, root)
            self.assertEqual(rel, "")

    def test_resolve_browse_dir_nested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            nested = root / "a" / "b"
            nested.mkdir(parents=True)
            cur, rel = _resolve_browse_dir(root, "a/b")
            self.assertEqual(cur, nested.resolve())
            self.assertEqual(rel, "a/b")

    def test_resolve_browse_dir_blocks_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with self.assertRaises(ValueError):
                _resolve_browse_dir(root, "../x")

    def test_parent_relative(self) -> None:
        self.assertIsNone(_parent_relative(""))
        self.assertEqual(_parent_relative("a"), "")
        self.assertEqual(_parent_relative("a/b"), "a")


if __name__ == "__main__":
    unittest.main()
