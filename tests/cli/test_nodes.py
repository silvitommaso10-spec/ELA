"""``ela device list`` and ``ela provider list``: the two lists, from their two routes."""

from __future__ import annotations

import json

from ela.composition import Ela
from tests.cli.support import Cli


async def test_device_list_shows_the_local_node_as_available(cli: Cli, ela: Ela) -> None:
    result = await cli("device", "list")

    assert result.exit_code == 0
    assert result.stdout.splitlines()[0].split() == [
        "NAME",
        "ID",
        "OS",
        "AVAILABLE",
        "STATUS",
        "LAST",
        "SEEN",
        "TOOLS",
    ]
    assert "yes" in result.stdout
    assert "core.echo" in result.stdout or "echo" in result.stdout


async def test_device_list_in_json_is_the_route_s_answer(cli: Cli, ela: Ela) -> None:
    nodes = json.loads((await cli("device", "list", "--json")).stdout)

    assert len(nodes) == 1
    assert nodes[0]["available"] is True
    assert set(nodes[0]["available_tools"]) == {tool.name for tool in ela.tools.tools()}


async def test_provider_list_shows_the_status_each_provider_reports(cli: Cli) -> None:
    """No key on this machine, so the provider is registered and UNAVAILABLE: ELA still runs."""
    result = await cli("provider", "list")

    assert result.exit_code == 0
    assert result.stdout.splitlines()[0].split() == ["PROVIDER", "STATUS"]
    assert "anthropic" in result.stdout
    assert "UNAVAILABLE" in result.stdout


async def test_provider_list_in_json_is_the_providers_and_not_the_diagnostics(cli: Cli) -> None:
    """The route answers a wider question than the command asks (ADR 0024 §5)."""
    answer = json.loads((await cli("provider", "list", "--json")).stdout)

    assert answer == {"anthropic": "UNAVAILABLE"}
