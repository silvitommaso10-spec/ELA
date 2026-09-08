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

__all__ = ["approvals", "diagnostics", "health", "perception", "sensor"]


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
        ("perception", _perception(payload["perception"])),
        (
            "recovered at start-up",
            f"{recovered['failed']} failed, {recovered['skipped']} skipped, "
            f"{recovered['expired']} expired",
        ),
    ]


def _perception(seen: dict[str, Any]) -> str:
    """The composition-shaped half: what ELA may do here, and how old the answer is.

    Permissions and not sensors, because ``/diagnostics`` says what ELA is wired to; the state of
    the microphone is the world and lives under ``ela perception``.
    """
    how = "watching" if seen["watching"] else "on request" if seen["enabled"] else "off"
    granted = ", ".join(
        f"{name.lower()} {state.lower().replace('_', ' ')}"
        for name, state in sorted(seen["permissions"].items())
    )
    return f"{how} (seen {seen['observed_at']}); {granted}"


def sensor(status: dict[str, str]) -> str:
    """A §11 state with the cause that qualifies it — never the state alone.

    ``OFF`` on its own would tell the reader that a device is switched off, when what ELA means
    may be that it could not look. Every line that shows a sensor goes through here.
    """
    return f"{status['state']} ({status['cause'].lower().replace('_', ' ')})"


@handled
def perception(as_json: Json = False) -> None:
    """What ELA sees of this machine: devices, permissions, and what just changed."""
    with client.connect() as api:
        payload = api.get("/perception")
    rows: list[tuple[str, Any]] = [
        ("observed at", payload["observed_at"]),
        ("microphone", sensor(payload["microphone"])),
        ("camera", sensor(payload["camera"])),
    ]
    rows.extend(
        (f"permission {name.lower()}", state.lower().replace("_", " "))
        for name, state in sorted(payload["permissions"].items())
    )
    rows.extend(
        [
            ("displays", payload["display_count"]),
            ("display asleep", payload["display_asleep"]),
            ("screen locked", payload["screen_locked"]),
            ("on console", payload["on_console"]),
            ("idle seconds", payload["idle_seconds"]),
            ("frontmost", payload["frontmost_bundle_id"]),
            ("windows", payload["window_count"]),
            ("running", ", ".join(payload["running_bundle_ids"] or ()) or None),
            ("watching", payload["watching"]),
            (
                "changed",
                ", ".join(
                    f"{one['field']}: {one['before']} -> {one['after']}"
                    for one in payload["changes"]
                )
                or "nothing",
            ),
        ]
    )
    emit(payload, as_json, fields(rows))


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
