"""The migration run (docs/MIGRATION.md, sections 1, 2 and 7 to 11)."""

import hashlib
import os
import sqlite3
import sys
from pathlib import Path

from . import db
from .records import FileError, Record, parse_file

MAX_EMAILS = 5
FAIL_AFTER_ENV = "CONTACTMIG_FAIL_AFTER_FILES"
SEAM_EXIT = 75


def source_files(source: Path) -> list[Path]:
    """The input files in processing order (F1, F2)."""
    names = [entry.name for entry in os.scandir(source)
             if entry.name.endswith(".rec") and not entry.name.startswith(".")
             and entry.is_file(follow_symlinks=True)]
    return [source / name for name in sorted(names)]


def open_database(db_path: str, dry_run: bool) -> sqlite3.Connection:
    """Open the database. A dry run works on an in-memory copy, so the file stays the same (C5)."""
    if not dry_run:
        conn = db.connect(db_path)
    else:
        conn = sqlite3.connect(":memory:")
        if Path(db_path).exists():
            disk = sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True)
            disk.backup(conn)
            disk.close()
        db.apply_schema(conn)
    conn.isolation_level = None  # explicit BEGIN and COMMIT: one transaction for each file (T3, T4)
    return conn


def add_issue(conn: sqlite3.Connection, file: str, record: int | None, level: str, code: str,
              detail: str | None = None) -> None:
    conn.execute("INSERT INTO issues (file, record, level, code, detail) VALUES (?, ?, ?, ?, ?)",
                 (file, record, level, code, detail))


def apply_record(conn: sqlite3.Connection, file: str, record: Record) -> None:
    """Create or merge the account of one record (M1 to M7, X1)."""
    row = None
    if record.match_key is not None:
        row = conn.execute("SELECT id, updated FROM accounts WHERE match_key = ?", (record.match_key,)).fetchone()
    owner = conn.execute("SELECT account_id FROM legacy_ids WHERE legacy_id = ?", (record.legacy_id,)).fetchone()
    if owner is not None and (row is None or owner[0] != row[0]):
        raise FileError("duplicate-id", record.number)

    if row is None:
        account_id = conn.execute(
            "INSERT INTO accounts (match_key, display_name, updated) VALUES (?, ?, ?)",
            (record.match_key, record.name, record.updated),
        ).lastrowid
    else:
        account_id, updated = row
        if record.updated >= updated:  # UTC strings of one fixed form compare as points in time
            conn.execute("UPDATE accounts SET display_name = ?, updated = ? WHERE id = ?",
                         (record.name, record.updated, account_id))

    present = [address for (address,) in conn.execute(
        "SELECT address FROM emails WHERE account_id = ? ORDER BY position", (account_id,))]
    seen = {address.lower() for address in present}
    count = len(present)
    for address in record.emails:
        key = address.lower()
        if key in seen:
            continue
        seen.add(key)
        if count >= MAX_EMAILS:
            add_issue(conn, file, record.number, "warning", "email-dropped", address)
            continue
        conn.execute("INSERT INTO emails (account_id, position, address) VALUES (?, ?, ?)",
                     (account_id, count, address))
        count += 1

    for tag in sorted(record.tags):
        conn.execute("INSERT OR IGNORE INTO tags (account_id, tag) VALUES (?, ?)", (account_id, tag))
    conn.execute("INSERT OR IGNORE INTO legacy_ids (legacy_id, account_id) VALUES (?, ?)",
                 (record.legacy_id, account_id))
    if record.name_truncated:
        add_issue(conn, file, record.number, "warning", "name-truncated")


def migrate_file(conn: sqlite3.Connection, name: str, data: bytes, digest: str) -> None:
    """Apply one file in the open transaction (T3). Raises FileError on a fault."""
    conn.execute("DELETE FROM issues WHERE file = ?", (name,))
    records, fallback = parse_file(data)
    if fallback:
        add_issue(conn, name, None, "warning", "encoding-fallback")
    for record in records:
        apply_record(conn, name, record)
    conn.execute("INSERT INTO migrated_files (name, sha256, records) VALUES (?, ?, ?)",
                 (name, digest, len(records)))


def write_error(conn: sqlite3.Connection, name: str, error: FileError, remove_warnings: bool) -> None:
    conn.execute("BEGIN")
    if remove_warnings:
        conn.execute("DELETE FROM issues WHERE file = ?", (name,))
    else:
        conn.execute("DELETE FROM issues WHERE file = ? AND level = 'error'", (name,))
    add_issue(conn, name, error.record, "error", error.code)
    conn.execute("COMMIT")


def fail_after() -> int | None:
    value = os.environ.get(FAIL_AFTER_ENV, "")
    return int(value) if value.isdigit() and int(value) > 0 else None


def run_migration(source: str, db_path: str, dry_run: bool = False) -> int:
    source_dir = Path(source)
    if not source_dir.is_dir():
        print(f"contactmig: {source} is not a directory", file=sys.stderr)
        return 2
    files = source_files(source_dir)
    conn = open_database(db_path, dry_run)
    stop_after = fail_after()
    migrated = unchanged = failed = processed = 0
    try:
        for path in files:
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            row = conn.execute("SELECT sha256 FROM migrated_files WHERE name = ?", (path.name,)).fetchone()
            if row is not None and row[0] == digest:
                unchanged += 1
                continue
            if row is not None:
                write_error(conn, path.name, FileError("changed-after-migration"), remove_warnings=False)
                failed += 1
            else:
                conn.execute("BEGIN")
                try:
                    migrate_file(conn, path.name, data, digest)
                except FileError as error:
                    conn.execute("ROLLBACK")
                    write_error(conn, path.name, error, remove_warnings=True)
                    failed += 1
                else:
                    conn.execute("COMMIT")
                    migrated += 1
            processed += 1
            if stop_after is not None and processed >= stop_after:
                return SEAM_EXIT
    finally:
        conn.close()
    print(f"migrated={migrated} unchanged={unchanged} failed={failed}")
    return 1 if failed else 0
