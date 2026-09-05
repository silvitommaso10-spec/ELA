"""The invariant of the Guardian over random calls (ADR 0011): ``ALLOWED`` implies a justification.

For random specifications (registered, tampered, unknown), arguments (valid, invalid, targets in
and out of scope), steps and authorizations (right and wrong capability, task binding, scope,
expiry, use limit), every ``ALLOWED`` decision is explained by exactly the rules of the policy,
HIGH and CRITICAL are never allowed, an allowed decision expires, and ``decide`` never raises.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from ela.domain import (
    Authorization,
    CapabilityId,
    CapabilitySpec,
    PermissionOutcome,
    RiskLevel,
    TaskStep,
)
from ela.permissions import (
    DEFAULT_DECISION_TTL,
    RISK_POLICY,
    InvalidArgumentsError,
    Rule,
    validate_arguments,
)
from ela.permissions.scope import scope_covers, targets_of
from ela.ports import NotFoundError
from ela.testing.fakes import FakeCapabilityRegistry
from tests.domain.examples import TASK
from tests.permissions.support import CATALOGUE, OTHER_TASK_ID, grant, harness, step_for

REGISTRY = FakeCapabilityRegistry(CATALOGUE)
IDS = tuple(spec.id for spec in CATALOGUE)
NOW = harness().now

paths = st.sampled_from(
    [
        "workspace/notes/a.md",
        "workspace/notes",
        "workspace/notes-old/a.md",
        "../workspace/notes/a.md",
        "/workspace/notes/a.md",
        "elsewhere/a.md",
    ]
)
arguments = st.one_of(
    st.fixed_dictionaries({"message": st.one_of(st.text(max_size=5), st.integers())}),
    st.fixed_dictionaries(
        {"path": st.one_of(paths, st.integers(), st.none()), "body": st.text(max_size=5)}
    ),
    st.fixed_dictionaries({"body": st.text(max_size=3)}),
    st.fixed_dictionaries({"input": st.text(max_size=5)}),
    st.just({}),
)


def _tamper(spec: CapabilitySpec, risk: RiskLevel) -> CapabilitySpec:
    return spec.model_copy(update={"risk": risk})


specs = st.one_of(
    st.sampled_from(CATALOGUE),
    st.builds(_tamper, st.sampled_from(CATALOGUE), st.sampled_from(list(RiskLevel))),
    st.sampled_from(CATALOGUE).map(
        lambda s: s.model_copy(update={"id": CapabilityId("nobody.knows")})
    ),
)

steps = st.one_of(
    st.none(),
    st.builds(
        lambda required, auth: step_for(*required, requires_authorization=auth),
        st.lists(st.sampled_from(IDS), max_size=3, unique=True),
        st.booleans(),
    ),
)


def _grant(
    spec: CapabilitySpec,
    scope: tuple[str, ...] | None,
    bound: bool,
    expiry: int | None,
    max_uses: int | None,
) -> Authorization:
    changes: dict[str, Any] = {"max_uses": max_uses}
    if scope is not None:
        changes["scope"] = scope
    if bound:
        changes["task_id"] = TASK.id
    if expiry is not None:
        changes["expires_at"] = NOW + timedelta(seconds=expiry)
    return grant(spec, **changes)


authorizations = st.one_of(
    st.none(),
    st.builds(
        _grant,
        st.sampled_from(CATALOGUE),
        st.one_of(st.none(), st.sampled_from([(), ("workspace/notes",), ("workspace",), ("x",)])),
        st.booleans(),
        st.one_of(st.none(), st.integers(min_value=-60, max_value=60)),
        st.one_of(st.none(), st.integers(min_value=1, max_value=3)),
    ),
)
tasks = st.sampled_from([None, TASK, TASK.model_copy(update={"id": OTHER_TASK_ID})])
uses = st.integers(min_value=-1, max_value=4)


def _is_registered(spec: CapabilitySpec) -> bool:
    try:
        return REGISTRY.get(spec.id) == spec
    except NotFoundError:
        return False


def _arguments_valid(spec: CapabilitySpec, args: dict[str, Any]) -> bool:
    try:
        validate_arguments(spec, args)
    except InvalidArgumentsError:
        return False
    return True


def _covers(
    authorization: Authorization,
    spec: CapabilitySpec,
    task: Any,
    step: TaskStep | None,
    targets: tuple[object, ...],
    count: int,
) -> bool:
    """The grant is coherent with the call (ADR 0011 §6): capability, task, step, scope, count."""
    if authorization.capability_id != spec.id:
        return False
    if authorization.task_id is not None and (task is None or task.id != authorization.task_id):
        return False
    if authorization.step_id is not None and (step is None or step.id != authorization.step_id):
        return False
    return scope_covers(authorization.scope, targets) and count >= 0


def _usable(authorization: Authorization, count: int) -> bool:
    if authorization.expires_at is not None and authorization.expires_at <= NOW:
        return False
    return authorization.max_uses is None or count < authorization.max_uses


@given(specs, arguments, tasks, steps, authorizations, uses)
@settings(max_examples=600, deadline=None)
def test_allowed_implies_a_justification(
    spec: CapabilitySpec,
    args: dict[str, Any],
    task: Any,
    step: TaskStep | None,
    authorization: Authorization | None,
    count: int,
) -> None:
    h = harness()
    decision = h.guardian.decide(
        spec, args, task=task, step=step, authorization=authorization, authorization_uses=count
    )
    if spec.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        assert decision.outcome is not PermissionOutcome.ALLOWED
    if decision.outcome is not PermissionOutcome.ALLOWED:
        assert decision.expires_at is None
        return
    assert _is_registered(spec)
    assert _arguments_valid(spec, args)
    assert step is None or not step.required_capabilities or spec.id in step.required_capabilities
    targets = targets_of(spec, args)
    coherent = authorization is None or _covers(authorization, spec, task, step, targets, count)
    assert coherent, "a grant that does not cover the call is never ignored"
    covered = authorization is not None and coherent and _usable(authorization, count)
    needs = spec.requires_authorization or (step is not None and step.requires_authorization)
    if spec.risk is RiskLevel.SAFE:
        assert covered or not needs
    elif spec.risk is RiskLevel.LOW:
        assert scope_covers(spec.scope, targets)
        assert covered or not needs
    else:
        assert spec.risk is RiskLevel.MEDIUM and covered
    assert decision.expires_at is not None
    assert h.now < decision.expires_at <= h.now + DEFAULT_DECISION_TTL
    if covered and authorization is not None and authorization.expires_at is not None:
        assert decision.expires_at <= authorization.expires_at


def _reaches_the_grant(spec: CapabilitySpec, args: dict[str, Any], step: TaskStep | None) -> bool:
    """Whether the checks before the grant (catalogue, arguments, step, policy row) all pass."""
    if not (_is_registered(spec) and _arguments_valid(spec, args)):
        return False
    declared = step is None or not step.required_capabilities
    if not declared and spec.id not in step.required_capabilities:  # type: ignore[union-attr]
        return False
    if RISK_POLICY[spec.risk] is Rule.DENY:
        return False
    return spec.risk is not RiskLevel.LOW or scope_covers(spec.scope, targets_of(spec, args))


@given(specs, arguments, tasks, steps, authorizations, uses)
@settings(max_examples=300, deadline=None)
def test_decide_never_raises_and_always_names_a_rule(
    spec: CapabilitySpec,
    args: dict[str, Any],
    task: Any,
    step: TaskStep | None,
    authorization: Authorization | None,
    count: int,
) -> None:
    decision = harness().guardian.decide(
        spec, args, task=task, step=step, authorization=authorization, authorization_uses=count
    )
    if _reaches_the_grant(spec, args, step) and authorization is not None:
        targets = targets_of(spec, args)
        if not _covers(authorization, spec, task, step, targets, count):
            assert decision.outcome is PermissionOutcome.DENIED
            assert decision.metadata["rule"] == "AUTHORIZATION_MISMATCH"
    assert decision.reason
    assert decision.metadata["policy"] == "v0.1"
    assert isinstance(decision.metadata["rule"], str)
    assert decision.capability_id == spec.id
    assert decision.authorization_id == (None if authorization is None else authorization.id)
