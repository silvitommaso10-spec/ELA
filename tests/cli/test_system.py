"""``health``, ``diagnostics`` and ``approvals``: what the CLI says about a running ELA."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from ela.cli import client
from ela.cli.errors import REFUSED, UNREACHABLE
from ela.cli.output import EMPTY
from ela.composition import ApiSettings, Ela
from ela.devices.local import LOCAL_DEVICE_ID
from tests.cli.support import Cli, plain, unreachable
from tests.composition.support import TOKEN


async def test_health_says_the_database_answered(cli: Cli) -> None:
    result = await cli("health")

    assert result.exit_code == 0
    assert "status" in result.stdout
    assert "database" in result.stdout
    assert "ok" in result.stdout


async def test_health_in_json_is_the_api_answer(cli: Cli) -> None:
    result = await cli("health", "--json")
    answer = json.loads(result.stdout)

    assert answer["status"] == "ok"
    assert answer["database"] == "ok"
    assert answer["now"]


async def test_diagnostics_says_how_ela_is_composed(cli: Cli, ela: Ela) -> None:
    result = await cli("diagnostics")

    assert result.exit_code == 0
    assert "anthropic: UNAVAILABLE" in result.stdout
    assert "local: available" in result.stdout
    assert str(ela.settings.workspace.workspace_dir) in result.stdout
    assert "recovered at start-up" in result.stdout


async def test_diagnostics_says_nothing_is_missing_from_the_row(cli: Cli) -> None:
    """Empty almost always — after a start-up the row of ``local`` cannot be behind."""
    result = await cli("diagnostics")

    printed = plain(result.stdout).splitlines()
    (row,) = [line for line in printed if line.startswith("tools missing from the row")]
    assert row.endswith(EMPTY)


async def test_diagnostics_names_the_tools_the_row_does_not_declare(cli: Cli, ela: Ela) -> None:
    """And the direction that matters, on the surface a person actually opens (M6.1b, punto 2).

    A field that lives only in the JSON is a field nobody reads: when a task answers
    ``waiting_device`` what gets opened is a terminal, not a ``curl``. The CLI is a client of the
    API and not a second world (ADR 0024, M8.3), so it says everything the route says.
    """
    node = await ela.devices.get(LOCAL_DEVICE_ID)
    await ela.devices.update(node.model_copy(update={"available_tools": ("core-echo",)}))

    result = await cli("diagnostics")

    assert result.exit_code == 0
    assert "workspace-notes" in plain(result.stdout).split("tools missing from the row")[1]


async def test_diagnostics_never_prints_a_secret(cli: Cli) -> None:
    """The token opens the API and is never part of an answer (ADR 0023 §6)."""
    result = await cli("diagnostics", "--json")

    assert TOKEN not in result.stdout
    assert "token" not in result.stdout


async def test_approvals_says_so_when_nothing_waits(cli: Cli) -> None:
    result = await cli("approvals")

    assert result.exit_code == 0
    assert "nothing to show" in result.stdout


async def test_approvals_takes_a_limit(cli: Cli) -> None:
    result = await cli("approvals", "--limit", "1", "--json")

    assert result.exit_code == 0
    assert json.loads(result.stdout) == []


async def test_a_wrong_token_is_a_refusal_and_not_a_crash(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 401 is an answer from ELA: exit code 1, with the API's own code."""
    wrong = ApiSettings(api_token=SecretStr("z" * 40))
    monkeypatch.setattr(
        client, "connect", lambda: client.open_client(wrong, transport=cli.transport)
    )
    result = await cli("health")

    assert result.exit_code == REFUSED
    assert "unauthorized" in plain(result.stderr)


async def test_ela_not_running_has_an_exit_code_of_its_own(
    cli: Cli, ela: Ela, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing answered: a script must be able to tell that from "ELA said no"."""
    monkeypatch.setattr(
        client,
        "connect",
        lambda: client.open_client(ela.settings.api, transport=httpx.MockTransport(unreachable)),
    )
    result = await cli("health")

    assert result.exit_code == UNREACHABLE
    assert "start it with `ela serve`" in plain(result.stderr)
