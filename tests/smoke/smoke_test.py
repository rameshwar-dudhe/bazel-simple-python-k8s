"""Post-deploy smoke validation.

This is the gate the release pipeline runs AFTER the images are pushed and the
Helm release is upgraded. It is deliberately small and fast: it answers "is the
thing we just shipped actually serving, and is it the version we shipped?" -
not "is the product correct" (that is what the unit tests are for).

It is a `manual` Bazel target because it needs a running deployment; a plain
`bazel test //...` must stay hermetic and cluster-free.

  SMOKE_BASE_URL=http://192.168.56.134:30080 EXPECTED_VERSION=1.4.0 \
    bazel test //tests/smoke:smoke_test --test_output=all
"""

import os
import time
import unittest

import requests

BASE_URL = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
EXPECTED_VERSION = os.environ.get("EXPECTED_VERSION", "")
TIMEOUT = float(os.environ.get("SMOKE_TIMEOUT", "5"))
RETRIES = int(os.environ.get("SMOKE_RETRIES", "10"))


def get(path: str) -> requests.Response:
    """GET with a short retry loop - pods may still be rolling when we start."""
    last = None
    for attempt in range(RETRIES):
        try:
            resp = requests.get(BASE_URL + path, timeout=TIMEOUT)
            if resp.status_code < 500:
                return resp
            last = AssertionError(f"{path} -> HTTP {resp.status_code}")
        except requests.RequestException as exc:  # connection refused, DNS, ...
            last = exc
        time.sleep(min(2 ** attempt * 0.25, 3))
    raise AssertionError(f"{BASE_URL}{path} never became healthy: {last}")


class SmokeTest(unittest.TestCase):
    def test_health_endpoint(self):
        resp = get("/healthz")
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["status"], "ok")

    def test_deployed_version_is_the_released_version(self):
        """The check that actually catches a broken release.

        A rollout can "succeed" while the cluster is still serving the old
        image (wrong tag in values, cached `latest`, failed pull with an old
        replica still up). Comparing /version against the tag the pipeline
        published is what makes that visible.
        """
        body = get("/version").json()
        self.assertEqual(body["service"], "api")
        if EXPECTED_VERSION:
            self.assertEqual(body["version"], EXPECTED_VERSION)
        else:
            self.assertRegex(body["version"], r"^\d+\.\d+\.\d+$")

    def test_business_endpoint_responds(self):
        body = get("/greet?name=smoke").json()
        self.assertEqual(body["message"], "hello, smoke!")


if __name__ == "__main__":
    unittest.main()
