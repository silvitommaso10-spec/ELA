"""The Guardian and the policies of §59 (M13.12, ADR 0062; decisions 2, 4, 9, 17; M13.14, ADR 0068).

A policy that covers allows, and says so; one that is revoked, expired or spent is the normal «ask»
of §62; one that does not cover is the caller's incoherence, as every grant that does not cover
(ADR 0011 §6) — the executor never hands it over (``tests/executive/test_select_policies.py``).
Since M13.14 a policy covers a ``HIGH`` that declares terms, and the place of the step is read by
one rule, only to take away: a policy of the Core does not cover a step elsewhere.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest

from ela.domain import (
    Authorization,
    AuthorizationId,
    CapabilityId,
    CapabilitySpec,
    DeviceId,
    PermissionOutcome,
    PlanAuthor,
    PlanAuthorKind,
    PolicyTerms,
    SessionCover,
    StepId,
    TaskId,
    TaskStep,
)
from ela.permissions import (
    BROWSER_ACT,
    BROWSER_ACT_AS_YOU,
    BROWSER_GUIDED,
    BROWSER_GUIDED_AS_YOU,
    PermissionGuardian,
    PolicyRequest,
    Rule,
    authorization_from_policy,
    browser_act,
    fs_write,
    short_id,
    terminal_run,
)
from ela.testing.fakes import (
    FakeAuditLog,
    FakeCapabilityRegistry,
    FakeClock,
    FakeIdGenerator,
)
from tests.domain.examples import NOW, STEP_ID, TASK
from tests.permissions.catalogue_calls import CALLS, CATALOGUE
from tests.permissions.policy_support import (
    GUIDED,
    GUIDED_ARGS,
    GUIDED_LIMITS,
    SITES,
    TERMED,
    TERMED_ARGS,
    policy_for,
    revoked,
)
from tests.permissions.support import (
    COMPLETE,
    ECHO,
    GUARDED_ECHO,
    NOTE,
    Harness,
    born_of_a_yes,
    grant,
    harness,
)

ACT = browser_act(SITES)
ACT_ARGS: dict[str, Any] = {
    "site": "httpbin.org",
    "path": "/forms/post",
    "fill": [["#custname", "ELA"]],
    "click": "#submit",
    "expect_text": "ELA",
    "purpose": "inviare il modulo",
}


@pytest.fixture
def h() -> Harness:
    return harness(
        registry=FakeCapabilityRegistry((GUIDED, TERMED, ACT, ECHO, NOTE, COMPLETE, GUARDED_ECHO))
    )


def decide(h: Harness, spec: Any, arguments: Any, policy: Any) -> Any:
    return h.guardian.decide(spec, arguments, authorization=policy)


def test_a_policy_that_covers_allows_and_says_policy(h: Harness) -> None:
    policy = policy_for(GUIDED, scope=("www.youtube.com",), limits=GUIDED_LIMITS)

    decision = decide(h, GUIDED, GUIDED_ARGS, policy)

    assert decision.outcome is PermissionOutcome.ALLOWED
    assert decision.metadata["rule"] == Rule.APPROVAL_UNLESS_AUTHORIZED.value
    assert decision.reason == f"browser.guided is covered by policy {policy.id}"
    assert decision.authorization_id == policy.id


def test_the_decision_expires_no_later_than_the_policy(h: Harness) -> None:
    policy = policy_for(GUIDED, expires_at=h.now + timedelta(seconds=30))

    decision = decide(h, GUIDED, GUIDED_ARGS, policy)

    assert decision.expires_at == h.now + timedelta(seconds=30)


def test_a_revoked_policy_asks_and_names_the_revocation(h: Harness) -> None:
    policy = revoked(policy_for(GUIDED), h.now)

    decision = decide(h, GUIDED, GUIDED_ARGS, policy)

    assert decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert decision.reason == (
        f"browser.guided requires an authorization: policy {short_id(policy.id)} was revoked on "
        f"{h.now.date().isoformat()}"
    )


def test_an_expired_policy_asks(h: Harness) -> None:
    policy = policy_for(GUIDED, expires_at=h.now)

    decision = decide(h, GUIDED, GUIDED_ARGS, policy)

    assert decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert "expired on" in decision.reason


@pytest.mark.parametrize(
    "arguments",
    [
        {**GUIDED_ARGS, "sites": ["example.com"]},
        {**GUIDED_ARGS, "max_cost_usd": "2.00"},
        {**GUIDED_ARGS, "task_type": "browsing"},
    ],
    ids=["site", "limit", "argument"],
)
def test_a_policy_handed_over_that_does_not_cover_is_an_incoherence(
    h: Harness, arguments: dict[str, Any]
) -> None:
    """ADR 0011 §6: the Guardian never ignores a fact it was handed."""
    policy = policy_for(GUIDED, scope=("www.youtube.com",), limits=GUIDED_LIMITS)

    decision = decide(h, GUIDED, arguments, policy)

    assert decision.outcome is PermissionOutcome.DENIED
    assert decision.metadata["rule"] == Rule.AUTHORIZATION_MISMATCH.value
    assert f"policy {short_id(policy.id)}" in decision.reason


TERMINAL = terminal_run(("git",))
TERMINAL_ARGS: dict[str, Any] = {"program": "git", "args": ["status"], "purpose": "la prova"}


def test_a_policy_fabricated_for_terminal_run_is_denied_with_the_reason_of_the_program() -> None:
    """The second defence of decision 2, re-aimed at what stays out (M13.14, ADR 0068; decision
    5): a standing grant for the ``HIGH`` that launches a program, with whole terms — denied with
    the sentence of the catalogue and of the birth."""
    fabricated = policy_for(
        TERMINAL, terms=PolicyTerms(limits=(), free=("args", "purpose", "cwd", "expect_exit"))
    )
    h = harness(registry=FakeCapabilityRegistry((TERMINAL,)))

    decision = decide(h, TERMINAL, TERMINAL_ARGS, fabricated)

    assert decision.outcome is PermissionOutcome.DENIED
    assert decision.metadata["rule"] == Rule.AUTHORIZATION_MISMATCH.value
    assert decision.reason == (
        f"authorization does not cover this call of terminal.run: authorization {fabricated.id} "
        "is a standing policy (§59): terminal.run launches a program the plan chooses: a program "
        "can read the Core's token and create a policy, and only you create one"
    )


def test_a_policy_with_another_capability_s_terms_does_not_cover_an_act(h: Harness) -> None:
    """The policy of ``browser.guided`` moved onto ``browser.act`` (the fabricated grant of
    M13.12): its terms are not the ones ``browser.act`` declares, so ``TERMS`` denies it."""
    fabricated = policy_for(GUIDED, scope=SITES).model_copy(update={"capability_id": ACT.id})

    decision = decide(h, ACT, ACT_ARGS, fabricated)

    assert decision.outcome is PermissionOutcome.DENIED
    assert decision.metadata["rule"] == Rule.AUTHORIZATION_MISMATCH.value
    assert decision.reason == (
        "authorization does not cover this call of browser.act: browser.act declares other terms "
        f"than those policy {short_id(fabricated.id)} was created under"
    )


def test_a_high_covered_by_its_own_policy_is_allowed_and_says_policy(h: Harness) -> None:
    """Criterion 1 of M13.14, (a): inside its boundaries ELA does it without asking — the row is
    «approval unless policy», the level stays ``HIGH``, the reason names the policy."""
    policy = policy_for(ACT, scope=("httpbin.org",))

    decision = decide(h, ACT, ACT_ARGS, policy)

    assert decision.outcome is PermissionOutcome.ALLOWED
    assert decision.risk.value == "HIGH"
    assert decision.metadata["rule"] == Rule.APPROVAL_UNLESS_POLICY.value
    assert decision.reason == f"browser.act is covered by policy {policy.id}"
    assert decision.authorization_id == policy.id


def test_a_high_with_terms_and_no_policy_asks(h: Harness) -> None:
    decision = h.guardian.decide(ACT, ACT_ARGS)

    assert decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert decision.metadata["rule"] == Rule.APPROVAL_UNLESS_POLICY.value


def test_a_spent_policy_of_a_high_asks_and_names_its_uses(h: Harness) -> None:
    policy = policy_for(ACT, scope=("httpbin.org",), max_uses=2)

    decision = h.guardian.decide(ACT, ACT_ARGS, authorization=policy, authorization_uses=2)

    assert decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert decision.reason == (
        f"browser.act requires an authorization: policy {short_id(policy.id)} was used 2 of its "
        "2 times"
    )


@pytest.mark.parametrize(
    ("spec", "arguments"),
    [
        (COMPLETE, {"input": "riassumi"}),
        (GUARDED_ECHO, {"message": "ciao"}),
        (ECHO, {"message": "ciao"}),
        (NOTE, {"path": "workspace/notes/a.md", "body": "x"}),
    ],
    ids=["model.complete", "a-guarded-safe", "a-safe", "a-low"],
)
def test_a_standing_grant_on_a_capability_that_declares_no_terms_never_covers(
    h: Harness, spec: Any, arguments: dict[str, Any]
) -> None:
    """Decision 17 of the review: the predicate holds for every grant without ``approval_id``."""
    standing = policy_for(TERMED).model_copy(update={"capability_id": spec.id, "scope": spec.scope})

    decision = decide(h, spec, arguments, standing)

    assert decision.outcome is PermissionOutcome.DENIED
    assert decision.metadata["rule"] == Rule.AUTHORIZATION_MISMATCH.value
    assert f"{spec.id} declares no terms for a policy" in decision.reason


def test_the_generic_capability_is_covered_like_browser_guided(h: Harness) -> None:
    decision = decide(h, TERMED, TERMED_ARGS, policy_for(TERMED))
    assert decision.outcome is PermissionOutcome.ALLOWED


def test_without_a_policy_a_session_asks(h: Harness) -> None:
    decision = h.guardian.decide(GUIDED, GUIDED_ARGS)

    assert decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert decision.reason == "browser.guided requires an authorization: none was given"


# ----------------------------------------------------------------------------------------
# The place of the step (M13.14, ADR 0068; decision 10, answer 21): read only to take away
# ----------------------------------------------------------------------------------------

CORE = DeviceId(UUID("00000000-0000-4000-8000-00000000c0e0"))
NODE = DeviceId(UUID("00000000-0000-4000-8000-00000000d0e0"))
WRITE = fs_write("ELA")
WRITE_ARGS: dict[str, Any] = {
    "path": "ELA/prova/uno/nota.md",
    "body": "una riga",
    "overwrite": False,
    "purpose": "la prova",
}


def guardian_of(*specs: CapabilitySpec, registry: Any = None) -> PermissionGuardian:
    """A Guardian that knows which device is the Core, as the composition builds it."""
    return PermissionGuardian(
        FakeCapabilityRegistry(specs) if registry is None else registry,
        FakeClock(),
        FakeIdGenerator(),
        FakeAuditLog(),
        core=CORE,
    )


def test_a_policy_of_fs_write_covers_a_step_on_the_core() -> None:
    policy = policy_for(WRITE, scope=("ELA/prova/uno",))

    decision = guardian_of(WRITE).decide(WRITE, WRITE_ARGS, authorization=policy, device_id=CORE)

    assert decision.outcome is PermissionOutcome.ALLOWED
    assert decision.reason == f"fs.write is covered by policy {policy.id}"


@pytest.mark.parametrize("device", [NODE, None], ids=["a-node", "not-said"])
def test_a_policy_of_the_core_handed_over_for_a_step_elsewhere_is_denied(
    device: DeviceId | None,
) -> None:
    """The executor never hands it over; handed over, it is an incoherence, and the reason is the
    ``ELSEWHERE`` gap's. ``device_id=None`` is «not said» — the fail-safe of §33 (answer 21)."""
    policy = policy_for(WRITE, scope=("ELA/prova/uno",))

    decision = guardian_of(WRITE).decide(WRITE, WRITE_ARGS, authorization=policy, device_id=device)

    assert decision.outcome is PermissionOutcome.DENIED
    assert decision.metadata["rule"] == Rule.AUTHORIZATION_MISMATCH.value
    assert decision.reason.endswith(
        f"policy {short_id(policy.id)} covers only a step that runs on the Core, and this step is "
        "not one"
    )


