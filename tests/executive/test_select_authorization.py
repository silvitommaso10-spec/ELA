"""``select_authorization`` (ADR 0013 §3): which grant the executor hands the Guardian. Pure."""

from __future__ import annotations

from datetime import timedelta

from ela.domain import AuthorizationId, StepId
from ela.executive import approved_targets, select_authorization
from tests.domain.examples import NOW, OTHER_STEP_ID, PERMISSION_DECISION, TASK, TASK_STEP
from tests.executive.support import grant_for
from tests.permissions.support import NOTE, OTHER_TASK_ID

TARGETS = ("workspace/notes/briefing.md",)
BOUND = grant_for(NOTE, task=TASK, step=TASK_STEP, created_at=NOW, max_uses=1, tail=701)
POLICY = grant_for(NOTE, created_at=NOW, tail=702)
OTHER_POLICY = grant_for(NOTE, created_at=NOW, tail=703)


def select(*candidates: tuple[object, int]) -> object:
    return select_authorization(
        candidates,  # type: ignore[arg-type]
        task=TASK,
        step=TASK_STEP,
        targets=TARGETS,
        now=NOW,
    )


def test_no_candidate_is_none() -> None:
    assert select() is None


def test_a_grant_that_does_not_cover_is_never_handed_over() -> None:
    other_task = BOUND.model_copy(update={"task_id": OTHER_TASK_ID})
    other_step = BOUND.model_copy(update={"step_id": OTHER_STEP_ID})
    elsewhere = POLICY.model_copy(update={"scope": ("workspace/other",)})
    empty_scope = POLICY.model_copy(update={"scope": ()})
    for grant in (other_task, other_step, elsewhere, empty_scope):
        assert select((grant, 0)) is None, grant


def test_a_covering_grant_that_is_not_usable_is_still_handed_over() -> None:
    """So the Guardian's reason, and the request for approval, name why."""
    expired = POLICY.model_copy(update={"expires_at": NOW})
    exhausted = (BOUND, 1)
    assert select((expired, 0)) == (expired, 0)
    assert select(exhausted) == exhausted


def test_a_usable_grant_beats_an_unusable_one_whatever_the_order() -> None:
    assert select((BOUND, 1), (POLICY, 0)) == (POLICY, 0)
    assert select((POLICY, 0), (BOUND, 1)) == (POLICY, 0)


def test_a_grant_bound_to_this_step_comes_before_a_policy_grant() -> None:
    assert select((POLICY, 0), (BOUND, 0)) == (BOUND, 0)


def test_between_policy_grants_the_first_granted_wins() -> None:
    assert select((POLICY, 0), (OTHER_POLICY, 0)) == (POLICY, 0)
    assert select((OTHER_POLICY, 0), (POLICY, 0)) == (OTHER_POLICY, 0)


def test_expiry_is_closed_and_the_use_limit_strict() -> None:
    later = POLICY.model_copy(update={"expires_at": NOW + timedelta(seconds=1)})
    at_now = POLICY.model_copy(update={"expires_at": NOW})
    limited = POLICY.model_copy(update={"max_uses": 3})
    assert select((at_now, 0), (later, 0)) == (later, 0)
    assert select((limited, 3), (limited, 2)) == (limited, 2)


def test_a_grant_bound_to_a_task_but_not_a_step_covers_the_task() -> None:
    task_only = POLICY.model_copy(update={"task_id": TASK.id})
    assert select((task_only, 0)) == (task_only, 0)
    assert select((task_only.model_copy(update={"task_id": OTHER_TASK_ID}), 0)) is None


def test_approved_targets_are_the_strings_of_the_decision() -> None:
    with_targets = PERMISSION_DECISION.model_copy(
        update={"metadata": {"targets": ["workspace/notes/a.md", None, 3]}}
    )
    assert approved_targets(with_targets) == ("workspace/notes/a.md",)
    assert approved_targets(PERMISSION_DECISION) == ()
    odd = PERMISSION_DECISION.model_copy(update={"metadata": {"targets": "not-a-list"}})
    assert approved_targets(odd) == ()


def test_the_step_key_is_the_step_id_not_the_object() -> None:
    twin = BOUND.model_copy(
        update={"id": AuthorizationId(BOUND.id), "step_id": StepId(TASK_STEP.id)}
    )
    assert select((POLICY, 0), (twin, 0)) == (twin, 0)
