import contextlib
import io
import json
import unittest
from pathlib import Path

from nodeinv.cli import main

INVENTORY = str(Path(__file__).resolve().parent.parent / "inventory.toml")


def run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(["--inventory", INVENTORY, *argv])
    return code, out.getvalue()


class ListTest(unittest.TestCase):
    def test_control_plane_table(self):
        code, out = run("list", "--role", "control-plane")
        self.assertEqual(code, 0)
        self.assertEqual(
            out.splitlines(),
            [
                "NAME            ROLE           ZONE    RACK  CPU  MEMORY  GPU  STATUS",
                "hel1-cp-r01-01  control-plane  hel1-a  r01    32  128Gi     0  ready",
                "hel1-cp-r02-01  control-plane  hel1-b  r02    32  128Gi     0  ready",
                "hel1-cp-r03-01  control-plane  hel1-c  r03    32  128Gi     0  ready",
            ],
        )

    def test_cordoned_nodes_are_hidden_by_default(self):
        _, out = run("list", "--json")
        names = [node["name"] for node in json.loads(out)]
        self.assertNotIn("hel1-cpu-r03-02", names)
        self.assertEqual(len(names), 9)

    def test_include_cordoned(self):
        _, out = run("list", "--json", "--include-cordoned")
        self.assertEqual(len(json.loads(out)), 11)

    def test_label_filter(self):
        _, out = run("list", "--json", "--label", "pool=gpu", "--zone", "hel1-a")
        self.assertEqual([n["name"] for n in json.loads(out)], ["hel1-gpu-r07-01", "hel1-gpu-r07-02"])


class ShowTest(unittest.TestCase):
    def test_unknown_node(self):
        code, _ = run("show", "nope")
        self.assertEqual(code, 1)

    def test_node_without_rack(self):
        code, out = run("show", "hel1-edge-01")
        self.assertEqual(code, 0)
        self.assertIsNone(json.loads(out)["rack"])


if __name__ == "__main__":
    unittest.main()