def test_a_guardian_that_knows_no_core_covers_no_step_with_a_policy_of_the_core() -> None:
    """``core=None`` — the default — means no device is the Core: nothing is covered."""
    policy = policy_for(WRITE, scope=("ELA/prova/uno",))
    guardian = PermissionGuardian(
        FakeCapabilityRegistry((WRITE,)), FakeClock(), FakeIdGenerator(), FakeAuditLog()
    )

    decision = guardian.decide(WRITE, WRITE_ARGS, authorization=policy, device_id=CORE)
    unsaid = guardian.decide(WRITE, WRITE_ARGS, authorization=policy)

    assert decision.outcome is PermissionOutcome.DENIED
    assert unsaid.outcome is PermissionOutcome.DENIED, "no Core and no place is not «the Core»"


def test_a_step_on_a_node_without_a_policy_asks_as_it_always_did() -> None:
    decision = guardian_of(WRITE).decide(WRITE, WRITE_ARGS, device_id=NODE)

    assert decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert decision.metadata["rule"] == Rule.APPROVAL_UNLESS_POLICY.value


async def test_authorize_hands_the_place_to_the_rule_and_the_audit() -> None:
    """``authorize`` passes ``device_id`` to ``decide`` — the one rule — and to the event."""
    policy = policy_for(WRITE, scope=("ELA/prova/uno",))
    audit = FakeAuditLog()
    guardian = PermissionGuardian(
        FakeCapabilityRegistry((WRITE,)), FakeClock(), FakeIdGenerator(), audit, core=CORE
    )

    on_the_core = await guardian.authorize(WRITE, WRITE_ARGS, authorization=policy, device_id=CORE)
    on_a_node = await guardian.authorize(WRITE, WRITE_ARGS, authorization=policy, device_id=NODE)

    assert on_the_core.outcome is PermissionOutcome.ALLOWED
    assert on_a_node.outcome is PermissionOutcome.DENIED
    events = await audit.read()
    assert [event.device_id for event in events] == [CORE, NODE]


