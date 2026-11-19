import unittest

from contactmig.records import FileError, decode, normalize_email, normalize_name, normalize_time, split_records


class DecodeTest(unittest.TestCase):
    def test_bom_and_declaration(self):
        self.assertEqual(decode(b"\xef\xbb\xbf#v1 encoding=utf-8\nx"), ("#v1 encoding=utf-8\nx", False))
        with self.assertRaises(FileError) as ctx:
            decode(b"\xef\xbb\xbf#v1 encoding=latin-1\n")
        self.assertEqual(ctx.exception.code, "encoding-conflict")

    def test_fallback_to_cp1252(self):
        self.assertEqual(decode(b"\x93a\x94"), ("“a”", True))
        with self.assertRaises(FileError):
            decode(b"\x81\xe9")


class LinesTest(unittest.TestCase):
    def test_only_cr_and_lf_end_lines(self):
        records = split_records("id: 1\rname: a b\r\n  c\n\n#x\nid: 2")
        self.assertEqual([r.fields for r in records], [[["id", " 1"], ["name", " a b c"]], [["id", " 2"]]])

    def test_continuation_starts_record(self):
        with self.assertRaises(FileError) as ctx:
            split_records("id: 1\n\n  x")
        self.assertEqual((ctx.exception.code, ctx.exception.record), ("syntax", 2))


class NormalizeTest(unittest.TestCase):
    def test_name_limit(self):
        self.assertEqual(normalize_name("a" * 63 + "é"), ("a" * 63, True))
        self.assertEqual(normalize_name("é" * 30), ("é" * 30, False))

    def test_email(self):
        self.assertEqual(normalize_email("A@Bücher.EXAMPLE", 1), "A@xn--bcher-kva.example")
        with self.assertRaises(FileError):
            normalize_email("x@a..b", 1)

    def test_time(self):
        self.assertEqual(normalize_time("2026-01-01T01:00:00+02:00", 1), "2025-12-31T23:00:00Z")
        with self.assertRaises(FileError):
            normalize_time("2026-01-01T00:00:00z", 1)


if __name__ == "__main__":
    unittest.main()
