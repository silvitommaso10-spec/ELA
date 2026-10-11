"""The capabilities of the browser with the user's accounts, in the catalogue and before the
Guardian (M13.9, ADR 0063; decisions 12 and 29).

``browser.read_as_you`` is **MEDIUM**: what it reads is the user's own content, and it leaves
with their credentials — a question at every use, and no policy of §59 for a single read.
``browser.act_as_you`` and ``browser.login`` are **HIGH**: a question at every use, which no
standing grant reaches. The arguments of the first two are the empty browser's, to the letter; a
login's have **no argument that could carry a value**.
"""

from __future__ import annotations

from typing import Any

import pytest

from ela.domain import Authorization, CapabilitySpec, PermissionOutcome, RiskLevel, TaskStep
from ela.permissions import (
    BROWSER_ACT,
    BROWSER_ACT_AS_YOU,
    BROWSER_LOGIN,
    BROWSER_READ,
    BROWSER_READ_AS_YOU,
    DECLARES_AN_EMPTY_SCOPE,
    ENTRY_MAX_LENGTH,
    UNDECLARED_SITES,
    PermissionGuardian,
    PolicyRefusedError,
    PolicyRequest,
    Rule,
    authorization_from_policy,
    browser_act_as_you,
    browser_login,
    browser_read_as_you,
    check_capability,
    production_catalogue,
)
from ela.permissions.rows import no_policy_for
from ela.testing.fakes import FakeAuditLog, FakeClock, FakeIdGenerator
from tests.domain.examples import NOW, STEP_ID, TASK
from tests.permissions.support import born_of_a_yes, grant

SITES = ("posta.example", "altro.example")
READ = {"site": "posta.example", "path": "/inbox", "purpose": "la prova"}
ACT = {
    "site": "posta.example",
    "path": "/scrivi",
    "fill": [["#testo", "ciao"]],
    "click": "#manda",
    "expect_text": "Mandato",
    "purpose": "la prova",
}
LOGIN = {
    "site": "posta.example",
    "path": "/login",
    "username_field": "#user",
    "password_field": "#word",
    "click": "#go",
    "expect_text": "Benvenuto",
    "purpose": "la prova",
}
CALLS: dict[str, dict[str, Any]] = {
    BROWSER_READ_AS_YOU: READ,
    BROWSER_ACT_AS_YOU: ACT,
    BROWSER_LOGIN: LOGIN,
}
EVERY = pytest.mark.parametrize("capability", sorted(CALLS))


def catalogue(sites: tuple[str, ...] = SITES) -> Any:
    return production_catalogue(sites=sites)


def decide(
    capability: str,
    arguments: dict[str, Any],
    *,
    sites: tuple[str, ...] = SITES,
    authorization: Authorization | None = None,
) -> tuple[PermissionOutcome, str]:
    specs = catalogue(sites)
    guardian = PermissionGuardian(specs, FakeClock(), FakeIdGenerator(), FakeAuditLog())
    spec: CapabilitySpec = specs.get(capability)
    step = TaskStep(
        id=STEP_ID,
        created_at=NOW,
        goal="usare il browser con il profilo",
        required_capabilities=(capability,),  # type: ignore[arg-type]
        arguments=arguments,
        risk=spec.risk,
        expected_result="la pagina",
        requires_authorization=True,
    )
    decision = guardian.decide(spec, arguments, task=TASK, step=step, authorization=authorization)
    return decision.outcome, str(decision.metadata["rule"])


def test_the_three_capabilities_as_the_catalogue_holds_them() -> None:
    read, act, login = browser_read_as_you(SITES), browser_act_as_you(SITES), browser_login(SITES)

    assert (read.id, read.risk) == (BROWSER_READ_AS_YOU, RiskLevel.MEDIUM)
    assert (act.id, act.risk) == (BROWSER_ACT_AS_YOU, RiskLevel.HIGH)
    assert (login.id, login.risk) == (BROWSER_LOGIN, RiskLevel.HIGH)
    for spec in (read, act, login):
        assert spec.requires_authorization is True
        assert spec.scope == SITES and spec.scoped_arguments == ("site",)
        assert spec.prompt_arguments == ("purpose",)
        assert spec.policy_terms is None and spec.covers is None
        check_capability(spec)
    assert {BROWSER_READ_AS_YOU, BROWSER_ACT_AS_YOU, BROWSER_LOGIN} <= DECLARES_AN_EMPTY_SCOPE
    assert browser_read_as_you().scope == UNDECLARED_SITES


def test_what_changes_is_the_browser_and_the_sentence_not_the_shape_of_the_call() -> None:
    """The schemas of the first two are ``browser.read``'s and ``browser.act``'s, with their
    grammars and their limits: «with the profile» is not an argument (ADR 0026 §7)."""
    specs = catalogue()

    assert specs.get(BROWSER_READ_AS_YOU).input_schema == specs.get(BROWSER_READ).input_schema
    assert specs.get(BROWSER_ACT_AS_YOU).input_schema == specs.get(BROWSER_ACT).input_schema
    for capability in CALLS:
        said = specs.get(capability).description
        assert "you" in said and "empty" not in said, capability
    assert "empty" in specs.get(BROWSER_READ).description


