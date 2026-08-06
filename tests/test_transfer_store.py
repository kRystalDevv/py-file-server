import time
import unittest

from fileshare_app.core.metrics import TransferMetrics
from fileshare_app.services.transfer_store import TransferStore


class TransferStoreTests(unittest.TestCase):
    def test_refresh_reflects_active_transfers_from_metrics(self) -> None:
        metrics = TransferMetrics()
        store = TransferStore(metrics)

        metrics.start("k1", "file1.bin")
        metrics.update("k1", 1024)

        snapshot = store.refresh()

        self.assertEqual(len(snapshot.active), 1)
        self.assertEqual(snapshot.active[0].filename, "file1.bin")
        self.assertEqual(snapshot.active[0].bytes_sent, 1024)
        self.assertEqual(snapshot.total_uploaded, 1024)

    def test_completed_transfer_moves_to_recent(self) -> None:
        metrics = TransferMetrics()
        store = TransferStore(metrics)

        metrics.start("k1", "file1.bin")
        metrics.update("k1", 2048)
        store.refresh()

        metrics.stop("k1")
        snapshot = store.refresh()

        self.assertEqual(snapshot.active, [])
        self.assertEqual(len(snapshot.recent), 1)
        self.assertEqual(snapshot.recent[0].filename, "file1.bin")
        self.assertIsNotNone(snapshot.recent[0].completed_at)

    def test_recent_deque_respects_max_recent(self) -> None:
        metrics = TransferMetrics()
        store = TransferStore(metrics, max_recent=2)

        for i in range(3):
            key = f"k{i}"
            metrics.start(key, f"file{i}.bin")
            metrics.update(key, 100)
            store.refresh()
            metrics.stop(key)
            store.refresh()

        snapshot = store.snapshot()
        self.assertEqual(len(snapshot.recent), 2)
        # Most recently completed comes first.
        self.assertEqual(snapshot.recent[0].filename, "file2.bin")

    def test_snapshot_without_refresh_returns_empty(self) -> None:
        metrics = TransferMetrics()
        store = TransferStore(metrics)
        snapshot = store.snapshot()
        self.assertEqual(snapshot.active, [])
        self.assertEqual(snapshot.recent, [])
        self.assertEqual(snapshot.total_uploaded, 0)

    def test_snapshot_reads_last_refreshed_state_without_hitting_metrics(self) -> None:
        metrics = TransferMetrics()
        store = TransferStore(metrics)

        metrics.start("k1", "file1.bin")
        metrics.update("k1", 500)
        store.refresh()

        # Mutate metrics after refresh; snapshot() should not reflect it until refresh() runs again.
        metrics.update("k1", 500)
        snapshot = store.snapshot()

        self.assertEqual(snapshot.active[0].bytes_sent, 500)

    def test_rate_bps_is_computed_from_elapsed_time(self) -> None:
        metrics = TransferMetrics()
        store = TransferStore(metrics)

        metrics.start("k1", "file1.bin")
        time.sleep(0.05)
        metrics.update("k1", 1000)

        snapshot = store.refresh()
        record = snapshot.active[0]
        self.assertGreater(record.elapsed_seconds, 0)
        self.assertAlmostEqual(record.rate_bps, record.bytes_sent / record.elapsed_seconds)


if __name__ == "__main__":
    unittest.main()
