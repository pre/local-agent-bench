"""Text output for the CLI."""

from __future__ import annotations

from collections.abc import Sequence


def human_mib(mib: int) -> str:
    """Format MiB with the largest binary unit that keeps one decimal or less."""
    for unit, size in (("Ti", 1024 * 1024), ("Gi", 1024)):
        if mib >= size:
            value = mib / size
            text = f"{value:.1f}".rstrip("0").rstrip(".")
            return f"{text}{unit}"
    return f"{mib}Mi"


def table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    """Format rows as columns separated by two spaces.

    A column in which every row value is an int is aligned right, other
    columns are aligned left. None is shown as "-".
    """
    cells = [[str(h) for h in headers]]
    cells += [["-" if value is None else str(value) for value in row] for row in rows]
    widths = [max(len(line[i]) for line in cells) for i in range(len(headers))]
    numeric = [
        bool(rows) and all(isinstance(row[i], int) and not isinstance(row[i], bool) for row in rows)
        for i in range(len(headers))
    ]
    lines = []
    for line in cells:
        parts = []
        for i, text in enumerate(line):
            parts.append(text.rjust(widths[i]) if numeric[i] else text.ljust(widths[i]))
        lines.append("  ".join(parts).rstrip())
    return "\n".join(lines)
