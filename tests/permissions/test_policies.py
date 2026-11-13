"""The policies of §59 in ``ela.permissions`` (M13.12, ADR 0062; M13.14, ADR 0068): the one
predicate, the birth, the revocation as a value, and the sentences the question and the preview
say. Pure, so exhausted here.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from ela.domain import Authorization, AuthorizationId, CapabilityId, PolicyTerms, PolicyWords
from ela.permissions import (
    GAPS,
    MAX_DAYS,
    MIN_DAYS,
    POLICY_CHECKS,
    POLICY_PROSPECT,
    SHORT_ID,
    UNCOVERED,
    UNUSABLE,
    WHY_DAYS,
    WHY_MAX,
    CapabilityRegistry,
    Gap,
    PolicyCheck,
    PolicyRefusedError,
    PolicyRequest,
    PolicyState,
    authorization_from_policy,
    browser_guided_as_you,
    browser_login,
    fs_read,
    never_covered,
    production_catalogue,
    prospect_arguments,
    scope_is_a_list,
    short_id,
    shortfall,
    state_of,
    terminal_run,
    why_lines,
)
from ela.testing.fakes import FakeCapabilityRegistry
from tests.domain.examples import NOW
from tests.permissions.policy_support import (
    GUIDED,
    GUIDED_ARGS,
    GUIDED_LIMITS,
    MODEL,
    SITES,
    TERMED,
    TERMED_ARGS,
    policy_for,
    revoked,
)
from tests.permissions.support import CRITICAL, ECHO, HIGH

POLICY = policy_for(GUIDED, scope=("www.youtube.com", "httpbin.org"), limits=GUIDED_LIMITS)


def gap(policy: Any = POLICY, arguments: dict[str, Any] | None = None, **kwargs: Any) -> Any:
    found = shortfall(
        policy, GUIDED, GUIDED_ARGS if arguments is None else arguments, now=NOW, **kwargs
    )
    return None if found is None else found.gap


# ----------------------------------------------------------------------------------------
# The predicate
# ----------------------------------------------------------------------------------------


def test_the_order_of_the_gaps_is_the_one_of_decision_4() -> None:
    """With the two gaps of M13.14 (ADR 0068), each in its slice: ``EXHAUSTED`` after the expiry,
    ``ELSEWHERE`` after the terms."""
    assert GAPS == (
        Gap.REVOKED,
        Gap.EXPIRED,
        Gap.EXHAUSTED,
        Gap.TERMS,
        Gap.ELSEWHERE,
        Gap.SITE,
        Gap.LIMIT,
        Gap.ARGUMENT,
    )
    assert UNUSABLE == (Gap.REVOKED, Gap.EXPIRED, Gap.EXHAUSTED)
    assert UNCOVERED == (Gap.TERMS, Gap.ELSEWHERE, Gap.SITE, Gap.LIMIT, Gap.ARGUMENT)
    assert set(UNUSABLE) | set(UNCOVERED) == set(GAPS)
    assert not set(UNUSABLE) & set(UNCOVERED)


def test_a_session_inside_the_policy_is_covered() -> None:
    assert shortfall(POLICY, GUIDED, GUIDED_ARGS, now=NOW) is None


def test_a_revoked_policy_does_not_cover_and_says_when() -> None:
    found = shortfall(revoked(POLICY, NOW), GUIDED, GUIDED_ARGS, now=NOW)

    assert found is not None and found.gap is Gap.REVOKED
    assert found.reason == f"policy {short_id(POLICY.id)} was revoked on {NOW.date().isoformat()}"


def test_expiry_is_a_closed_bound() -> None:
    at_now = POLICY.model_copy(update={"expires_at": NOW})
    just_after = POLICY.model_copy(update={"expires_at": NOW + timedelta(microseconds=1)})

    assert gap(at_now) is Gap.EXPIRED
    assert gap(just_after) is None
    found = shortfall(at_now, GUIDED, GUIDED_ARGS, now=NOW)
    assert found is not None
    assert found.reason == f"policy {short_id(POLICY.id)} expired on {NOW.date().isoformat()}"


def test_a_capability_without_terms_is_never_covered_by_a_policy() -> None:
    """Decision 17 of the review: a standing grant on a capability that declares nothing."""
    undeclared = POLICY.model_copy(update={"capability_id": ECHO.id})
    found = shortfall(undeclared, ECHO, {"message": "ciao"}, now=NOW)

    assert found is not None and found.gap is Gap.TERMS
    assert "declares no terms" in found.reason


@pytest.mark.parametrize(
    "terms",
    [
        PolicyTerms(
            limits=("max_cost_usd", "looks"),
            uncovered=("task_type",),
            free=("goal",),
            route="browsing",
            model=MODEL,
        ),
        PolicyTerms(
            limits=("max_cost_usd", "looks", "seconds"),
            free=("goal", "task_type"),
            route="browsing",
            model=MODEL,
        ),
        PolicyTerms(
            limits=("max_cost_usd", "looks", "seconds"),
            uncovered=("task_type",),
            free=("goal",),
            route="browsing",
            model="claude-sonnet-5-5",
        ),
    ],
    ids=["a-limit-added-since", "task-type-uncovered-since", "another-model-since"],
)
def test_terms_changed_since_the_policy_was_born_stop_it_covering(terms: PolicyTerms) -> None:
    """Decisions 4 and 16: a limit added, an argument no longer free, a model changed."""
    old = policy_for(
        GUIDED, terms=terms, limits={name: "999" for name in terms.limits}, scope=SITES
    )

    found = shortfall(old, GUIDED, GUIDED_ARGS, now=NOW)

    assert found is not None and found.gap is Gap.TERMS
    assert found.reason == (
        f"browser.guided declares other terms than those policy {short_id(old.id)} was created "
        "under"
    )


def test_a_policy_without_bounds_or_with_limits_its_terms_do_not_name_does_not_cover() -> None:
    bare = POLICY.model_copy(update={"bounds": None})
    assert POLICY.bounds is not None
    lopsided = POLICY.model_copy(
        update={"bounds": POLICY.bounds.model_copy(update={"limits": {"max_cost_usd": "1"}})}
    )

    assert gap(bare) is Gap.TERMS
    assert gap(lopsided) is Gap.TERMS


def test_a_site_outside_the_policy_is_named_by_its_argument_never_by_its_value() -> None:
    found = shortfall(POLICY, GUIDED, {**GUIDED_ARGS, "sites": ["example.com"]}, now=NOW)

    assert found is not None and found.gap is Gap.SITE
    assert found.reason == f"a value of sites is not among those of policy {short_id(POLICY.id)}"
    assert "example.com" not in found.reason


def test_every_site_of_the_session_must_be_in_the_policy() -> None:
    assert gap(arguments={**GUIDED_ARGS, "sites": ["www.youtube.com", "httpbin.org"]}) is None
    assert gap(arguments={**GUIDED_ARGS, "sites": ["www.youtube.com", "example.com"]}) is Gap.SITE


@pytest.mark.parametrize(
    ("name", "value", "covered"),
    [
        ("max_cost_usd", "1.1", True),
        ("max_cost_usd", "1.10", True),
        ("max_cost_usd", "1.100001", False),
        ("max_cost_usd", "2.00", False),
        ("looks", 10, True),
        ("looks", 11, False),
        ("seconds", 300, True),
        ("seconds", 301, False),
    ],
)
def test_a_limit_is_compared_as_a_number(name: str, value: object, covered: bool) -> None:
    """Decision 3b: ``Decimal``, so ``1.1`` and ``1.10`` are the same limit."""
    assert (gap(arguments={**GUIDED_ARGS, name: value}) is None) is covered


def test_the_reason_of_a_limit_says_the_two_numbers_and_never_a_site() -> None:
    found = shortfall(POLICY, GUIDED, {**GUIDED_ARGS, "max_cost_usd": "2.00"}, now=NOW)

    assert found is not None and found.gap is Gap.LIMIT
    assert found.reason == f"max_cost_usd 2.00 is above the 1.10 of policy {short_id(POLICY.id)}"


def test_the_limits_are_judged_one_at_a_time_in_the_order_of_the_declaration() -> None:
    found = shortfall(
        POLICY, GUIDED, {**GUIDED_ARGS, "looks": 30, "seconds": 1800, "max_cost_usd": "5"}, now=NOW
    )
    assert found is not None
    assert found.reason.startswith("max_cost_usd 5 is above")


@pytest.mark.parametrize("value", ["NaN", "Infinity", "uno", "", True])
def test_a_value_that_is_not_a_finite_number_does_not_cover(value: object) -> None:
    """Decision 10: never an exception, never a cover — the step asks."""
    in_the_call = shortfall(POLICY, GUIDED, {**GUIDED_ARGS, "max_cost_usd": value}, now=NOW)
    assert POLICY.bounds is not None
    broken = POLICY.model_copy(
        update={
            "bounds": POLICY.bounds.model_copy(
                update={"limits": {**GUIDED_LIMITS, "max_cost_usd": value}}
            )
        }
    )
    in_the_policy = shortfall(broken, GUIDED, GUIDED_ARGS, now=NOW)

    assert in_the_call is not None and in_the_call.gap is Gap.LIMIT
    assert in_the_call.reason == "max_cost_usd of this call is not a number"
    assert in_the_policy is not None and in_the_policy.gap is Gap.LIMIT
    assert in_the_policy.reason == f"max_cost_usd of policy {short_id(POLICY.id)} is not a number"


def test_an_uncovered_argument_asks() -> None:
    found = shortfall(POLICY, GUIDED, {**GUIDED_ARGS, "task_type": "browsing"}, now=NOW)

    assert found is not None and found.gap is Gap.ARGUMENT
    assert found.reason == (
        f"task_type is never covered by a policy: policy {short_id(POLICY.id)} does not cover "
        "this call"
    )


def test_an_argument_the_terms_do_not_classify_asks_the_world_is_closed() -> None:
    """Decision B1 of the critical re-read: an argument nobody classified is not covered."""
    found = shortfall(POLICY, GUIDED, {**GUIDED_ARGS, "profile": "work"}, now=NOW)

    assert found is not None and found.gap is Gap.ARGUMENT
    assert found.reason == f"profile is not among the terms of policy {short_id(POLICY.id)}"


def test_the_goal_is_not_looked_at() -> None:
    assert gap(arguments={**GUIDED_ARGS, "goal": "qualunque altra cosa"}) is None


def test_the_first_reason_wins_in_the_order_of_the_tuple() -> None:
    everything_wrong = revoked(POLICY.model_copy(update={"expires_at": NOW}), NOW)
    arguments = {**GUIDED_ARGS, "sites": ["example.com"], "task_type": "x", "looks": 30}

    assert gap(everything_wrong, arguments) is Gap.REVOKED
    assert gap(everything_wrong, arguments, gaps=UNCOVERED) is Gap.SITE
    assert gap(everything_wrong, arguments, gaps=UNUSABLE) is Gap.REVOKED


def test_the_generic_capability_of_the_tests_is_covered_the_same_way() -> None:
    termed = policy_for(TERMED)

    assert shortfall(termed, TERMED, TERMED_ARGS, now=NOW) is None
    assert shortfall(termed, TERMED, {**TERMED_ARGS, "count": 30}, now=NOW) is None
    narrow = policy_for(TERMED, limits={"budget": "1", "count": "2"})
    found = shortfall(narrow, TERMED, TERMED_ARGS, now=NOW)
    assert found is not None and found.reason.startswith("budget 1.10 is above the 1 of policy")


# ----------------------------------------------------------------------------------------
# Short id, state
# ----------------------------------------------------------------------------------------


def test_the_short_id_is_the_first_eight_characters() -> None:
    assert SHORT_ID == 8
    assert short_id(AuthorizationId(POLICY.id)) == str(POLICY.id)[:8]


def test_the_state_of_a_policy() -> None:
    assert state_of(POLICY, NOW, uses=0) is PolicyState.LIVE
    assert state_of(revoked(POLICY, NOW), NOW, uses=0) is PolicyState.REVOKED
    assert (
        state_of(POLICY.model_copy(update={"expires_at": NOW}), NOW, uses=0) is PolicyState.EXPIRED
    )


def test_a_policy_whose_uses_are_spent_is_exhausted_and_not_live() -> None:
    """Answer 30 of the review of the SPEC of M13.14: a policy that can cover nothing any more is
    not ``LIVE`` — a state of its own, derived, among the ended ones."""
    three = POLICY.model_copy(update={"max_uses": 3})

    assert state_of(three, NOW, uses=2) is PolicyState.LIVE
    assert state_of(three, NOW, uses=3) is PolicyState.EXHAUSTED
    assert state_of(three, NOW, uses=4) is PolicyState.EXHAUSTED
    assert state_of(POLICY, NOW, uses=10**6) is PolicyState.LIVE, "no limit never exhausts"
    # In the order of the gaps: revoked, then expired, then exhausted.
    assert state_of(revoked(three, NOW), NOW, uses=3) is PolicyState.REVOKED
    assert (
        state_of(three.model_copy(update={"expires_at": NOW}), NOW, uses=3) is PolicyState.EXPIRED
    )


# ----------------------------------------------------------------------------------------
# The line «why I ask» (decision 8)
# ----------------------------------------------------------------------------------------


def why(
    policies: tuple[Authorization, ...],
    arguments: dict[str, Any] = GUIDED_ARGS,
    *,
    uses: int = 0,
    on_the_core: bool | None = True,
) -> tuple[str, ...]:
    """The line of a call of ``browser.guided``, every policy with ``uses`` uses."""
    return why_lines(
        [(one, uses) for one in policies], GUIDED, arguments, now=NOW, on_the_core=on_the_core
    )


def test_with_no_policy_the_line_says_so() -> None:
    assert why(()) == ("no policy of yours for browser.guided",)


def test_the_line_names_at_most_three_the_most_recent_first() -> None:
    policies = tuple(
        policy_for(
            GUIDED,
            created_at=NOW - timedelta(hours=10 - n),
            limits={**GUIDED_LIMITS, "looks": "1"},
            tail=910 + n,
        )
        for n in range(4)
    )

    lines = why(policies)

    assert WHY_MAX == 3
    assert len(lines) == 3
    assert [line.rsplit(" ", 1)[-1] for line in lines] == [
        short_id(one.id) for one in reversed(policies[1:])
    ]


def test_a_policy_ended_more_than_thirty_days_ago_is_not_named() -> None:
    assert WHY_DAYS == 30
    old = policy_for(
        GUIDED, created_at=NOW - timedelta(days=40), expires_at=NOW - timedelta(days=31)
    )
    recent = policy_for(
        GUIDED, created_at=NOW - timedelta(days=40), expires_at=NOW - timedelta(days=29), tail=901
    )
    revoked_long_ago = revoked(
        policy_for(
            GUIDED,
            created_at=NOW - timedelta(days=40),
            expires_at=NOW + timedelta(days=40),
            tail=902,
        ),
        NOW - timedelta(days=31),
    )

    lines = why((old, recent, revoked_long_ago))

    assert lines == (
        f"policy {short_id(recent.id)} expired on {recent.expires_at.date().isoformat()}",
    )  # type: ignore[union-attr]


def test_a_policy_born_after_the_decision_is_not_named() -> None:
    later = policy_for(GUIDED, created_at=NOW + timedelta(seconds=1))
    assert why((later,)) == ("no policy of yours for browser.guided",)


def test_a_policy_that_covers_says_the_step_asks_again_for_its_own_yes() -> None:
    lines = why((POLICY,))

    assert lines == (
        f"policy {short_id(POLICY.id)} covers this call: this step asks again for the yes it was "
        "given",
    )


def test_no_sentence_of_the_line_names_a_site() -> None:
    policies = (
        POLICY,
        revoked(policy_for(GUIDED, tail=920), NOW),
        policy_for(GUIDED, scope=("example.com",), tail=921),
    )
    for line in why(policies, {**GUIDED_ARGS, "sites": ["httpbin.org"]}):
        for site in SITES:
            assert site not in line, line


# ----------------------------------------------------------------------------------------
# What «partirebbe» asks the tool, and what the preview says the policy never covers
# ----------------------------------------------------------------------------------------


def test_the_prospect_is_a_call_at_the_limits_on_the_sites_with_ela_s_sentence() -> None:
    assert prospect_arguments(POLICY, GUIDED) == {
        "goal": POLICY_PROSPECT,
        "sites": ["www.youtube.com", "httpbin.org"],
        "max_cost_usd": "1.10",
        "looks": 10,
        "seconds": 300,
    }


def test_an_optional_free_argument_is_left_out_of_the_prospect() -> None:
    """Only a **required** free argument needs ELA's sentence: an optional one, the tool does
    without, as a step that does not write it."""
    schema = dict(TERMED.input_schema)
    schema["required"] = ["places", "budget", "count"]
    optional = TERMED.model_copy(update={"input_schema": schema})

    arguments = prospect_arguments(policy_for(optional), optional)

    assert "text" not in arguments
    assert set(arguments) == {"places", "budget", "count"}


NOT_TAKEN_BACK = "what has left is not taken back: a revocation stops only what comes after"


def test_never_covered_names_the_rows_that_ask_at_every_use_and_the_terms() -> None:
    """Since M13.14 (ADR 0068) the rows that ask at every use are the ``HIGH`` that declare no
    terms — ``fs.write`` and the two gestures left the list —, a guided session's gestures need a
    policy of their own — ``browser.guided`` too, whose sessions make ``browser.act`` gestures, and
    not only the session that declares ``covers`` —, and the last line says what no revocation
    calls back."""
    catalogue = production_catalogue(sites=SITES, guided_model=MODEL)

    said = never_covered(GUIDED, catalogue.specs())

    assert said == (
        "every call of a capability that asks at every use asks every time: "
        "browser.download, browser.download_as_you, browser.login, browser.upload, "
        "browser.upload_as_you, terminal.run",
        "a call above a limit, or outside the scope, asks",
        "a call with task_type asks",
        "a gesture of its sessions asks, unless a policy of the gesture's own capability covers it",
        NOT_TAKEN_BACK,
    )


def test_never_covered_says_a_node_asks_for_a_policy_of_the_core() -> None:
    catalogue = production_catalogue(sites=SITES, fs_scope="ELA", guided_model=MODEL)

    said = never_covered(catalogue.get(CapabilityId("fs.write")), catalogue.specs())

    assert said[-2:] == (
        "a step that runs on a node asks: only a step on the Core is covered",
        NOT_TAKEN_BACK,
    )


def test_never_covered_says_a_gesture_of_a_session_needs_a_policy_of_its_own() -> None:
    """Proposal 10: a policy of a session covers its reads and never a gesture."""
    catalogue = production_catalogue(sites=SITES, guided_model=MODEL)

    said = never_covered(browser_guided_as_you(SITES, model=MODEL), catalogue.specs())

    assert said[-2:] == (
        "a gesture of its sessions asks, unless a policy of the gesture's own capability covers it",
        NOT_TAKEN_BACK,
    )


# ----------------------------------------------------------------------------------------
# The birth (decision 6)
# ----------------------------------------------------------------------------------------

CATALOGUE = CapabilityRegistry((*production_catalogue(sites=SITES, guided_model=MODEL).specs(),))
REQUEST = PolicyRequest(
    capability_id=GUIDED.id,
    scope=("www.youtube.com", "httpbin.org"),
    limits=GUIDED_LIMITS,
    days=1,
)


def born(request: PolicyRequest = REQUEST, catalogue: Any = CATALOGUE) -> Any:
    return authorization_from_policy(
        request,
        catalogue=catalogue,
        granted_by="local",
        now=NOW,
        authorization_id=AuthorizationId(POLICY.id),
    )


def refused(request: PolicyRequest, catalogue: Any = CATALOGUE) -> PolicyRefusedError:
    with pytest.raises(PolicyRefusedError) as caught:
        born(request, catalogue)
    return caught.value


def test_the_checks_run_in_the_order_of_decision_6() -> None:
    assert POLICY_CHECKS == (
        PolicyCheck.CATALOGUE,
        PolicyCheck.ADMITS,
        PolicyCheck.SCOPE,
        PolicyCheck.LIMITS,
        PolicyCheck.USES,
        PolicyCheck.DAYS,
    )
    assert set(POLICY_CHECKS) == set(PolicyCheck)
    assert (MIN_DAYS, MAX_DAYS) == (1, 90)


def test_a_policy_is_born_with_its_bounds_its_terms_and_an_end() -> None:
    grant = born()

    assert grant.capability_id == GUIDED.id
    assert grant.scope == ("www.youtube.com", "httpbin.org")
    assert grant.approval_id is None and grant.task_id is None and grant.step_id is None
    assert grant.max_uses is None
    assert grant.expires_at == NOW + timedelta(days=1)
    assert grant.granted_by == "local"
    assert grant.bounds is not None
    assert grant.bounds.terms == GUIDED.policy_terms
    assert dict(grant.bounds.limits) == GUIDED_LIMITS
    assert grant.metadata["origin"] == "policy"


def test_a_capability_outside_the_catalogue_is_refused() -> None:
    found = refused(PolicyRequest(CapabilityId("browser.nowhere"), ("example.com",), {}, 1))
    assert found.check is PolicyCheck.CATALOGUE


@pytest.mark.parametrize(
    ("spec", "reason"),
    [
        (
            browser_login(SITES),
            "browser.login is HIGH and declares no terms: only a grant born from an approval "
            "covers it",
        ),
        (
            terminal_run(("git",)),
            "terminal.run launches a program the plan chooses: a program can read the Core's "
            "token and create a policy, and only you create one",
        ),
        (ECHO, "core.echo does not ask: it needs no policy"),
        (fs_read("ELA"), "no milestone has said what a policy must bound for fs.read"),
    ],
    ids=["browser.login", "terminal.run", "core.echo", "fs.read"],
)
def test_admits_has_its_distinct_reasons(spec: Any, reason: str) -> None:
    """M13.14 (ADR 0068): a ``HIGH`` without terms, the program, a row that does not ask, a
    ``MEDIUM`` that declares nothing — ``browser.act`` and ``fs.write`` left the refusals, and are
    born below."""
    catalogue = CapabilityRegistry((spec,))
    found = refused(PolicyRequest(spec.id, ("ELA",), {}, 1), catalogue)

    assert found.check is PolicyCheck.ADMITS
    assert found.reason == reason


CRITICAL_WITH_TERMS = TERMED.model_copy(
    update={
        "id": CapabilityId("finance.pay_termed"),
        "risk": CRITICAL.risk,
        "policy_words": PolicyWords(does="pays", goes="away"),
    }
)
"""A ``CRITICAL`` carrying a whole declaration, in a registry that admits it: the mutant natural to
``row_of`` — a condition ``risk >= HIGH`` — is what it is for (proposal 15)."""


def test_a_critical_capability_with_terms_is_refused_at_the_birth() -> None:
    """Criterion 2 of M13.14: a policy for a ``CRITICAL`` is not born, terms or not."""
    catalogue = FakeCapabilityRegistry((CRITICAL_WITH_TERMS,))
    found = refused(
        PolicyRequest(CRITICAL_WITH_TERMS.id, ("alpha.example",), {"budget": "1", "count": "1"}, 1),
        catalogue,
    )

    assert found.check is PolicyCheck.ADMITS
    assert found.reason == "finance.pay_termed is CRITICAL: its row denies, and no policy covers it"


# ----------------------------------------------------------------------------------------
# The policies of a HIGH (M13.14, ADR 0068): fs.write, browser.act, browser.act_as_you
# ----------------------------------------------------------------------------------------

HIGH_CATALOGUE = production_catalogue(sites=SITES, fs_scope="ELA", guided_model=MODEL)
WRITE = HIGH_CATALOGUE.get(CapabilityId("fs.write"))
ACT = HIGH_CATALOGUE.get(CapabilityId("browser.act"))
WRITE_ARGS: dict[str, Any] = {
    "path": "ELA/prova/uno/nota.md",
    "body": "una riga",
    "overwrite": False,
    "purpose": "la prova",
}


@pytest.mark.parametrize(
    ("capability", "scope"),
    [("fs.write", ("ELA/prova/uno", "ELA/prova/due")), ("browser.act", ("httpbin.org",))],
)
def test_a_policy_of_a_high_is_born_with_no_limit_and_its_terms(
    capability: str, scope: tuple[str, ...]
) -> None:
    grant = born(PolicyRequest(CapabilityId(capability), scope, {}, 2), HIGH_CATALOGUE)
    spec = HIGH_CATALOGUE.get(CapabilityId(capability))

    assert grant.capability_id == capability and grant.scope == scope
    assert grant.bounds is not None and grant.bounds.terms == spec.policy_terms
    assert dict(grant.bounds.limits) == {}
    assert grant.max_uses is None and grant.expires_at == NOW + timedelta(days=2)


def test_the_scope_of_a_high_is_the_one_value_of_each_call() -> None:
    assert scope_is_a_list(GUIDED) is True
    assert scope_is_a_list(WRITE) is False and scope_is_a_list(ACT) is False


def test_a_policy_of_fs_write_covers_a_write_in_its_folders_on_the_core() -> None:
    policy = born(PolicyRequest(WRITE.id, ("ELA/prova/uno",), {}, 1), HIGH_CATALOGUE)

    assert shortfall(policy, WRITE, WRITE_ARGS, now=NOW, on_the_core=True) is None
    outside = {**WRITE_ARGS, "path": "ELA/prova/tre/nota.md"}
    found = shortfall(policy, WRITE, outside, now=NOW, on_the_core=True)
    assert found is not None and found.gap is Gap.SITE
    assert found.reason == f"a value of path is not among those of policy {short_id(policy.id)}"


@pytest.mark.parametrize("where", [False, None], ids=["a-node", "not-said"])
def test_a_policy_of_the_core_does_not_cover_a_step_elsewhere(where: bool | None) -> None:
    """``ELSEWHERE`` (decision 10): on a node, or where the caller did not say — the fail-safe."""
    policy = born(PolicyRequest(WRITE.id, ("ELA/prova/uno",), {}, 1), HIGH_CATALOGUE)

    found = shortfall(policy, WRITE, WRITE_ARGS, now=NOW, on_the_core=where)

    assert found is not None and found.gap is Gap.ELSEWHERE
    assert found.reason == (
        f"policy {short_id(policy.id)} covers only a step that runs on the Core, and this step is "
        "not one"
    )
    assert gap_of(policy, WRITE, WRITE_ARGS, where, UNCOVERED) is Gap.ELSEWHERE
    assert gap_of(policy, WRITE, WRITE_ARGS, where, UNUSABLE) is None


def test_a_policy_not_of_the_core_covers_a_step_wherever_it_is() -> None:
    """A gesture's terms do not say ``on_the_core``: the place is not read for it."""
    policy = born(PolicyRequest(ACT.id, ("httpbin.org",), {}, 1), HIGH_CATALOGUE)
    act = {
        "site": "httpbin.org",
        "path": "/forms/post",
        "fill": [["#a", "b"]],
        "click": "#go",
        "expect_text": "ok",
        "purpose": "la prova",
    }

    for where in (True, False, None):
        assert shortfall(policy, ACT, act, now=NOW, on_the_core=where) is None


