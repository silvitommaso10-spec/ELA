"""The nodes ELA can work through, and the providers it can call (spec §16, §25, §26).

Two lists, and they read from two different places for a stated reason (ADR 0024 §5): of a node
the registry knows much more than ``/diagnostics`` shows — what it runs, which tools it has, when
it was last heard from — so ``device list`` has a route of its own; of a provider the port knows
its name and its status, which is exactly what ``/diagnostics`` already says, so ``provider list``
reads that and a route with nothing new to add was not written.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

import typer

from ela.cli import client
from ela.cli.errors import handled
from ela.cli.output import Json, emit, table

__all__ = ["EnrolledRole", "RemotePrivacy", "devices", "node", "providers"]

devices = typer.Typer(no_args_is_help=True, help="The nodes ELA can operate through.")
node = typer.Typer(no_args_is_help=True, help="Enroll a node, or revoke one (ADR 0037).")
providers = typer.Typer(no_args_is_help=True, help="The model providers ELA can route to.")


@devices.command("list")
@handled
def list_devices(as_json: Json = False) -> None:
    """Every registered node, and whether ELA would use it right now.

    "Available" is derived from the last heartbeat, not read from a column that keeps saying what
    was true when someone wrote it: a node nobody has heard from is not available.

    Two facts, two names (M12.5 dec. B): **last contact** is when that identity spoke to ELA — for
    a node a heartbeat, for a browser a page — and **available** is the fact of the heartbeat,
    which is why a companion or a console that opened a page a second ago reads ``False``. Neither
    column says "connected", which nobody here can know.
    """
    with client.connect() as api:
        payload = api.get("/devices")
    emit(
        payload,
        as_json,
        table(
            (
                "name",
                "id",
                "os",
                "role",
                "available",
                "status",
                "last contact",
                "revoked",
                "tools",
            ),
            [
                (
                    one["name"],
                    one["id"],
                    one["os"],
                    one["role"],
                    one["available"],
                    one["status"],
                    one["last_seen_at"],
                    one["revoked_at"],
                    one["available_tools"],
                )
                for one in payload
            ],
        ),
    )


@providers.command("list")
@handled
def list_providers(as_json: Json = False) -> None:
    """The providers ELA is wired to, with the status each one reports.

    A provider with no credentials is registered all the same and says ``UNAVAILABLE``: ELA
    starts on a machine where nobody configured a key, it just cannot call a model there.

    ``--json`` prints the providers, not the whole of ``/diagnostics``: the route answers a wider
    question than the command asks.
    """
    with client.connect() as api:
        payload = api.get("/diagnostics")["providers"]
    emit(payload, as_json, table(("provider", "status"), sorted(payload.items())))


class EnrolledRole(StrEnum):
    """What the code will make: a node that takes work, or one of the two browsers.

    Lower case because that is how the guide writes it — ``--role companion`` — and matched
    without case, so ``COMPANION`` works too (M12.5 dec. A, C.2).
    """

    WORKER = "worker"
    COMPANION = "companion"
    CONSOLE = "console"
    """The browser of the Mac: the Command Center (M17.2 dec. A; ADR 0044)."""


class RemotePrivacy(StrEnum):
    """The levels a user can impose on a remote node: ``LOCAL_ONLY`` is this machine's (D18)."""

    TRUSTED = "TRUSTED"
    CLOUD_ALLOWED = "CLOUD_ALLOWED"


@node.command("enroll")
@handled
def enroll_node(
    privacy: Annotated[
        RemotePrivacy,
        typer.Option("--privacy", help="The ceiling of what the node may receive. No default."),
    ],
    role: Annotated[
        EnrolledRole,
        typer.Option(
            "--role",
            case_sensitive=False,
            help="What the code will enrol: a worker, the iPhone companion, or the console.",
        ),
    ] = EnrolledRole.WORKER,
    as_json: Json = False,
) -> None:
    """Issue a one-shot code for a new identity, with the privacy and the role it will have.

    ADR 0037 §5, and M12.5 dec. A for the role: both are imposed here, by the user, and neither is
    ever declared by what presents the code. ``--role companion`` mints the code the iPhone spends
    in the enrolment form of its browser, and that code opens no other route.

    The code is printed once, beside its expiry. A code is not a token: it opens one route once
    and dies in minutes, so the reason ADR 0024 §8 keeps secrets off the terminal — a value that
    stays valid in the scrollback — does not hold for it. Paste it into the node; the node never
    sees ELA's token, and its own secret is never printed at all.

    The table keeps the three columns it had, in the same order: a measure of M12.5 (P3) showed
    that a double click on the terminal takes the whole code and stops at the next cell, and that
    is how the code reaches the iPhone (dec. C.4). ``--json`` carries the role.
    """
    with client.connect() as api:
        payload = api.post(
            "/nodes/enrollments", {"privacy": privacy.value, "role": role.value.upper()}
        )
    emit(
        payload,
        as_json,
        table(
            ("code", "privacy", "expires at"),
            [(payload["code"], payload["privacy"], payload["expires_at"])],
        ),
    )


@node.command("revoke")
@handled
def revoke_node(
    device_id: Annotated[str, typer.Argument(help="The node's id, as `ela device list` shows it.")],
    as_json: Json = False,
) -> None:
    """Revoke a node: its row stays, and its secret opens nothing any more (ADR 0037 §12)."""
    with client.connect() as api:
        payload = api.post(f"/nodes/{device_id}/revoke")
    emit(
        payload,
        as_json,
        table(
            ("name", "id", "revoked at"),
            [(payload["name"], payload["id"], payload["revoked_at"])],
        ),
    )
