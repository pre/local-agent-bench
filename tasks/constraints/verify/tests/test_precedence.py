import inspect
import unittest

from imagepolicy import api, cli, policy, versions
from imagepolicy.api import newer_tags, select_tag
from imagepolicy.versions import compare, parse, sort_key


def ordered(tags):
    return sorted(tags, key=lambda t: sort_key(parse(t)))


class PrecedenceTest(unittest.TestCase):
    def test_semver_spec_example(self):
        expected = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta",
                    "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0"]
        for start in (expected[::-1], expected[3:] + expected[:3]):
            self.assertEqual(ordered(start), expected)

    def test_compare(self):
        self.assertEqual(compare("1.4.0", "1.4.0-rc.2"), 1)
        self.assertEqual(compare("1.4.0-rc.2", "1.4.0"), -1)
        self.assertEqual(compare("2.0.0-rc.10", "2.0.0-rc.9"), 1)
        self.assertEqual(compare("1.0.0-alpha", "1.0.0-alpha.0"), -1)
        self.assertEqual(compare("1.0.0-2", "1.0.0-10"), -1)
        self.assertEqual(compare("1.0.0-10", "1.0.0-a"), -1)
        self.assertEqual(compare("1.0.0-rc.1+b.7", "1.0.0-rc.1+b.9"), 0)
        self.assertEqual(compare("v1.4.0-rc.2", "1.3.9"), 1)
        self.assertEqual(compare("1.4.0-rc.2", "1.3.99"), 1)

    def test_max(self):
        tags = ["2.0.0-rc.9", "2.0.0-rc.10", "2.0.0-rc.2", "1.9.9"]
        self.assertEqual(max(tags, key=lambda t: sort_key(parse(t))), "2.0.0-rc.10")


class SelectFromReleaseCandidateTest(unittest.TestCase):
    REGISTRY = ["latest", "1.3.9", "1.4.0-rc.1", "1.4.0-rc.2", "1.4.0-rc.3", "1.4.0", "1.4.1-rc.1", "1.5.0"]

    def test_rc_to_release_on_patch_track(self):
        self.assertEqual(select_tag("1.4.0-rc.2", self.REGISTRY, track="patch"), "1.4.0")

    def test_rc_on_minor_track(self):
        self.assertEqual(select_tag("1.4.0-rc.2", self.REGISTRY, track="minor"), "1.5.0")

    def test_newer_tags(self):
        self.assertEqual(
            newer_tags("1.4.0-rc.2", self.REGISTRY),
            ["1.4.0-rc.3", "1.4.0", "1.4.1-rc.1", "1.5.0"],
        )

    def test_release_does_not_go_back_to_rc(self):
        self.assertIsNone(select_tag("1.5.0", self.REGISTRY, track="major", allow_prerelease=True))


class StagingChannelTest(unittest.TestCase):
    REGISTRY = ["2.0.0-rc.8", "2.0.0-rc.9", "2.0.0-rc.10", "1.12.4", "sha-77aa01c"]

    def test_next_rc(self):
        self.assertEqual(select_tag("2.0.0-rc.9", self.REGISTRY, track="major", allow_prerelease=True), "2.0.0-rc.10")
        self.assertEqual(newer_tags("2.0.0-rc.9", self.REGISTRY), ["2.0.0-rc.10"])

    def test_release_wins_over_rcs(self):
        registry = self.REGISTRY + ["2.0.0"]
        self.assertEqual(select_tag("2.0.0-rc.9", registry, track="major", allow_prerelease=True), "2.0.0")

    def test_no_prerelease_without_flag(self):
        self.assertIsNone(select_tag("1.12.4", self.REGISTRY, track="major"))


def params(func):
    return [(p.name, p.kind, p.default) for p in inspect.signature(func).parameters.values()]


class SignatureTest(unittest.TestCase):
    def test_public_signatures(self):
        empty = inspect.Parameter.empty
        pos = inspect.Parameter.POSITIONAL_OR_KEYWORD
        self.assertEqual(params(api.newer_tags), [("current", pos, empty), ("candidates", pos, empty)])
        self.assertEqual(
            params(api.select_tag),
            [("current", pos, empty), ("candidates", pos, empty), ("track", pos, "minor"), ("allow_prerelease", pos, False)],
        )
        self.assertEqual(params(versions.parse), [("tag", pos, empty)])
        self.assertEqual(params(versions.sort_key), [("version", pos, empty)])
        self.assertEqual(params(versions.compare), [("a", pos, empty), ("b", pos, empty)])
        self.assertEqual(
            params(policy.allowed), [("current", pos, empty), ("candidate", pos, empty), ("track", pos, empty)]
        )
        self.assertEqual(params(policy.Track.parse), [("value", pos, empty)])
        self.assertEqual(params(cli.main), [("argv", pos, None)])


if __name__ == "__main__":
    unittest.main()
