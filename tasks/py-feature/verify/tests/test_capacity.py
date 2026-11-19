import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from nodeinv.cli import main
from nodeinv.inventory import Node, load_inventory

FIXTURE = """
[cluster]
name = "oul1-stage-01"

[[nodes]]
name = "oul-cp-1"
role = "control-plane"
zone = "oul1-a"
rack = "r01"
cpu = 16
memory = "64Gi"
labels = { pool = "system" }

[[nodes]]
name = "oul-w-1"
role = "worker"
zone = "oul1-a"
rack = "r01"
cpu = 64
memory = "300000Mi"
labels = { pool = "general", tier = "batch" }

[[nodes]]
name = "oul-w-2"
role = "worker"
zone = "oul1-a"
rack = "r01"
cpu = 64
memory = "300000Mi"
labels = { pool = "general", tier = "batch" }

[[nodes]]
name = "oul-w-3"
role = "worker"
zone = "oul1-b"
rack = "r02"
cpu = 96
memory = "1Ti"
labels = { pool = "general", tier = "web" }

[[nodes]]
name = "oul-w-4"
role = "worker"
zone = "oul1-b"
rack = "r02"
cpu = 96
memory = "1Ti"
cordoned = true
labels = { pool = "general", tier = "web" }

[[nodes]]
name = "oul-g-1"
role = "gpu-worker"
zone = "oul1-b"
rack = "r05"
cpu = 128
memory = "1.5Ti"
gpu = { model = "MI300X", count = 4 }
labels = { pool = "gpu" }

[[nodes]]
name = "oul-g-2"
role = "gpu-worker"
zone = "oul1-c"
rack = "r05"
cpu = 128
memory = "1.5Ti"
gpu = { model = "MI300X", count = 8 }
labels = { pool = "gpu" }

[[nodes]]
name = "oul-g-3"
role = "gpu-worker"
zone = "oul1-c"
rack = "r06"
cpu = 128
memory = "2Ti"
gpu = { model = "MI325X", count = 8 }
cordoned = true
labels = { pool = "gpu" }

[[nodes]]
name = "oul-edge-1"
role = "edge"
zone = "oul1-a"
cpu = 8
memory = "16384Mi"
labels = { pool = "edge" }

[[nodes]]
name = "oul-edge-2"
role = "edge"
zone = "oul1-c"
cpu = 8
memory = "20000Mi"
labels = { pool = "edge" }
"""


def group(name, nodes, cpu, mem_gib, gpu):
    return {"name": name, "nodes": nodes, "cpu": cpu, "mem_gib": mem_gib, "gpu": gpu}


def total(nodes, cpu, mem_gib, gpu):
    return {"nodes": nodes, "cpu": cpu, "mem_gib": mem_gib, "gpu": gpu}


class FixtureMixin:
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.inventory = os.path.join(cls._tmp.name, "nodes.toml")
        Path(cls.inventory).write_text(FIXTURE)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["--inventory", self.inventory, *argv])
        return code, out.getvalue()


class SummarizeFunctionTest(FixtureMixin, unittest.TestCase):
    def test_by_rack_counts_all_given_nodes(self):
        from nodeinv.capacity import summarize_capacity

        nodes = load_inventory(self.inventory).nodes
        self.assertEqual(
            summarize_capacity(nodes, "rack"),
            [
                group("-", 2, 16, 35, 0),
                group("r01", 3, 144, 649, 0),
                group("r02", 2, 192, 2048, 0),
                group("r05", 2, 256, 3072, 12),
                group("r06", 1, 128, 2048, 8),
            ],
        )

    def test_by_role(self):
        from nodeinv.capacity import summarize_capacity

        nodes = load_inventory(self.inventory).nodes
        self.assertEqual(
            summarize_capacity(nodes, "role"),
            [
                group("control-plane", 1, 16, 64, 0),
                group("edge", 2, 16, 35, 0),
                group("gpu-worker", 3, 384, 5120, 20),
                group("worker", 4, 320, 2633, 0),
            ],
        )

    def test_plain_node_objects(self):
        from nodeinv.capacity import summarize_capacity

        nodes = [
            Node(name="a", role="worker", zone="z2", rack=None, cpu=4, memory_mib=1536),
            Node(name="b", role="worker", zone="z1", rack=None, cpu=8, memory_mib=1536, gpu_count=2),
            Node(name="c", role="worker", zone="z2", rack=None, cpu=2, memory_mib=512, cordoned=True),
        ]
        self.assertEqual(
            summarize_capacity(nodes, "zone"),
            [group("z1", 1, 8, 1, 2), group("z2", 2, 6, 2, 0)],
        )
        self.assertEqual(summarize_capacity([], "rack"), [])


