"""The worst case of the Planner's call, worked out by ``WorstCase`` and not by hand (decision 14).

``max_output_tokens`` is ``PLANNING_OUTPUT_TOKENS``, 16384, in ``parameters``: Opus 5.5 always
thinks, and thinking is inside ``max_tokens``. With the table of ADR 0057 the call costs at most
**4.262144 USD** — the window less the output in, at 4 $/MTok, and 16384 out at 20 $/MTok —, and
ADR 0058 writes that number. Here it is asked of the real adapter and the real tool, on the very
arguments the Planner writes: if the table, the route or the constant change, this test sees it.
"""

from __future__ import annotations

from decimal import Decimal

from ela.domain import IntentId, Task, TaskId, TaskState, WorstCase
from ela.executive.planner import PLANNING_OUTPUT_TOKENS, catalogue, planning_arguments
from ela.permissions import catalogue_v01
from ela.providers.anthropic.models import OPUS_5_5
from ela.routing import DEFAULT_ROUTES
from ela.testing.fakes import FakeClock, FakeIdGenerator
from ela.tools import ModelCompleteTool, tools_v01, verifiers_v01
from tests.domain.examples import NOW
from tests.providers.support import make_provider
from tests.routing.support import routing_for

PLANNING_WORST_CASE = Decimal("4.262144")
"""ADR 0058: the most one planning costs, with ``PLANNING_OUTPUT_TOKENS`` and ADR 0057's table."""


async def test_the_worst_case_of_a_planning_is_the_one_adr_0058_writes(tmp_path: object) -> None:
    provider, client = make_provider()
    router, providers = routing_for(provider)
    clock, ids = FakeClock(), FakeIdGenerator()
    root = f"{tmp_path}/workspace"
    tools = tools_v01(root=root, clock=clock, ids=ids, router=router, providers=providers)
    entries = catalogue(
        capabilities=catalogue_v01(), tools=tools, verifiers=verifiers_v01(root=root, router=router)
    )
    task = Task(
        id=TaskId(IntentId(ids.new_uuid())),
        created_at=NOW,
        goal="Scrivi una nota.",
        state=TaskState.PLANNING,
    )
    arguments = planning_arguments(task, entries, task_types=tuple(sorted(DEFAULT_ROUTES)))

    bound = await ModelCompleteTool(router, providers, clock, ids).worst_case(arguments)

    assert isinstance(bound, WorstCase)
    assert bound.model == OPUS_5_5
    assert bound.output_tokens == PLANNING_OUTPUT_TOKENS
    assert bound.input_tokens == 1_000_000 - PLANNING_OUTPUT_TOKENS
    assert bound.amount == PLANNING_WORST_CASE
    assert client is not None and client.messages.calls == [], "nothing left this machine"
