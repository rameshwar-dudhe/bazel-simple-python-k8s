"""Tests for the release tool's decision logic.

The tagging rules are the part of a release pipeline that is easy to get
wrong and expensive to get wrong (a bad `latest` goes to every customer), so
they live in pure functions that are unit tested without docker or a registry.
"""

import unittest

from tools.release import release

MANIFEST = {
    "registry": {"default": "europe-west1-docker.pkg.dev/acme-prod/platform"},
    "images": [
        {"name": "api", "repository": "api", "version": "1.4.0"},
        {"name": "worker", "repository": "worker", "version": "1.4.0"},
    ],
}


class ComputeTagsTest(unittest.TestCase):
    def test_nightly_has_an_immutable_tag_and_a_floating_one(self):
        tags = release.compute_tags("nightly", "1.4.0", "20260816", "abcdef1234567")
        self.assertEqual(tags, ["nightly-20260816-abcdef1", "nightly"])

    def test_release_publishes_semver_minor_and_latest(self):
        tags = release.compute_tags("release", "1.4.0", "20260816", "abcdef1234567")
        self.assertEqual(tags, ["1.4.0", "1.4", "latest"])

    def test_hotfix_never_moves_latest(self):
        tags = release.compute_tags("hotfix", "1.4.0", "20260816", "abcdef1", hotfix_number=2)
        self.assertEqual(tags, ["1.4.0-hotfix.2"])
        self.assertNotIn("latest", tags)

    def test_hotfix_requires_a_number(self):
        with self.assertRaises(ValueError):
            release.compute_tags("hotfix", "1.4.0", "20260816", "abcdef1")

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            release.compute_tags("yolo", "1.4.0", "20260816", "abcdef1")


class SelectImagesTest(unittest.TestCase):
    def test_default_is_every_image(self):
        self.assertEqual(len(release.select_images(MANIFEST, None)), 2)

    def test_only_filters_and_keeps_order(self):
        picked = release.select_images(MANIFEST, ["worker"])
        self.assertEqual([i["name"] for i in picked], ["worker"])

    def test_unknown_name_fails_loudly(self):
        with self.assertRaises(SystemExit):
            release.select_images(MANIFEST, ["frontend"])


class RemoteRefTest(unittest.TestCase):
    def test_uses_the_manifest_registry_prefix(self):
        ref = release.remote_ref(MANIFEST, MANIFEST["images"][0], None)
        self.assertEqual(ref, "europe-west1-docker.pkg.dev/acme-prod/platform/api")

    def test_registry_override_wins(self):
        # This is exactly what a hotfix to a customer registry does.
        ref = release.remote_ref(MANIFEST, MANIFEST["images"][0], "acme.jfrog.io/cust-a/")
        self.assertEqual(ref, "acme.jfrog.io/cust-a/api")


if __name__ == "__main__":
    unittest.main()
