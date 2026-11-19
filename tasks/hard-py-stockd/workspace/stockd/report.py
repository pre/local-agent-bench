"""The stock report: a table for people and JSON for scripts."""

import json

from .projection import Inventory

COLUMNS = ("WAREHOUSE", "SKU", "ON_HAND", "RESERVED", "AVAILABLE")


def report_rows(inventory: Inventory, warehouse: str | None = None) -> list[dict]:
    rows = []
    for wh, sku, level in inventory.rows():
        if warehouse is not None and wh != warehouse:
            continue
        rows.append({"warehouse": wh, "sku": sku, "on_hand": level.on_hand,
                     "reserved": level.reserved, "available": level.available})
    return rows


def report_reservations(inventory: Inventory, warehouse: str | None = None) -> list[dict]:
    """The open reservations, sorted by warehouse, SKU and order."""
    result = []
    entries = sorted(inventory.reservations.items(), key=lambda e: (e[1].warehouse, e[1].sku, e[1].order))
    for number, res in entries:
        if warehouse is not None and res.warehouse != warehouse:
            continue
        result.append({"id": number, "warehouse": res.warehouse, "sku": res.sku,
                       "qty": res.qty, "order": res.order})
    return result


def render_json(inventory: Inventory, warehouse: str | None = None) -> str:
    body = {"levels": report_rows(inventory, warehouse),
            "reservations": report_reservations(inventory, warehouse)}
    return json.dumps(body, sort_keys=True, indent=2)


def render_table(inventory: Inventory, warehouse: str | None = None) -> str:
    rows = [COLUMNS] + [(r["warehouse"], r["sku"], str(r["on_hand"]), str(r["reserved"]), str(r["available"]))
                        for r in report_rows(inventory, warehouse)]
    widths = [max(len(row[i]) for row in rows) for i in range(len(COLUMNS))]
    lines = []
    for row in rows:
        cells = [row[0].ljust(widths[0]), row[1].ljust(widths[1])]
        cells += [cell.rjust(width) for cell, width in zip(row[2:], widths[2:])]
        lines.append("  ".join(cells).rstrip())
    open_res = len(report_reservations(inventory, warehouse))
    lines.append(f"{open_res} open reservation(s)")
    return "\n".join(lines)
