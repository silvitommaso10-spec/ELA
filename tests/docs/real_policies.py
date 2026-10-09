"""What a real ELA answers along the proof of M13.12, recorded once, for the tests of its script.

The form of ``tests/docs/real_guided.py``: every kind of ``scripts/prova_m13_12.py`` that reads the
API is fed by **the routes themselves** — ELA as ``build`` makes it, with the cap, the key and the
three sites of section 27, the real gateway, and a fake session of Claude Code that runs the turn
of its sentence (``tests/api/guided.py``). The commands of the guide are run by the command line in
this process, and their output is what Tommaso reads.

Recorded in the order of section 27: the question with no policy and its stop; the four refusals;
the preview that creates nothing, the creation, the list; the covered session and its ``ela task
show``;
the two questions outside the policy; the revocation and the question after it; a policy created
from a console and revoked there. The gesture that asks inside a covered session — step 7 — is read
by the kinds of section 26, which ``tests/docs/test_prova_m14_3.py`` feeds already.

A negative case starts from one of these answers and changes it; nothing else is written by hand.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pytest

from ela.cli import client as cli_client
from ela.providers.anthropic.models import HAIKU_5_5
from tests.api.guided import Guided, Script, call, gesture, guided
from tests.api.test_console_policies import FIELDS, a_console, posted
from tests.cli.support import Cli, LoopTransport, plain
from tests.docs.real_guided import ByGoal

ROOT: Final = Path(__file__).resolve().parents[2]
EXAMPLES: Final = ROOT / "docs" / "examples"
YOUTUBE: Final = "policy-youtube.json"
MORE: Final = "policy-youtube-more.json"
EXAMPLE: Final = "policy-example.json"
CREATE: Final = (
    "policy",
    "create",
    "browser.guided",
    "--scope",
    "www.youtube.com",
    "--scope",
    "httpbin.org",
    "--limit",
    "max_cost_usd=1.10",
    "--limit",
    "looks=10",
    "--limit",
    "seconds=300",
    "--days",
    "1",
)
"""The command of step 4, without ``--confirm``: section 27 writes it on one line."""
REFUSALS: Final = (
    ("policy", "create", "browser.act", "--scope", "example.com", "--days", "1", "--confirm"),
    ("policy", "create", "fs.write", "--scope", "notes", "--days", "1", "--confirm"),
    (
        *CREATE[:5],
        "--limit",
        "max_cost_usd=0.05",
        "--limit",
        "looks=10",
        "--limit",
        "seconds=300",
        "--days",
        "1",
        "--confirm",
    ),
    (
        "policy",
        "create",
        "browser.guided",
        "--scope",
        "www.wikipedia.org",
        "--limit",
        "max_cost_usd=1.10",
        "--limit",
        "looks=10",
        "--limit",
        "seconds=300",
        "--days",
        "1",
        "--confirm",
    ),
)
"""The four refusals of step 3, as section 27 writes them."""


def sentence(name: str) -> str:
    (step,) = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))["steps"]
    return str(step["arguments"]["goal"])


def turns() -> ByGoal:
    return ByGoal(
        [],
        turns={
            sentence(YOUTUBE): Script(
                [
                    call(),
                    gesture("read", site="www.youtube.com", path="/results?search_query=MrBeast"),
                    call(),
                ]
            ),
        },
    )


@dataclass(frozen=True)
class Asked:
    """A session that asks: the task, the questions that wait, and the stop."""

    task: str
    waiting_output: str
    question: Any
    cancel_output: str


@dataclass(frozen=True)
class Real:
    """The answers of the routes and of the command line, in the order of the proof."""

    openapi: Any
    spend_start: Any
    none: Asked
    """Step 2: no policy, the question says so."""
    approvals_output: str
    """``ela approvals`` while the question of step 2 waits."""
    refusals: tuple[str, ...]
    """What the four refusals of step 3 printed, each with its exit code first."""
    policies_empty: Any
    preview_output: str
    """``ela policy create`` without ``--confirm``, out of a terminal."""
    after_preview: Any
    created_output: str
    policies_live: Any
    list_output: str
    covered_task: str
    covered_output: str
    covered_results: Any
    show_output: str
    policies_used: Any
    """``GET /policies?all=true`` after the covered session."""
    above: Asked
    outside: Asked
    revoke_output: str
    policies_revoked: Any
    revoked: Asked
    console_policies: Any
    """``GET /policies?all=true`` after a policy created and revoked from a console."""
    spend_end: Any


class Recorder:
    def __init__(self, g: Guided, cli: Cli) -> None:
        self.g = g
        self.cli = cli

    async def get(self, path: str) -> Any:
        response = await self.g.client.get(path)
        assert response.status_code == 200, (path, response.text)
        return response.json()

    async def command(self, *words: str) -> str:
        result = await self.cli(*words)
        assert result.exit_code == 0, result.output
        return plain(result.stdout)

    async def any_exit(self, *words: str) -> str:
        result = await self.cli(*words)
        return f"{result.exit_code}\n{plain(result.output)}"

    async def planned(self, name: str) -> str:
        created = await self.command("task", "create", sentence(name), "--json")
        task = str(json.loads(created)["id"])
        await self.command("task", "plan", task, "--file", str(EXAMPLES / name))
        return task

    async def asked(self, name: str) -> Asked:
        task = await self.planned(name)
        waiting = await self.command("task", "run", task)
        question = await self.get("/approvals")
        return Asked(task, waiting, question, await self.command("task", "cancel", task))


async def recorded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Real:
    async with guided(monkeypatch, tmp_path, turns()) as g:
        transport = LoopTransport(g.app, asyncio.get_running_loop())
        monkeypatch.setattr(
            cli_client,
            "connect",
            lambda: cli_client.open_client(g.ela.settings.api, transport=transport),
        )
        r = Recorder(g, Cli(transport))
        openapi, spend_start = await r.get("/openapi.json"), await r.get("/spend")

        task = await r.planned(YOUTUBE)
        waiting = await r.command("task", "run", task)
        question = await r.get("/approvals")
        approvals_output = await r.command("approvals")
        none = Asked(task, waiting, question, await r.command("task", "cancel", task))

        refusals = tuple([await r.any_exit(*words) for words in REFUSALS])
        policies_empty = await r.get("/policies")

        preview_output = await r.command(*CREATE)
        after_preview = await r.get("/policies")
        created_output = await r.command(*CREATE, "--confirm")
        policies_live = await r.get("/policies?all=true")
        list_output = await r.command("policy", "list")

        covered_task = await r.planned(YOUTUBE)
        covered_output = await r.command("task", "run", covered_task)
        covered_results = await r.get(f"/tasks/{covered_task}/results")
        show_output = await r.command("task", "show", covered_task)
        policies_used = await r.get("/policies?all=true")

        above = await r.asked(MORE)
        outside = await r.asked(EXAMPLE)

        (policy,) = policies_live["policies"]
        revoke_output = await r.command("policy", "revoke", str(policy["short"]))
        policies_revoked = await r.get("/policies?all=true")
        revoked = await r.asked(YOUTUBE)

        async with a_console(g) as console:
            made = await posted(console, "/console/policies", [*FIELDS, ("model", HAIKU_5_5)])
            assert made.status_code in (200, 303), made.text
            mine = [
                one for one in (await r.get("/policies"))["policies"] if one["id"] != policy["id"]
            ]
            (by_console,) = mine
            gone = await console.post("/console/policies/revoke", data={"id": by_console["id"]})
            assert gone.status_code == 303, gone.text
        console_policies = await r.get("/policies?all=true")
        spend_end = await r.get("/spend")
    return Real(
        openapi=openapi,
        spend_start=spend_start,
        none=none,
        approvals_output=approvals_output,
        refusals=refusals,
        policies_empty=policies_empty,
        preview_output=preview_output,
        after_preview=after_preview,
        created_output=created_output,
        policies_live=policies_live,
        list_output=list_output,
        covered_task=covered_task,
        covered_output=covered_output,
        covered_results=covered_results,
        show_output=show_output,
        policies_used=policies_used,
        above=above,
        outside=outside,
        revoke_output=revoke_output,
        policies_revoked=policies_revoked,
        revoked=revoked,
        console_policies=console_policies,
        spend_end=spend_end,
    )


def record(tmp_path_factory: pytest.TempPathFactory) -> Real:
    """The answers, from a world that lives only while they are asked."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        return asyncio.run(recorded(monkeypatch, tmp_path_factory.mktemp("policies")))
