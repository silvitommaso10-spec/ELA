"""What the CLI prints (ADR 0024 §6).

Plain text in aligned columns, and ``--json`` where a script would rather have the API's own
answer than our table. No boxes and no colour: the output is read as often through a pipe as on a
terminal, and a drawn table is noise in a pipe.

Nothing here formats a secret, because nothing here is ever given one: the token lives in the
request header and never in a payload (``/diagnostics`` does not return it either).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from typing import Annotated, Any

import typer

__all__ = ["Json", "emit", "fields", "table", "text"]

Json = Annotated[bool, typer.Option("--json", help="print ELA's own JSON answer instead")]
"""``--json`` on every command that reads something."""

EMPTY = "—"
"""What an absent value looks like in a column: something is there, and it is nothing."""
GAP = "  "


def text(value: Any) -> str:
    """One value as a cell: ``None`` is visibly absent, a list is comma-separated."""
    if value is None:
        return EMPTY
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        return ", ".join(text(one) for one in value) or EMPTY
    if isinstance(value, dict):
        return ", ".join(f"{name}: {text(one)}" for name, one in value.items()) or EMPTY
    return str(value)


def table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    """Aligned columns, header first. An empty table is a sentence, not a bare header."""
    body = [[text(cell) for cell in row] for row in rows]
    if not body:
        return "nothing to show"
    widths = [
        max(len(header), *(len(row[column]) for row in body))
        for column, header in enumerate(headers)
    ]
    lines = [
        GAP.join(header.upper().ljust(widths[column]) for column, header in enumerate(headers))
    ]
    lines.extend(
        GAP.join(cell.ljust(widths[column]) for column, cell in enumerate(row)).rstrip()
        for row in body
    )
    return "\n".join(line.rstrip() for line in lines)


def fields(pairs: Sequence[tuple[str, Any]]) -> str:
    """A block of ``name  value`` lines, the names aligned."""
    width = max(len(name) for name, _ in pairs)
    return "\n".join(f"{name.ljust(width)}{GAP}{text(value)}" for name, value in pairs)


def emit(payload: Any, as_json: bool, rendered: str) -> None:
    """The API's own answer, or the text we made of it."""
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False) if as_json else rendered)
