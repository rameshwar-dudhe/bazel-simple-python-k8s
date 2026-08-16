"""A tiny HTTP API, stdlib only.

Stdlib only is a deliberate choice: the container image then contains just the
app + the hermetic interpreter, which keeps the Bazel/OCI part of this repo
easy to read. Third-party dependency management is demonstrated where it
actually matters in a platform repo - the tooling and tests
(see //third_party/python).

Endpoints
  GET /healthz   liveness  - process is up
  GET /readyz    readiness - app is ready to serve traffic
  GET /version   build metadata (used by the smoke test)
  GET /greet     the actual "business logic", shared via //libs/greeter
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from libs.greeter import greeter

SERVICE_NAME = "api"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - name comes from BaseHTTPRequestHandler
        url = urlparse(self.path)
        env = os.environ.get("APP_ENV", "local")

        if url.path in ("/healthz", "/readyz"):
            self._send(200, {"status": "ok"})
        elif url.path == "/version":
            self._send(200, greeter.build_info(SERVICE_NAME, env))
        elif url.path in ("/", "/greet"):
            name = parse_qs(url.query).get("name", [None])[0]
            self._send(200, {"message": greeter.greet(name)})
        else:
            self._send(404, {"error": "not found", "path": url.path})

    def log_message(self, fmt: str, *args) -> None:
        # One structured line per request instead of the noisy default format.
        print(json.dumps({"service": SERVICE_NAME, "msg": fmt % args}), flush=True)


def serve(port: int) -> None:
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    info = greeter.build_info(SERVICE_NAME, os.environ.get("APP_ENV", "local"))
    print(json.dumps({"msg": "listening", "port": port, **info}), flush=True)
    server.serve_forever()


def main() -> None:
    serve(int(os.environ.get("PORT", "8080")))


if __name__ == "__main__":
    main()
