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

    The filters are the API's; the *last* ``n`` are taken here, because ``GET /audit`` answers
    with the **first** entries and a tail is the other end. It reads the window it then trims,
    which is the same debt ``/diagnostics`` declares for counting tasks (ADR 0024 §6).
    """
    with client.connect() as api:
        payload = api.get("/audit", client.query(task_id=task, since=since))
    shown = payload[-count:]
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
