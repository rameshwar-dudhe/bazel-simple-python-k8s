"""Unit test for the API: starts the real server on an ephemeral port.

Runs as a hermetic `bazel test` target - no network, no cluster, no docker.
The cluster-level check lives in //tests/smoke.
"""

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from services.api import app


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as resp:
            return resp.status, json.loads(resp.read())

    def test_healthz(self):
        status, body = self.get("/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")

    def test_version_reports_service_and_version(self):
        _, body = self.get("/version")
        self.assertEqual(body["service"], "api")
        self.assertRegex(body["version"], r"^\d+\.\d+\.\d+$")

    def test_greet(self):
        _, body = self.get("/greet?name=vikrant")
        self.assertEqual(body["message"], "hello, vikrant!")

    def test_unknown_path_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/nope")
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
