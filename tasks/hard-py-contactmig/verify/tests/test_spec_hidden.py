"""Hidden tests of the contact store migration. Each test class is one check of verify.sh.

The tests use only the command line (C1 to C5), the schema and docs/MIGRATION.md.
"""

import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOM = b"\xef\xbb\xbf"
TABLES = ("accounts", "emails", "legacy_ids", "tags", "migrated_files", "issues")


def rec(*lines: str, eol: str = "\n") -> bytes:
    return "".join(line + eol for line in lines).encode("utf-8")


def person(legacy_id: str, name: str, updated: str, *emails: str, tags: str | None = None) -> list[str]:
    lines = [f"id: {legacy_id}", f"name: {name}"]
    lines += [f"email: {e}" for e in emails]
    if tags is not None:
        lines.append(f"tags: {tags}")
    lines.append(f"updated: {updated}")
    return lines


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class MigrationCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp(prefix="contactmig-hidden-")
        self.addCleanup(shutil.rmtree, tmp, True)
        self.tmp = Path(tmp)
        self.source = self.tmp / "v1"
        self.source.mkdir()
        self.db = self.tmp / "contacts.db"

    def write(self, name: str, data: bytes, source: Path | None = None) -> bytes:
        path = (source or self.source) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return data

    def migrate(self, *extra: str, source: Path | None = None, db: Path | None = None,
                env: dict | None = None) -> subprocess.CompletedProcess:
        full_env = {k: v for k, v in os.environ.items() if k != "CONTACTMIG_FAIL_AFTER_FILES"}
        full_env.update(env or {})
        return subprocess.run(
            [sys.executable, "-m", "contactmig", "migrate", "--source", str(source or self.source),
             "--db", str(db or self.db), *extra],
            cwd=ROOT, capture_output=True, text=True, timeout=60, env=full_env,
        )

    def assertRun(self, proc: subprocess.CompletedProcess, status: int, summary: str | None = None):
        self.assertEqual(proc.returncode, status, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
        if summary is not None:
            lines = proc.stdout.splitlines()
            self.assertTrue(lines, "no output")
            self.assertEqual(lines[-1], summary)

    def query(self, sql: str, params: tuple = (), db: Path | None = None) -> list[tuple]:
        conn = sqlite3.connect(db or self.db)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def accounts(self) -> list[tuple]:
        return self.query("SELECT id, match_key, display_name, updated FROM accounts ORDER BY id")

    def emails(self, account_id: int) -> list[str]:
        return [a for (a,) in self.query(
            "SELECT address FROM emails WHERE account_id = ? ORDER BY position", (account_id,))]

    def positions(self) -> list[tuple]:
        return self.query("SELECT account_id, position FROM emails ORDER BY account_id, position")

    def tags(self, account_id: int) -> list[str]:
        return [t for (t,) in self.query("SELECT tag FROM tags WHERE account_id = ? ORDER BY tag", (account_id,))]

    def legacy(self) -> dict[str, int]:
        return dict(self.query("SELECT legacy_id, account_id FROM legacy_ids"))

    def issues(self, db: Path | None = None) -> list[tuple]:
        rows = self.query("SELECT file, record, level, code, detail FROM issues", db=db)
        return sorted(rows, key=repr)

    def assertIssues(self, expected: list[tuple]):
        self.assertEqual(self.issues(), sorted(expected, key=repr))

    def files(self) -> dict[str, tuple]:
        return {name: (digest, count) for name, digest, count in
                self.query("SELECT name, sha256, records FROM migrated_files")}

    def dump(self, db: Path | None = None) -> dict[str, list]:
        conn = sqlite3.connect(db or self.db)
        try:
            return {t: sorted(conn.execute(f"SELECT * FROM {t}").fetchall(), key=repr) for t in TABLES}
        finally:
            conn.close()

    def assertPositionsDense(self):
        by_account: dict[int, list[int]] = {}
        for account_id, position in self.positions():
            by_account.setdefault(account_id, []).append(position)
        for account_id, positions in by_account.items():
            self.assertEqual(positions, list(range(len(positions))), f"positions of account {account_id}")


SPEC_EXAMPLE = rec(
    "# exported 2026-10-01",
    "id: c-100",
    "name: Ada   Lovelace",
    "email: Ada@Example.COM",
    "email: ada.l@example.org",
    "tags: Math, history,",
    "updated: 2026-03-01T10:00:00+02:00",
    "",
    "id: c-101",
    "Name: Ada L.",
    "email: ada@example.com",
    "updated: 2026-03-01T08:00:00Z",
)


class BasicMigrationTest(MigrationCase):
    def test_spec_example(self):
        data = self.write("a.rec", SPEC_EXAMPLE)
        self.assertRun(self.migrate(), 0, "migrated=1 unchanged=0 failed=0")
        self.assertEqual(self.accounts(), [(1, "ada@example.com", "Ada L.", "2026-03-01T08:00:00Z")])
        self.assertEqual(self.emails(1), ["Ada@example.com", "ada.l@example.org"])
        self.assertEqual(self.tags(1), ["history", "math"])
        self.assertEqual(self.legacy(), {"c-100": 1, "c-101": 1})
        self.assertEqual(self.files(), {"a.rec": (sha(data), 2)})
        self.assertIssues([])

    def test_schema_unchanged(self):
        self.write("a.rec", SPEC_EXAMPLE)
        self.assertRun(self.migrate(), 0)
        for table, columns in {
            "accounts": ["id", "match_key", "display_name", "updated"],
            "emails": ["account_id", "position", "address"],
            "legacy_ids": ["legacy_id", "account_id"],
            "tags": ["account_id", "tag"],
            "migrated_files": ["name", "sha256", "records"],
            "issues": ["file", "record", "level", "code", "detail"],
        }.items():
            self.assertEqual([row[1] for row in self.query(f"PRAGMA table_info({table})")], columns, table)


class DecodingTest(MigrationCase):
    def test_encodings(self):
        self.write("1-latin.rec", b"#v1 encoding=latin-1  \r\nid: d-1\r\nname: Ren\xe9e Fran\xe7ois\r\n"
                                  b"email: renee@example.fr\r\nupdated: 2026-01-01T00:00:00Z\r\n")
        self.write("2-fallback.rec", b"id: d-2\nname: \x93Nord\x94 \x80 Handel\nemail: nord@example.com\n"
                                     b"updated: 2026-01-02T00:00:00Z\n")
        self.write("3-bom-decl.rec", BOM + b"#v1 encoding=utf-8\r\nid: d-3\r\nname: Zo\xc3\xab\r\n"
                                     b"email: zoe@example.com\r\nupdated: 2026-01-03T00:00:00Z\r\n")
        self.write("4-bom.rec", BOM + "id: d-4\nname: Łukasz\nemail: lukasz@example.pl\n"
                                      "updated: 2026-01-04T00:00:00Z\n".encode("utf-8"))
        self.write("5-cp1252.rec", b"#v1 encoding=cp1252\nid: d-5\nname: Euro \x80 Shop\nemail: shop@example.com\n"
                                   b"updated: 2026-01-05T00:00:00Z\n")
        self.write("6-utf8.rec", "id: d-6\nname: Ēvalds Šīrons\nemail: evalds@example.lv\n"
                                 "updated: 2026-01-06T00:00:00Z\n".encode("utf-8"))
        self.assertRun(self.migrate(), 0, "migrated=6 unchanged=0 failed=0")
        self.assertEqual([a[2] for a in self.accounts()],
                         ["Renée François", "“Nord” € Handel", "Zoë", "Łukasz", "Euro € Shop", "Ēvalds Šīrons"])
        self.assertIssues([("2-fallback.rec", None, "warning", "encoding-fallback", None)])

    def test_encoding_errors(self):
        body = b"id: x-1\nname: Bad\nemail: bad@example.com\nupdated: 2026-01-01T00:00:00Z\n"
        self.write("0-good.rec", b"id: g-1\nname: Good\nemail: good@example.com\nupdated: 2026-01-01T00:00:00Z\n")
        self.write("e1.rec", b"#v1 encoding=ascii\n" + body)
        self.write("e2.rec", b"#v1 encoding=Latin-1\n" + body)
        self.write("e3.rec", BOM + b"#v1 encoding=latin-1\n" + body)
        self.write("e4.rec", BOM + b"#v1 encoding=cp1252\r\n" + body)
        self.write("e5.rec", b"#v1 encoding=utf-8\nid: x-5\nname: Ren\xe9e\nemail: r@example.com\n"
                             b"updated: 2026-01-01T00:00:00Z\n")
        self.write("e6.rec", b"id: x-6\nname: Caf\xe9 \x81\nemail: c@example.com\nupdated: 2026-01-01T00:00:00Z\n")
        self.write("e7.rec", BOM + b"id: x-7\nname: Caf\xe9\nemail: c7@example.com\nupdated: 2026-01-01T00:00:00Z\n")
        self.assertRun(self.migrate(), 1, "migrated=1 unchanged=0 failed=7")
        self.assertIssues([
            ("e1.rec", None, "error", "unknown-encoding", None),
            ("e2.rec", None, "error", "unknown-encoding", None),
            ("e3.rec", None, "error", "encoding-conflict", None),
            ("e4.rec", None, "error", "encoding-conflict", None),
            ("e5.rec", None, "error", "undecodable", None),
            ("e6.rec", None, "error", "undecodable", None),
            ("e7.rec", None, "error", "undecodable", None),
        ])
        self.assertEqual(self.accounts(), [(1, "good@example.com", "Good", "2026-01-01T00:00:00Z")])
        self.assertEqual(list(self.files()), ["0-good.rec"])


class LinesTest(MigrationCase):
    def test_line_ends_continuations_and_comments(self):
        data = (b"id: L-1\r\nname: Anna\r\n  Maria\r\n\tSchmidt \r\nemail: anna@example.com\r\n"
                b"updated: 2026-01-01T00:00:00Z\r\n"
                b"   \t \r\n"
                b"# comment between records\r\n"
                b"ID: L-2\rNAME: Bo\xe2\x80\xa8Ek\x0cSon\rEmail: bo@example.com\rUPDATED: 2026-01-02T00:00:00Z\r\n"
                b"\n"
                b"id: L-3\nname: Cy\n# note inside the record\nemail: cy@example.com\n#v1 encoding=latin-1\n"
                b"updated: 2026-01-03T00:00:00Z\nunknown-key: ignored\nX_Other: also ignored\n"
                b"\n\n\n# trailing comment\n")
        self.write("lines.rec", data)
        self.write("nel.rec", b"#v1 encoding=latin-1\nid: L-4\nname: Dee\x85Dee\xa0Jay\nemail: dee@example.com\n"
                              b"updated: 2026-01-04T00:00:00Z")
        self.write("zero.rec", b"# nothing here\n\n   \n\t\n")
        self.assertRun(self.migrate(), 0, "migrated=3 unchanged=0 failed=0")
        self.assertEqual([a[2] for a in self.accounts()], ["Anna Maria Schmidt", "Bo Ek Son", "Cy", "Dee Dee Jay"])
        self.assertEqual({k: v[1] for k, v in self.files().items()}, {"lines.rec": 3, "nel.rec": 1, "zero.rec": 0})
        self.assertEqual(self.legacy(), {"L-1": 1, "L-2": 2, "L-3": 3, "L-4": 4})

    def test_continuation_of_tags(self):
        self.write("c.rec", b"id: k-1\nname: Kim\nemail: kim@example.com\ntags: one,\n two\n\t, Three\n"
                            b"updated: 2026-01-01T00:00:00Z\n")
        self.assertRun(self.migrate(), 0, "migrated=1 unchanged=0 failed=0")
        self.assertEqual(self.tags(1), ["one", "three", "two"])

    def test_syntax_errors(self):
        good = person("g-1", "Good", "2026-01-01T00:00:00Z", "good@example.com")
        self.write("s1.rec", rec(*good, "", "  continuation at the start of record 2", "name: X"))
        self.write("s2.rec", rec(*person("g-2", "Ok", "2026-01-01T00:00:00Z", "ok2@example.com"), "",
                                 *person("g-3", "Ok", "2026-01-01T00:00:00Z", "ok3@example.com"), "",
                                 "id: g-4", "this line has no colon", "name: X", "updated: 2026-01-01T00:00:00Z"))
        self.write("s3.rec", rec("id: g-5", "1abc: bad key", "name: X", "updated: 2026-01-01T00:00:00Z"))
        self.write("s4.rec", rec("# only a comment", "\tcontinuation after a comment"))
        self.write("s5.rec", rec("id: g-6", "na me: bad key", "name: X", "updated: 2026-01-01T00:00:00Z"))
        self.assertRun(self.migrate(), 1, "migrated=0 unchanged=0 failed=5")
        self.assertIssues([
            ("s1.rec", 2, "error", "syntax", None),
            ("s2.rec", 3, "error", "syntax", None),
            ("s3.rec", 1, "error", "syntax", None),
            ("s4.rec", 1, "error", "syntax", None),
            ("s5.rec", 1, "error", "syntax", None),
        ])
        self.assertEqual(self.accounts(), [])


class NormalizationTest(MigrationCase):
    def test_names_emails_times_tags(self):
        self.write("n.rec", rec(
            *person("n-1", "José  \t García ", "2026-05-10T23:30:00-02:00",
                    "Jose.G@Bücher.Example", tags="VIP, , Beta ,vip"),
            "",
            *person("n-2", " Mixed　Case ", "2026-12-31T23:59:59+01:00", "Mixed.Case@EXAMPLE.ORG",
                    "a@b@Straße.DE"),
            "",
            *person("n-3", "Ångström", "2026-06-01T00:30:00+00:30", "jose.g@xn--bcher-kva.example"),
        ))
        self.assertRun(self.migrate(), 0, "migrated=1 unchanged=0 failed=0")
        self.assertEqual(self.accounts(), [
            (1, "jose.g@xn--bcher-kva.example", "Ångström", "2026-06-01T00:00:00Z"),
            (2, "mixed.case@example.org", "Mixed Case", "2026-12-31T22:59:59Z"),
        ])
        self.assertEqual(self.emails(1), ["Jose.G@xn--bcher-kva.example"])
        self.assertEqual(self.emails(2), ["Mixed.Case@example.org", "a@b@strasse.de"])
        self.assertEqual(self.tags(1), ["beta", "vip"])
        self.assertEqual(self.legacy(), {"n-1": 1, "n-2": 2, "n-3": 1})

    def test_name_is_nfc(self):
        self.write("n.rec", rec(*person("n-1", "José  \t García ", "2026-05-10T23:30:00-02:00",
                                        "jose@example.com")))
        self.assertRun(self.migrate(), 0)
        self.assertEqual(self.accounts(), [(1, "jose@example.com", "José García", "2026-05-11T01:30:00Z")])

    def test_field_errors(self):
        t = "2026-01-01T00:00:00Z"
        ok = person("ok-1", "Ok", t, "ok@example.com")
        cases = {
            "f01.rec": (rec(*ok, "", "id: f-1", "name: A", "name: B", "updated: " + t), 2, "duplicate-field"),
            "f02.rec": (rec("id: f-2", "name: A", "email: a2@example.com"), 1, "missing-field"),
            "f03.rec": (rec("id:   ", "name: A", "updated: " + t), 1, "missing-field"),
            "f04.rec": (rec(*ok, "", "id: f-4", "name:    ", "updated: " + t), 2, "missing-field"),
            "f05.rec": (rec("id: f_5", "name: A", "updated: " + t), 1, "bad-id"),
            "f06.rec": (rec("id: " + "x" * 33, "name: A", "updated: " + t), 1, "bad-id"),
            "f07.rec": (rec(*ok, "", "id: f-7", "name: A", "updated: 2026-02-30T00:00:00Z"), 2, "bad-timestamp"),
            "f08.rec": (rec("id: f-8", "name: A", "updated: 2026-01-01 00:00:00Z"), 1, "bad-timestamp"),
            "f09.rec": (rec("id: f-9", "name: A", "updated: 2026-01-01T00:00:00z"), 1, "bad-timestamp"),
            "f10.rec": (rec("id: f-10", "name: A", "updated: 2026-01-01T00:00:00+0200"), 1, "bad-timestamp"),
            "f11.rec": (rec("id: f-11", "name: A", "updated: 2026-01-01T00:00:00.5Z"), 1, "bad-timestamp"),
            "f12.rec": (rec("id: f-12", "name: A", "updated: 2026-01-01"), 1, "bad-timestamp"),
            "f13.rec": (rec("id: f-13", "name: A", "email: no-at-sign", "updated: " + t), 1, "bad-email"),
            "f14.rec": (rec("id: f-14", "name: A", "email: ok14@example.com", "email: @example.com",
                            "updated: " + t), 1, "bad-email"),
            "f15.rec": (rec(*ok, "", "id: f-15", "name: A", "email: x@exa..mple.com", "updated: " + t),
                        2, "bad-email"),
            "f16.rec": (rec("id: f-16", "name: A", "email: x@", "updated: " + t), 1, "bad-email"),
            "f17.rec": (rec("id: f-17", "name: A", "email: x@" + "a" * 64 + ".com", "updated: " + t),
                        1, "bad-email"),
            "f18.rec": (rec("id: f-18", "ID: f-18b", "name: A", "updated: " + t), 1, "duplicate-field"),
            "f19.rec": (rec("id: f-19", "name: A", "updated: ٢026-01-01T00:00:00Z"), 1, "bad-timestamp"),
        }
        for name, (data, _, _) in cases.items():
            self.write(name, data)
        self.assertRun(self.migrate(), 1, f"migrated=0 unchanged=0 failed={len(cases)}")
        expected = sorted(((name, record, "error", code, None) for name, (_, record, code) in cases.items()),
                          key=repr)
        self.assertIssues(expected)
        self.assertEqual(self.accounts(), [])
        self.assertEqual(self.files(), {})


class NameLimitTest(MigrationCase):
    def test_truncation(self):
        t = "2026-01-01T00:00:00Z"
        self.write("names.rec", rec(
            *person("t-1", "a" * 63 + "é", t, "t1@example.com"),
            "", *person("t-2", "b" * 62 + " " + "€x", t, "t2@example.com"),
            "", *person("t-3", "c" * 60 + "😀", t, "t3@example.com"),
            "", *person("t-4", "d    " * 20, t, "t4@example.com"),
            "", *person("t-5", "é" * 30, t, "t5@example.com"),
            "", *person("t-6", "f" * 61 + "😀z", t, "t6@example.com"),
            "", *person("t-7", "Short Name", "2026-06-01T00:00:00Z", "t7@example.com"),
            "", *person("t-8", "g" * 70, "2026-05-01T00:00:00Z", "t7@example.com"),
        ))
        self.assertRun(self.migrate(), 0, "migrated=1 unchanged=0 failed=0")
        self.assertEqual([a[2] for a in self.accounts()], [
            "a" * 63, "b" * 62, "c" * 60 + "😀", ("d " * 20).strip(), "é" * 30, "f" * 61, "Short Name",
        ])
        self.assertIssues([
            ("names.rec", 1, "warning", "name-truncated", None),
            ("names.rec", 2, "warning", "name-truncated", None),
            ("names.rec", 6, "warning", "name-truncated", None),
            ("names.rec", 8, "warning", "name-truncated", None),
        ])

    def test_truncated_name_wins_merge(self):
        self.write("w.rec", rec(*person("w-1", "Old", "2026-01-01T00:00:00Z", "w@example.com"), "",
                                *person("w-2", "Ж" * 40, "2026-01-02T00:00:00Z", "W@example.com")))
        self.assertRun(self.migrate(), 0)
        self.assertEqual(self.accounts(), [(1, "w@example.com", "Ж" * 32, "2026-01-02T00:00:00Z")])
        self.assertIssues([("w.rec", 2, "warning", "name-truncated", None)])


class MergeTest(MigrationCase):
    def test_merge_rules(self):
        self.write("m.rec", rec(
            *person("m-1", "First", "2026-04-01T12:00:00Z", "Pat@Example.com", "pat.work@example.net", tags="a"),
            "", *person("m-2", "Older", "2026-04-01T11:59:59Z", "pat@example.com", "PAT.WORK@example.net",
                        "pat.home@example.org", tags="b"),
            "", *person("m-3", "Same Time", "2026-04-01T14:00:00+02:00", "PAT@EXAMPLE.COM"),
            "", *person("m-4", "Not primary", "2026-05-01T00:00:00Z", "other@example.com", "pat@example.com"),
            "", *person("m-5", "No Email", "2026-05-02T00:00:00Z"),
            "", *person("m-6", "No Email", "2026-05-03T00:00:00Z"),
            "", *person("m-1", "Pat Again", "2026-03-01T00:00:00Z", "pat@example.com", tags="c"),
            "", *person("m-8", "Work", "2026-05-04T00:00:00Z", "pat.work@example.net"),
            "", *person("m-9", "Later Offset", "2026-04-01T13:00:00+00:59", "pat@example.com"),
        ))
        self.assertRun(self.migrate(), 0, "migrated=1 unchanged=0 failed=0")
        self.assertEqual(self.accounts(), [
            (1, "pat@example.com", "Later Offset", "2026-04-01T12:01:00Z"),
            (2, "other@example.com", "Not primary", "2026-05-01T00:00:00Z"),
            (3, None, "No Email", "2026-05-02T00:00:00Z"),
            (4, None, "No Email", "2026-05-03T00:00:00Z"),
            (5, "pat.work@example.net", "Work", "2026-05-04T00:00:00Z"),
        ])
        self.assertEqual(self.emails(1), ["Pat@example.com", "pat.work@example.net", "pat.home@example.org"])
        self.assertEqual(self.emails(2), ["other@example.com", "pat@example.com"])
        self.assertEqual(self.emails(3), [])
        self.assertEqual(self.tags(1), ["a", "b", "c"])
        self.assertEqual(self.legacy(), {"m-1": 1, "m-2": 1, "m-3": 1, "m-4": 2, "m-5": 3, "m-6": 4,
                                         "m-8": 5, "m-9": 1})
        self.assertEqual(self.files()["m.rec"][1], 9)
        self.assertPositionsDense()

    def test_times_compare_in_utc(self):
        self.write("o.rec", rec(*person("o-1", "Newest", "2026-04-02T00:00:00+05:00", "o@example.com"), "",
                                *person("o-2", "Oldest", "2026-04-01T20:00:00Z", "O@EXAMPLE.com")))
        self.assertRun(self.migrate(), 0)
        # 2026-04-02T00:00:00+05:00 is 2026-04-01T19:00:00Z, so the second record is later.
        self.assertEqual(self.accounts(), [(1, "o@example.com", "Oldest", "2026-04-01T20:00:00Z")])
        self.assertEqual(self.emails(1), ["o@example.com"])


class EmailLimitTest(MigrationCase):
    def test_limit_of_five(self):
        self.write("l.rec", rec(
            *person("e-1", "Many", "2026-01-01T00:00:00Z", "u0@example.com", "u1@example.com", "U1@example.com",
                    "u2@example.com", "u3@example.com", "u4@example.com", "u5@example.com", "U6@Example.COM",
                    "u5@EXAMPLE.com"),
            "", *person("e-2", "Many", "2026-01-01T00:00:00Z", "U0@example.com", "u9@example.com",
                        "u4@example.com"),
            "", *person("e-3", "Few", "2026-01-01T00:00:00Z", "v0@example.com", "v1@example.com", "V1@example.com"),
        ))
        self.assertRun(self.migrate(), 0, "migrated=1 unchanged=0 failed=0")
        self.assertEqual(self.emails(1), [f"u{i}@example.com" for i in range(5)])
        self.assertEqual(self.emails(2), ["v0@example.com", "v1@example.com"])
        self.assertIssues([
            ("l.rec", 1, "warning", "email-dropped", "U6@example.com"),
            ("l.rec", 1, "warning", "email-dropped", "u5@example.com"),
            ("l.rec", 2, "warning", "email-dropped", "u9@example.com"),
        ])
        self.assertPositionsDense()

    def test_limit_over_runs(self):
        self.write("a.rec", rec(*person("e-1", "Run", "2026-01-01T00:00:00Z", *[f"r{i}@example.com" for i in range(4)])))
        self.assertRun(self.migrate(), 0)
        self.write("b.rec", rec(*person("e-2", "Run", "2026-01-01T00:00:00Z", "r0@example.com", "r3@example.com",
                                        "r7@example.com", "r8@example.com")))
        self.assertRun(self.migrate(), 0, "migrated=1 unchanged=1 failed=0")
        self.assertEqual(self.emails(1), ["r0@example.com", "r1@example.com", "r2@example.com", "r3@example.com",
                                          "r7@example.com"])
        self.assertIssues([("b.rec", 1, "warning", "email-dropped", "r8@example.com")])


class FileOrderTest(MigrationCase):
    def test_order_and_selection(self):
        t = "2026-01-01T00:00:00Z"
        names = ["B.rec", "a.rec", "a b.rec", "ä.rec", "10.rec", "9.rec", ".hidden.rec", "notes.txt",
                 "c.REC", "c.rec.bak", "sub/x.rec"]
        for number, name in enumerate(names):
            label = name.replace("/", "-")
            self.write(name, rec(*person(f"o-{number}", label, t, f"o{number}@example.com")))
        (self.source / "dir.rec").mkdir()
        self.write("inner.rec", rec(*person("o-inner", "inner", t, "inner@example.com")), self.source / "dir.rec")
        proc = self.migrate()
        self.assertRun(proc, 0, "migrated=6 unchanged=0 failed=0")
        self.assertEqual([(a[0], a[2]) for a in self.accounts()],
                         [(1, "10.rec"), (2, "9.rec"), (3, "B.rec"), (4, "a b.rec"), (5, "a.rec"), (6, "ä.rec")])
        self.assertEqual(sorted(self.files()), ["10.rec", "9.rec", "B.rec", "a b.rec", "a.rec", "ä.rec"])

    def test_tie_break_by_file_order(self):
        t = "2026-02-02T02:02:02Z"
        self.write("b.rec", rec(*person("b-1", "From b", t, "same@example.com")))
        self.write("a.rec", rec(*person("a-1", "From a", t, "same@example.com")))
        self.write("Z.rec", rec(*person("z-1", "From Z", t, "same@example.com")))
        self.assertRun(self.migrate(), 0)
        self.assertEqual(self.accounts(), [(1, "same@example.com", "From b", t)])
        self.assertEqual(self.legacy(), {"z-1": 1, "a-1": 1, "b-1": 1})


class PartialFailureTest(MigrationCase):
    def test_bad_file_is_skipped_as_a_whole_and_fixed_later(self):
        a = self.write("1.rec", rec(*person("p-1", "Alpha", "2026-01-01T00:00:00Z", "a@example.com", tags="one")))
        bad = rec(
            *person("p-2", "Beta " + "x" * 80, "2026-01-02T00:00:00Z", "b@example.com", tags="two"),
            "", *person("p-3", "Alpha New", "2026-02-01T00:00:00Z", "A@example.com", "a2@example.com", tags="three"),
            "", *person("p-4", "Broken", "2026-13-01T00:00:00Z", "d@example.com"),
        )
        self.write("2.rec", bad)
        c = self.write("3.rec", b"id: p-5\nname: Gamma \x80\nemail: c@example.com\nupdated: 2026-01-03T00:00:00Z\n")
        self.assertRun(self.migrate(), 1, "migrated=2 unchanged=0 failed=1")
        self.assertEqual(self.accounts(), [(1, "a@example.com", "Alpha", "2026-01-01T00:00:00Z"),
                                           (2, "c@example.com", "Gamma €", "2026-01-03T00:00:00Z")])
        self.assertEqual(self.emails(1), ["a@example.com"])
        self.assertEqual(self.tags(1), ["one"])
        self.assertEqual(self.legacy(), {"p-1": 1, "p-5": 2})
        self.assertEqual(self.files(), {"1.rec": (sha(a), 1), "3.rec": (sha(c), 1)})
        self.assertIssues([("2.rec", 3, "error", "bad-timestamp", None),
                                         ("3.rec", None, "warning", "encoding-fallback", None)])

        fixed = self.write("2.rec", bad.replace(b"2026-13-01", b"2026-12-01"))
        self.assertRun(self.migrate(), 0, "migrated=1 unchanged=2 failed=0")
        self.assertEqual(self.accounts(), [
            (1, "a@example.com", "Alpha New", "2026-02-01T00:00:00Z"),
            (2, "c@example.com", "Gamma €", "2026-01-03T00:00:00Z"),
            (3, "b@example.com", "Beta " + "x" * 59, "2026-01-02T00:00:00Z"),
            (4, "d@example.com", "Broken", "2026-12-01T00:00:00Z"),
        ])
        self.assertEqual(self.emails(1), ["a@example.com", "a2@example.com"])
        self.assertEqual(self.tags(1), ["one", "three"])
        self.assertEqual(self.files()["2.rec"], (sha(fixed), 3))
        self.assertIssues([("2.rec", 1, "warning", "name-truncated", None),
                                         ("3.rec", None, "warning", "encoding-fallback", None)])


class DuplicateIdTest(MigrationCase):
    def test_duplicate_ids(self):
        t = "2026-01-01T00:00:00Z"
        self.write("1.rec", rec(*person("g-1", "One", t, "one@example.com"), "",
                                *person("g-0", "Zero", t)))
        self.write("2.rec", rec(*person("g-2", "Two", t, "two@example.com"), "",
                                *person("g-2", "Two Again", t, "other@example.com")))
        self.write("3.rec", rec(*person("g-3", "Three", t, "three@example.com"), "",
                                *person("g-1", "Not One", t, "notone@example.com")))
        self.write("4.rec", rec(*person("g-1", "One Same", "2026-02-01T00:00:00Z", "ONE@example.com")))
        self.write("5.rec", rec(*person("g-0", "Zero Again", t)))
        self.write("6.rec", rec(*person("g-6", "Six", t, "six@example.com"), "",
                                *person("g-6", "Six Same", t, "SIX@example.com")))
        self.assertRun(self.migrate(), 1, "migrated=3 unchanged=0 failed=3")
        self.assertIssues([("2.rec", 2, "error", "duplicate-id", None),
                                         ("3.rec", 2, "error", "duplicate-id", None),
                                         ("5.rec", 1, "error", "duplicate-id", None)])
        self.assertEqual(self.accounts(), [(1, "one@example.com", "One Same", "2026-02-01T00:00:00Z"),
                                           (2, None, "Zero", t),
                                           (3, "six@example.com", "Six Same", t)])
        self.assertEqual(self.legacy(), {"g-1": 1, "g-0": 2, "g-6": 3})

    def test_duplicate_id_over_runs(self):
        t = "2026-01-01T00:00:00Z"
        self.write("1.rec", rec(*person("r-1", "One", t, "one@example.com")))
        self.assertRun(self.migrate(), 0)
        self.write("2.rec", rec(*person("r-2", "Two", t, "two@example.com"), "",
                                *person("r-1", "Other", t, "other@example.com")))
        self.assertRun(self.migrate(), 1, "migrated=0 unchanged=1 failed=1")
        self.assertIssues([("2.rec", 2, "error", "duplicate-id", None)])
        self.assertEqual(len(self.accounts()), 1)


class RepeatRunTest(MigrationCase):
    def make_store(self):
        self.write("1.rec", rec(*person("i-1", "One " + "y" * 70, "2026-01-01T00:00:00Z", "one@example.com")))
        self.write("2.rec", b"id: i-2\nname: Caf\xe9\nemail: cafe@example.com\nupdated: 2026-01-01T00:00:00Z\n")
        self.write("3.rec", rec(*person("i-3", "Bad", "2026-01-01T00:00:00Z", "bad-email")))
        self.write("4.rec", rec(*person("i-4", "Four", "2026-01-01T00:00:00Z", "ONE@example.com", "x@example.com")))

    def test_second_run_changes_nothing(self):
        self.make_store()
        self.assertRun(self.migrate(), 1, "migrated=3 unchanged=0 failed=1")
        first = self.dump()
        self.assertIssues([("1.rec", 1, "warning", "name-truncated", None),
                                         ("2.rec", None, "warning", "encoding-fallback", None),
                                         ("3.rec", 1, "error", "bad-email", None)])
        self.assertRun(self.migrate(), 1, "migrated=0 unchanged=3 failed=1")
        self.assertEqual(self.dump(), first)
        self.assertRun(self.migrate(), 1, "migrated=0 unchanged=3 failed=1")
        self.assertEqual(self.dump(), first)

    def test_changed_file_after_migration(self):
        self.make_store()
        self.assertRun(self.migrate(), 1)
        before = self.dump()
        self.write("1.rec", rec(*person("i-1", "One Changed", "2026-03-01T00:00:00Z", "one@example.com")))
        for _ in range(2):
            self.assertRun(self.migrate(), 1, "migrated=0 unchanged=2 failed=2")
            after = self.dump()
            for table in ("accounts", "emails", "legacy_ids", "tags", "migrated_files"):
                self.assertEqual(after[table], before[table], table)
            self.assertIssues([("1.rec", None, "error", "changed-after-migration", None),
                                             ("1.rec", 1, "warning", "name-truncated", None),
                                             ("2.rec", None, "warning", "encoding-fallback", None),
                                             ("3.rec", 1, "error", "bad-email", None)])

    def test_changed_file_restored(self):
        self.make_store()
        self.assertRun(self.migrate(), 1)
        before = self.dump()
        original = (self.source / "1.rec").read_bytes()
        self.write("1.rec", original + b"\n# changed\n")
        self.assertRun(self.migrate(), 1)
        self.write("1.rec", original)
        self.assertRun(self.migrate(), 1, "migrated=0 unchanged=3 failed=1")
        after = self.dump()
        for table in ("accounts", "emails", "legacy_ids", "tags", "migrated_files"):
            self.assertEqual(after[table], before[table], table)
        self.assertIn(("1.rec", None, "error", "changed-after-migration", None), self.issues())


class CrossRunMergeTest(MigrationCase):
    def test_runs_in_steps_equal_one_run(self):
        t = "2026-07-07T07:07:07Z"
        files = {
            "a.rec": rec(*person("x-1", "Xavier", t, "xavier@example.com", "x2@example.com", tags="a")),
            "b.rec": rec(*person("x-2", "Xavier B", "2026-07-07T09:07:07+02:00", "XAVIER@example.com",
                                 "x3@example.com", tags="b"), "",
                         *person("y-1", "Yara", t, "yara@example.com")),
            "c.rec": rec(*person("x-1", "Xavier C", "2026-07-07T07:07:06Z", "xavier@example.com", "x4@example.com",
                                 "x5@example.com", "x6@example.com"), "",
                         *person("z-1", "Zed " + "z" * 64, t)),
            "d.rec": rec(*person("d-1", "Dee", t, "dee@example.com"), "", *person("y-1", "Not Yara", t)),
        }
        steps = [["a.rec"], ["b.rec"], ["c.rec", "d.rec"]]
        for step in steps:
            for name in step:
                self.write(name, files[name])
            self.migrate()
        stepped = self.dump()

        single_source = self.tmp / "single"
        single_db = self.tmp / "single.db"
        for name, data in files.items():
            self.write(name, data, single_source)
        proc = self.migrate(source=single_source, db=single_db)
        self.assertRun(proc, 1, "migrated=3 unchanged=0 failed=1")
        self.assertEqual(stepped, self.dump(single_db))
        self.assertEqual(self.accounts(), [
            (1, "xavier@example.com", "Xavier B", "2026-07-07T07:07:07Z"),
            (2, "yara@example.com", "Yara", t),
            (3, None, "Zed " + "z" * 60, t),
        ])
        self.assertEqual(self.emails(1), ["xavier@example.com", "x2@example.com", "x3@example.com",
                                          "x4@example.com", "x5@example.com"])
        self.assertIssues([("c.rec", 1, "warning", "email-dropped", "x6@example.com"),
                                         ("c.rec", 2, "warning", "name-truncated", None),
                                         ("d.rec", 2, "error", "duplicate-id", None)])


class DryRunTest(MigrationCase):
    def store(self, source: Path):
        self.write("1.rec", rec(*person("q-1", "One", "2026-01-01T00:00:00Z", "one@example.com")), source)
        self.write("2.rec", rec(*person("q-2", "Two", "2026-01-01T00:00:00Z", "bad")), source)

    def test_dry_run_on_new_database(self):
        self.store(self.source)
        dry = self.migrate("--dry-run")
        self.assertFalse(self.db.exists(), "--dry-run created the database")
        real = self.migrate()
        self.assertRun(real, 1, "migrated=1 unchanged=0 failed=1")
        self.assertEqual((dry.returncode, dry.stdout), (real.returncode, real.stdout))

    def test_dry_run_on_existing_database(self):
        self.store(self.source)
        self.assertRun(self.migrate(), 1)
        self.write("2.rec", rec(*person("q-2", "Two", "2026-01-01T00:00:00Z", "two@example.com")))
        self.write("3.rec", rec(*person("q-3", "Three " + "w" * 64, "2026-01-01T00:00:00Z", "ONE@example.com",
                                        "three@example.com")))
        self.write("1.rec", rec(*person("q-1", "One Changed", "2026-01-01T00:00:00Z", "one@example.com")))
        before = self.db.read_bytes()
        dry = self.migrate("--dry-run")
        self.assertEqual(self.db.read_bytes(), before, "--dry-run changed the database file")
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["contacts.db", "v1"])
        real = self.migrate()
        self.assertRun(real, 1, "migrated=2 unchanged=0 failed=1")
        self.assertEqual((dry.returncode, dry.stdout), (real.returncode, real.stdout))

    def test_dry_run_clean_store(self):
        self.write("1.rec", rec(*person("q-1", "One", "2026-01-01T00:00:00Z", "one@example.com")))
        self.assertRun(self.migrate("--dry-run"), 0, "migrated=1 unchanged=0 failed=0")
        self.assertFalse(self.db.exists())


