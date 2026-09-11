"""``ela device list`` and ``ela provider list``: the two lists, from their two routes."""

from __future__ import annotations

import json

from ela.composition import Ela
from ela.domain import (
    OperatingSystem,
    PerformanceClass,
    PrivacyLevel,
)
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
        "REVOKED",
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


async def test_node_enroll_prints_a_code_once_with_its_expiry(cli: Cli) -> None:
    result = await cli("node", "enroll", "--privacy", "TRUSTED", "--json")

    assert result.exit_code == 0
    issued = json.loads(result.stdout)
    assert set(issued) == {"code", "privacy", "expires_at"}
    assert issued["privacy"] == "TRUSTED"


async def test_node_enroll_offers_no_default_and_not_this_machines_level(cli: Cli) -> None:
    """Criterion 2 at the command line, and dec. D §2: ``--privacy`` is required, and only the two
    remote levels are offered — the route refuses ``LOCAL_ONLY`` on its own as well."""
    assert (await cli("node", "enroll")).exit_code != 0
    assert (await cli("node", "enroll", "--privacy", "LOCAL_ONLY")).exit_code != 0


async def test_node_revoke_refuses_this_machine(cli: Cli, ela: Ela) -> None:
    from ela.devices import LOCAL_DEVICE_ID

    result = await cli("node", "revoke", str(LOCAL_DEVICE_ID))

    assert result.exit_code == 1
    assert "not_revocable" in result.stderr


async def test_node_revoke_revokes_a_node_and_says_when(cli: Cli, ela: Ela) -> None:
    issued = await ela.enrollment.issue(PrivacyLevel.TRUSTED)
    node = (
        await ela.enrollment.enroll(
            issued.code,
            name="pc",
            os=OperatingSystem.WINDOWS,
            capabilities=(),
            available_tools=(),
            performance=PerformanceClass.HIGH,
        )
    ).device

    result = await cli("node", "revoke", str(node.id))

    assert result.exit_code == 0
    assert str(node.id) in result.stdout
    assert (await ela.devices.get(node.id)).revoked_at is not None
