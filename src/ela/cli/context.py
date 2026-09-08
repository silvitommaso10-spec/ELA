"""``ela context``: what is going on now, and what ELA cannot know (spec §44; M10.4).

The command's whole point is the last block it prints. A picture that showed only what ELA can
answer would read as complete, and §44's own worked example — "prepare tomorrow's meeting" —
rests on three sources this ELA does not have. So the seven questions are printed **all seven**,
each with what answers it here and what is missing by name.

Where a limit bit, the line says so: ``20 of 137`` and never a bare ``20``. "There are no more"
and "I am not showing you the rest" must not have the same face (ADR 0032 §9-bis).
"""

from __future__ import annotations

from typing import Any

from ela.cli import client
from ela.cli.errors import handled
from ela.cli.output import Json, emit, fields, text

__all__ = ["context"]


def _of(section: dict[str, Any]) -> str:
    """``shown`` out of ``total`` — and only ever the bare number when nothing was cut."""
    shown, total = section["shown"], section["total"]
    return str(shown) if shown == total else f"{shown} of {total}"


def _answer(status: dict[str, Any]) -> str:
    """One question of §44: what answers it, and what is missing — never silence."""
    answered = ", ".join(status["answered_by"]) or "nothing"
    missing = ", ".join(status["missing"])
    return f"{answered}" + (f" — missing: {missing}" if missing else "")


@handled
def context(as_json: Json = False) -> None:
    """What the user is doing, what ELA has under way, and what ELA has no source for."""
    with client.connect() as api:
        payload = api.get("/context")
    activity, work, deadlines = payload["activity"], payload["work"], payload["deadlines"]
    device, recent = payload["device"], payload["recent"]
    rows: list[tuple[str, Any]] = [
        ("at", payload["at"]),
        ("observed at", activity["observed_at"]),
        ("frontmost", activity["frontmost_bundle_id"]),
        ("windows", activity["window_count"]),
        ("idle seconds", activity["idle_seconds"]),
        ("screen locked", activity["screen_locked"]),
        ("running", ", ".join(activity["running_bundle_ids"] or ()) or None),
        ("device", None if device is None else f"{device['name']} ({device['os']})"),
        (
            "device available",
            None if device is None else device["available"],
        ),
        ("tasks", _of(work)),
        ("pending approvals", len(work["pending_approvals"])),
        ("deadlines", _of(deadlines)),
        ("since", recent["since"]),
        (
            "changed",
            ", ".join(
                f"{one['field']}: {one['before']} -> {one['after']}" for one in recent["changes"]
            )
            or "nothing",
        ),
    ]
    rows.extend((task["state"].lower(), task["goal"]) for task in work["tasks"])
    rows.extend((f"due {one['deadline']}", one["goal"]) for one in deadlines["deadlines"])
    rows.extend((f"§44 {one['question'].lower()}", _answer(one)) for one in payload["questions"])
    emit(payload, as_json, fields([(name, text(value)) for name, value in rows]))
