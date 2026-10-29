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
from uuid import UUID

import pytest

from ela.domain import (
    Authorization,
    CapabilitySpec,
    PermissionOutcome,
    PlanAuthor,
    PlanAuthorKind,
    RiskLevel,
    SessionCover,
    StepId,
    TaskId,
    TaskStep,
)
from ela.permissions import (
    BROWSER_ACT,
    BROWSER_ACT_AS_YOU,
    BROWSER_GUIDED_AS_YOU,
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
from ela.permissions.rows import no_policy_for, no_session_covers
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


MODEL = "claude-haiku-5-5"
"""The model the default route of a session reads, as the composition hands it to the catalogue:
a policy carries the terms of the day it was born, and the model is one of them."""


def catalogue(sites: tuple[str, ...] = SITES) -> Any:
    return production_catalogue(sites=sites, guided_model=MODEL)


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
    # ``expect_text`` optional since M13.10 (ADR 0065 §4, decision 31): without it the verifier
    # looks for the form to be gone.
    assert set(schema["required"]) == set(schema["properties"]) - {"entry", "expect_text"}
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


def test_they_come_after_the_guided_session_in_the_catalogue_the_composition_builds() -> None:
    ids = [spec.id for spec in production_catalogue().specs()]

    assert ids[ids.index("browser.guided") + 1 :] == [
        BROWSER_READ_AS_YOU,
        BROWSER_ACT_AS_YOU,
        BROWSER_LOGIN,
        BROWSER_GUIDED_AS_YOU,
    ]


# ----------------------------------------------------------------------------------------
# browser.guided_as_you: another capability, one site, and its reads covered by the session
# ----------------------------------------------------------------------------------------

SESSION = {
    "goal": "Guarda se è arrivata la conferma dell'ordine.",
    "sites": ["posta.example"],
    "max_cost_usd": "1.10",
    "looks": 10,
    "seconds": 600,
}
SESSION_STEP = StepId(UUID("00000000-0000-4000-8000-0000000005e5"))
SESSION_TASK = TaskId(UUID("00000000-0000-4000-8000-0000000005e6"))
CHILD = TASK.model_copy(update={"parent_id": SESSION_TASK})
WRITTEN_BY_THE_SESSION = PlanAuthor(
    by=PlanAuthorKind.SESSION, session=SESSION_STEP, model="claude-haiku-5-5"
)


def attested(
    capability: str = BROWSER_GUIDED_AS_YOU, sites: tuple[str, ...] = ("posta.example",)
) -> SessionCover:
    """What the room says of an open session of ``capability`` on ``sites``."""
    return SessionCover(
        session=SESSION_STEP,
        task_id=SESSION_TASK,
        capability_id=capability,  # type: ignore[arg-type]
        sites=sites,
    )


def gesture(
    capability: str, arguments: dict[str, Any], cover: SessionCover | None
) -> tuple[Any, str]:
    """The decision about a gesture a session's model wrote: a child of the session's task."""
    specs = catalogue()
    guardian = PermissionGuardian(specs, FakeClock(), FakeIdGenerator(), FakeAuditLog())
    spec = specs.get(capability)
    step = TaskStep(
        id=STEP_ID,
        created_at=NOW,
        goal="un gesto della sessione",
        required_capabilities=(capability,),  # type: ignore[arg-type]
        arguments=arguments,
        risk=spec.risk,
        expected_result="la pagina",
        requires_authorization=True,
    )
    decision = guardian.decide(
        spec, arguments, task=CHILD, step=step, author=WRITTEN_BY_THE_SESSION, session=cover
    )
    return decision.outcome, str(decision.metadata["rule"])


def policy(capability: str, sites: tuple[str, ...]) -> Authorization:
    return authorization_from_policy(
        PolicyRequest(
            capability_id=capability,  # type: ignore[arg-type]
            scope=sites,
            limits={"max_cost_usd": "1.10", "looks": "10", "seconds": "600"},
            days=1,
        ),
        catalogue=catalogue(),
        granted_by="tommaso",
        now=FakeClock().now(),
        authorization_id=FakeIdGenerator().new_uuid(),  # type: ignore[arg-type]
    )


def test_the_session_with_the_profile_as_the_catalogue_holds_it() -> None:
    specs = catalogue()
    session, empty = specs.get(BROWSER_GUIDED_AS_YOU), specs.get("browser.guided")  # type: ignore[arg-type]

    assert (session.risk, session.requires_authorization) == (RiskLevel.MEDIUM, True)
    assert session.scope == SITES and session.scoped_arguments == ("sites",)
    assert session.policy_terms == empty.policy_terms, "the limits are a session's, whichever it is"
    assert session.input_schema["properties"]["sites"]["maxItems"] == 1
    assert "maxItems" not in empty.input_schema["properties"]["sites"]
    assert "you" in session.description and "empty" not in session.description
    assert "any address of that site as you" in session.description
    assert BROWSER_GUIDED_AS_YOU in DECLARES_AN_EMPTY_SCOPE


def test_it_declares_that_its_reads_are_the_profile_s_with_their_very_schema() -> None:
    """Decision 29: outside the terms of a policy, and with a copy of the covered capability's
    schema — which the catalogue holds equal to the original, or does not build."""
    specs = catalogue()
    covered = specs.get(BROWSER_GUIDED_AS_YOU).covers

    assert covered is not None and covered.capability_id == BROWSER_READ_AS_YOU
    assert covered.input_schema == specs.get(BROWSER_READ_AS_YOU).input_schema
    assert specs.get("browser.guided").covers is None, "a LOW read asks nobody: nothing to cover"  # type: ignore[arg-type]
    assert no_session_covers(specs.get(BROWSER_READ_AS_YOU)) is None
    for high in (BROWSER_ACT_AS_YOU, BROWSER_LOGIN):
        assert no_session_covers(specs.get(high)) is not None, f"no session covers {high}"


def test_a_session_with_the_profile_names_one_site_and_two_are_refused_before_the_question() -> (
    None
):
    """Criterion 22: what the model reads on a site of the user's is not carried to another."""
    assert decide(BROWSER_GUIDED_AS_YOU, SESSION)[0] is PermissionOutcome.REQUIRES_APPROVAL

    two = {**SESSION, "sites": ["posta.example", "altro.example"]}

    assert decide(BROWSER_GUIDED_AS_YOU, two) == (PermissionOutcome.DENIED, Rule.ARGUMENTS.value)


def test_one_site_among_those_of_a_policy_that_lists_several_starts_without_a_question() -> None:
    """The scope of a policy may list more than one; each session chooses one."""
    standing = policy(BROWSER_GUIDED_AS_YOU, SITES)

    for site in SITES:
        outcome, _ = decide(
            BROWSER_GUIDED_AS_YOU, {**SESSION, "sites": [site]}, authorization=standing
        )
        assert outcome is PermissionOutcome.ALLOWED, site


def test_a_policy_of_one_session_does_not_cover_the_other_either_way() -> None:
    """Criterion 7: ``browser.guided_as_you`` is another capability, and a standing yes for the
    empty browser is not a yes for the browser with the user's accounts — nor the reverse."""
    empty = {**SESSION, "sites": ["posta.example"]}

    with_the_wrong_one, _ = decide(
        BROWSER_GUIDED_AS_YOU, SESSION, authorization=policy("browser.guided", SITES)
    )
    the_reverse, _ = decide(
        "browser.guided", empty, authorization=policy(BROWSER_GUIDED_AS_YOU, SITES)
    )

    assert with_the_wrong_one is PermissionOutcome.DENIED
    assert the_reverse is PermissionOutcome.DENIED
    assert decide("browser.guided", empty, authorization=policy("browser.guided", SITES))[0] is (
        PermissionOutcome.ALLOWED
    )


def test_the_session_covers_the_reads_its_model_writes_on_its_site_and_nothing_else() -> None:
    """The road A of decision 29, on the catalogue ELA builds: a read with the profile written by
    the model of an open session with the profile is allowed under the session's own rule — no
    question at every look —; an act asks, always; and another site is not the session's."""
    assert gesture(BROWSER_READ_AS_YOU, READ, attested()) == (
        PermissionOutcome.ALLOWED,
        Rule.SESSION.value,
    )
    assert gesture(BROWSER_ACT_AS_YOU, ACT, attested()) == (
        PermissionOutcome.DENIED,
        Rule.SESSION_MISMATCH.value,
    )
    assert gesture(BROWSER_ACT_AS_YOU, ACT, None) == (
        PermissionOutcome.REQUIRES_APPROVAL,
        Rule.APPROVAL_EVERY_USE.value,
    )
    elsewhere = {**READ, "site": "altro.example"}
    assert gesture(BROWSER_READ_AS_YOU, elsewhere, attested())[0] is not PermissionOutcome.ALLOWED


def test_a_session_on_the_empty_browser_covers_no_read_with_the_profile() -> None:
    """``browser.guided`` declares no cover: its word, presented for a read as the user, is a
    mismatch — and without any word the read asks, as a ``MEDIUM`` does."""
    assert gesture(BROWSER_READ_AS_YOU, READ, attested("browser.guided")) == (
        PermissionOutcome.DENIED,
        Rule.SESSION_MISMATCH.value,
    )
    assert gesture(BROWSER_READ_AS_YOU, READ, None) == (
        PermissionOutcome.REQUIRES_APPROVAL,
        Rule.APPROVAL_UNLESS_AUTHORIZED.value,
    )
