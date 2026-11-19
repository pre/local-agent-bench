import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SIMPLE = """id: c-1
name: Ada Lovelace
email: ada@example.com
email: ada.l@example.org
tags: math, history
updated: 2026-03-01T10:00:00Z

id: c-2
name: Charles Babbage
email: charles@example.com
updated: 2026-02-01T09:00:00Z
"""


def migrate(source: Path, db: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "contactmig", "migrate", "--source", str(source), "--db", str(db)],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )


class BasicMigrationTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.source = Path(tmp.name) / "v1"
        self.source.mkdir()
        self.db = Path(tmp.name) / "contacts.db"

    def test_two_simple_records(self):
        (self.source / "a.rec").write_text(SIMPLE, encoding="utf-8")
        proc = migrate(self.source, self.db)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.splitlines()[-1], "migrated=1 unchanged=0 failed=0")
        conn = sqlite3.connect(self.db)
        self.addCleanup(conn.close)
        self.assertEqual(
            conn.execute("SELECT id, match_key, display_name, updated FROM accounts ORDER BY id").fetchall(),
            [(1, "ada@example.com", "Ada Lovelace", "2026-03-01T10:00:00Z"),
             (2, "charles@example.com", "Charles Babbage", "2026-02-01T09:00:00Z")],
        )
        self.assertEqual(
            conn.execute("SELECT account_id, position, address FROM emails ORDER BY 1, 2").fetchall(),
            [(1, 0, "ada@example.com"), (1, 1, "ada.l@example.org"), (2, 0, "charles@example.com")],
        )
        self.assertEqual(conn.execute("SELECT tag FROM tags WHERE account_id = 1 ORDER BY tag").fetchall(),
                         [("history",), ("math",)])
        self.assertEqual(conn.execute("SELECT legacy_id, account_id FROM legacy_ids ORDER BY 1").fetchall(),
                         [("c-1", 1), ("c-2", 2)])
        self.assertEqual(conn.execute("SELECT name, records FROM migrated_files").fetchall(), [("a.rec", 2)])


if __name__ == "__main__":
    unittest.main()