def test_a_gesture_s_policy_covers_wherever_the_step_is() -> None:
    """``on_the_core`` is a term of ``fs.write`` only: a gesture's policy does not read the
    place."""
    policy = policy_for(ACT, scope=("httpbin.org",))

    for device in (CORE, NODE, None):
        decision = guardian_of(ACT).decide(ACT, ACT_ARGS, authorization=policy, device_id=device)
        assert decision.outcome is PermissionOutcome.ALLOWED, device


RANK = {
    PermissionOutcome.DENIED: 0,
    PermissionOutcome.REQUIRES_APPROVAL: 1,
    PermissionOutcome.ALLOWED: 2,
}


def _situations(spec: CapabilitySpec) -> dict[str, Authorization | None]:
    """Every grant a call can be decided with: none, a yes for it, a standing grant for it —
    built from its terms when it declares them, without any when it does not."""
    yes = born_of_a_yes(spec)
    standing = policy_for(spec) if spec.policy_terms is not None else grant(spec)
    return {"none": None, "yes": yes, "standing": standing}


def test_the_calls_of_the_property_are_every_capability_of_the_catalogue() -> None:
    assert set(CALLS) == {spec.id for spec in CATALOGUE.specs()}


def test_with_a_node_a_decision_is_never_more_permissive_than_with_the_core() -> None:
    """Answer 21 of the review of the SPEC of M13.14: on every capability of the catalogue, under
    every row, with no grant, a yes and a standing grant, the place can only take away — and it
    takes away exactly one thing: the policy of ``fs.write`` on a step that is not on the Core."""
    guardian = guardian_of(registry=CATALOGUE)
    differing = []
    for spec in CATALOGUE.specs():
        arguments = CALLS[spec.id]
        step = TaskStep(
            id=STEP_ID,
            created_at=NOW,
            goal="un passo",
            required_capabilities=(spec.id,),
            arguments=arguments,
            risk=spec.risk,
            expected_result="qualcosa",
            requires_authorization=True,
        )
        for name, authorization in _situations(spec).items():
            outcomes = {
                device: guardian.decide(
                    spec,
                    arguments,
                    task=TASK,
                    step=step,
                    authorization=authorization,
                    device_id=device,
                ).outcome
                for device in (CORE, NODE, None)
            }
            for elsewhere in (NODE, None):
                assert RANK[outcomes[elsewhere]] <= RANK[outcomes[CORE]], (spec.id, name)
            if outcomes[NODE] is not outcomes[CORE]:
                differing.append((spec.id, name))
    assert differing == [("fs.write", "standing")]


