"""``OPERATIONS`` and ``TRANSITIONS`` describe the same moves (ADR 0008 §3).

Every source of every operation may legally reach its target, and every legal transition of
ADR 0004 is some operation's: nothing is reachable only by walking around the engine.
"""

from __future__ import annotations

import pytest

from ela.domain import TaskState
from ela.tasks.engine import LIVE_STATES, OPERATIONS, Operation, TaskEngine
from ela.tasks.state_machine import TERMINAL_STATES, TRANSITIONS, can_transition

LEGAL = {(a, b) for a, targets in TRANSITIONS.items() for b in targets}


@pytest.mark.parametrize("op", OPERATIONS.values(), ids=list(OPERATIONS))
def test_every_source_may_reach_the_target(op: Operation) -> None:
    for source in op.sources:
        assert can_transition(source, op.target), f"{op.name}: {source} -> {op.target}"
    assert op.target not in op.sources
    assert op.sources


def test_every_legal_transition_is_some_operation() -> None:
    covered = {(s, op.target) for op in OPERATIONS.values() for s in op.sources}
    assert covered == LEGAL
    assert len(LEGAL) == 23


def test_no_terminal_state_is_a_source() -> None:
    for op in OPERATIONS.values():
        assert not (op.sources & TERMINAL_STATES), op.name


def test_live_states_are_the_non_terminal_ones() -> None:
    assert set(TaskState) - TERMINAL_STATES == LIVE_STATES
    assert OPERATIONS["cancel"].sources == OPERATIONS["expire"].sources == LIVE_STATES


def test_every_row_has_a_public_method() -> None:
    """``deny_by_*`` are the two facts of ``deny``; every other row is a method of its name."""
    for name in OPERATIONS:
        method = name.partition("_by_")[0]
        assert callable(getattr(TaskEngine, method)), name


def test_keys_name_the_input_that_makes_the_operation_idempotent() -> None:
    keyed = {name: op.key for name, op in OPERATIONS.items() if op.key is not None}
    assert keyed == {
        "request_approval": "approval_id",
        "approve": "approval_id",
        "deny_by_approval": "approval_id",
        "deny_by_decision": "decision_id",
        "complete": "result_id",
    }


def test_the_table_is_immutable_and_keyed_by_name() -> None:
    with pytest.raises(TypeError):
        OPERATIONS["queue"] = OPERATIONS["start"]  # type: ignore[index]
    assert all(name == op.name for name, op in OPERATIONS.items())
