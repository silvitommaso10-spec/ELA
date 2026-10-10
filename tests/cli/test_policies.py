"""``ela policy`` (M13.12, ADR 0062; decisions 9 and 19): create, list, revoke — against the real
API of an ELA whose guided session the test scripts.

``create`` shows the preview and asks «Create this policy? (s/N)» in a terminal; out of a terminal
and without ``--confirm`` it shows and does not create — the way the proof's script asks Tommaso
before creating, since its ``run`` captures stdout and only inherits stdin.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

import pytest
from click.testing import Result
from typer.testing import CliRunner

from ela.cli import client, policies
from ela.cli.app import app as ela_app
from ela.domain import AuthorizationId, CapabilityId
from ela.permissions import PolicyRequest, authorization_from_policy
from ela.providers.anthropic.models import HAIKU_5_5
from tests.api.guided import MAX_COST, Guided, Script, guided
from tests.cli.support import LoopTransport, plain

CREATE = (
    "policy",
    "create",
    "browser.guided",
    "--scope",
    "www.youtube.com",
    "--scope",
    "httpbin.org",
    "--limit",
    f"max_cost_usd={MAX_COST}",
    "--limit",
    "looks=10",
    "--limit",
    "seconds=600",
    "--days",
    "1",
)


@asynccontextmanager
async def a_cli(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> AsyncIterator[tuple[Guided, CliRunner]]:
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        transport = LoopTransport(g.app, asyncio.get_running_loop())
        monkeypatch.setattr(
            client, "connect", lambda: client.open_client(g.ela.settings.api, transport=transport)
        )
        yield g, CliRunner()


async def invoke(runner: CliRunner, *arguments: str, input: str | None = None) -> Result:
    return await asyncio.to_thread(runner.invoke, ela_app, list(arguments), input=input)


async def test_a_short_id_that_names_two_policies_is_refused_by_the_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Two policies whose ids start alike, saved through the port — a short id is eight characters,
    and two that share them are one in four billion: built, never waited for."""
    async with a_cli(monkeypatch, tmp_path) as (g, runner):
        for tail in (1, 2):
            grant = authorization_from_policy(
                PolicyRequest(
                    capability_id=CapabilityId("browser.guided"),
                    scope=("www.youtube.com",),
                    limits={"max_cost_usd": MAX_COST, "looks": "10", "seconds": "600"},
                    days=1,
                ),
                catalogue=g.ela.capabilities,
                granted_by="tommaso",
                now=g.ela.clock.now(),
                authorization_id=AuthorizationId(
                    UUID(f"3f2a1b2c-0000-4000-8000-00000000000{tail}")
                ),
            )
            await g.ela.authorizations.grant(grant)
        refused = await invoke(runner, "policy", "revoke", "3f2a1b2c")
        listed = (await g.client.get("/policies")).json()["policies"]

    assert refused.exit_code != 0
    assert "3f2a1b2c names more than one policy: give the whole id" in plain(refused.output)
    assert [one["state"] for one in listed] == ["LIVE", "LIVE"]


async def test_out_of_a_terminal_and_without_confirm_it_shows_and_does_not_create(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with a_cli(monkeypatch, tmp_path) as (g, runner):
        shown = await invoke(runner, *CREATE)
        listed = (await g.client.get("/policies")).json()["policies"]

    assert shown.exit_code == 0, shown.output
    out = plain(shown.output)
    # The sites are arguments, shown as every list of arguments is: borders visible (M13.2 dec. 12).
    assert '["www.youtube.com", "httpbin.org"]' in out
    assert HAIKU_5_5 in out
    assert "0.516384 USD" in out
    assert "not created" in out and "--confirm" in out
    assert listed == []


async def test_with_confirm_it_creates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async with a_cli(monkeypatch, tmp_path) as (g, runner):
        made = await invoke(runner, *CREATE, "--confirm")
        (policy,) = (await g.client.get("/policies")).json()["policies"]

    assert made.exit_code == 0, made.output
    assert f"created policy {policy['short']}" in plain(made.output)


@pytest.mark.parametrize(
    ("answer", "created"),
    [("s\n", True), ("sì\n", True), ("si\n", True), ("\n", False), ("n\n", False), ("y\n", False)],
)
async def test_in_a_terminal_it_asks_s_n_and_only_s_creates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, answer: str, created: bool
) -> None:
    monkeypatch.setattr(policies, "in_a_terminal", lambda: True)
    async with a_cli(monkeypatch, tmp_path) as (g, runner):
        asked = await invoke(runner, *CREATE, input=answer)
        stored = (await g.client.get("/policies")).json()["policies"]

    assert asked.exit_code == 0, asked.output
    assert "Create this policy? (s/N)" in plain(asked.output)
    assert bool(stored) is created


