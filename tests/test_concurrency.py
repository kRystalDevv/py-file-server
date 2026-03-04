import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fileshare_app.app import _start_waitress
from fileshare_app.core.config import build_settings
from fileshare_app.core.metrics import TransferMetrics
from fileshare_app.core.security import BlacklistStore
from fileshare_app.core.server import RuntimeState, create_app


class _DummyServer:
    def run(self) -> None:
        return

    def close(self) -> None:
        return


class ConcurrencyTests(unittest.TestCase):
    def test_start_waitress_uses_configured_threads(self) -> None:
        captured: dict[str, int] = {}

        def fake_create_server(app, **kwargs):  # type: ignore[no-untyped-def]
            captured.update({k: int(v) for k, v in kwargs.items() if k in {"threads", "connection_limit"}})
            return _DummyServer()

        with patch("fileshare_app.app.create_server", side_effect=fake_create_server):
            server, thread, errors = _start_waitress(object(), host="0.0.0.0", port=8080, threads=18)

        thread.join(timeout=1)
        self.assertFalse(errors)
        self.assertEqual(server.__class__.__name__, "_DummyServer")
        self.assertEqual(captured["threads"], 18)
        self.assertEqual(captured["connection_limit"], 216)

    def test_download_limit_returns_503_when_slots_full(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shared = root / "share"
            shared.mkdir()
            (shared / "large.bin").write_bytes(b"x" * (1024 * 1024))
            config_path = root / "settings.json"

            settings = build_settings(
                {
                    "mode": "lan",
                    "host": "127.0.0.1",
                    "port": 0,
                    "directory": str(shared),
                    "threads": 4,
                    "max_downloads": 1,
                    "tunnel": "off",
                },
                config_path_override=config_path,
            )

            logger = logging.getLogger("test_download_limit")
            logger.handlers = [logging.NullHandler()]
            runtime_state = RuntimeState(share_dir=shared, current_port=8080)
            with patch("fileshare_app.core.server.threading.BoundedSemaphore") as semaphore_ctor:
                semaphore = semaphore_ctor.return_value
                semaphore.acquire.return_value = False
                app = create_app(
                    settings,
                    logger=logger,
                    metrics=TransferMetrics(),
                    blacklist_store=BlacklistStore(settings.app_paths.blacklist_file),
                    runtime_state=runtime_state,
                )

            app.testing = True
            client = app.test_client()
            response = client.get("/files/large.bin")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.headers.get("Retry-After"), "2")
            semaphore.acquire.assert_called_with(blocking=False)


if __name__ == "__main__":
    unittest.main()
