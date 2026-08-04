from __future__ import annotations

import io
import os
import time
import unittest
from unittest import mock

from fileshare_app.core import hotkeys as hotkeys_module
from fileshare_app.core.hotkeys import HotkeyReader, PosixHotkeyReader, WindowsHotkeyReader

POSIX_ONLY = os.name == "posix"

if POSIX_ONLY:
    import pty
    import termios


class _FDStream:
    def __init__(self, fd: int) -> None:
        self._fd = fd

    def fileno(self) -> int:
        return self._fd


@unittest.skipUnless(POSIX_ONLY, "termios/tty/select are POSIX-only")
class PosixHotkeyReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.master_fd, self.slave_fd = pty.openpty()
        self.reader = PosixHotkeyReader(stream=_FDStream(self.slave_fd))

    def tearDown(self) -> None:
        self.reader.stop()
        os.close(self.master_fd)
        os.close(self.slave_fd)

    def test_non_tty_stream_never_activates(self) -> None:
        reader = PosixHotkeyReader(stream=io.StringIO())
        reader.start()
        self.assertIsNone(reader.read_nonblocking())
        reader.stop()  # must not raise

    def test_no_pending_input_returns_none_immediately(self) -> None:
        self.reader.start()
        self.assertIsNone(self.reader.read_nonblocking())

    def test_reads_single_keypress(self) -> None:
        self.reader.start()
        os.write(self.master_fd, b"t")
        time.sleep(0.05)
        self.assertEqual(self.reader.read_nonblocking(), "t")

    def test_stop_restores_original_termios_attrs(self) -> None:
        original = termios.tcgetattr(self.slave_fd)
        self.reader.start()
        self.reader.stop()
        self.assertEqual(termios.tcgetattr(self.slave_fd), original)

    def test_suspended_restores_cooked_mode_then_cbreak(self) -> None:
        self.reader.start()
        with self.reader.suspended():
            attrs = termios.tcgetattr(self.slave_fd)
            self.assertTrue(attrs[3] & termios.ICANON)
            self.assertTrue(attrs[3] & termios.ECHO)
        attrs = termios.tcgetattr(self.slave_fd)
        self.assertFalse(attrs[3] & termios.ICANON)
        self.assertFalse(attrs[3] & termios.ECHO)

    def test_escape_sequence_is_drained_not_leaked(self) -> None:
        self.reader.start()
        os.write(self.master_fd, b"\x1b[A")
        time.sleep(0.05)
        self.assertIsNone(self.reader.read_nonblocking())
        self.assertIsNone(self.reader.read_nonblocking())


class _FakeMsvcrt:
    def __init__(self, keys: list[str]) -> None:
        self._keys = list(keys)

    def kbhit(self) -> bool:
        return bool(self._keys)

    def getwch(self) -> str:
        return self._keys.pop(0)


class WindowsHotkeyReaderTests(unittest.TestCase):
    def test_returns_none_when_msvcrt_unavailable(self) -> None:
        with mock.patch.object(hotkeys_module, "msvcrt", None):
            self.assertIsNone(WindowsHotkeyReader().read_nonblocking())

    def test_returns_none_when_no_key_pressed(self) -> None:
        with mock.patch.object(hotkeys_module, "msvcrt", _FakeMsvcrt([])):
            self.assertIsNone(WindowsHotkeyReader().read_nonblocking())

    def test_returns_plain_key(self) -> None:
        with mock.patch.object(hotkeys_module, "msvcrt", _FakeMsvcrt(["q"])):
            self.assertEqual(WindowsHotkeyReader().read_nonblocking(), "q")

    def test_discards_extended_key_prefix(self) -> None:
        with mock.patch.object(hotkeys_module, "msvcrt", _FakeMsvcrt(["\x00", "H"])):
            self.assertIsNone(WindowsHotkeyReader().read_nonblocking())
        with mock.patch.object(hotkeys_module, "msvcrt", _FakeMsvcrt(["\xe0", "P"])):
            self.assertIsNone(WindowsHotkeyReader().read_nonblocking())

    def test_lone_prefix_byte_returned_when_queue_exhausted(self) -> None:
        with mock.patch.object(hotkeys_module, "msvcrt", _FakeMsvcrt(["\x00"])):
            self.assertEqual(WindowsHotkeyReader().read_nonblocking(), "\x00")


class BaseHotkeyReaderTests(unittest.TestCase):
    def test_base_reader_is_a_safe_noop(self) -> None:
        reader = HotkeyReader()
        reader.start()
        self.assertIsNone(reader.read_nonblocking())
        with reader.suspended():
            pass
        reader.stop()


if __name__ == "__main__":
    unittest.main()
