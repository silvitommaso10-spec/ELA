"""The invariant of ``authorization_from_approval`` over random inputs (ADR 0012 §2).

For random approvals, tasks, steps and specifications — coherent by construction or perturbed in
one or more fields — a grant comes back *if and only if* the approval is GRANTED, signed, in time,
cites this task, step and capability, the step declares the capability or nothing, and the
targets are inside the registered scope on a capability that has targets. When it comes back it
is single use, bound, scoped to the targets, expires after ``ttl``; nothing else is ever raised.
"""

from __future__ import annotations

from datetime import timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from ela.domain import (
    Approval,
    ApprovalStatus,
    Authorization,
    CapabilityId,
    CapabilitySpec,
    Task,
    TaskStep,
)
from ela.permissions import ApprovalMismatchError, authorization_from_approval
from ela.permissions.scope import scope_covers
from tests.domain.examples import APPROVAL, NOW, TASK, TASK_STEP
from tests.domain.strategies import utc_datetimes, uuids
from tests.permissions.support import CATALOGUE, GUARDED_NOTE, NOTE
from tests.permissions.test_authorizations import GRANT_ID

specs = st.sampled_from(CATALOGUE)
target_paths = st.sampled_from(
    [
        "workspace/notes/a.md",
        "workspace/notes",
        "workspace/notes-old/a.md",
        "../workspace/notes/a.md",
        "/workspace/notes/a.md",
        "elsewhere/a.md",
    ]
)
targets = st.lists(target_paths, max_size=2).map(tuple)
capability_ids = st.sampled_from([spec.id for spec in CATALOGUE] + [CapabilityId("other.thing")])
tasks = st.one_of(st.just(TASK), uuids.map(lambda u: TASK.model_copy(update={"id": u})))
steps = st.builds(
    lambda u, required: TASK_STEP.model_copy(update={"id": u, "required_capabilities": required}),
    st.one_of(st.just(TASK_STEP.id), uuids),
    st.lists(capability_ids, max_size=2).map(tuple),
)
approvals = st.builds(
    lambda changes: APPROVAL.model_copy(update=changes),
    st.fixed_dictionaries(
        {},
        optional={
            "status": st.sampled_from(ApprovalStatus),
            "responded_by": st.one_of(st.none(), st.just(""), st.just("tommaso")),
            "responded_at": st.one_of(st.none(), utc_datetimes),
            "expires_at": st.one_of(st.none(), utc_datetimes),
            "task_id": uuids,
            "step_id": uuids,
            "capability_id": capability_ids,
            "targets": targets,
        },
    ),
)
ttls = st.timedeltas(min_value=timedelta(seconds=1), max_value=timedelta(hours=24))


def _should_grant(approval: Approval, task: Task, step: TaskStep, spec: CapabilitySpec) -> bool:
    return (
        approval.status is ApprovalStatus.GRANTED
        and bool(approval.responded_by)
        and approval.responded_at is not None
        and (approval.expires_at is None or approval.responded_at < approval.expires_at)
        and approval.task_id == task.id
        and approval.step_id == step.id
        and approval.capability_id == spec.id
        and (not step.required_capabilities or spec.id in step.required_capabilities)
        and (
            not approval.targets
            or (bool(spec.scoped_arguments) and scope_covers(spec.scope, approval.targets))
        )
    )


# ``deadline=None`` as in the other property tests: Hypothesis fails an example that takes
# longer than 200ms, and a runner under load is not a bug in the code under test.
@settings(max_examples=400, deadline=None)
@given(approval=approvals, task=tasks, step=steps, spec=specs, ttl=ttls)
def test_a_grant_comes_back_iff_the_approval_is_this_call(
    approval: Approval, task: Task, step: TaskStep, spec: CapabilitySpec, ttl: timedelta
) -> None:
    expected = _should_grant(approval, task, step, spec)
    try:
        grant: Authorization | None = authorization_from_approval(
            approval,
            task=task,
            step=step,
            capability=spec,
            now=NOW,
            authorization_id=GRANT_ID,
            ttl=ttl,
        )
    except ApprovalMismatchError as error:
        grant = None
        assert error.approval_id == approval.id
    assert (grant is not None) == expected
    if grant is not None:
        assert grant.max_uses == 1
        assert grant.approval_id == approval.id
        assert (grant.task_id, grant.step_id, grant.capability_id) == (task.id, step.id, spec.id)
        assert grant.scope == (approval.targets or spec.scope)
        assert grant.expires_at is not None and grant.expires_at - grant.created_at == ttl
        assert Authorization.model_validate(grant.model_dump()) == grant


@settings(deadline=None)
@given(spec=st.sampled_from([NOTE, GUARDED_NOTE]), approved=targets)
def test_the_scope_never_widens_beyond_what_was_approved(
    spec: CapabilitySpec, approved: tuple[str, ...]
) -> None:
    approval = APPROVAL.model_copy(update={"capability_id": spec.id, "targets": approved})
    step = TASK_STEP.model_copy(update={"required_capabilities": (spec.id,)})
    try:
        grant = authorization_from_approval(
            approval, task=TASK, step=step, capability=spec, now=NOW, authorization_id=GRANT_ID
        )
    except ApprovalMismatchError:
        return
    assert scope_covers(spec.scope, grant.scope) or grant.scope == spec.scope
    for target in approved:
        assert target in grant.scope