def gap_of(
    policy: Authorization,
    spec: Any,
    arguments: dict[str, Any],
    where: bool | None,
    gaps: Any,
    uses: int = 0,
) -> Gap | None:
    found = shortfall(policy, spec, arguments, now=NOW, uses=uses, on_the_core=where, gaps=gaps)
    return None if found is None else found.gap


def test_a_policy_whose_uses_are_spent_is_exhausted_usable_no() -> None:
    """``EXHAUSTED``: in the slice that says *usable*, never in the one that says *covers* — the
    step asks, it is never denied — and its sentence names the policy and the numbers."""
    policy = POLICY.model_copy(update={"max_uses": 5})

    assert gap_of(policy, GUIDED, GUIDED_ARGS, True, UNUSABLE, uses=4) is None
    found = shortfall(policy, GUIDED, GUIDED_ARGS, now=NOW, uses=5, gaps=UNUSABLE)
    assert found is not None and found.gap is Gap.EXHAUSTED
    assert found.reason == f"policy {short_id(policy.id)} was used 5 of its 5 times"
    assert gap_of(policy, GUIDED, GUIDED_ARGS, True, UNCOVERED, uses=5) is None
    assert gap_of(POLICY, GUIDED, GUIDED_ARGS, True, GAPS, uses=10**6) is None


