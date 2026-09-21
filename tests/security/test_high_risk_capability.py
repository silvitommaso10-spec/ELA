"""The catalogue cap and the policy rows hold each other up, and neither may move in silence.

There are two defences against a capability the policy would refuse, and only one of them is
usually reachable:

1. :class:`~ela.permissions.CapabilityRegistry` **refuses to hold** a specification above
   :data:`~ela.permissions.MAX_RISK`: in a running ELA such a capability never reaches the
   Guardian at all.
2. The row of :data:`~ela.permissions.RISK_POLICY` denies it anyway.

Because the first works, the second can only be exercised on purpose, with a catalogue that
admits what the real one would not. That is exactly why it is worth exercising: the Guardian must
not be resting on the catalogue's cap.

**M13.1 moved the cap, and this file is what the move taught.** Until then the third test here
asked whether every level *above* ``MAX_RISK`` was denied — a question derived from the very
constant it was defending, so raising the cap from MEDIUM to HIGH did not make it fail: it made it
quietly narrower, still green, no longer proving anything about HIGH. **An assertion that adapts
to the change it exists to catch is not an assertion** (M13.1 dec. M). So the cap and the rows are
now stated together, in full, and the message says what to rewrite.
"""

from __future__ import annotations

import pytest

from ela.domain import AuditEventType as E
from ela.domain import CapabilityId, PermissionOutcome, RiskLevel, TaskState
from ela.permissions import MAX_RISK, POLICY_VERSION, RISK_POLICY, asks_at_every_use
from ela.permissions.guardian import Rule
from ela.testing.fakes import FakeCapabilityRegistry
from tests.executive.support import World, world
from tests.permissions.support import (
    CRITICAL,
    ECHO,
    ECHO_ARGS,
    HIGH,
    NOTE_ARGS,
    born_of_a_yes,
    grant,
    harness,
)


@pytest.fixture
def w() -> World:
    return world()


MOVE_THEM_TOGETHER = (
    "The cap, the rows and the version of the policy are three halves of one decision: a "
    "capability may exist up to here, this is what happens to it, and this is the name the audit "
    "stamps on every decision taken under those rules. Move one and you move all three, in the "
    "open, with an ADR that revises ADR 0011 §3 the way ADR 0045 did (M13.1 dec. M)."
)


def test_the_cap_the_rows_and_the_version_are_stated_together_and_none_moves_alone() -> None:
    """The pin that must **fail** when the world moves, instead of narrowing (dec. M).

    Written out rather than derived: the old form asked whether every level *above the cap* was
    denied, so raising the cap made it quietly narrower instead of making it fail.

    ``POLICY_VERSION`` is here for the same reason it was bumped to ``v0.2`` at all. A decision
    carries the version of the table that took it, so a milestone that changes a row and forgets
    the bump makes every decision name a table that is not the one it was decided under —
    **exactly what the bump exists to prevent**. Nothing else in the suite asserts its value, so
    if it is not asserted here it is not asserted anywhere.
    """
    assert MAX_RISK is RiskLevel.HIGH, f"the catalogue cap moved. {MOVE_THEM_TOGETHER}"
    assert RISK_POLICY == {
        RiskLevel.SAFE: Rule.ALLOW,
        RiskLevel.LOW: Rule.ALLOW_WITHIN_SCOPE,
        RiskLevel.MEDIUM: Rule.APPROVAL_UNLESS_AUTHORIZED,
        RiskLevel.HIGH: Rule.APPROVAL_EVERY_USE,
        RiskLevel.CRITICAL: Rule.DENY,
    }, f"the policy moved. {MOVE_THEM_TOGETHER}"
    assert POLICY_VERSION == "v0.2", (
        f"the policy version moved, and this is the only place that says which one it is. "
        f"{MOVE_THEM_TOGETHER}"
    )
    assert [level for level in RiskLevel if level > MAX_RISK] == [RiskLevel.CRITICAL], (
        "what is above the cap changed: the tests below exercise CRITICAL because it was the one "
        "level the catalogue refuses, and that is no longer true"
    )


def test_the_version_the_audit_stamps_is_the_one_stated_above() -> None:
    """And it is the one a decision really carries, not only the one the constant holds.

    Every decision stamps it in ``metadata["policy"]`` — that is what an audit row keeps — and
    the rows that settle on the table itself say it in words too.
    """
    h = harness()

    asked = h.guardian.decide(HIGH, ECHO_ARGS)
    allowed = h.guardian.decide(ECHO, ECHO_ARGS)
    denied = h.guardian.decide(CRITICAL, ECHO_ARGS)

    assert asked.metadata["policy"] == POLICY_VERSION
    assert POLICY_VERSION in allowed.reason
    assert POLICY_VERSION in denied.reason


