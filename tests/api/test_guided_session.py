"""A guided session of the browser through the API, end to end (M14.3, ADR 0060): nothing paid.

The question names the sentence, the sites, the model, the most the session may spend, the looks,
the duration and what leaves the machine, with the worst case and the month (decision 4); the yes
launches the session; its calls pass the gateway with the key put on there; each gesture is a child
task walked by the runner, with its decision (decision 6); the end closes the reservation with what
the calls cost, and the audit gets numbers only (decision 13).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from ela.domain import AuditEventType, ExecutionStatus, PlanAuthorKind, StepId, TaskId, TaskState
from ela.providers.anthropic.models import HAIKU_5_5
from tests.api.guided import (
    GOAL,
    LOOPBACK,
    Guided,
    Script,
    approve,
    approved_and_run,
    call,
    gesture,
    guided,
    planned,
    question,
    run,
)
from tests.providers.support import SECRET


def tid(task: str) -> TaskId:
    return TaskId(UUID(task))


async def children(g: Guided, task: str) -> list[Any]:
    """The tasks of the session's gestures: every task whose parent is the session's task."""
    return [one for one in await g.ela.repository.tasks() if str(one.parent_id) == task]


async def results(g: Guided, task: str) -> list[Any]:
    plan = await g.ela.repository.plan(tid(task))  # type: ignore[arg-type]
    return list(await g.ela.results.for_step(tid(task), plan.steps[0].id))


async def test_the_question_names_the_session_and_what_leaves_the_machine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        task = await planned(g)

        first = await run(g, task)
        asked = await question(g, task)

    assert first["outcome"] == "waiting_approval"
    assert asked["capability_id"] == "browser.guided"
    assert asked["phrase"] == GOAL
    assert asked["sites"] == ["www.youtube.com"]
    assert asked["model"] == HAIKU_5_5
    assert asked["max_cost"] == "0.6 USD"
    assert asked["looks"] == 8
    assert asked["timeout_seconds"] == 600
    assert "go to anthropic" in asked["sends"]
    assert asked["worst_case"] == (
        f"0.6 USD, {HAIKU_5_5}, up to 991808 tokens in and 8192 out per call"
    )
    assert asked["left"].startswith("30 of 30 USD left")
    assert asked["targets"] == ["www.youtube.com"]
    assert g.sessions.launched == [], "nothing is launched before the yes"


async def test_a_session_calls_through_the_gateway_reads_a_page_and_ends_verified(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = Script(
        [
            call(),
            gesture("read", site="www.youtube.com", path="/results?search_query=MrBeast"),
            call(),
        ]
    )
    async with guided(monkeypatch, tmp_path, script) as g:
        g.browser.page.texts = {None: "Risultati: @MrBeast, 300 Mln di iscritti"}
        task = await planned(g)

        ran = await approved_and_run(g, task)
        kids = await children(g, task)
        rows = await results(g, task)
        audit = await g.ela.audit.read(task_id=TaskId(kids[0].id))
        own = await g.ela.audit.read(task_id=tid(task))  # type: ignore[arg-type]
        month, held = await g.ela.spending.ledger(g.ela.clock.now())

    assert ran["outcome"] == "completed", ran
    (child,) = kids
    assert child.state is TaskState.COMPLETED
    assert "@MrBeast" in script.read[0] and "address:" in script.read[0]
    assert [status for status, _ in script.answered] == [200, 200]
    sent = g.anthropic.received
    assert len(sent) == 2
    assert all(request.headers["x-api-key"] == SECRET for request in sent)
    assert all(
        request.headers["anthropic-beta"] == "fine-grained-tool-streaming" for request in sent
    )
    assert json.loads(sent[0].content)["model"] == HAIKU_5_5
    (outcome,) = [row for row in rows if row.status is ExecutionStatus.SUCCEEDED]
    assert outcome.output["text"].startswith("Il canale è @MrBeast")
    assert (outcome.output["looks"], outcome.output["calls"], outcome.output["refused"]) == (
        1,
        2,
        0,
    )
    assert outcome.usage is not None and outcome.usage.request_bytes == sum(
        len(request.content) for request in sent
    )
    expected = 2 * (1_200 * Decimal("0.10") + 40 * Decimal("0.50")) / Decimal(1_000_000)
    assert outcome.usage.cost == expected
    assert held.spent == expected and held.reserved == 0 and held.open == 0
    assert [event.event_type for event in audit][0] is AuditEventType.TASK_CREATED
    executed = [event for event in own if event.event_type is AuditEventType.TOOL_EXECUTED]
    numbers = executed[-1].payload["numbers"]
    assert numbers == {
        "acts": 0,
        "calls": 2,
        "input_minus_bytes_max": max(1_200 - len(request.content) for request in sent),
        "input_tokens": 2_400,
        "looks": 1,
        "output_tokens": 80,
        "refused": 0,
        "unknown_calls": 0,
    }
    assert GOAL not in repr([event.payload for event in executed])


async def test_the_plan_of_a_gesture_says_the_session_wrote_it_within_its_sites(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = Script([gesture("read", site="www.youtube.com", path="/")])
    async with guided(monkeypatch, tmp_path, script) as g:
        task = await planned(g)
        await approved_and_run(g, task)
        (child,) = await children(g, task)
        plan = await g.ela.repository.plan(child.id)
        session_plan = await g.ela.repository.plan(tid(task))  # type: ignore[arg-type]

    (step,) = plan.steps
    assert plan.author.by is PlanAuthorKind.SESSION
    assert plan.author.session == session_plan.steps[0].id
    assert plan.author.model == HAIKU_5_5
    assert step.within == ("www.youtube.com",)
    assert step.required_capabilities == ("browser.read",)
    assert step.arguments["purpose"].startswith("gesture 1 of the guided session")
    assert "www.youtube.com" in child.goal and str(session_plan.steps[0].id) in child.goal


async def test_the_session_s_token_opens_nothing_but_its_own_gateway(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Criterion 1, the last half: the session has no key to send away, and its token is worth
    nothing outside its own paths, from loopback, while it is open."""
    tokens: list[str] = []
    elsewhere: list[int] = []

    async def peek(script: Script, plan: Any, host: Any) -> None:
        tokens.append(plan.token)
        http = script.http(plan)
        on_a_route = await http.get(
            f"{LOOPBACK}/tasks", headers={"Authorization": f"Bearer {plan.token}"}
        )
        another = await http.post(
            f"{LOOPBACK}/sessions/{StepId(TaskId(plan.session))}0/v1/messages",
            content=b"{}",
            headers={"x-api-key": plan.token},
        )
        elsewhere.extend([on_a_route.status_code, another.status_code])

    script = Script([peek])
    async with guided(monkeypatch, tmp_path, script) as g:
        task = await planned(g)
        await approved_and_run(g, task)
        (launched,) = g.sessions.launched
        after = await g.client.post(
            f"/sessions/{launched[1].session}/v1/messages",
            content=b"{}",
            headers={"x-api-key": tokens[0]},
        )

    reservation, plan = launched
    assert SECRET not in json.dumps(
        [str(value) for value in vars(plan).values()] if hasattr(plan, "__dict__") else [str(plan)]
    )
    assert SECRET not in repr(plan) and SECRET not in repr(reservation)
    assert elsewhere == [401, 401]
    assert after.status_code == 401


