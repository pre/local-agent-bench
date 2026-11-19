"""Decoding, parsing and normalization of the v1 record files (docs/MIGRATION.md, sections 3 to 6)."""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone

BOM = b"\xef\xbb\xbf"
DECLARATION = b"#v1 encoding="
ENCODINGS = ("utf-8", "latin-1", "cp1252")
KEY_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
ID_RE = re.compile(r"[A-Za-z0-9-]{1,32}")
TIME_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(Z|[+-][0-9]{2}:[0-9]{2})")
NAME_LIMIT = 64
SINGLE_KEYS = ("id", "name", "updated")


class FileError(Exception):
    """A fault that makes the whole file fail. record is the record number or None."""

    def __init__(self, code: str, record: int | None = None):
        super().__init__(code if record is None else f"{code} in record {record}")
        self.code = code
        self.record = record


@dataclass
class RawRecord:
    number: int
    fields: list[list[str]] = field(default_factory=list)  # [key in lower case, value]


@dataclass
class Record:
    number: int
    legacy_id: str
    name: str
    name_truncated: bool
    updated: str
    emails: list[str]
    tags: set[str]

    @property
    def match_key(self) -> str | None:
        return self.emails[0].lower() if self.emails else None


def decode(data: bytes) -> tuple[str, bool]:
    """Return the text and True if the cp1252 fallback was used (E1 to E6)."""
    has_bom = data.startswith(BOM)
    body = data[len(BOM):] if has_bom else data
    first_line = re.match(rb"[^\r\n]*", body).group(0)
    declared = None
    if first_line.startswith(DECLARATION):
        declared = first_line[len(DECLARATION):].strip(b" \t").decode("ascii", "replace")
        if declared not in ENCODINGS:
            raise FileError("unknown-encoding")
    if has_bom and declared not in (None, "utf-8"):
        raise FileError("encoding-conflict")
    encoding = "utf-8" if has_bom else declared
    if encoding is None:
        try:
            return body.decode("utf-8"), False
        except UnicodeDecodeError:
            encoding = "cp1252"
            fallback = True
    else:
        fallback = False
    try:
        return body.decode(encoding), fallback
    except UnicodeDecodeError:
        raise FileError("undecodable") from None


def split_records(text: str) -> list[RawRecord]:
    """Split the text into records of field lines (L1 to L7)."""
    records: list[RawRecord] = []
    current: RawRecord | None = None
    for line in re.split(r"\r\n|\r|\n", text):
        if line.strip(" \t") == "":
            current = None
            continue
        if line.startswith("#"):
            continue
        if current is None:
            current = RawRecord(len(records) + 1)
            records.append(current)
        if line[0] in " \t":
            if not current.fields:
                raise FileError("syntax", current.number)
            current.fields[-1][1] += " " + line.lstrip(" \t")
            continue
        key, sep, value = line.partition(":")
        key = key.strip(" \t")
        if not sep or not KEY_RE.fullmatch(key):
            raise FileError("syntax", current.number)
        current.fields.append([key.lower(), value])
    return records


def normalize_name(value: str) -> tuple[str, bool]:
    name = " ".join(unicodedata.normalize("NFC", value).split())
    data = name.encode("utf-8")
    if len(data) <= NAME_LIMIT:
        return name, False
    return data[:NAME_LIMIT].decode("utf-8", "ignore").rstrip(" "), True


def normalize_email(value: str, record: int) -> str:
    local, sep, domain = value.rpartition("@")
    if not sep or not local or not domain:
        raise FileError("bad-email", record)
    try:
        domain = domain.lower().encode("idna").decode("ascii")
    except UnicodeError:
        raise FileError("bad-email", record) from None
    return f"{local}@{domain}"


def normalize_time(value: str, record: int) -> str:
    if not TIME_RE.fullmatch(value):
        raise FileError("bad-timestamp", record)
    try:
        moment = datetime.fromisoformat(value).astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise FileError("bad-timestamp", record) from None
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_record(raw: RawRecord) -> Record:
    """Check and normalize one record (V1 to V6, N1 to N6)."""
    single: dict[str, str] = {}
    emails: list[str] = []
    tags: set[str] = set()
    for key, value in raw.fields:
        value = value.strip(" \t")
        if key in SINGLE_KEYS:
            if key in single:
                raise FileError("duplicate-field", raw.number)
            single[key] = value
        elif key == "email":
            emails.append(value)
        elif key == "tags":
            tags.update(item.strip().lower() for item in value.split(",") if item.strip())
    if any(not single.get(key) for key in SINGLE_KEYS):
        raise FileError("missing-field", raw.number)
    name, truncated = normalize_name(single["name"])
    if not name:
        raise FileError("missing-field", raw.number)
    if not ID_RE.fullmatch(single["id"]):
        raise FileError("bad-id", raw.number)
    updated = normalize_time(single["updated"], raw.number)
    addresses = [normalize_email(value, raw.number) for value in emails]
    return Record(raw.number, single["id"], name, truncated, updated, addresses, tags)


def parse_file(data: bytes) -> tuple[list[Record], bool]:
    """Return the records of a file and True if the cp1252 fallback was used."""
    text, fallback = decode(data)
    return [build_record(raw) for raw in split_records(text)], fallback