def test_each_new_gap_is_first_when_more_than_one_is_found_in_its_order() -> None:
    """``EXPIRED`` before ``EXHAUSTED``, ``EXHAUSTED`` before ``TERMS``; ``TERMS`` before
    ``ELSEWHERE``, ``ELSEWHERE`` before ``SITE``."""
    write = born(PolicyRequest(WRITE.id, ("ELA/prova/uno",), {}, 1), HIGH_CATALOGUE).model_copy(
        update={"max_uses": 1}
    )
    outside = {**WRITE_ARGS, "path": "ELA/prova/tre/nota.md"}
    ended = write.model_copy(update={"expires_at": NOW})

    assert gap_of(ended, WRITE, outside, False, GAPS, uses=1) is Gap.EXPIRED
    assert gap_of(write, WRITE, outside, False, GAPS, uses=1) is Gap.EXHAUSTED
    assert gap_of(write, WRITE, outside, False, GAPS, uses=0) is Gap.ELSEWHERE
    other_terms = WRITE.model_copy(
        update={"policy_terms": PolicyTerms(limits=(), free=("body", "overwrite", "purpose"))}
    )
    assert gap_of(write, other_terms, outside, False, GAPS, uses=0) is Gap.TERMS
    assert gap_of(write, WRITE, outside, True, GAPS, uses=0) is Gap.SITE
    terms_exhausted = gap_of(write, other_terms, outside, False, GAPS, uses=1)
    assert terms_exhausted is Gap.EXHAUSTED


