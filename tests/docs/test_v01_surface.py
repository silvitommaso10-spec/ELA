"""What v0.1 exposes, counted: no route, capability, tool or command more than today.

M9.4 is a release milestone — documents, derivations and observations — and its first promise is
that it adds nothing. A promise like that is worth exactly as much as the test that holds it, so
here are the four numbers, each read from the thing itself and not from a list kept beside it: the
application's own routes, the catalogue the composition root builds, the registry of tools, the
Typer tree of the CLI.

These numbers are meant to change — a capability is the whole point of the next phase. When one
does, this test fails and somebody writes down what was added, which is the only thing it is for.
"""

from __future__ import annotations

from pathlib import Path

from typer import Typer

from ela.api import approvals, audit, devices, results, system, tasks
from ela.cli.app import app as cli_app
from ela.permissions import catalogue_v01
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeModelProvider
from ela.tools import tools_v01, verifiers_v01
from tests.routing.support import routing_for

ROUTERS = (
    system.router,
    tasks.router,
    approvals.router,
    audit.router,
    devices.router,
    results.router,
)

CAPABILITIES = ("core.echo", "workspace.write_note", "model.complete")
TOOLS = ("core-echo", "workspace-notes", "model-complete")
COMMANDS = (
    "approvals",
    "audit tail",
    "audit verify",
    "device list",
    "diagnostics",
    "health",
    "init",
    "provider list",
    "serve",
    "task approve",
    "task cancel",
    "task create",
    "task deny",
    "task list",
    "task plan",
    "task results",
    "task run",
    "task show",
)


def commands_of(app: Typer, prefix: str = "") -> list[str]:
    found = [
        prefix + (command.name or command.callback.__name__)
        for command in app.registered_commands
        if command.callback is not None or command.name is not None
    ]
    for group in app.registered_groups:
        assert group.typer_instance is not None and group.name is not None
        found += commands_of(group.typer_instance, f"{group.name} ")
    return sorted(found)


def test_the_routers_carry_the_fifteen_routes_of_v01_and_no_others() -> None:
    """Fifteen written routes (ADR 0023 §6); ``/openapi.json`` is FastAPI's, and behind the token
    like the rest (``tests/api/test_security.py`` counts the sixteen the app really serves)."""
    coded = {
        (method, route.path)
        for router in ROUTERS
        for route in router.routes
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
    }
    assert len(coded) == 15


def test_the_catalogue_holds_the_three_capabilities_of_v01() -> None:
    assert tuple(str(spec.id) for spec in catalogue_v01().specs()) == CAPABILITIES


def test_the_registry_holds_one_tool_and_one_verifier_per_capability(tmp_path: Path) -> None:
    clock, ids = FakeClock(), FakeIdGenerator()
    router, providers = routing_for(FakeModelProvider(clock, ids))
    tools = tools_v01(root=tmp_path, clock=clock, ids=ids, router=router, providers=providers)
    verifiers = verifiers_v01(root=tmp_path, router=router)

    assert tuple(sorted(tool.name for tool in tools.tools())) == tuple(sorted(TOOLS))
    assert {tool.capability_id for tool in tools.tools()} == {
        verifier.capability_id for verifier in verifiers.verifiers()
    }


def test_the_cli_offers_the_eighteen_commands_of_v01() -> None:
    assert tuple(commands_of(cli_app)) == COMMANDS