# ----------------------------------------------------------------------------------------
# A session is not a gesture (M13.14, ADR 0068; decision 7, proposal 10), for both pairs
# ----------------------------------------------------------------------------------------

PAIRS = [(BROWSER_GUIDED, BROWSER_ACT), (BROWSER_GUIDED_AS_YOU, BROWSER_ACT_AS_YOU)]
SESSION_STEP = StepId(UUID("00000000-0000-4000-8000-0000000005e5"))
SESSION_TASK = TaskId(UUID("00000000-0000-4000-8000-0000000005e6"))
CHILD = TASK.model_copy(update={"parent_id": SESSION_TASK})
WRITTEN_BY_THE_SESSION = PlanAuthor(by=PlanAuthorKind.SESSION, session=SESSION_STEP, model="m")


def _born(capability: str, scope: tuple[str, ...], limits: dict[str, str]) -> Authorization:
    return authorization_from_policy(
        PolicyRequest(CapabilityId(capability), scope, limits, 1),
        catalogue=CATALOGUE,
        granted_by="local",
        now=FakeClock().now(),
        authorization_id=AuthorizationId(FakeIdGenerator().new_uuid()),
    )


def _gesture(
    gesture: str,
    *,
    authorization: Authorization | None = None,
    session: SessionCover | None = None,
) -> Any:
    spec = CATALOGUE.get(CapabilityId(gesture))
    step = TaskStep(
        id=STEP_ID,
        created_at=NOW,
        goal="un gesto della sessione",
        required_capabilities=(spec.id,),
        arguments=CALLS[gesture],
        risk=spec.risk,
        expected_result="la pagina",
        requires_authorization=True,
    )
    return guardian_of(registry=CATALOGUE).decide(
        spec,
        CALLS[gesture],
        task=CHILD,
        step=step,
        authorization=authorization,
        author=WRITTEN_BY_THE_SESSION,
        session=session,
        device_id=CORE,
    )


