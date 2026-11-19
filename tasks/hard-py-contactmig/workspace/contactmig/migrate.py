"""The migration run.

First draft: it creates one account for each new primary email and skips
the other records. Merge, limits, issues, repeated runs and --dry-run are
not done yet. See docs/MIGRATION.md.
"""

import hashlib
from pathlib import Path

from . import db
from .records import parse_records


def run_migration(source: str, db_path: str, dry_run: bool = False) -> int:
    conn = db.connect(db_path)
    migrated = 0
    for path in sorted(Path(source).glob("*.rec")):
        data = path.read_bytes()
        records = parse_records(data.decode("utf-8"))
        for record in records:
            emails = record.get("email", [])
            match_key = emails[0].lower() if emails else None
            if match_key and conn.execute("SELECT 1 FROM accounts WHERE match_key = ?", (match_key,)).fetchone():
                continue  # TODO: merge into the account
            cur = conn.execute(
                "INSERT INTO accounts (match_key, display_name, updated) VALUES (?, ?, ?)",
                (match_key, record["name"], record["updated"]),
            )
            account_id = cur.lastrowid
            for position, address in enumerate(emails):
                conn.execute(
                    "INSERT INTO emails (account_id, position, address) VALUES (?, ?, ?)",
                    (account_id, position, address),
                )
            conn.execute("INSERT INTO legacy_ids (legacy_id, account_id) VALUES (?, ?)", (record["id"], account_id))
            for value in record.get("tags", []):
                for tag in value.split(","):
                    if tag.strip():
                        conn.execute(
                            "INSERT OR IGNORE INTO tags (account_id, tag) VALUES (?, ?)",
                            (account_id, tag.strip().lower()),
                        )
        conn.execute(
            "INSERT INTO migrated_files (name, sha256, records) VALUES (?, ?, ?)",
            (path.name, hashlib.sha256(data).hexdigest(), len(records)),
        )
        migrated += 1
    conn.commit()
    conn.close()
    print(f"migrated={migrated} unchanged=0 failed=0")
    return 0
