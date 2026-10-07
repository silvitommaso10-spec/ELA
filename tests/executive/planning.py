"""What the tests of the Planner share: the answers a model could write, and a world to plan in.

M14.2, ADR 0058. The world is the pipeline of ``tests/executive/test_end_to_end.py`` — the real
catalogue of v0.1, the real Guardian, ``tools_v01`` and ``verifiers_v01``, the real router over a
fake provider, the month's cap — with a Planner on top: the call that writes a plan goes the way
of every other call, so the tests see it go.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from ela.domain import (
    ApprovalStatus,
    IntentId,
    ProviderRequest,
    Task,
    TaskId,
)
from ela.executive.planner import Planner, Planning
from ela.routing import DEFAULT_ROUTES
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeModelProvider
from tests.domain.examples import USER_INTENT
from tests.executive.test_end_to_end import CAP, Pipeline

NOTE_PATH = "workspace/notes/planned.md"
NOTE_BODY = "Questa nota l'ha pianificata ELA."
GOAL = f"Scrivi in {NOTE_PATH} una nota con il testo: {NOTE_BODY}"

ECHO_STEP: dict[str, Any] = {
    "name": "greet",
    "goal": "say hello",
    "capability": "core.echo",
    "arguments": {"message": "hello"},
    "expected_result": "the message comes back",
    "success_conditions": ["echo.message_matches"],
}
NOTE_STEP: dict[str, Any] = {
    "name": "write",
    "goal": "write the note",
    "capability": "workspace.write_note",
    "arguments": {"path": NOTE_PATH, "body": NOTE_BODY},
    "after": ["greet"],
    "expected_result": "the note, with its text",
    "success_conditions": ["note.exists", "note.content_matches"],
}
ASK_STEP: dict[str, Any] = {
    "name": "ask",
    "goal": "ask the model",
    "capability": "model.complete",
    "arguments": {"input": "Che cos'è un grafo aciclico diretto?", "task_type": "reasoning"},
    "expected_result": "two sentences",
    "success_conditions": ["model.answered", "model.routed_as_asked"],
}
NO_PLAN_REASON = "no capability of the catalogue switches a light off"


def plan_of(*steps: dict[str, Any]) -> str:
    return json.dumps({"plan": {"steps": list(steps)}})


def step(base: dict[str, Any], **changed: Any) -> dict[str, Any]:
    return {**base, **changed}


NOTE_PLAN = plan_of(ECHO_STEP, NOTE_STEP)
NO_PLAN = json.dumps({"no_plan": {"reason": NO_PLAN_REASON}})


class Planned(Pipeline):
    """The pipeline, with a Planner and a provider whose answer the test writes."""

    def __init__(
        self,
        workspace: Path,
        *,
        answer: str = NOTE_PLAN,
        cap: Decimal | None = CAP,
        **provider: Any,
    ) -> None:
        self.answer = answer
        # The provider's own clock and ids, as the other tests of the pipeline build it: what it
        # stamps is the provider's result, which the tool turns into the step's own.
        model = FakeModelProvider(FakeClock(), FakeIdGenerator(), reply=self._reply, **provider)
        super().__init__(workspace, model_providers=(model,), cap=cap)
        self.model = model
        self.planner = Planner(
            engine=self.engine,
            runner=self.runner,
            repository=self.repository,
            results=self.results,
            approvals=self.approvals,
            capabilities=self.registry,
            tools=self.tools,
            verifiers=self.verifiers,
            router=self.router,
            task_types=tuple(sorted(DEFAULT_ROUTES)),
        )

    def _reply(self, request: ProviderRequest) -> str:
        return self.answer

    async def task(self, goal: str = GOAL) -> Task:
        intent = USER_INTENT.model_copy(update={"id": IntentId(self.ids.new_uuid()), "text": goal})
        return await self.engine.create(intent)

    async def yes(self, planning: Planning) -> None:
        """The user's yes to the question of the planning task: the store, then the engine."""
        assert planning.approval is not None
        approval = await self.approvals.respond(
            planning.approval.id,
            status=ApprovalStatus.GRANTED,
            responded_by="tommaso",
            now=self.clock.now(),
        )
        assert planning.planning_task is not None
        await self.engine.approve(planning.planning_task.id, approval)

    async def no(self, planning: Planning) -> None:
        assert planning.approval is not None
        approval = await self.approvals.respond(
            planning.approval.id,
            status=ApprovalStatus.REJECTED,
            responded_by="tommaso",
            now=self.clock.now(),
        )
        assert planning.planning_task is not None
        await self.engine.deny(planning.planning_task.id, approval=approval)

    async def planned(self, goal: str = GOAL) -> tuple[TaskId, Planning]:
        """Asked, answered yes, and asked again: the whole planning of one task."""
        task = await self.task(goal)
        asked = await self.planner.plan(task.id)
        await self.yes(asked)
        return task.id, await self.planner.plan(task.id)
