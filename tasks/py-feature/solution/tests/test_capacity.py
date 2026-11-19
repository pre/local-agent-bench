import contextlib
import io
import json
import unittest
from pathlib import Path

from nodeinv.capacity import summarize_capacity
from nodeinv.cli import main
from nodeinv.inventory import Node

INVENTORY = str(Path(__file__).resolve().parent.parent / "inventory.toml")


def run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(["--inventory", INVENTORY, *argv])
    return code, out.getvalue()


class SummarizeCapacityTest(unittest.TestCase):
    def test_rounds_the_group_sum(self):
        nodes = [
            Node(name="a", role="worker", zone="z", rack="r1", cpu=4, memory_mib=1536),
            Node(name="b", role="worker", zone="z", rack="r1", cpu=4, memory_mib=1536, gpu_count=2),
            Node(name="c", role="worker", zone="z", rack=None, cpu=2, memory_mib=512),
        ]
        self.assertEqual(
            summarize_capacity(nodes, "rack"),
            [
                {"name": "-", "nodes": 1, "cpu": 2, "mem_gib": 0, "gpu": 0},
                {"name": "r1", "nodes": 2, "cpu": 8, "mem_gib": 3, "gpu": 2},
            ],
        )


class CapacityCommandTest(unittest.TestCase):
    def test_by_zone_table(self):
        code, out = run("capacity", "--by", "zone")
        self.assertEqual(code, 0)
        self.assertEqual(
            out.splitlines(),
            [
                "ZONE    NODES  CPU  MEM_GIB  GPU",
                "hel1-a      6  688     5824   16",
                "hel1-b      2  224     1664    0",
                "hel1-c      1   32      128    0",
                "TOTAL       9  944     7616   16",
            ],
        )

    def test_json_with_filters(self):
        code, out = run("capacity", "--json", "--role", "gpu-worker", "--include-cordoned")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual([g["name"] for g in data["groups"]], ["r07", "r08"])
        self.assertEqual(data["total"], {"nodes": 3, "cpu": 576, "mem_gib": 6144, "gpu": 24})


if __name__ == "__main__":
    unittest.main()