def test_the_line_says_a_policy_spent_its_uses_and_one_of_the_core() -> None:
    """The line «why I ask» receives every policy with its uses, and the step with its place
    (M13.14): the same predicate."""
    spent = POLICY.model_copy(update={"max_uses": 2})
    assert why((spent,), uses=2) == (f"policy {short_id(POLICY.id)} was used 2 of its 2 times",)
    write = born(PolicyRequest(WRITE.id, ("ELA/prova/uno",), {}, 1), HIGH_CATALOGUE)
    on_a_node = why_lines([(write, 0)], WRITE, WRITE_ARGS, now=NOW, on_the_core=False)
    assert on_a_node == (
        f"policy {short_id(write.id)} covers only a step that runs on the Core, and this step is "
        "not one",
    )


def test_an_old_session_policy_without_the_new_terms_still_covers() -> None:
    """Criterion 21: a policy of M13.9 or M13.12, saved without ``on_the_core``, reads as the
    declaration of today — its terms default to the same — and covers what it covered, wherever."""
    stored = POLICY.model_dump(mode="json")
    assert stored["bounds"] is not None
    del stored["bounds"]["terms"]["on_the_core"]
    old = Authorization.model_validate(stored)

    for where in (True, False, None):
        assert shortfall(old, GUIDED, GUIDED_ARGS, now=NOW, on_the_core=where) is None


