import tempfile
import unittest
from pathlib import Path

from scripts.bump_version import bump_file, compute_next_version


class BumpVersionTests(unittest.TestCase):
    def test_compute_next_version_patch(self) -> None:
        self.assertEqual(compute_next_version("1.3.0", "patch"), "1.3.1")

    def test_compute_next_version_minor(self) -> None:
        self.assertEqual(compute_next_version("1.3.9", "minor"), "1.4.0")

    def test_compute_next_version_major(self) -> None:
        self.assertEqual(compute_next_version("1.3.9", "major"), "2.0.0")

    def test_bump_file_writes_new_version_and_preserves_rest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "__init__.py"
            path.write_text(
                '"""63xky file sharing application package."""\n'
                "\n"
                '__all__ = ["__version__"]\n'
                "\n"
                '__version__ = "1.3.0"\n',
                encoding="utf-8",
            )

            new_version = bump_file(path, "patch", dry_run=False)

            self.assertEqual(new_version, "1.3.1")
            text = path.read_text(encoding="utf-8")
            self.assertIn('__version__ = "1.3.1"', text)
            self.assertIn('"""63xky file sharing application package."""', text)
            self.assertIn('__all__ = ["__version__"]', text)

    def test_bump_file_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "__init__.py"
            original = '__version__ = "1.3.0"\n'
            path.write_text(original, encoding="utf-8")

            new_version = bump_file(path, "minor", dry_run=True)

            self.assertEqual(new_version, "1.4.0")
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_bump_file_rejects_malformed_version_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "__init__.py"
            path.write_text('__version__ = "not-a-version"\n', encoding="utf-8")

            with self.assertRaises(ValueError):
                bump_file(path, "patch", dry_run=True)

    def test_bump_file_rejects_multiple_version_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "__init__.py"
            path.write_text(
                '__version__ = "1.0.0"\n__version__ = "2.0.0"\n',
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                bump_file(path, "patch", dry_run=True)


if __name__ == "__main__":
    unittest.main()
