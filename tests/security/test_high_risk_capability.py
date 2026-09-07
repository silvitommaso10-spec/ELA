"""A HIGH capability is denied whatever else is true: the second line holds on its own.

There are two defences against a capability above ``MAX_RISK`` (§29), and only one of them is
usually reachable:

1. :class:`~ela.permissions.CapabilityRegistry` **refuses to hold** a specification above
   ``MAX_RISK`` (MEDIUM, ADR 0010 §5): in a running ELA a HIGH never reaches the Guardian at all.
2. ``RISK_POLICY[HIGH] is Rule.DENY``: the Guardian denies it anyway.

Because the first works, the second can only be exercised on purpose, with a catalogue that
admits what the real one would not. That is exactly why it is worth exercising: the Guardian must
not be resting on the catalogue's cap, or the day the cap moves — and it will move, §29 has
levels above MEDIUM for a reason — the second line would turn out never to have existed.

So the test builds the situation deliberately and then makes it as favourable as it can be to the
call going through: the user has already approved, a covering grant is in the store, the step
declares the capability, the arguments are valid, the node is eligible. Still ``DENIED``, and the
tool is never called.

ADR 0026 §8.
"""

from __future__ import annotations

import pytest

from ela.domain import AuditEventType as E
from ela.domain import CapabilitySpec, PermissionOutcome, RiskLevel, TaskState
from ela.permissions import MAX_RISK, RISK_POLICY
from ela.permissions.guardian import Rule
from tests.executive.support import World, world
from tests.permissions.support import CRITICAL, HIGH, grant


@pytest.fixture
def w() -> World:
    return world()


@pytest.mark.parametrize("spec", [HIGH, CRITICAL], ids=lambda s: s.risk.value)
async def test_a_capability_above_the_cap_is_denied_through_the_whole_pipeline(
    w: World, spec: CapabilitySpec
) -> None:
    assert spec.risk > MAX_RISK
    task, step = await w.running(spec.id, requires_authorization=True)
    # Everything a caller could put in its favour, short of changing the policy:
    await w.store.grant(grant(spec, task_id=task.id, step_id=step.id, max_uses=None))

    execution = await w.execute(task.id, step.id)

    assert execution.decision is not None
    assert execution.decision.outcome is PermissionOutcome.DENIED
    assert execution.decision.metadata["rule"] == Rule.DENY.value
    assert execution.task.state is TaskState.DENIED
    assert w.tool(spec.id).calls == ()
    assert E.PERMISSION_DECIDED in await w.event_types(task.id)
    assert E.TOOL_EXECUTED not in await w.event_types(task.id)


async def test_the_denial_does_not_depend_on_the_catalogue_refusing_it_first(w: World) -> None:
    """The two defences are independent, and this is the sentence that says so.

    The catalogue this world uses **holds** a HIGH specification — the real one would raise
    ``RiskNotAllowedError`` — so the decision under test is the Guardian's alone.
    """
    assert HIGH in w.registry.specs()
    assert w.registry.get(HIGH.id).risk is RiskLevel.HIGH

    task, step = await w.running(HIGH.id)
    execution = await w.execute(task.id, step.id)

    assert execution.decision is not None
    assert execution.decision.outcome is PermissionOutcome.DENIED
    assert "not allowed by policy" in execution.decision.reason


def test_the_policy_denies_every_level_above_the_catalogue_cap() -> None:
    """The table and the cap agree, so no level can be added above MEDIUM and left allowed."""
    above = [level for level in RiskLevel if level > MAX_RISK]

    assert above  # a cap with nothing above it would make this vacuous
    assert all(RISK_POLICY[level] is Rule.DENY for level in above)
