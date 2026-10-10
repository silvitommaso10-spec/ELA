"""``ela policy``: create, list and revoke the policies of §59 (M13.12, ADR 0062; decision 9).

A policy is Tommaso's own standing yes for a capability that admits one: its scope — for
``browser.guided`` the sites —, a limit per call for every one the capability declares, and an end
in days, from 1 to 90, with no default. ``create`` shows the preview first, which names what is
approved; **in a terminal** it asks «Create this policy? (s/N)», and only «s», «si» or «sì» creates;
**out of a terminal and without** ``--confirm`` it shows and does not create — the way the script of
the hand test asks before creating, since its ``run`` captures what a command prints.

``--limit`` is generic and repeatable: this command knows no limit's name, it sends them, and the
route judges them against the capability's declaration — ``ela policy list`` says which they are.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Final

import typer

from ela.cli import client
from ela.cli.errors import REFUSED, fail, handled
from ela.cli.output import Json, emit, fields, table
from ela.domain import listed

__all__ = ["YES", "Ambiguous", "app", "in_a_terminal", "resolved"]

app = typer.Typer(no_args_is_help=True, help="The policies of §59: your standing yes (ADR 0062).")

YES: Final = frozenset({"s", "si", "sì"})
"""The answers that create (decision 19): every other, the Enter key included, does not."""
QUESTION: Final = "Create this policy? (s/N)"
NOT_CREATED: Final = "not created: run it again with --confirm, or in a terminal, to create it"
SHORT: Final = 8


class Ambiguous(Exception):
    """A short id that names more than one policy: the whole id is needed."""


def in_a_terminal() -> bool:
    """Whether a person is at a terminal: **both** ends. The script of the hand test captures what
    a command prints and only inherits the keyboard, and a question it cannot show is a question
    nobody answers."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def _limits(written: Sequence[str]) -> dict[str, str]:
    limits: dict[str, str] = {}
    for one in written:
        name, equals, value = one.partition("=")
        if not equals or not name:
            fail(REFUSED, f"a limit is written name=value, as max_cost_usd=1.10, not {one!r}")
        limits[name] = value
    return limits


def _preview_text(shown: Mapping[str, Any]) -> str:
    rows = fields(
        [
            ("capability", shown["capability"]),
            ("what", shown["description"]),
            ("sites", listed(shown["scope"])),
            ("limits", ", ".join(f"{name}={value}" for name, value in shown["limits"].items())),
            ("expires", f"in {shown['days']} day(s), at {shown['expires_at']}"),
            ("model", shown["model"]),
            ("sends", shown["sends"] or None),
            ("one call", shown["one_call"] or None),
            ("cost", shown["cost"] or None),
        ]
    )
    never = "\n".join(f"  - {line}" for line in shown["never"])
    return f"{rows}\nnever covered:\n{never}"


@app.command("create")
@handled
def create(
    capability: Annotated[str, typer.Argument(help="The capability, as browser.guided.")],
    scope: Annotated[
        list[str] | None,
        typer.Option("--scope", help="a target the policy covers: for browser.guided a site"),
    ] = None,
    limit: Annotated[
        list[str] | None,
        typer.Option("--limit", help="a limit per call, name=value: see ela policy list"),
    ] = None,
    days: Annotated[int | None, typer.Option("--days", help="how long it lives: 1 to 90")] = None,
    confirm: Annotated[bool, typer.Option("--confirm", help="create without asking")] = False,
    as_json: Json = False,
) -> None:
    """Show the preview of a policy, and create it — with --confirm, or with «s» in a terminal."""
    body: dict[str, Any] = {
        "capability": capability,
        "scope": list(scope or ()),
        "limits": _limits(limit or ()),
        "days": days,
    }
    with client.connect() as api:
        shown = api.post("/policies/preview", body)
        typer.echo(_preview_text(shown))
        if not confirm:
            if not in_a_terminal():
                typer.echo(NOT_CREATED)
                return
            answer = typer.prompt(QUESTION, default="", show_default=False)
            if answer.strip().lower() not in YES:
                typer.echo("not created")
                return
        made = api.post("/policies", {**body, "model": shown["model"]})
    emit(made, as_json, f"created policy {made['short']}")


def _row(one: Mapping[str, Any]) -> Sequence[Any]:
    who = one["created_by"]
    return (
        one["short"],
        one["capability"],
        listed(one["scope"]),
        ", ".join(f"{name}={value}" for name, value in one["limits"].items()),
        one["expires_at"],
        one["uses"],
        f"{who.get('name') or who['identity']} ({who.get('role') or '—'}) at {one['created_at']}",
        one["state"],
    )


@app.command("list")
@handled
def list_policies(
    everything: Annotated[bool, typer.Option("--all", help="the revoked and ended too")] = False,
    as_json: Json = False,
) -> None:
    """The live policies — with --all, the revoked and the ended too — and the limits each
    capability that admits a policy declares. `uses` counts the times a policy was spent: a session
    refused after it, by the month's cap, counts too."""
    with client.connect() as api:
        payload = api.get("/policies", client.query(all="true" if everything else None))
    policies = (
        table(
            ("policy", "capability", "sites", "limits", "expires", "uses", "created by", "state"),
            [_row(one) for one in payload["policies"]],
        )
        if payload["policies"]
        else "no policy"
    )
    admitting = "\n".join(
        f"{terms['capability']}: --limit "
        + ", --limit ".join(f"{limit['name']}=…" for limit in terms["limits"])
        + f"; never covered: {', '.join(terms['uncovered']) or '—'}"
        for terms in payload["admitting"]
    )
    emit(payload, as_json, f"{policies}\n\nwhat a policy must bound:\n{admitting}")


def resolved(given: str, policies: Sequence[Mapping[str, Any]]) -> str | None:
    """The whole id ``given`` names: itself, or the one policy its first eight characters start;
    ``None`` for neither, :class:`Ambiguous` for a short id that names two."""
    ids = [str(one["id"]) for one in policies]
    if given in ids:
        return given
    if len(given) != SHORT:
        return None
    matching = [one for one in ids if one.startswith(given)]
    if len(matching) > 1:
        raise Ambiguous(given)
    return matching[0] if matching else None


@app.command("revoke")
@handled
def revoke(
    policy: Annotated[str, typer.Argument(help="The policy's id, or its first eight characters.")],
    as_json: Json = False,
) -> None:
    """Revoke a live policy. A session it already covered goes on until it ends: the stop of a task
    is `ela task cancel`."""
    with client.connect() as api:
        listed_ = api.get("/policies", client.query(all="true"))["policies"]
        try:
            found = resolved(policy, listed_)
        except Ambiguous:
            fail(REFUSED, f"{policy} names more than one policy: give the whole id")
        if found is None:
            fail(REFUSED, f"no policy {policy}")
        payload = api.post(f"/policies/{found}/revoke")
    emit(payload, as_json, f"revoked policy {payload['policy']['short']}\n{payload['running']}")