class ResumeTest(MigrationCase):
    def store(self, source: Path):
        t = "2026-01-01T00:00:00Z"
        self.write("1.rec", rec(*person("s-1", "One", t, "one@example.com")), source)
        self.write("2.rec", rec(*person("s-2", "Two", t, "two@example.com"), "",
                                *person("s-3", "One Merge", "2026-02-01T00:00:00Z", "one@example.com",
                                        "one.b@example.com")), source)
        self.write("3.rec", rec(*person("s-4", "Bad", t, "@bad")), source)
        self.write("4.rec", rec(*person("s-5", "Four", t, "four@example.com")), source)
        self.write("5.rec", rec(*person("s-6", "Five", t, "Two@example.com", "five@example.com")), source)

    def clean_dump(self) -> dict:
        source = self.tmp / "clean"
        db = self.tmp / "clean.db"
        self.store(source)
        self.assertRun(self.migrate(source=source, db=db), 1, "migrated=4 unchanged=0 failed=1")
        return self.dump(db)

    def test_stop_and_resume(self):
        expected = self.clean_dump()
        self.store(self.source)
        stopped = self.migrate(env={"CONTACTMIG_FAIL_AFTER_FILES": "2"})
        self.assertEqual(stopped.returncode, 75, stopped.stderr)
        self.assertNotIn("migrated=", stopped.stdout)
        self.assertEqual(sorted(self.files()), ["1.rec", "2.rec"])
        self.assertEqual([a[0] for a in self.accounts()], [1, 2])
        stopped = self.migrate(env={"CONTACTMIG_FAIL_AFTER_FILES": "2"})
        self.assertEqual(stopped.returncode, 75, stopped.stderr)
        self.assertEqual(sorted(self.files()), ["1.rec", "2.rec", "4.rec"])
        self.assertIssues([("3.rec", 1, "error", "bad-email", None)])
        self.assertRun(self.migrate(), 1, "migrated=1 unchanged=3 failed=1")
        self.assertEqual(self.dump(), expected)

    def test_stop_after_more_files_than_present(self):
        expected = self.clean_dump()
        self.store(self.source)
        self.assertRun(self.migrate(env={"CONTACTMIG_FAIL_AFTER_FILES": "9"}), 1,
                       "migrated=4 unchanged=0 failed=1")
        self.assertEqual(self.dump(), expected)


class CliContractTest(MigrationCase):
    def test_source_is_not_a_directory(self):
        proc = self.migrate(source=self.tmp / "missing")
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertFalse(self.db.exists())
        plain = self.tmp / "plain.rec"
        plain.write_bytes(b"")
        proc = self.migrate(source=plain)
        self.assertEqual(proc.returncode, 2, proc.stderr)
        self.assertFalse(self.db.exists())

    def test_usage_error(self):
        proc = subprocess.run([sys.executable, "-m", "contactmig", "migrate", "--db", str(self.db)],
                              cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 2)
        self.assertFalse(self.db.exists())

    def test_empty_source(self):
        self.assertRun(self.migrate(), 0, "migrated=0 unchanged=0 failed=0")
        self.assertEqual(self.dump(), {t: [] for t in TABLES})


if __name__ == "__main__":
    unittest.main()
