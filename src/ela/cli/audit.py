"""The trail, read and verified (spec §32, §58; ADR 0024 §4).

Reading and checking are two different questions, and the second is the one that makes the first
worth anything: a log nobody can verify has to be believed.
"""

from __future__ import annotations

from typing import Annotated

import typer

from ela.cli import client
from ela.cli.errors import handled
from ela.cli.output import Json, emit, fields, table

__all__ = ["DEFAULT_TAIL", "app"]

DEFAULT_TAIL = 20
"""How many entries ``tail`` shows when nobody says."""

app = typer.Typer(no_args_is_help=True, help="Read and verify the append-only audit trail.")


@app.command("tail")
@handled
def tail(
    count: Annotated[int, typer.Option("-n", "--count", min=1, help="how many")] = DEFAULT_TAIL,
    task: Annotated[str | None, typer.Option("--task", help="only this task")] = None,
    since: Annotated[str | None, typer.Option("--since", help="ISO instant, inclusive")] = None,
    as_json: Json = False,
) -> None:
    """The last entries, oldest of them first.

    ``newest_first`` is asked of the API, so ELA reads ``n`` rows from the end of the log instead
    of reading the whole window and trimming it here (M8.3, ADR 0025 §3 — the debt ADR 0024 §6
    declared). What comes back runs newest to oldest; it is turned around to print, because a
    tail is read downwards even when it is fetched upwards.
    """
    with client.connect() as api:
        payload = api.get(
            "/audit",
            client.query(task_id=task, since=since, limit=count, newest_first=True),
        )
    shown = list(reversed(payload))
    emit(
        shown,
        as_json,
        table(
            ("when", "event", "actor", "task", "summary"),
            [
                (
                    one["created_at"],
                    one["event_type"],
                    f"{one['actor']['kind']}:{one['actor']['id']}",
                    one["task_id"],
                    one["summary"],
                )
                for one in shown
            ],
        ),
    )


@app.command("verify")
@handled
def verify(as_json: Json = False) -> None:
    """Check that the chain still holds, and print what to anchor outside the log.

    A trail that does not verify is a refusal — ``tampered``, with the position of the first
    entry that does not fit — and the exit code of a refusal.
    """
    with client.connect() as api:
        payload = api.get("/audit/verify")
    emit(
        payload,
        as_json,
        fields([("entries", payload["length"]), ("head hash", payload["head_hash"])]),
    )
