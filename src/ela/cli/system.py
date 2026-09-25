"""Is ELA alive, how is it put together, and what is waiting for an answer (spec §54).

Three commands over three routes, and no judgement of their own: ``health`` says what ``/health``
said, and if the database did not answer the exit code is the one for a refusal, not a crash.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Final

import typer

from ela.cli import client
from ela.cli.errors import handled
from ela.cli.output import Json, emit, fields
from ela.domain import listed, visible

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
    """How this ELA is composed right now: never a secret, never your content.

    ``tools missing from the row`` is empty almost always, and when it is not it names the
    capabilities the node's row does not declare — the ones no step will be placed for. It is
    here and not only in the JSON because a diagnostic that lives where nobody looks is not a
    diagnostic: when a task says ``waiting_device`` what gets opened is a terminal.
    """
    with client.connect() as api:
        payload = api.get("/diagnostics")
    emit(payload, as_json, fields(_composition(payload)))


def _composition(payload: dict[str, Any]) -> list[tuple[str, Any]]:
    recovered = payload["recovered"]
    return [
        ("version", payload["version"]),
        ("database", payload["database"]),
        ("workspace", payload["workspace"]),
        ("addresses", payload["addresses"]),
        ("providers", payload["providers"]),
        ("task types", payload["task_types"]),
        ("default profile", payload["default_profile"]),
        ("capabilities", payload["capabilities"]),
        ("tools", payload["tools"]),
        ("devices", payload["devices"]),
        ("tools missing from the row", payload["undeclared_tools"]),
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


QUESTION_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "description",
        "risk",
        "max_privacy",
        "goal",
        "stated",
        "grant_uses",
        "grant_seconds",
        "target",
        "does",
        "label",
        "runs",
        "arguments",
        "folder",
        "timeout_seconds",
        "expect_exit",
        "machine",
        "unseen",
    }
)
"""Every field of the question this surface shows, declared here so it can be checked.

``ela task approve`` is the first yes anybody gives, so this is an **answering surface**, and the
rule of M13.1 dec. H holds for it as it holds for the two pages: *a surface may answer a question
only if it shows everything that question names.* The pages show the parts because a page cannot
make somebody read a sentence (M12.5 dec. F); here the sentence is shown too, and the parts
beside it.

The gap this closes is older than M13.1 — M12.5 gave the bag of the question to the pages and left
the command line with the sentence — and what made it visible was adding two fields to the bag.
``tests/api/test_answering_surfaces.py`` compares this set with ``Asked`` in both directions: a
field added to the question tomorrow without a line below fails the suite.
"""


@handled
def approvals(
    limit: Annotated[int | None, typer.Option("--limit", min=1, help="at most this many")] = None,
    as_json: Json = False,
) -> None:
    """What ELA is waiting for you to answer, oldest first.

    A request whose task has moved on — stopped, expired — is not shown: answering it would no
    longer do anything, and asking for an answer that cannot land is asking the impossible.

    **One block per question, not a row**: a question names nine things, and nine columns are a
    dump rather than something a person reads before saying yes.
    """
    with client.connect() as api:
        payload = api.get("/approvals", client.query(limit=limit))
    emit(payload, as_json, _questions(payload))


def _questions(payload: Sequence[Mapping[str, Any]]) -> str:
    """The waiting questions, one block each, or the sentence that says there are none."""
    if not payload:
        return "nothing to show"
    return "\n\n".join(fields(_rows(one)) for one in payload)


def _rows(one: Mapping[str, Any]) -> list[tuple[str, Any]]:
    """What a question names, in the order somebody reads it before answering.

    Who is asking and about what, then how much it costs to say yes, then what exactly it will
    do. The two facts of a file (M13.1 dec. G) sit next to the targets they resolve.

    **Two expiries, and each says whose it is**: the question stops being answerable at one
    instant, and the grant a "yes" mints lives for another — reading one as the other would be
    reading the life of a permission off the deadline of a request.

    ``does`` is rendered as the capability wrote it: this surface owns no sentence about files
    (dec. G, blocker 2 of the proof by hand), and since M13.2 no word for the target either — the
    row is called what the tool calls it (``label``), and ``target`` when the question does not
    say. **Every word of the plan or of the machine passes** :func:`~ela.domain.visible`, and the
    arguments of a command :func:`~ela.domain.listed` (M13.2 dec. 12, 13): what the user reads
    before saying yes cannot be rewritten by what it shows. The rows of a command are there only
    for a command (:data:`COMMAND_ROWS`).
    """
    arguments = one.get("arguments")
    timeout = one.get("timeout_seconds")
    rows = [
        ("approval", one["id"]),
        ("task", one["task_id"]),
        ("capability", one["capability_id"]),
        ("what", one.get("description") or None),
        ("risk", one.get("risk")),
        ("may go", one.get("max_privacy")),
        ("question expires", one.get("expires_at")),
        ("grant if you say yes", _terms(one.get("grant_uses"), one.get("grant_seconds"))),
        ("step goal", _seen(one.get("goal"))),
        ("declared", [_seen(pair) for pair in one.get("stated") or ()] or None),
        ("targets", [_seen(target) for target in one["targets"]]),
        ("machine", _seen(one.get("machine"))),
        (one.get("label") or TARGET, _seen(one.get("target"))),
        ("runs", _seen(one.get("runs"))),
        ("arguments", None if arguments is None else listed(arguments)),
        ("folder", _seen(one.get("folder"))),
        ("timeout", None if timeout is None else f"{timeout} s"),
        ("expects exit", one.get("expect_exit")),
        ("does", one.get("does") or None),
        ("disk", one.get("unseen") or None),
        ("asks", _seen(one["prompt"])),
    ]
    return [
        (name, value)
        for name, value in rows
        if value is not None or name not in COMMAND_ROWS | NODE_ROWS
    ]


COMMAND_ROWS: Final[frozenset[str]] = frozenset(
    {"runs", "arguments", "folder", "timeout", "expects exit"}
)
"""The rows only a command has (M13.2): absent, not dashed, when the question is about something
else — a question about a file names no program, and five dashes under it would be five things to
read that are not there. Every other row keeps its dash: its absence is something to read."""

NODE_ROWS: Final[frozenset[str]] = frozenset({"machine", "disk"})
"""The rows only a question about a machine ELA has not looked at has (M13.3, ADR 0048): absent,
not dashed, for every other — the question about this machine is the one it always was."""

TARGET: Final = "target"
"""The row of a target whose question does not say what its tool calls it (M13.2 dec. 12)."""


def _seen(value: str | None) -> str | None:
    """A word of the plan or of the machine, as a question renders it; ``None`` stays absent."""
    return visible(value, lines=False) if value else None


def _terms(uses: int | None, seconds: int | None) -> str | None:
    """What the "yes" mints: how many uses, and for how long (ADR 0012 §2).

    Half of it is not an answer — «one use» without «for how long» is a permission of unknown
    life — so either both are there or neither is.
    """
    if uses is None or seconds is None:
        return None
    minutes, remainder = divmod(seconds, 60)
    span = f"{minutes} minutes" if not remainder else f"{seconds} seconds"
    return f"{uses} use, within {span}" if uses == 1 else f"{uses} uses, within {span}"