async def test_a_capability_above_the_cap_is_denied_through_the_whole_pipeline(w: World) -> None:
    """CRITICAL, with everything a caller could put in its favour, and still nothing runs."""
    spec = CRITICAL
    assert spec.risk > MAX_RISK
    task, step = await w.running(spec.id, requires_authorization=True)
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

    The catalogue this world uses **holds** a CRITICAL specification — the real one would raise
    ``RiskNotAllowedError`` — so the decision under test is the Guardian's alone.
    """
    assert CRITICAL in w.registry.specs()
    assert w.registry.get(CRITICAL.id).risk is RiskLevel.CRITICAL

    task, step = await w.running(CRITICAL.id)
    execution = await w.execute(task.id, step.id)

    assert execution.decision is not None
    assert execution.decision.outcome is PermissionOutcome.DENIED
    assert "not allowed by policy" in execution.decision.reason


async def test_a_high_capability_asks_every_time_and_no_standing_policy_covers_it(
    w: World,
) -> None:
    """The row the cap now admits, exercised through the executor (M13.1 dec. D, N).

    A HIGH capability is **registrable** since M13.1, so this is not a hand-built world: it is
    what a real one does. The user is asked; a standing policy of §59 — constructible today, which
    is why this is a defence exercised and not a defence declared — does not cover it; the grant
    born from a yes does.
    """
    task, step = await w.running(HIGH.id)
    asked = await w.execute(task.id, step.id)

    assert asked.decision is not None
    assert asked.decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert asked.decision.metadata["rule"] == Rule.APPROVAL_EVERY_USE.value
    assert w.tool(HIGH.id).calls == ()

    # A second task, because the first one is now waiting for the user: what changes is the store,
    # which holds a standing policy of §59 for this very capability.
    other = world()
    task, step = await other.running(HIGH.id)
    standing = grant(HIGH, task_id=task.id, step_id=step.id, max_uses=None)
    assert standing.approval_id is None
    await other.store.grant(standing)

    again = await other.execute(task.id, step.id)

    assert again.decision is not None
    assert again.decision.outcome is PermissionOutcome.REQUIRES_APPROVAL, (
        "a standing policy of §59 must not turn a HIGH into a run, and it must not turn it into a "
        "denial either: the user is still the one who answers (M13.1 dec. D)"
    )
    assert again.decision.metadata["rule"] == Rule.APPROVAL_EVERY_USE.value
    assert other.tool(HIGH.id).calls == ()


def test_the_grant_a_yes_mints_is_the_one_that_covers_a_high_row() -> None:
    """The other side of dec. D, on the two shapes the domain itself keeps apart."""
    assert asks_at_every_use(RiskLevel.HIGH)
    assert not asks_at_every_use(RiskLevel.MEDIUM)
    assert born_of_a_yes(HIGH).approval_id is not None
    assert grant(HIGH).approval_id is None


@pytest.mark.parametrize("level", list(RISK_POLICY), ids=lambda level: level.value)
def test_a_target_outside_the_scope_is_denied_on_every_row_of_the_table(level: RiskLevel) -> None:
    """M13.1 dec. C: the boundary is bound to the **fact** that a scope is declared.

    A scope only the LOW row enforced would be a boundary a capability could escape by being more
    dangerous — the shape ADR 0026 §7 calls worse than no defence at all. So one case per row, a
    closed world over :data:`RISK_POLICY`: a row added tomorrow without a case here fails.

    And the denial signs itself ``SCOPE`` and not the row that allows, because a HIGH refused for
    its scope presenting itself as ``ALLOW_WITHIN_SCOPE`` would be the false diagnosis of dec. B.
    """
    scoped = HIGH.model_copy(
        update={
            "id": CapabilityId(f"fs.scoped_{level.value.lower()}"),
            "risk": level,
            "scope": ("allowed",),
            "scoped_arguments": ("path",),
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "body": {"type": "string"}},
                "required": ["path", "body"],
                "additionalProperties": False,
            },
        }
    )
    h = harness(registry=FakeCapabilityRegistry([scoped]))

    decision = h.guardian.decide(scoped, {**NOTE_ARGS, "path": "elsewhere/x.md"})

    assert decision.outcome is PermissionOutcome.DENIED
    if level is RiskLevel.CRITICAL:
        # The row denies first, and deliberately: a CRITICAL is refused **for being CRITICAL**,
        # which is the more important fact about it. The order is the one ADR 0011 §3 keeps — the
        # denials of the table before anything else — and the scope check sits right after it,
        # before any question.
        assert decision.metadata["rule"] == Rule.DENY.value
        return
    assert decision.metadata["rule"] == Rule.SCOPE.value
    assert "not within scope" in decision.reason
