"""The cap on a node's call, through the real application (M14.1, proposal 5; ADR 0057).

A call that spends is decided on the Core: the claim is the gate, the order carries the worst case
reserved, and the delivery closes the reservation with what the node says the call cost. The ELA
here has a cap and a key that no socket ever carries: ``tests/conftest.py`` makes httpx's network
transports unusable, and nothing below would need them — the worst case is a computation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from ela.domain import ExecutionId, ExecutionResult, ExecutionStatus, TaskId, WorstCase
from ela.executive.spending import CAP_VARIABLE
from ela.ports import SPENDING_OVER_RESERVATION
from ela.tools.model import MODEL_COMPLETE
from tests.api.reasons import World, answer_the_question, ending, example, opened, run
from tests.api.support import queued
from tests.api.test_nodes import enrolled

OPUS = WorstCase(
    amount=Decimal("4.065536"),
    currency="USD",
    model="claude-opus-5-5",
    input_tokens=995904,
    output_tokens=4096,
)
"""The worst case of ``ask-model.json`` (``reasoning`` → Opus 5.5, 4096 out), ADR 0057's table."""


@asynccontextmanager
async def capped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cap: str = "5"
) -> AsyncIterator[tuple[World, dict[str, str]]]:
    """An ELA with a cap and a key, and a node that declares every tool and is built to win."""
    async with opened(
        monkeypatch, tmp_path, ELA_SPENDING_CAP_USD=cap, ELA_ANTHROPIC_API_KEY="sk-ant-test"
    ) as w:
        _, headers = await enrolled(
            w.client, "TRUSTED", available_tools=[tool.name for tool in w.ela.tools.tools()]
        )
        await w.client.post(
            "/nodes/heartbeat", json={"status": "IDLE", "power_source": "AC"}, headers=headers
        )
        yield w, headers


async def handed(w: World) -> str:
    """The model's question asked, answered yes, and its step handed to the node."""
    task = await queued(w.client, example("ask-model.json"), privacy="TRUSTED")
    assert (await run(w, task))["outcome"] == "waiting_approval"
    await answer_the_question(w, task, "approve")
    assigned = await run(w, task)
    assert assigned["outcome"] == "assigned", assigned
    return task


async def spend(w: World) -> dict[str, Any]:
    answer = await w.client.get("/spend")
    assert answer.status_code == 200, answer.text
    body: dict[str, Any] = answer.json()
    return body


def delivered(order: dict[str, Any], **envelope: Any) -> dict[str, Any]:
    return {
        "assignment_id": order["assignment_id"],
        "form": "result",
        "duration_ms": 12,
        "node": {"finished_at": "2026-10-06T08:00:02Z"},
        **envelope,
    }


async def test_the_order_carries_the_reservation_and_the_claim_wrote_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with capped(monkeypatch, tmp_path) as (w, headers):
        task = await handed(w)

        taken = await w.client.post("/nodes/work", headers=headers)

        assert taken.status_code == 200, taken.text
        assert WorstCase.model_validate(taken.json()["worst_case"]) == OPUS
        (started,) = await w.ela.results.for_task(TaskId(UUID(task)))
        assert started.status is ExecutionStatus.STARTED and started.worst_case == OPUS
        ledger = await spend(w)
        assert (ledger["reserved"], ledger["open"], ledger["spent"]) == ("4.065536", 1, "0")


async def test_the_delivery_closes_the_reservation_with_the_nodes_cost(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with capped(monkeypatch, tmp_path) as (w, headers):
        await handed(w)
        order = (await w.client.post("/nodes/work", headers=headers)).json()
        usage = {"input_tokens": 30, "output_tokens": 40, "cost": "0.00092", "currency": "USD"}
        output = {"text": "due righe", "model": OPUS.model, "finish_reason": "end_turn"}

        answer = await w.client.post(
            "/nodes/work/result",
            json=delivered(order, status="SUCCEEDED", output=output, usage=usage),
            headers=headers,
        )

        assert answer.status_code == 200, answer.text
        ledger = await spend(w)
        assert (ledger["spent"], ledger["reserved"], ledger["open"]) == ("0.00092", "0", 0)


async def test_a_node_that_refused_to_spend_beyond_it_closes_it_at_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The envelope of :func:`ela.node.runner.beyond_the_reservation`: not sent, so nothing."""
    async with capped(monkeypatch, tmp_path) as (w, headers):
        await handed(w)
        order = (await w.client.post("/nodes/work", headers=headers)).json()
        error = {"code": SPENDING_OVER_RESERVATION, "message": "not sent"}
        usage = {"input_tokens": 0, "output_tokens": 0, "sent": False}

        answer = await w.client.post(
            "/nodes/work/result",
            json=delivered(order, status="FAILED", output={}, error=error, usage=usage),
            headers=headers,
        )

        assert answer.status_code == 200, answer.text
        ledger = await spend(w)
        assert (ledger["spent"], ledger["reserved"], ledger["unknown"]) == ("0", "0", 0)


async def test_a_claim_the_month_cannot_let_out_sends_no_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Between the yes and the claim another call took the month's margin: the claim withdraws the
    offer, the task is denied with the four numbers, and the node is told there is nothing — it
    never receives the call."""
    async with capped(monkeypatch, tmp_path) as (w, headers):
        task = await handed(w)
        rival = ExecutionResult(
            id=ExecutionId(w.ela.ids.new_uuid()),
            created_at=w.ela.clock.now(),
            capability_id=MODEL_COMPLETE,
            status=ExecutionStatus.STARTED,
            worst_case=OPUS.model_copy(update={"amount": Decimal(2)}),
        )
        await w.ela.results.add(rival)

        taken = await w.client.post("/nodes/work", headers=headers)

        assert taken.status_code == 204, taken.text
        shown = (await w.client.get(f"/tasks/{task}")).json()
        assert shown["state"] == "DENIED"
        assert (await w.client.get(f"/tasks/{task}/results")).json() == []
        denied = await ending(w, task)
        assert denied["event_type"] == "TASK_DENIED"
        assert denied["payload"]["operation"] == "deny_by_cap"
        assert denied["payload"]["code"] == "spending.over_cap"
        assert (denied["payload"]["reserved"], denied["payload"]["worst_case"]) == (
            "2",
            "4.065536",
        )
        assert CAP_VARIABLE in denied["payload"]["reason"]
