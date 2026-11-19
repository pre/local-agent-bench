import unittest

from nodeinv.inventory import InventoryError, parse_memory
from nodeinv.render import human_mib, table


class ParseMemoryTest(unittest.TestCase):
    def test_units(self):
        self.assertEqual(parse_memory("512Mi"), 512)
        self.assertEqual(parse_memory("128Gi"), 131072)
        self.assertEqual(parse_memory("1.5Ti"), 1572864)

    def test_rejects_decimal_units(self):
        with self.assertRaises(InventoryError):
            parse_memory("128G")


class RenderTest(unittest.TestCase):
    def test_human_mib(self):
        self.assertEqual(human_mib(65536), "64Gi")
        self.assertEqual(human_mib(1572864), "1.5Ti")
        self.assertEqual(human_mib(300), "300Mi")

    def test_table_alignment(self):
        text = table(("NAME", "CPU"), [("a", 8), ("long-name", 128)])
        self.assertEqual(text.splitlines(), ["NAME       CPU", "a            8", "long-name  128"])


if __name__ == "__main__":
    unittest.main()
