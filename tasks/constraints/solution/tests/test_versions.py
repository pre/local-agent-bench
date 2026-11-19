import unittest

from imagepolicy.versions import compare, parse, sort_key


class ParseTest(unittest.TestCase):
    def test_release(self):
        v = parse("1.4.2")
        self.assertEqual((v.major, v.minor, v.patch, v.prerelease), (1, 4, 2, ""))

    def test_prefix_prerelease_and_build(self):
        v = parse("v2.0.0-rc.1+sha.5114f85")
        self.assertEqual(v.core, (2, 0, 0))
        self.assertEqual(v.prerelease, "rc.1")
        self.assertEqual(v.build, "sha.5114f85")
        self.assertEqual(v.tag, "v2.0.0-rc.1+sha.5114f85")

    def test_not_a_version(self):
        for tag in ("latest", "sha-5114f85", "1.4", "01.2.3", "1.2.3-"):
            with self.subTest(tag=tag):
                self.assertIsNone(parse(tag))


class OrderTest(unittest.TestCase):
    def test_numeric_parts(self):
        self.assertEqual(compare("1.10.0", "1.9.7"), 1)
        self.assertEqual(compare("1.2.3", "1.2.10"), -1)

    def test_build_metadata_is_ignored(self):
        self.assertEqual(compare("1.2.3+build.1", "1.2.3+build.2"), 0)

    def test_sorted(self):
        tags = ["1.2.0", "v1.10.1", "1.9.0"]
        self.assertEqual(sorted(tags, key=lambda t: sort_key(parse(t))), ["1.2.0", "1.9.0", "v1.10.1"])

    def test_prerelease_precedence(self):
        ordered = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta",
                   "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0"]
        self.assertEqual(sorted(reversed(ordered), key=lambda t: sort_key(parse(t))), ordered)

    def test_release_is_newer_than_its_candidates(self):
        self.assertEqual(compare("1.4.0", "1.4.0-rc.2"), 1)
        self.assertEqual(compare("2.0.0-rc.10", "2.0.0-rc.9"), 1)

    def test_rejects_non_version(self):
        with self.assertRaises(ValueError):
            compare("latest", "1.0.0")


if __name__ == "__main__":
    unittest.main()
