"""Parser of the v1 record files.

First draft: it reads the simple files of the sample directory. See
docs/MIGRATION.md for the full format.
"""


def parse_records(text: str) -> list[dict]:
    """Return one dict for each record: single fields as strings, email and tags as lists."""
    records = []
    current: dict = {}
    for line in text.splitlines():
        if not line.strip():
            if current:
                records.append(current)
                current = {}
            continue
        if line.startswith("#"):
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key in ("email", "tags"):
            current.setdefault(key, []).append(value)
        else:
            current[key] = value
    if current:
        records.append(current)
    return records
