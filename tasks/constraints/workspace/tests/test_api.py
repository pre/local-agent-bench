import unittest

from imagepolicy.api import newer_tags, select_tag

REGISTRY = ["latest", "1.8.4", "1.9.0", "1.9.3", "1.10.0", "1.10.2", "2.0.0", "2.1.0-rc.1", "sha-5114f85"]


class SelectTagTest(unittest.TestCase):
    def test_tracks(self):
        self.assertEqual(select_tag("1.9.0", REGISTRY, track="patch"), "1.9.3")
        self.assertEqual(select_tag("1.9.0", REGISTRY, track="minor"), "1.10.2")
        self.assertEqual(select_tag("1.9.0", REGISTRY, track="major"), "2.0.0")

    def test_prerelease_only_when_allowed(self):
        self.assertEqual(select_tag("2.0.0", REGISTRY, track="minor"), None)
        self.assertEqual(select_tag("2.0.0", REGISTRY, track="minor", allow_prerelease=True), "2.1.0-rc.1")

    def test_up_to_date(self):
        self.assertIsNone(select_tag("1.10.2", REGISTRY, track="minor"))

    def test_unknown_track(self):
        with self.assertRaises(ValueError):
            select_tag("1.9.0", REGISTRY, track="nightly")


class NewerTagsTest(unittest.TestCase):
    def test_oldest_first(self):
        self.assertEqual(newer_tags("1.10.0", REGISTRY), ["1.10.2", "2.0.0", "2.1.0-rc.1"])


if __name__ == "__main__":
    unittest.main()