async def test_a_refusal_is_a_failure_with_the_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with a_cli(monkeypatch, tmp_path) as (_, runner):
        high = await invoke(
            runner,
            "policy",
            "create",
            "browser.act",
            "--scope",
            "httpbin.org",
            "--days",
            "1",
            "--confirm",
        )
        cheap = await invoke(
            runner,
            *[a if a != f"max_cost_usd={MAX_COST}" else "max_cost_usd=0.05" for a in CREATE],
            "--confirm",
        )

    assert high.exit_code != 0
    assert "no policy reaches a HIGH" in plain(high.output)
    assert cheap.exit_code != 0
    assert "guided.cap_below_one_call" in plain(cheap.output)


async def test_a_limit_must_be_written_name_equals_value(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with a_cli(monkeypatch, tmp_path) as (_, runner):
        wrong = await invoke(
            runner, "policy", "create", "browser.guided", "--limit", "looks", "--days", "1"
        )

    assert wrong.exit_code != 0
    assert "name=value" in plain(wrong.output)


async def test_list_shows_the_live_ones_and_all_shows_the_ended_too(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with a_cli(monkeypatch, tmp_path) as (g, runner):
        await invoke(runner, *CREATE, "--confirm")
        (policy,) = (await g.client.get("/policies")).json()["policies"]
        live = await invoke(runner, "policy", "list")
        await invoke(runner, "policy", "revoke", policy["short"])
        after = await invoke(runner, "policy", "list")
        everything = await invoke(runner, "policy", "list", "--all")

    out = plain(live.output)
    for word in (
        policy["short"],
        "browser.guided",
        "www.youtube.com",
        "looks=10",
        "the command line on the Core",
        "LIVE",
    ):
        assert word in out, word
    assert policy["short"] not in plain(after.output)
    assert "REVOKED" in plain(everything.output)


async def test_revoke_takes_the_short_id_and_says_a_running_session_goes_on(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with a_cli(monkeypatch, tmp_path) as (g, runner):
        await invoke(runner, *CREATE, "--confirm")
        (policy,) = (await g.client.get("/policies")).json()["policies"]
        gone = await invoke(runner, "policy", "revoke", policy["short"])
        twice = await invoke(runner, "policy", "revoke", policy["id"])
        nobody = await invoke(runner, "policy", "revoke", "deadbeef")

    assert gone.exit_code == 0, gone.output
    assert "goes on until it ends" in plain(gone.output)
    assert "ela task cancel" in plain(gone.output)
    assert twice.exit_code != 0 and "policy.not_live" in plain(twice.output)
    assert nobody.exit_code != 0 and "no policy" in plain(nobody.output)


def test_a_short_id_that_names_two_policies_is_refused_and_a_whole_id_is_itself() -> None:
    first = "3f2a1b2c-0000-4000-8000-000000000001"
    two = [{"id": first}, {"id": "3f2a1b2c-0000-4000-8000-000000000002"}]

    with pytest.raises(policies.Ambiguous):
        policies.resolved("3f2a1b2c", two)
    assert policies.resolved(first, two) == first
    assert policies.resolved("3f2a1b2c-0000-4000-8000-00000000000", two) is None
