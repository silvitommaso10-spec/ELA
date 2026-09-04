"""The transition table of spec §14 as decided in ADR 0004, checked pair by pair.

Two layers on purpose: the principles P1–P8 *explain* the table, the exhaustive 100-pair test
*guarantees* it. If they ever disagree, one of them is wrong and the test says so.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from itertools import product
from types import MappingProxyType

import pytest
from pydantic import ValidationError

from ela.domain import Task, TaskEvent, TaskEventType, TaskState
from ela.tasks.state_machine import (
    TERMINAL_STATES,
    TRANSITIONS,
    IllegalTransitionError,
    Transition,
    allowed_transitions,
    can_transition,
    is_terminal,
    transition,
)
from tests.domain.examples import LATER, NOW, STEP_ID, TASK, TASK_EVENT_ID, TASK_ID

S = TaskState

# The table of ADR 0004, written out a second time by hand so that a typo in the code cannot
# hide behind a test that reads the code.
EXPECTED: dict[TaskState, frozenset[TaskState]] = {
    S.CREATED: frozenset({S.PLANNING, S.CANCELLED, S.EXPIRED}),
    S.PLANNING: frozenset(
        {S.WAITING_APPROVAL, S.QUEUED, S.FAILED, S.DENIED, S.CANCELLED, S.EXPIRED}
    ),
    S.WAITING_APPROVAL: frozenset({S.QUEUED, S.DENIED, S.CANCELLED, S.EXPIRED}),
    S.QUEUED: frozenset({S.EXECUTING, S.CANCELLED, S.EXPIRED}),
    S.EXECUTING: frozenset(
        {S.COMPLETED, S.FAILED, S.WAITING_APPROVAL, S.QUEUED, S.DENIED, S.CANCELLED, S.EXPIRED}
    ),
    S.COMPLETED: frozenset(),
    S.FAILED: frozenset(),
    S.CANCELLED: frozenset(),
    S.DENIED: frozenset(),
    S.EXPIRED: frozenset(),
}

ALL_PAIRS = list(product(TaskState, TaskState))
LEGAL = [(a, b) for a, b in ALL_PAIRS if b in EXPECTED[a]]
ILLEGAL = [(a, b) for a, b in ALL_PAIRS if b not in EXPECTED[a]]
LIVE = [state for state in TaskState if state not in TERMINAL_STATES]


def pair_id(pair: tuple[TaskState, TaskState]) -> str:
    return f"{pair[0].value}->{pair[1].value}"


def task_in(state: TaskState) -> Task:
    return TASK.model_copy(update={"state": state})


def move(task: Task, new_state: TaskState) -> Transition:
    return transition(task, new_state, event_id=TASK_EVENT_ID, now=LATER)


# --------------------------------------------------------------------------------------
# The table itself
# --------------------------------------------------------------------------------------


def test_terminal_states_are_the_five_of_section_14() -> None:
    assert {S.COMPLETED, S.FAILED, S.CANCELLED, S.DENIED, S.EXPIRED} == TERMINAL_STATES
    for state in TaskState:
        assert is_terminal(state) is (state in TERMINAL_STATES)


def test_table_is_total_and_immutable() -> None:
    assert set(TRANSITIONS) == set(TaskState)
    assert isinstance(TRANSITIONS, MappingProxyType)
    with pytest.raises(TypeError):
        TRANSITIONS[S.CREATED] = frozenset()  # type: ignore[index]
    for targets in TRANSITIONS.values():
        assert isinstance(targets, frozenset)


def test_counts_match_the_adr() -> None:
    assert len(LEGAL) == 23
    assert len(ILLEGAL) == 77


@pytest.mark.parametrize("pair", ALL_PAIRS, ids=pair_id)
def test_can_transition_matches_the_table(pair: tuple[TaskState, TaskState]) -> None:
    current, new_state = pair
    assert can_transition(current, new_state) is (new_state in EXPECTED[current])


@pytest.mark.parametrize("state", list(TaskState), ids=lambda s: s.value)
def test_allowed_transitions_is_the_table_row(state: TaskState) -> None:
    assert allowed_transitions(state) == EXPECTED[state]
    assert allowed_transitions(state) is TRANSITIONS[state]


# --------------------------------------------------------------------------------------
# transition(): the 23 legal moves and the 77 illegal ones
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("pair", LEGAL, ids=pair_id)
def test_legal_transition_returns_new_task_and_event(pair: tuple[TaskState, TaskState]) -> None:
    current, new_state = pair
    before = task_in(current)
    result = move(before, new_state)

    assert isinstance(result, Transition)
    assert result.task.state is new_state
    assert result.task is not before
    assert before.state is current

    event = result.event
    assert event.id == TASK_EVENT_ID
    assert event.created_at == LATER
    assert event.task_id == before.id
    assert event.event_type is TaskEventType.STATE_CHANGED
    assert event.previous_state is current
    assert event.new_state is new_state


@pytest.mark.parametrize("pair", ILLEGAL, ids=pair_id)
def test_illegal_transition_raises_and_leaves_task_untouched(
    pair: tuple[TaskState, TaskState],
) -> None:
    current, new_state = pair
    before = task_in(current)
    snapshot = before.model_dump()

    with pytest.raises(IllegalTransitionError) as info:
        move(before, new_state)

    assert info.value.task_id == before.id
    assert info.value.current is current
    assert info.value.requested is new_state
    assert before.model_dump() == snapshot


@pytest.mark.parametrize(
    ("pair", "why"),
    [
        ((S.COMPLETED, S.PLANNING), "COMPLETED is terminal"),
        ((S.EXPIRED, S.EXPIRED), "EXPIRED is terminal"),
        ((S.EXECUTING, S.EXECUTING), "cannot re-enter the state it is already in"),
        ((S.CREATED, S.COMPLETED), "not in the table"),
    ],
    ids=["terminal", "terminal-self", "self", "not-listed"],
)
def test_error_explains_why(pair: tuple[TaskState, TaskState], why: str) -> None:
    current, new_state = pair
    with pytest.raises(IllegalTransitionError) as info:
        move(task_in(current), new_state)
    text = str(info.value)
    assert str(TASK_ID) in text
    assert f"from {current.value} to {new_state.value}" in text
    assert why in text


# --------------------------------------------------------------------------------------
# The event and the copy
# --------------------------------------------------------------------------------------


def test_event_passthrough_fields() -> None:
    result = transition(
        task_in(S.EXECUTING),
        S.WAITING_APPROVAL,
        event_id=TASK_EVENT_ID,
        now=LATER,
        message="lo step chiede l'approvazione",
        step_id=STEP_ID,
        metadata={"decision_id": "abc", "attempt": 2},
    )
    event = result.event
    assert event.message == "lo step chiede l'approvazione"
    assert event.step_id == STEP_ID
    assert dict(event.metadata) == {"decision_id": "abc", "attempt": 2}


def test_default_event_fields_are_empty() -> None:
    event = move(task_in(S.CREATED), S.PLANNING).event
    assert event.message == ""
    assert event.step_id is None
    assert dict(event.metadata) == {}


def test_event_is_frozen_and_roundtrips_in_json() -> None:
    event = move(task_in(S.QUEUED), S.EXECUTING).event
    with pytest.raises(ValidationError):
        event.message = "x"  # type: ignore[misc]
    assert TaskEvent.model_validate_json(event.model_dump_json()) == event


def test_only_state_changes() -> None:
    before = task_in(S.PLANNING)
    after = move(before, S.QUEUED).task
    expected = {**before.model_dump(), "state": S.QUEUED}
    assert after.model_dump() == expected
    assert Task.model_validate_json(after.model_dump_json()) == after


def test_transition_is_deterministic() -> None:
    before = task_in(S.WAITING_APPROVAL)
    first = move(before, S.QUEUED)
    second = move(before, S.QUEUED)
    assert first == second
    assert first.task == second.task
    assert first.event == second.event


def test_string_state_is_rejected_even_when_it_spells_a_state() -> None:
    """``"QUEUED" == TaskState.QUEUED`` is true for a StrEnum: the type check is what saves us."""
    before = task_in(S.PLANNING)
    with pytest.raises(TypeError, match="TaskState"):
        transition(before, "QUEUED", event_id=TASK_EVENT_ID, now=LATER)  # type: ignore[arg-type]
    assert before.state is S.PLANNING


def test_naive_now_is_rejected_by_the_event() -> None:
    with pytest.raises(ValidationError):
        transition(task_in(S.CREATED), S.PLANNING, event_id=TASK_EVENT_ID, now=datetime(2026, 9, 4))


def test_now_may_precede_task_creation() -> None:
    """The state machine has no policy: ordering instants is the Task Engine's job, not ours."""
    result = transition(task_in(S.CREATED), S.PLANNING, event_id=TASK_EVENT_ID, now=NOW)
    assert result.event.created_at == NOW