class CapacityTableTest(FixtureMixin, unittest.TestCase):
    def test_default_groups_by_rack(self):
        code, out = self.run_cli("capacity")
        self.assertEqual(code, 0)
        self.assertEqual(
            out.splitlines(),
            [
                "RACK   NODES  CPU  MEM_GIB  GPU",
                "-          2   16       35    0",
                "r01        3  144      649    0",
                "r02        1   96     1024    0",
                "r05        2  256     3072   12",
                "TOTAL      8  512     4781   12",
            ],
        )

    def test_by_role_with_cordoned(self):
        code, out = self.run_cli("capacity", "--by", "role", "--include-cordoned")
        self.assertEqual(code, 0)
        self.assertEqual(
            out.splitlines(),
            [
                "ROLE           NODES  CPU  MEM_GIB  GPU",
                "control-plane      1   16       64    0",
                "edge               2   16       35    0",
                "gpu-worker         3  384     5120   20",
                "worker             4  320     2633    0",
                "TOTAL             10  736     7853   20",
            ],
        )


class CapacityJsonTest(FixtureMixin, unittest.TestCase):
    def test_by_zone(self):
        code, out = self.run_cli("capacity", "--by", "zone", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(out),
            {
                "by": "zone",
                "groups": [
                    group("oul1-a", 4, 152, 665, 0),
                    group("oul1-b", 2, 224, 2560, 4),
                    group("oul1-c", 2, 136, 1555, 8),
                ],
                "total": total(8, 512, 4781, 12),
            },
        )


class CapacityFilterTest(FixtureMixin, unittest.TestCase):
    def test_labels(self):
        code, out = self.run_cli("capacity", "--json", "--label", "pool=general", "--label", "tier=batch")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["groups"], [group("r01", 2, 128, 585, 0)])
        self.assertEqual(data["total"], total(2, 128, 585, 0))

    def test_role_and_cordoned(self):
        code, out = self.run_cli("capacity", "--json", "--role", "gpu-worker", "--include-cordoned")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["by"], "rack")
        self.assertEqual(data["groups"], [group("r05", 2, 256, 3072, 12), group("r06", 1, 128, 2048, 8)])
        self.assertEqual(data["total"], total(3, 384, 5120, 20))

    def test_zone(self):
        code, out = self.run_cli("capacity", "--by", "role", "--zone", "oul1-c")
        self.assertEqual(code, 0)
        self.assertEqual(
            out.splitlines(),
            [
                "ROLE        NODES  CPU  MEM_GIB  GPU",
                "edge            1    8       19    0",
                "gpu-worker      1  128     1536    8",
                "TOTAL           2  136     1555    8",
            ],
        )

    def test_no_match(self):
        code, out = self.run_cli("capacity", "--json", "--role", "storage")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"by": "rack", "groups": [], "total": total(0, 0, 0, 0)})


class CapacityErrorTest(FixtureMixin, unittest.TestCase):
    def test_unknown_attribute_fails(self):
        code, _ = self.run_cli("capacity", "--by", "zone")
        self.assertEqual(code, 0)
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                code = main(["--inventory", self.inventory, "capacity", "--by", "host"])
        except SystemExit as stop:
            code = stop.code
        self.assertNotIn(code, (0, None))


class ModuleEntryTest(FixtureMixin, unittest.TestCase):
    def test_python_m(self):
        env = dict(os.environ, NODEINV_INVENTORY=self.inventory, PYTHONDONTWRITEBYTECODE="1")
        root = Path(__file__).resolve().parent.parent
        result = subprocess.run(
            [sys.executable, "-m", "nodeinv", "capacity", "--by", "zone"],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            [
                "ZONE    NODES  CPU  MEM_GIB  GPU",
                "oul1-a      4  152      665    0",
                "oul1-b      2  224     2560    4",
                "oul1-c      2  136     1555    8",
                "TOTAL       8  512     4781   12",
            ],
        )


if __name__ == "__main__":
    unittest.main()
