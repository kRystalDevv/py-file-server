from __future__ import annotations

import math


class QRManager:
    """Renders terminal-friendly ASCII QR output."""

    def __init__(self) -> None:
        try:
            import qrcode  # type: ignore
        except Exception:
            qrcode = None  # type: ignore[assignment]
        self._qrcode = qrcode

    @property
    def available(self) -> bool:
        return self._qrcode is not None

    def render_ascii(self, url: str, *, target_width: int = 100) -> str:
        if not self._qrcode:
            return "QR library not available. Install dependency: qrcode."

        qr = self._qrcode.QRCode(border=2)
        qr.add_data(url)
        qr.make(fit=True)
        matrix = qr.get_matrix()
        scaled = self._downsample(matrix, target_width=max(target_width, 32))

        on = "██"
        off = "  "
        lines = []
        for row in scaled:
            lines.append("".join(on if cell else off for cell in row))
        return "\n".join(lines)

    def _downsample(self, matrix: list[list[bool]], *, target_width: int) -> list[list[bool]]:
        if not matrix:
            return matrix
        matrix_width_chars = len(matrix[0]) * 2
        if matrix_width_chars <= target_width:
            return matrix

        # Keep QR readable in narrow terminals by nearest-neighbor downsampling.
        max_modules = max(16, target_width // 2)
        stride = max(1, math.ceil(len(matrix) / max_modules))
        resized: list[list[bool]] = []
        for y in range(0, len(matrix), stride):
            row = matrix[y]
            resized.append([row[x] for x in range(0, len(row), stride)])
        return resized
