import contextlib
import io
import json
import os
import tempfile
import unittest

import addrplan
from addrplan.cli import main
from addrplan.plan import Node, bmc_address, bmc_gateway, hostname, mtu, node_plan, vlan_id


class BmcGeneralTest(unittest.TestCase):
    def test_host_octet_is_slot_plus_20(self):
        cases = [
            (("HEL1", 3, 7), "10.16.3.27"),
            (("HEL1", 46, 42), "10.16.46.62"),
            (("OUL1", 12, 1), "10.24.12.21"),
            (("ESP1", 30, 18), "10.40.30.38"),
            (("HEL2", 1, 5), "10.17.1.25"),
            (("HEL2", 40, 33), "10.17.40.53"),
        ]
        for args, expected in cases:
            with self.subTest(args=args):
                self.assertEqual(bmc_address(*args), expected)

    def test_gateway_general(self):
        self.assertEqual(bmc_gateway("OUL1", 9), "10.24.9.1")
        self.assertEqual(bmc_gateway("HEL2", 40), "10.17.40.1")
        self.assertEqual(bmc_gateway("HEL1", 41), "10.16.41.1")


class BmcTmp1Test(unittest.TestCase):
    def test_withdrawn_deviation_does_not_apply(self):
        self.assertEqual(bmc_address("TMP1", 5, 2), "10.32.5.22")
        self.assertEqual(bmc_address("TMP1", 24, 40), "10.32.24.60")


class Hel2HallBTest(unittest.TestCase):
    def test_hall_b_subnets(self):
        cases = [
            (("HEL2", 41, 1), "10.17.141.21", "10.17.141.1"),
            (("HEL2", 45, 3), "10.17.145.23", "10.17.145.1"),
            (("HEL2", 52, 17), "10.17.152.37", "10.17.152.1"),
            (("HEL2", 64, 40), "10.17.164.60", "10.17.164.1"),
        ]
        for (site, rack, slot), address, gateway in cases:
            with self.subTest(rack=rack, slot=slot):
                self.assertEqual(bmc_address(site, rack, slot), address)
                self.assertEqual(bmc_gateway(site, rack), gateway)

    def test_only_hel2(self):
        self.assertEqual(bmc_address("HEL1", 41, 1), "10.16.41.21")
        self.assertEqual(bmc_address("HEL1", 44, 10), "10.16.44.30")


class VlanTest(unittest.TestCase):
    def test_storage_vlan(self):
        self.assertEqual(vlan_id("HEL1", 3, "storage"), 2003)
        self.assertEqual(vlan_id("HEL2", 64, "storage"), 2064)
        self.assertEqual(vlan_id("OUL1", 30, "storage"), 2030)

    def test_data_vlan(self):
        self.assertEqual(vlan_id("HEL1", 3, "data"), 1003)
        self.assertEqual(vlan_id("HEL2", 45, "data"), 1045)
        self.assertEqual(vlan_id("ESP1", 36, "data"), 1036)


class MtuTest(unittest.TestCase):
    def test_oul1_storage(self):
        self.assertEqual(mtu("OUL1", "storage"), 4470)
        self.assertEqual(mtu("oul1", "storage"), 4470)

    def test_oul1_other_networks(self):
        self.assertEqual(mtu("OUL1", "data"), 9000)
        self.assertEqual(mtu("OUL1", "mgmt"), 1500)
        self.assertEqual(mtu("OUL1", "bmc"), 1500)

    def test_other_sites(self):
        for site in ("HEL1", "HEL2", "TMP1", "ESP1"):
            with self.subTest(site=site):
                self.assertEqual(mtu(site, "storage"), 9000)
                self.assertEqual(mtu(site, "data"), 9000)
                self.assertEqual(mtu(site, "mgmt"), 1500)
                self.assertEqual(mtu(site, "bmc"), 1500)


class NodePlanTest(unittest.TestCase):
    def test_hel2_hall_b_gpu_node(self):
        self.assertEqual(
            node_plan(Node("HEL2", 45, 3, "gpu")),
            {
                "hostname": "hel2-gpu-r45-s03",
                "bmc": {"address": "10.17.145.23", "prefix": 24, "gateway": "10.17.145.1", "mtu": 1500},
                "interfaces": {"data": {"vlan": 1045, "mtu": 9000}, "storage": {"vlan": 2045, "mtu": 9000}},
                "mgmt_mtu": 1500,
            },
        )

    def test_oul1_storage_node(self):
        self.assertEqual(
            node_plan(Node("OUL1", 30, 12, "storage")),
            {
                "hostname": "oul1-sto-r30-s12",
                "bmc": {"address": "10.24.30.32", "prefix": 24, "gateway": "10.24.30.1", "mtu": 1500},
                "interfaces": {"data": {"vlan": 1030, "mtu": 9000}, "storage": {"vlan": 2030, "mtu": 4470}},
                "mgmt_mtu": 1500,
            },
        )

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nodes.csv")
            with open(path, "w") as handle:
                handle.write("site,rack,slot,role\nHEL2,41,1,compute\nTMP1,5,2,infra\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main([path])
        self.assertEqual(code, 0)
        plans = json.loads(out.getvalue())
        self.assertEqual([p["bmc"]["address"] for p in plans], ["10.17.141.21", "10.32.5.22"])


class UnchangedBehaviourTest(unittest.TestCase):
    def test_hostname(self):
        self.assertEqual(hostname("HEL1", 3, 7, "gpu"), "hel1-gpu-r03-s07")
        self.assertEqual(hostname("hel2", 52, 17, "compute"), "hel2-cpu-r52-s17")
        self.assertEqual(hostname("ESP1", 30, 1, "control-plane"), "esp1-cp-r30-s01")

    def test_errors(self):
        with self.assertRaises(ValueError):
            hostname("HEL1", 3, 7, "database")
        with self.assertRaises(ValueError):
            bmc_address("TMP1", 25, 1)
        with self.assertRaises(ValueError):
            bmc_address("XXX1", 1, 1)
        with self.assertRaises(ValueError):
            vlan_id("HEL1", 3, "mgmt")
        with self.assertRaises(ValueError):
            mtu("HEL1", "wan")


class RevisionTest(unittest.TestCase):
    def test_revision(self):
        self.assertEqual(addrplan.STANDARD_REVISION, 14)


if __name__ == "__main__":
    unittest.main()
