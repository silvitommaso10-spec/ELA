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

__all__ = ["RemotePrivacy", "devices", "node", "providers"]

devices = typer.Typer(no_args_is_help=True, help="The nodes ELA can operate through.")
node = typer.Typer(no_args_is_help=True, help="Enroll a node, or revoke one (ADR 0037).")
providers = typer.Typer(no_args_is_help=True, help="The model providers ELA can route to.")


@devices.command("list")
@handled
def list_devices(as_json: Json = False) -> None:
    """Every registered node, and whether ELA would use it right now.

    "Available" is derived from the last heartbeat, not read from a column that keeps saying what
    was true when someone wrote it: a node nobody has heard from is not available.
    """
    with client.connect() as api:
        payload = api.get("/devices")
    emit(
        payload,
        as_json,
        table(
            ("name", "id", "os", "available", "status", "last seen", "revoked", "tools"),
            [
                (
                    one["name"],
                    one["id"],
                    one["os"],
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
    as_json: Json = False,
) -> None:
    """Issue a one-shot code for a new node, with the privacy it will have (ADR 0037 §5).

    The code is printed once, beside its expiry. A code is not a token: it opens one route once
    and dies in minutes, so the reason ADR 0024 §8 keeps secrets off the terminal — a value that
    stays valid in the scrollback — does not hold for it. Paste it into the node; the node never
    sees ELA's token, and its own secret is never printed at all.
    """
    with client.connect() as api:
        payload = api.post("/nodes/enrollments", {"privacy": privacy.value})
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