def test_a_login_has_no_argument_that_could_carry_a_value() -> None:
    """The value never comes from the plan (decision 15a): what a login may be told is where,
    which fields, which click, which text to wait for, and — by its id — which entry."""
    schema = browser_login(SITES).input_schema

    assert set(schema["properties"]) == {
        "site",
        "path",
        "username_field",
        "password_field",
        "click",
        "expect_text",
        "purpose",
        "entry",
    }
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"]) - {"entry"}
    assert schema["properties"]["entry"]["maxLength"] == ENTRY_MAX_LENGTH == 64


@pytest.mark.parametrize(
    "extra",
    [{"password": "x"}, {"username": "mario"}, {"value": "x"}, {"fill": [["#word", "x"]]}],
    ids=["a-password", "a-username", "a-value", "a-fill"],
)
def test_a_login_that_carries_a_value_is_denied_for_its_arguments(extra: dict[str, Any]) -> None:
    outcome, rule = decide(BROWSER_LOGIN, {**LOGIN, **extra})

    assert (outcome, rule) == (PermissionOutcome.DENIED, Rule.ARGUMENTS.value)


def test_a_read_with_the_profile_asks_where_the_empty_browser_s_does_not() -> None:
    """MEDIUM, on the row that asks unless authorized — and nothing authorizes a single read."""
    outcome, rule = decide(BROWSER_READ_AS_YOU, READ)

    assert outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert rule == Rule.APPROVAL_UNLESS_AUTHORIZED.value


@pytest.mark.parametrize("capability", [BROWSER_ACT_AS_YOU, BROWSER_LOGIN])
def test_an_action_and_a_login_ask_at_every_use_and_no_standing_grant_reaches_them(
    capability: str,
) -> None:
    spec = catalogue().get(capability)

    assert decide(capability, CALLS[capability]) == (
        PermissionOutcome.REQUIRES_APPROVAL,
        Rule.APPROVAL_EVERY_USE.value,
    )
    standing, _ = decide(capability, CALLS[capability], authorization=grant(spec))
    assert standing is not PermissionOutcome.ALLOWED
    assert no_policy_for(spec) is not None


@EVERY
def test_a_yes_to_that_use_allows_it_once(capability: str) -> None:
    spec = catalogue().get(capability)
    yes = born_of_a_yes(spec, scope=("posta.example",))

    outcome, _ = decide(capability, CALLS[capability], authorization=yes)

    assert outcome is PermissionOutcome.ALLOWED


@EVERY
def test_a_site_nobody_declared_is_denied_for_the_scope(capability: str) -> None:
    outcome, rule = decide(capability, {**CALLS[capability], "site": "banca.example"})

    assert (outcome, rule) == (PermissionOutcome.DENIED, Rule.SCOPE.value)


@EVERY
def test_no_site_declared_denies_every_call(capability: str) -> None:
    assert decide(capability, CALLS[capability], sites=()) == (
        PermissionOutcome.DENIED,
        Rule.SCOPE.value,
    )


@EVERY
@pytest.mark.parametrize(
    ("site", "declared"),
    [
        ("posta.example/x", ("posta.example/x",)),
        ("POSTA.example", ("POSTA.example",)),
        ("https://posta.example", ()),
        ("posta.example:8443", ()),
    ],
)
def test_a_site_outside_the_grammar_is_denied_before_the_scope_is_read(
    capability: str, site: str, declared: tuple[str, ...]
) -> None:
    """A site is a host name, not a path: ``posta.example/x`` does not pass as «inside»
    ``posta.example`` — not even when somebody declared it so."""
    outcome, rule = decide(
        capability, {**CALLS[capability], "site": site}, sites=(*SITES, *declared)
    )

    assert (outcome, rule) == (PermissionOutcome.DENIED, Rule.ARGUMENTS.value)


@EVERY
def test_no_policy_of_59_can_be_born_for_any_of_the_three(capability: str) -> None:
    """ADR 0062 §1: a capability that declares no terms admits no policy — a single read with
    the profile among them (decision 29, the road C)."""
    request = PolicyRequest(capability_id=capability, scope=("posta.example",), limits={}, days=1)  # type: ignore[arg-type]

    with pytest.raises(PolicyRefusedError):
        authorization_from_policy(
            request,
            catalogue=catalogue(),
            granted_by="tommaso",
            now=NOW,
            authorization_id=FakeIdGenerator().new_uuid(),  # type: ignore[arg-type]
        )


def test_the_three_come_after_the_guided_session_in_the_catalogue_the_composition_builds() -> None:
    ids = [spec.id for spec in production_catalogue().specs()]

    assert ids[-3:] == [BROWSER_READ_AS_YOU, BROWSER_ACT_AS_YOU, BROWSER_LOGIN]
