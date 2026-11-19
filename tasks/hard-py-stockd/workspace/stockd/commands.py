"""Validation of the command objects that clients send (see README.md)."""

from dataclasses import dataclass

from .errors import CommandError

OPS = ("receive", "adjust", "reserve", "release", "ship", "transfer")


@dataclass(frozen=True)
class ReceiveLine:
    sku: str
    qty: int | None
    packs: int | None


@dataclass(frozen=True)
class Command:
    op: str
    request_id: str | None
    args: dict


def _text(obj: dict, key: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CommandError(f"{key} must be a non-empty string")
    return value


def _positive(obj: dict, key: str) -> int:
    value = obj.get(key)
    if type(value) is not int or value < 1:
        raise CommandError(f"{key} must be a positive integer")
    return value


def _nonzero(obj: dict, key: str) -> int:
    value = obj.get(key)
    if type(value) is not int or value == 0:
        raise CommandError(f"{key} must be a non-zero integer")
    return value


def parse_command(obj: object, max_lines: int) -> Command:
    if not isinstance(obj, dict):
        raise CommandError("a command must be a JSON object")
    op = obj.get("op")
    if op not in OPS:
        raise CommandError(f"unknown op {op!r}")
    rid = obj.get("request_id")
    if rid is not None and (not isinstance(rid, str) or not rid):
        raise CommandError("request_id must be a non-empty string")
    if op == "receive":
        lines = obj.get("lines")
        if not isinstance(lines, list) or not lines:
            raise CommandError("lines must be a non-empty list")
        if len(lines) > max_lines:
            raise CommandError(f"a receive can have at most {max_lines} lines")
        parsed = []
        for line in lines:
            if not isinstance(line, dict):
                raise CommandError("each line must be an object")
            has_qty, has_packs = "qty" in line, "packs" in line
            if has_qty == has_packs:
                raise CommandError("each line needs qty or packs, not both")
            parsed.append(ReceiveLine(_text(line, "sku"),
                                      _positive(line, "qty") if has_qty else None,
                                      _positive(line, "packs") if has_packs else None))
        args = {"warehouse": _text(obj, "warehouse"), "lines": parsed}
    elif op == "adjust":
        args = {"warehouse": _text(obj, "warehouse"), "sku": _text(obj, "sku"),
                "delta": _nonzero(obj, "delta"), "reason": _text(obj, "reason")}
    elif op == "reserve":
        args = {"warehouse": _text(obj, "warehouse"), "sku": _text(obj, "sku"),
                "qty": _positive(obj, "qty"), "order": _text(obj, "order")}
    elif op in ("release", "ship"):
        args = {"reservation": _positive(obj, "reservation")}
    else:
        args = {"from": _text(obj, "from"), "to": _text(obj, "to"), "sku": _text(obj, "sku"),
                "qty": _positive(obj, "qty")}
        if args["from"] == args["to"]:
            raise CommandError("from and to must be different warehouses")
    return Command(op=op, request_id=rid, args=args)
