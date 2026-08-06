import logging
import unittest

from fileshare_app.services.log_bridge import LogBridge


class LogBridgeTests(unittest.TestCase):
    def test_attach_captures_log_records(self) -> None:
        bridge = LogBridge()
        logger = logging.getLogger("test_log_bridge.captures")
        try:
            bridge.attach()
            logger.warning("hello from test")
            lines = bridge.snapshot()
            self.assertTrue(any("hello from test" in line for line in lines))
        finally:
            bridge.detach()

    def test_detach_stops_capturing(self) -> None:
        bridge = LogBridge()
        logger = logging.getLogger("test_log_bridge.detach")
        bridge.attach()
        bridge.detach()
        logger.warning("should not be captured")
        lines = bridge.snapshot()
        self.assertFalse(any("should not be captured" in line for line in lines))

    def test_attach_is_idempotent(self) -> None:
        bridge = LogBridge()
        logger = logging.getLogger("test_log_bridge.idempotent")
        try:
            bridge.attach()
            bridge.attach()
            logger.warning("only once")
            lines = bridge.snapshot()
            occurrences = sum(1 for line in lines if "only once" in line)
            self.assertEqual(occurrences, 1)
        finally:
            bridge.detach()

    def test_detach_without_attach_is_noop(self) -> None:
        bridge = LogBridge()
        bridge.detach()  # should not raise

    def test_max_lines_rolls_over_oldest_entries(self) -> None:
        bridge = LogBridge(max_lines=3)
        logger = logging.getLogger("test_log_bridge.rollover")
        try:
            bridge.attach()
            for i in range(5):
                logger.warning("line-%s", i)
            lines = bridge.snapshot()
            self.assertEqual(len(lines), 3)
            self.assertTrue(lines[-1].endswith("line-4"))
            self.assertFalse(any("line-0" in line for line in lines))
        finally:
            bridge.detach()

    def test_snapshot_limit_returns_most_recent_n(self) -> None:
        bridge = LogBridge()
        logger = logging.getLogger("test_log_bridge.limit")
        try:
            bridge.attach()
            for i in range(5):
                logger.warning("entry-%s", i)
            lines = bridge.snapshot(limit=2)
            self.assertEqual(len(lines), 2)
            self.assertTrue(lines[-1].endswith("entry-4"))
        finally:
            bridge.detach()


if __name__ == "__main__":
    unittest.main()
