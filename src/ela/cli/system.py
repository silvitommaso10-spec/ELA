"""Is ELA alive, how is it put together, and what is waiting for an answer (spec §54).

Three commands over three routes, and no judgement of their own: ``health`` says what ``/health``
said, and if the database did not answer the exit code is the one for a refusal, not a crash.
"""

from __future__ import annotations

from typing import Annotated, Any

import typer

from ela.cli import client
from ela.cli.errors import handled
from ela.cli.output import Json, emit, fields, table

__all__ = ["approvals", "diagnostics", "health"]


@handled
def health(as_json: Json = False) -> None:
    """Whether ELA is alive and its database answers."""
    with client.connect() as api:
        payload = api.get("/health")
    emit(
        payload,
        as_json,
        fields(
            [
                ("status", payload["status"]),
                ("database", payload["database"]),
                ("now", payload["now"]),
            ]
        ),
    )


@handled
def diagnostics(as_json: Json = False) -> None:
    """How this ELA is composed right now: never a secret, never your content."""
    with client.connect() as api:
        payload = api.get("/diagnostics")
    emit(payload, as_json, fields(_composition(payload)))


def _composition(payload: dict[str, Any]) -> list[tuple[str, Any]]:
    recovered = payload["recovered"]
    return [
        ("version", payload["version"]),
        ("database", payload["database"]),
        ("workspace", payload["workspace"]),
        ("user", payload["user_name"]),
        ("providers", payload["providers"]),
        ("task types", payload["task_types"]),
        ("default profile", payload["default_profile"]),
        ("capabilities", payload["capabilities"]),
        ("tools", payload["tools"]),
        ("devices", payload["devices"]),
        ("tasks", payload["tasks"]),
        ("approvals waiting", payload["pending_approvals"]),
        (
            "recovered at start-up",
            f"{recovered['failed']} failed, {recovered['skipped']} skipped, "
            f"{recovered['expired']} expired",
        ),
    ]


@handled
def approvals(
    limit: Annotated[int | None, typer.Option("--limit", min=1, help="at most this many")] = None,
    as_json: Json = False,
) -> None:
    """What ELA is waiting for you to answer, oldest first.

    A request whose task has moved on — stopped, expired — is not shown: answering it would no
    longer do anything, and asking for an answer that cannot land is asking the impossible.
    """
    with client.connect() as api:
        payload = api.get("/approvals", client.query(limit=limit))
    emit(
        payload,
        as_json,
        table(
            ("approval", "task", "capability", "targets", "asks"),
            [
                (one["id"], one["task_id"], one["capability_id"], one["targets"], one["prompt"])
                for one in payload
            ],
        ),
    )
