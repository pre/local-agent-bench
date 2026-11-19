import unittest

from addrplan.plan import Node, bmc_address, bmc_gateway, hostname, mtu, node_plan, vlan_id


class HostnameTest(unittest.TestCase):
    def test_format(self):
        self.assertEqual(hostname("HEL1", 3, 7, "gpu"), "hel1-gpu-r03-s07")
        self.assertEqual(hostname("oul1", 12, 40, "storage"), "oul1-sto-r12-s40")

    def test_rejects_unknown_role(self):
        with self.assertRaises(ValueError):
            hostname("HEL1", 3, 7, "database")

    def test_rejects_rack_outside_site(self):
        with self.assertRaises(ValueError):
            hostname("TMP1", 25, 1, "compute")


class BmcTest(unittest.TestCase):
    def test_address(self):
        self.assertEqual(bmc_address("HEL1", 3, 7), "10.16.3.27")
        self.assertEqual(bmc_address("ESP1", 30, 1), "10.40.30.21")

    def test_withdrawn_tmp1_rule_does_not_apply(self):
        self.assertEqual(bmc_address("TMP1", 5, 2), "10.32.5.22")

    def test_hel2_hall_b(self):
        self.assertEqual(bmc_address("HEL2", 45, 3), "10.17.145.23")
        self.assertEqual(bmc_gateway("HEL2", 45), "10.17.145.1")
        self.assertEqual(bmc_address("HEL2", 40, 3), "10.17.40.23")

    def test_gateway(self):
        self.assertEqual(bmc_gateway("OUL1", 9), "10.24.9.1")


class VlanTest(unittest.TestCase):
    def test_data(self):
        self.assertEqual(vlan_id("HEL1", 3, "data"), 1003)

    def test_storage(self):
        self.assertEqual(vlan_id("HEL1", 3, "storage"), 2003)


class MtuTest(unittest.TestCase):
    def test_values(self):
        self.assertEqual(mtu("HEL1", "data"), 9000)
        self.assertEqual(mtu("HEL1", "storage"), 9000)
        self.assertEqual(mtu("HEL1", "bmc"), 1500)

    def test_oul1_storage(self):
        self.assertEqual(mtu("OUL1", "storage"), 4470)
        self.assertEqual(mtu("OUL1", "data"), 9000)


class NodePlanTest(unittest.TestCase):
    def test_plan(self):
        plan = node_plan(Node("HEL1", 3, 7, "gpu"))
        self.assertEqual(plan["hostname"], "hel1-gpu-r03-s07")
        self.assertEqual(plan["bmc"]["address"], "10.16.3.27")
        self.assertEqual(plan["interfaces"]["storage"], {"vlan": 2003, "mtu": 9000})


if __name__ == "__main__":
    unittest.main()
