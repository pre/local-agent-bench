"""Access to the v2 database."""

import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")


def connect(path: str) -> sqlite3.Connection:
    """Open the database at path and apply the schema. The file is created if it does not exist."""
    conn = sqlite3.connect(path)
    apply_schema(conn)
    return conn


def apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))


def dump(conn: sqlite3.Connection) -> dict[str, list[tuple]]:
    """Return the sorted rows of each table. Two databases with the same dump have the same content."""
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
    result = {}
    for table in tables:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        result[table] = sorted(rows, key=repr)
    return result
