"""``browser.read`` and ``browser.act`` in the catalogue and before the Guardian (M13.4 D, E).

``browser.read`` is ``LOW``: inside the declared sites it is allowed without a question — unless a
step asks for one —, outside it is denied with ``Rule.SCOPE``. ``browser.act`` is ``HIGH``: a
question at every use, and no standing grant reaches it. The site is the one scoped argument, and a
site outside the grammar is denied with ``Rule.ARGUMENTS`` before the scope is read (census C1): a
site is a host name, not a path, and ``example.com/x`` must not pass as «inside» ``example.com``.
"""

from __future__ import annotations

import pytest

from ela.domain import Authorization, PermissionOutcome, RiskLevel, TaskStep
from ela.permissions import (
    BROWSER_ACT,
    BROWSER_READ,
    DECLARES_AN_EMPTY_SCOPE,
    UNDECLARED_SITES,
    PermissionGuardian,
    Rule,
    browser_act,
    browser_read,
    check_capability,
)
from ela.testing.fakes import FakeAuditLog, FakeCapabilityRegistry, FakeClock, FakeIdGenerator
from tests.domain.examples import NOW, STEP_ID
from tests.permissions.support import grant

SITES = ("example.com", "httpbin.org")
READ = {"site": "example.com", "path": "/", "purpose": "la prova"}
ACT = {
    "site": "httpbin.org",
    "path": "/forms/post",
    "fill": [["input[name=custname]", "ELA"]],
    "click": "form button",
    "expect_text": "ELA",
    "purpose": "la prova",
}


def guardian(sites: tuple[str, ...] = SITES) -> PermissionGuardian:
    return PermissionGuardian(
        FakeCapabilityRegistry((browser_read(sites), browser_act(sites))),
        FakeClock(),
        FakeIdGenerator(),
        FakeAuditLog(),
    )


def step(capability: str, arguments: dict[str, object], *, asks: bool = False) -> TaskStep:
    return TaskStep(
        id=STEP_ID,
        created_at=NOW,
        goal="usare il browser",
        required_capabilities=(capability,),  # type: ignore[arg-type]
        arguments=arguments,
        risk=RiskLevel.LOW,
        expected_result="la pagina",
        requires_authorization=asks,
    )


def decide(
    capability: str,
    arguments: dict[str, object],
    *,
    sites: tuple[str, ...] = SITES,
    asks: bool = False,
    authorization: Authorization | None = None,
) -> tuple[PermissionOutcome, str]:
    spec = browser_read(sites) if capability == BROWSER_READ else browser_act(sites)
    decision = guardian(sites).decide(
        spec,
        arguments,
        step=step(capability, arguments, asks=asks),
        authorization=authorization,
    )
    return decision.outcome, str(decision.metadata["rule"])


def test_the_two_capabilities_as_the_catalogue_holds_them() -> None:
    read, act = browser_read(SITES), browser_act(SITES)

    assert (read.id, read.risk, read.requires_authorization) == (BROWSER_READ, RiskLevel.LOW, False)
    assert (act.id, act.risk, act.requires_authorization) == (BROWSER_ACT, RiskLevel.HIGH, True)
    for spec in (read, act):
        assert spec.scope == SITES
        assert spec.scoped_arguments == ("site",)
        assert spec.prompt_arguments == ("purpose",)
        check_capability(spec)
    assert {BROWSER_READ, BROWSER_ACT} <= DECLARES_AN_EMPTY_SCOPE


def test_the_default_of_the_factories_is_a_placeholder_that_is_not_a_site() -> None:
    assert browser_read().scope == browser_act().scope == UNDECLARED_SITES
    assert UNDECLARED_SITES != ()


def test_a_read_inside_the_sites_is_allowed_without_a_question() -> None:
    assert decide(BROWSER_READ, READ) == (PermissionOutcome.ALLOWED, Rule.ALLOW_WITHIN_SCOPE.value)


def test_a_read_a_step_asks_about_is_a_question() -> None:
    """Decision E of M4: ``LOW`` asks when the step says so, and then the read has a question."""
    outcome, _ = decide(BROWSER_READ, READ, asks=True)

    assert outcome is PermissionOutcome.REQUIRES_APPROVAL


def test_a_site_that_was_not_declared_is_denied_for_the_scope() -> None:
    outcome, rule = decide(BROWSER_READ, {**READ, "site": "example.org"})

    assert (outcome, rule) == (PermissionOutcome.DENIED, Rule.SCOPE.value)


@pytest.mark.parametrize(
    "site",
    ["example.com/x", "EXAMPLE.com", "example.com:443", "https://example.com", "example.com\n"],
)
def test_a_site_outside_the_grammar_is_denied_before_the_scope_is_read(site: str) -> None:
    outcome, rule = decide(BROWSER_READ, {**READ, "site": site}, sites=(*SITES, site))

    assert (outcome, rule) == (PermissionOutcome.DENIED, Rule.ARGUMENTS.value)


def test_no_site_declared_denies_every_call() -> None:
    assert decide(BROWSER_READ, READ, sites=()) == (PermissionOutcome.DENIED, Rule.SCOPE.value)
    assert decide(BROWSER_ACT, ACT, sites=()) == (PermissionOutcome.DENIED, Rule.SCOPE.value)


def test_an_action_asks_at_every_use() -> None:
    outcome, rule = decide(BROWSER_ACT, ACT)

    assert (outcome, rule) == (PermissionOutcome.REQUIRES_APPROVAL, Rule.APPROVAL_EVERY_USE.value)


def test_a_standing_grant_does_not_reach_an_action() -> None:
    """§59's policies widen, and HIGH is the level they never reach (ADR 0045 §3)."""
    outcome, _ = decide(BROWSER_ACT, ACT, authorization=grant(browser_act(SITES)))

    assert outcome is not PermissionOutcome.ALLOWED