# ----------------------------------------------------------------------------------------
# The uses (M13.14, ADR 0068; decision 8, answer 23)
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "uses", [0, -1, True, "3", 1.0], ids=["zero", "negative", "true", "text", "float"]
)
def test_the_uses_are_none_or_a_whole_number_from_one_and_fail_there(uses: Any) -> None:
    """Every other check passes: the refusal is ``USES``'s and not an earlier one's."""
    found = refused(PolicyRequest(GUIDED.id, ("www.youtube.com",), GUIDED_LIMITS, 1, uses=uses))

    assert found.check is PolicyCheck.USES
    assert found.reason == (
        f"the uses of a policy are none, for no limit, or a whole number from 1 up, not {uses!r}"
    )


def test_uses_come_after_the_limits_and_before_the_days() -> None:
    assert (
        refused(PolicyRequest(GUIDED.id, ("www.youtube.com",), {}, 0, uses=0)).check
        is PolicyCheck.LIMITS
    )
    assert (
        refused(PolicyRequest(GUIDED.id, ("www.youtube.com",), GUIDED_LIMITS, 0, uses=0)).check
        is PolicyCheck.USES
    )


@pytest.mark.parametrize("uses", [1, 7, 10**6])
def test_a_policy_with_uses_is_born_with_them_as_its_max_uses(uses: int) -> None:
    """Answer 23: the field is one, and a ``MEDIUM`` policy — a session's — has it too: no
    maximum, the user's boundary."""
    grant = born(PolicyRequest(GUIDED.id, ("www.youtube.com",), GUIDED_LIMITS, 1, uses=uses))

    assert grant.max_uses == uses