# --------------------------------------------------------------------------------------
# The principles of ADR 0004, each as a test
# --------------------------------------------------------------------------------------


def test_p1_terminal_states_have_no_exit() -> None:
    for state in TERMINAL_STATES:
        assert TRANSITIONS[state] == frozenset()


def test_p2_no_self_transition() -> None:
    for state in TaskState:
        assert state not in TRANSITIONS[state]


def test_p3_cancel_and_expire_from_every_live_state() -> None:
    for state in LIVE:
        assert {S.CANCELLED, S.EXPIRED} <= TRANSITIONS[state]


def test_p4_failed_only_while_working() -> None:
    assert sources_of(S.FAILED) == {S.PLANNING, S.EXECUTING}


def test_p5_denied_only_where_someone_decides() -> None:
    assert sources_of(S.DENIED) == {S.PLANNING, S.WAITING_APPROVAL, S.EXECUTING}


def test_p6_executing_only_from_queued() -> None:
    assert sources_of(S.EXECUTING) == {S.QUEUED}


def test_p7_completed_only_from_executing() -> None:
    assert sources_of(S.COMPLETED) == {S.EXECUTING}


def test_p8_every_state_reachable_and_no_dead_end() -> None:
    assert reachable_from(S.CREATED) == set(TaskState) - {S.CREATED}
    for state in LIVE:
        assert reachable_from(state) & TERMINAL_STATES, f"{state} cannot reach a terminal state"


def test_task_state_has_no_behaviour() -> None:
    """The table lives here, not on the enum (CLAUDE.md: the domain holds data, not behaviour)."""
    extra = [
        name
        for name in vars(TaskState)
        if not name.startswith("_") and name not in TaskState.__members__
    ]
    assert extra == []


def sources_of(target: TaskState) -> set[TaskState]:
    return {state for state, targets in TRANSITIONS.items() if target in targets}


def reachable_from(start: TaskState) -> set[TaskState]:
    seen: set[TaskState] = set()
    queue = deque([start])
    while queue:
        for target in TRANSITIONS[queue.popleft()]:
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return seen