SESSION_LIMITS = {"max_cost_usd": "1.10", "looks": "10", "seconds": "600"}


@pytest.mark.parametrize(("session", "gesture"), PAIRS)
def test_without_a_policy_of_the_gesture_the_gesture_asks(session: str, gesture: str) -> None:
    """A session covered by its own policy covers no gesture: the gesture asks."""
    decision = _gesture(gesture)

    assert decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert decision.metadata["rule"] == Rule.APPROVAL_UNLESS_POLICY.value


@pytest.mark.parametrize(("session", "gesture"), PAIRS)
def test_a_policy_of_the_gesture_covers_the_gesture_of_a_session(
    session: str, gesture: str
) -> None:
    policy = _born(gesture, (CALLS[gesture]["site"],), {})

    decision = _gesture(gesture, authorization=policy)

    assert decision.outcome is PermissionOutcome.ALLOWED
    assert decision.reason == f"{gesture} is covered by policy {policy.id}"


@pytest.mark.parametrize(("session", "gesture"), PAIRS)
def test_a_policy_of_the_session_handed_over_for_a_gesture_is_denied(
    session: str, gesture: str
) -> None:
    policy = _born(session, (CALLS[gesture]["site"],), SESSION_LIMITS)

    decision = _gesture(gesture, authorization=policy)

    assert decision.outcome is PermissionOutcome.DENIED
    assert decision.metadata["rule"] == Rule.AUTHORIZATION_MISMATCH.value
    assert f"authorization {policy.id} is for {session}" in decision.reason


@pytest.mark.parametrize(("session", "gesture"), PAIRS)
def test_the_cover_of_a_session_handed_over_for_a_gesture_is_denied(
    session: str, gesture: str
) -> None:
    cover = SessionCover(
        session=SESSION_STEP,
        task_id=SESSION_TASK,
        capability_id=CapabilityId(session),
        sites=(CALLS[gesture]["site"],),
    )

    decision = _gesture(gesture, session=cover)

    assert decision.outcome is PermissionOutcome.DENIED
    assert decision.metadata["rule"] == Rule.SESSION_MISMATCH.value