def test_a_medium_policy_with_uses_covers_until_they_are_spent() -> None:
    """Answer 23: the field has a producer on a ``MEDIUM`` too, and the predicate reads it."""
    grant = born(PolicyRequest(GUIDED.id, ("www.youtube.com",), GUIDED_LIMITS, 1, uses=2))

    assert shortfall(grant, GUIDED, GUIDED_ARGS, now=NOW, uses=1) is None
    found = shortfall(grant, GUIDED, GUIDED_ARGS, now=NOW, uses=2)
    assert found is not None and found.gap is Gap.EXHAUSTED


def test_a_critical_capability_never_reaches_the_catalogue() -> None:
    """The ``CRITICAL`` half of the first reason is the catalogue's cap: it never gets here."""
    from ela.permissions import RiskNotAllowedError

    with pytest.raises(RiskNotAllowedError):
        CapabilityRegistry((CRITICAL,))
    assert HIGH.risk.value == "HIGH"


@pytest.mark.parametrize(
    "scope",
    [(), ("www.google.com",), ("www.youtube.com", "www.google.com"), ("../etc",)],
    ids=["empty", "outside", "one-outside", "malformed"],
)
def test_the_scope_is_not_empty_and_inside_the_capability_s(scope: tuple[str, ...]) -> None:
    found = refused(PolicyRequest(GUIDED.id, scope, GUIDED_LIMITS, 1))
    assert found.check is PolicyCheck.SCOPE


