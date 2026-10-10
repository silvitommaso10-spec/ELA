"""The policies of §59 in ``ela.permissions`` (M13.12, ADR 0062): the one predicate, the birth, the
revocation as a value, and the sentences the question and the preview say. Pure, so exhausted here.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from ela.domain import AuthorizationId, CapabilityId, PolicyTerms
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
    browser_act,
    fs_read,
    fs_write,
    never_covered,
    production_catalogue,
    prospect_arguments,
    short_id,
    shortfall,
    state_of,
    why_lines,
)
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
    assert GAPS == (Gap.REVOKED, Gap.EXPIRED, Gap.TERMS, Gap.SITE, Gap.LIMIT, Gap.ARGUMENT)
    assert UNUSABLE == (Gap.REVOKED, Gap.EXPIRED)
    assert UNCOVERED == (Gap.TERMS, Gap.SITE, Gap.LIMIT, Gap.ARGUMENT)
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
    assert state_of(POLICY, NOW) is PolicyState.LIVE
    assert state_of(revoked(POLICY, NOW), NOW) is PolicyState.REVOKED
    assert state_of(POLICY.model_copy(update={"expires_at": NOW}), NOW) is PolicyState.EXPIRED


# ----------------------------------------------------------------------------------------
# The line «why I ask» (decision 8)
# ----------------------------------------------------------------------------------------


def test_with_no_policy_the_line_says_so() -> None:
    assert why_lines((), GUIDED, GUIDED_ARGS, now=NOW) == ("no policy of yours for browser.guided",)


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

    lines = why_lines(policies, GUIDED, GUIDED_ARGS, now=NOW)

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

    lines = why_lines((old, recent, revoked_long_ago), GUIDED, GUIDED_ARGS, now=NOW)

    assert lines == (
        f"policy {short_id(recent.id)} expired on {recent.expires_at.date().isoformat()}",
    )  # type: ignore[union-attr]


def test_a_policy_born_after_the_decision_is_not_named() -> None:
    later = policy_for(GUIDED, created_at=NOW + timedelta(seconds=1))
    assert why_lines((later,), GUIDED, GUIDED_ARGS, now=NOW) == (
        "no policy of yours for browser.guided",
    )


def test_a_policy_that_covers_says_the_step_asks_again_for_its_own_yes() -> None:
    lines = why_lines((POLICY,), GUIDED, GUIDED_ARGS, now=NOW)

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
    for line in why_lines(policies, GUIDED, {**GUIDED_ARGS, "sites": ["httpbin.org"]}, now=NOW):
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


def test_never_covered_names_the_rows_that_ask_at_every_use_and_the_terms() -> None:
    catalogue = production_catalogue(sites=SITES, guided_model=MODEL)

    said = never_covered(GUIDED, catalogue.specs())

    assert said[0] == (
        "every call of a capability that asks at every use asks every time: browser.act, "
        "fs.write, terminal.run"
    )
    assert said[1] == "a call above a limit, or outside the scope, asks"
    assert said[2] == "a call with task_type asks"


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
        (browser_act(SITES), "no policy reaches a HIGH (ADR 0045 §3)"),
        (fs_write("ELA"), "no policy reaches a HIGH (ADR 0045 §3)"),
        (ECHO, "core.echo does not ask: it needs no policy"),
        (fs_read("ELA"), "no milestone has said what a policy must bound for fs.read"),
    ],
    ids=["browser.act", "fs.write", "core.echo", "fs.read"],
)
def test_admits_has_three_distinct_reasons(spec: Any, reason: str) -> None:
    catalogue = CapabilityRegistry((spec,))
    found = refused(PolicyRequest(spec.id, ("ELA",), {}, 1), catalogue)

    assert found.check is PolicyCheck.ADMITS
    assert found.reason == reason


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
