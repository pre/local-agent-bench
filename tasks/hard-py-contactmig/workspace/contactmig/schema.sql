-- Schema of the v2 contact store. Do not change it: other services read these tables.
CREATE TABLE IF NOT EXISTS accounts (
    id           INTEGER PRIMARY KEY,
    match_key    TEXT UNIQUE,
    display_name TEXT NOT NULL,
    updated      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS emails (
    account_id INTEGER NOT NULL REFERENCES accounts (id),
    position   INTEGER NOT NULL,
    address    TEXT NOT NULL,
    PRIMARY KEY (account_id, position)
);

CREATE TABLE IF NOT EXISTS legacy_ids (
    legacy_id  TEXT PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts (id)
);

CREATE TABLE IF NOT EXISTS tags (
    account_id INTEGER NOT NULL REFERENCES accounts (id),
    tag        TEXT NOT NULL,
    PRIMARY KEY (account_id, tag)
);

CREATE TABLE IF NOT EXISTS migrated_files (
    name    TEXT PRIMARY KEY,
    sha256  TEXT NOT NULL,
    records INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS issues (
    file   TEXT NOT NULL,
    record INTEGER,
    level  TEXT NOT NULL CHECK (level IN ('warning', 'error')),
    code   TEXT NOT NULL,
    detail TEXT
);