@pytest.mark.parametrize(
    ("limits", "fragment"),
    [
        ({"max_cost_usd": "1.10", "looks": "10"}, "missing ['seconds']"),
        ({**GUIDED_LIMITS, "tokens": "5"}, "not declared ['tokens']"),
        ({**GUIDED_LIMITS, "looks": "31"}, "looks"),
        ({**GUIDED_LIMITS, "looks": "1.5"}, "looks"),
        ({**GUIDED_LIMITS, "seconds": "10"}, "seconds"),
        ({**GUIDED_LIMITS, "max_cost_usd": "1,10"}, "max_cost_usd"),
    ],
    ids=[
        "one-less",
        "one-more",
        "above-the-schema",
        "not-an-integer",
        "below-the-schema",
        "a-comma",
    ],
)
def test_the_limits_are_exactly_the_declared_ones_and_valid(
    limits: dict[str, str], fragment: str
) -> None:
    found = refused(PolicyRequest(GUIDED.id, ("www.youtube.com",), limits, 1))

    assert found.check is PolicyCheck.LIMITS
    assert fragment in found.reason


@pytest.mark.parametrize("days", [0, 91, -1, True])
def test_the_days_are_from_one_to_ninety(days: Any) -> None:
    found = refused(PolicyRequest(GUIDED.id, ("www.youtube.com",), GUIDED_LIMITS, days))
    assert found.check is PolicyCheck.DAYS


@pytest.mark.parametrize("days", [1, 90])
def test_the_edges_of_the_days_are_admitted(days: int) -> None:
    grant = born(PolicyRequest(GUIDED.id, ("www.youtube.com",), GUIDED_LIMITS, days))
    assert grant.expires_at == NOW + timedelta(days=days)


def test_the_first_failing_check_wins() -> None:
    found = refused(PolicyRequest(GUIDED.id, (), {}, 0))
    assert found.check is PolicyCheck.SCOPE


def test_an_integer_limit_is_kept_as_its_number_in_words() -> None:
    grant = born(
        PolicyRequest(GUIDED.id, ("www.youtube.com",), {**GUIDED_LIMITS, "looks": "010"}, 1)
    )
    assert grant.bounds is not None
    assert grant.bounds.limits["looks"] == "10"