async def test_without_a_cap_the_session_is_denied_before_the_question_and_nothing_leaves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Criterion 2: no cap, no question, no session, and the provider counts zero."""
    monkeypatch.delenv("ELA_SPENDING_CAP_USD", raising=False)
    async with guided(monkeypatch, tmp_path, Script([call()]), ELA_SPENDING_CAP_USD="") as g:
        task = await planned(g)
        ran = await run(g, task)
        pending = (await g.client.get("/approvals")).json()

    assert ran["outcome"] == "denied", ran
    assert pending == []
    assert g.sessions.launched == [] and g.anthropic.received == []


async def test_a_yes_to_a_gesture_that_acts_is_the_user_s_and_the_session_waits_for_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Decision 6: a ``browser.act`` asks, the session waits for the child to end, and a no is a
    gesture denied that the session reads."""
    script = Script(
        [
            gesture(
                "act",
                site="www.youtube.com",
                path="/",
                fill=[],
                click="button[type=submit]",
                expect_text="ok",
            )
        ]
    )
    async with guided(monkeypatch, tmp_path, script) as g:
        task = await planned(g)
        first = await run(g, task)
        assert first["outcome"] == "waiting_approval"
        await approve(g, task)
        running = __import__("asyncio").ensure_future(run(g, task))
        child = None
        for _ in range(200):
            kids = await children(g, task)
            if kids and kids[0].state is TaskState.WAITING_APPROVAL:
                child = kids[0]
                break
            await __import__("asyncio").sleep(0.01)
        assert child is not None, "the act waits for its own yes"
        asked = await question(g, str(child.id))
        assert g.browser.clicks == []
        denied = await g.client.post(
            f"/tasks/{child.id}/deny", json={"approval_id": asked["id"], "reason": "no"}
        )
        assert denied.status_code == 200, denied.text
        ran = await running

    assert ran["outcome"] == "completed", ran
    assert script.read[0].startswith("gesture 1: DENIED")
    assert g.browser.clicks == []
