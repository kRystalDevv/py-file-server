import sys
import types
import unittest
from unittest.mock import patch

from fileshare_app.services.qr_manager import QRManager


class QRManagerUnavailableTests(unittest.TestCase):
    def test_available_is_false_without_qrcode_installed(self) -> None:
        with patch.dict(sys.modules, {"qrcode": None}):
            manager = QRManager()
        self.assertFalse(manager.available)

    def test_render_ascii_reports_missing_dependency(self) -> None:
        with patch.dict(sys.modules, {"qrcode": None}):
            manager = QRManager()
        result = manager.render_ascii("https://example.com")
        self.assertIn("qrcode", result)


class _FakeQRCode:
    def __init__(self, *, border: int = 2) -> None:
        self.border = border
        self._data = None

    def add_data(self, data: str) -> None:
        self._data = data

    def make(self, fit: bool = True) -> None:
        pass

    def get_matrix(self) -> list[list[bool]]:
        return [[bool((x + y) % 2) for x in range(21)] for y in range(21)]


class QRManagerAvailableTests(unittest.TestCase):
    def setUp(self) -> None:
        fake_qrcode = types.ModuleType("qrcode")
        fake_qrcode.QRCode = _FakeQRCode
        self._patch = patch.dict(sys.modules, {"qrcode": fake_qrcode})
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self.manager = QRManager()

    def test_available_is_true_with_qrcode_installed(self) -> None:
        self.assertTrue(self.manager.available)

    def test_render_ascii_produces_grid_output(self) -> None:
        output = self.manager.render_ascii("https://example.com", target_width=100)
        lines = output.splitlines()
        self.assertGreater(len(lines), 0)
        self.assertTrue(all(len(line) == len(lines[0]) for line in lines))

    def test_downsample_leaves_narrow_matrix_untouched(self) -> None:
        matrix = [[True, False], [False, True]]
        result = self.manager._downsample(matrix, target_width=100)
        self.assertEqual(result, matrix)

    def test_downsample_shrinks_wide_matrix(self) -> None:
        matrix = [[bool((x + y) % 2) for x in range(200)] for y in range(200)]
        result = self.manager._downsample(matrix, target_width=40)
        self.assertLess(len(result), len(matrix))
        self.assertLess(len(result[0]), len(matrix[0]))

    def test_downsample_handles_empty_matrix(self) -> None:
        result = self.manager._downsample([], target_width=40)
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
