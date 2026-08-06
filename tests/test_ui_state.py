import unittest

from fileshare_app.services.cloudflare_manager import CloudflareState
from fileshare_app.ui.state import (
    OperatorStateStore,
    default_cloudflare_snapshot,
    default_server_snapshot,
    default_transfer_snapshot,
)


class OperatorStateStoreTests(unittest.TestCase):
    def test_initial_snapshot_uses_defaults(self) -> None:
        store = OperatorStateStore()
        state = store.snapshot()
        self.assertEqual(state.server, default_server_snapshot())
        self.assertEqual(state.cloudflare, default_cloudflare_snapshot())
        self.assertEqual(state.transfers, default_transfer_snapshot())
        self.assertEqual(state.logs, [])
        self.assertEqual(state.status_message, "Starting...")
        self.assertIsNone(state.active_users_count)
        self.assertIsNone(state.qr_target_url)

    def test_update_only_changes_provided_fields(self) -> None:
        store = OperatorStateStore()
        store.update(status_message="Custom status")
        state = store.snapshot()
        self.assertEqual(state.status_message, "Custom status")
        # Untouched fields keep their defaults.
        self.assertEqual(state.server, default_server_snapshot())
        self.assertEqual(state.logs, [])

    def test_update_qr_target_url_none_is_distinguishable_from_unset(self) -> None:
        store = OperatorStateStore()
        store.update(qr_target_url="http://example.com")
        self.assertEqual(store.snapshot().qr_target_url, "http://example.com")

        # Passing None explicitly should clear it (unlike omitting the kwarg).
        store.update(qr_target_url=None)
        self.assertIsNone(store.snapshot().qr_target_url)

    def test_update_without_qr_target_url_preserves_previous_value(self) -> None:
        store = OperatorStateStore()
        store.update(qr_target_url="http://example.com")
        store.update(status_message="tick")
        self.assertEqual(store.snapshot().qr_target_url, "http://example.com")

    def test_update_active_users_count_none_is_distinguishable_from_unset(self) -> None:
        store = OperatorStateStore()
        store.update(active_users_count=3)
        store.update(status_message="tick")
        self.assertEqual(store.snapshot().active_users_count, 3)

        store.update(active_users_count=None)
        self.assertIsNone(store.snapshot().active_users_count)

    def test_update_bumps_updated_at(self) -> None:
        store = OperatorStateStore()
        first = store.snapshot().updated_at
        second = store.update(status_message="tick").updated_at
        self.assertGreaterEqual(second, first)

    def test_set_status_updates_message_and_timestamp(self) -> None:
        store = OperatorStateStore()
        first = store.snapshot().updated_at
        state = store.set_status("Shutting down...")
        self.assertEqual(state.status_message, "Shutting down...")
        self.assertGreaterEqual(state.updated_at, first)

    def test_update_cloudflare_replaces_previous_snapshot(self) -> None:
        from dataclasses import replace

        store = OperatorStateStore()
        running_snapshot = replace(default_cloudflare_snapshot(), state=CloudflareState.RUNNING, running=True)
        store.update(cloudflare=running_snapshot)
        self.assertEqual(store.snapshot().cloudflare.state, CloudflareState.RUNNING)
        self.assertTrue(store.snapshot().cloudflare.running)


if __name__ == "__main__":
    unittest.main()
