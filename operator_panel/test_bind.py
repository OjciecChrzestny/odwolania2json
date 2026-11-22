"""Lekki odbiór wyboru adresu i niezmienionej ochrony nagłówków panelu."""
import io
import sys
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from http.client import HTTPConnection
from threading import Thread
from unittest.mock import patch

from operator_panel import __main__ as panel


class BindingTest(unittest.TestCase):
    def test_addresses_and_local_url(self):
        for options, address in (([], "127.0.0.1"), (["--bind", "0.0.0.0"], "0.0.0.0")):
            with (
                self.subTest(address=address),
                patch.object(sys, "argv", ["operator_panel", "--port", "0", *options]),
                patch.object(panel, "ThreadingHTTPServer") as create_server,
                redirect_stdout(io.StringIO()) as output,
            ):
                create_server.return_value.__enter__.return_value.server_port = 43210
                self.assertEqual(panel.main(), 0)
                create_server.assert_called_once_with((address, 0), panel.Handler)
                self.assertIn("Panel dostępny na http://127.0.0.1:43210", output.getvalue())

    def test_other_bind_address_is_rejected(self):
        with patch.object(sys, "argv", ["operator_panel", "--bind", "192.0.2.1"]), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                panel.main()
        self.assertEqual(error.exception.code, 2)

    def test_http_headers(self):
        with panel.ThreadingHTTPServer(("127.0.0.1", 0), panel.Handler) as server:
            server.demo = None
            worker = Thread(target=server.serve_forever)
            worker.start()
            local_origin = f"http://127.0.0.1:{server.server_port}"
            try:
                cases = [
                    ("GET", "/api/mode", {}, 200),
                    ("GET", "/api/mode", {"Host": "0.0.0.0"}, 403),
                    ("GET", "/api/mode", {"Host": "inna-domena.invalid"}, 403),
                    ("POST", "/api/upload", {"Origin": "https://inna-domena.invalid"}, 403),
                    ("POST", "/api/upload", {}, 403),
                    ("POST", "/api/upload", {"Origin": local_origin}, 404),
                ]
                for method, path, headers, expected in cases:
                    with self.subTest(method=method, headers=headers), closing(
                        HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                    ) as connection:
                        connection.request(method, path, headers=headers)
                        with connection.getresponse() as response:
                            self.assertEqual(response.status, expected)
                            response.read()
            finally:
                server.shutdown()
                worker.join()
