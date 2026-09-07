"""The nodes ELA can work through, and the providers it can call (spec §16, §25, §26).

Two lists, and they read from two different places for a stated reason (ADR 0024 §5): of a node
the registry knows much more than ``/diagnostics`` shows — what it runs, which tools it has, when
it was last heard from — so ``device list`` has a route of its own; of a provider the port knows
its name and its status, which is exactly what ``/diagnostics`` already says, so ``provider list``
reads that and a route with nothing new to add was not written.
"""

from __future__ import annotations

import typer

from ela.cli import client
from ela.cli.errors import handled
from ela.cli.output import Json, emit, table

__all__ = ["devices", "providers"]

devices = typer.Typer(no_args_is_help=True, help="The nodes ELA can operate through.")
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
            ("name", "id", "os", "available", "status", "last seen", "tools"),
            [
                (
                    one["name"],
                    one["id"],
                    one["os"],
                    one["available"],
                    one["status"],
                    one["last_seen_at"],
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
