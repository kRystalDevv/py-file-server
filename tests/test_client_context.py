import unittest

from flask import Flask, request

from fileshare_app.core.server import build_request_log_message, get_client_context


class ClientContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Flask(__name__)

    def test_direct_local_request(self) -> None:
        with self.app.test_request_context("/", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
            ctx = get_client_context(request)
        self.assertEqual(ctx["client_ip"], "127.0.0.1")
        self.assertEqual(ctx["source"], "local")
        self.assertFalse(ctx["proxied"])
        self.assertEqual(ctx["client_country"], "Unknown")

    def test_lan_request(self) -> None:
        with self.app.test_request_context("/", environ_base={"REMOTE_ADDR": "192.168.1.8"}):
            ctx = get_client_context(request)
        self.assertEqual(ctx["client_ip"], "192.168.1.8")
        self.assertEqual(ctx["source"], "lan")
        self.assertFalse(ctx["proxied"])
        self.assertEqual(ctx["client_country"], "Unknown")

    def test_cloudflare_proxied_request(self) -> None:
        headers = {
            "CF-Connecting-IP": "8.8.8.8",
            "CF-IPCountry": "US",
            "CF-Ray": "abc123-def456",
        }
        with self.app.test_request_context("/", environ_base={"REMOTE_ADDR": "127.0.0.1"}, headers=headers):
            ctx = get_client_context(request)
        self.assertEqual(ctx["client_ip"], "8.8.8.8")
        self.assertEqual(ctx["source"], "cloudflare")
        self.assertTrue(ctx["proxied"])
        self.assertEqual(ctx["client_country"], "US")
        self.assertEqual(ctx["client_ray"], "abc123-def456")

    def test_cloudflare_missing_country(self) -> None:
        headers = {"CF-Connecting-IP": "1.1.1.1", "CF-Ray": "abc"}
        with self.app.test_request_context("/", environ_base={"REMOTE_ADDR": "::1"}, headers=headers):
            ctx = get_client_context(request)
        self.assertEqual(ctx["client_ip"], "1.1.1.1")
        self.assertEqual(ctx["source"], "cloudflare")
        self.assertTrue(ctx["proxied"])
        self.assertEqual(ctx["client_country"], "Unknown")

    def test_does_not_trust_cf_headers_from_non_local_remote(self) -> None:
        headers = {"CF-Connecting-IP": "8.8.4.4", "CF-IPCountry": "US", "CF-Ray": "zzz"}
        with self.app.test_request_context("/", environ_base={"REMOTE_ADDR": "192.168.1.50"}, headers=headers):
            ctx = get_client_context(request)
        self.assertEqual(ctx["client_ip"], "192.168.1.50")
        self.assertEqual(ctx["source"], "lan")
        self.assertFalse(ctx["proxied"])
        self.assertEqual(ctx["client_country"], "Unknown")

    def test_log_message_lan_is_concise(self) -> None:
        msg = build_request_log_message(
            mode="lan",
            ctx={"source": "lan", "client_ip": "192.168.1.19", "user_agent": "UA"},
            method="GET",
            path="/",
            status=200,
            verbosity="medium",
            app_version="1.3.0",
        )
        self.assertIn("mode=lan", msg)
        self.assertIn("source=lan", msg)
        self.assertIn("client_ip=192.168.1.19", msg)
        self.assertNotIn("country=", msg)
        self.assertNotIn("ray=", msg)
        self.assertNotIn("proxied=", msg)

    def test_log_message_cloudflare_includes_cf_fields(self) -> None:
        msg = build_request_log_message(
            mode="public",
            ctx={
                "source": "cloudflare",
                "client_ip": "8.8.8.8",
                "client_country": "US",
                "client_ray": "abc",
                "user_agent": "UA",
            },
            method="GET",
            path="/files/a",
            status=206,
            verbosity="full",
            app_version="1.3.0",
        )
        self.assertIn("mode=public", msg)
        self.assertIn("source=cloudflare", msg)
        self.assertIn("country=US", msg)
        self.assertIn("ray=abc", msg)
        self.assertIn("proxied=true", msg)
        self.assertIn("version=1.3.0", msg)

    def test_log_message_basic(self) -> None:
        msg = build_request_log_message(
            mode="lan",
            ctx={"source": "lan", "client_ip": "192.168.1.19"},
            method="GET",
            path="/x",
            status=200,
            verbosity="basic",
            app_version="1.3.0",
        )
        self.assertIn("client_ip=192.168.1.19", msg)
        self.assertIn("path=/x", msg)
        self.assertNotIn("mode=", msg)
        self.assertNotIn("source=", msg)

    def test_log_message_no(self) -> None:
        msg = build_request_log_message(
            mode="lan",
            ctx={"source": "lan", "client_ip": "192.168.1.19"},
            method="GET",
            path="/x",
            status=200,
            verbosity="no",
            app_version="1.3.0",
        )
        self.assertEqual(msg, "")


if __name__ == "__main__":
    unittest.main()
