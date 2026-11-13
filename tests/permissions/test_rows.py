"""The row of a capability, in one place (M13.14, ADR 0068; decisions 5 and 6).

:func:`~ela.permissions.rows.row_of` is the row of the level, read from ``RISK_POLICY``; for a
``HIGH`` that declares policy terms and does not launch a program, a row of its own,
``APPROVAL_UNLESS_POLICY``. No level moves; ``CRITICAL`` stays ``DENY``, terms or not; and
``terminal.run`` stays out, with the reason that names the program.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import pytest

from ela.domain import CapabilityId, PermissionOutcome, PolicyTerms, PolicyWords, RiskLevel
from ela.permissions import (
    ASKING_RULES,
    LAUNCHES_A_PROGRAM,
    PermissionGuardian,
    Rule,
    asks_at_every_use,
    no_policy_for,
    row_of,
    terminal_run,
)
from ela.permissions import rows as rows_module
from ela.permissions.rows import no_session_covers, no_session_of
from ela.testing.fakes import FakeAuditLog, FakeCapabilityRegistry, FakeClock, FakeIdGenerator
from tests.permissions.catalogue_calls import CATALOGUE
from tests.permissions.policy_support import TERMED, TERMED_ARGS, policy_for

PROGRAM_REASON = (
    "terminal.run launches a program the plan chooses: a program can read the Core's token and "
    "create a policy, and only you create one"
)
WORDS = PolicyWords(does="does something of the tests", goes="nowhere")
HIGH_WITH_TERMS = TERMED.model_copy(
    update={"id": CapabilityId("test.high_termed"), "risk": RiskLevel.HIGH, "policy_words": WORDS}
)
CRITICAL_WITH_TERMS = HIGH_WITH_TERMS.model_copy(
    update={"id": CapabilityId("test.critical_termed"), "risk": RiskLevel.CRITICAL}
)
"""A ``CRITICAL`` with a whole declaration, in a registry that admits it: the natural mutant of
``row_of`` — a condition ``risk >= HIGH`` — turns it into a row a policy covers (proposal 15)."""
TERMINAL_WITH_TERMS = terminal_run(("git",)).model_copy(
    update={
        "policy_terms": PolicyTerms(limits=(), free=("args", "purpose", "cwd", "expect_exit")),
        "policy_words": WORDS,
    }
)
"""``terminal.run`` as a registry that admits anything could hold it: with terms and words."""

ROWS = {
    "core.echo": Rule.ALLOW,
    "workspace.write_note": Rule.ALLOW_WITHIN_SCOPE,
    "browser.read": Rule.ALLOW_WITHIN_SCOPE,
    "model.complete": Rule.APPROVAL_UNLESS_AUTHORIZED,
    "perception.capture_screen": Rule.APPROVAL_UNLESS_AUTHORIZED,
    "perception.read_screen_text": Rule.APPROVAL_UNLESS_AUTHORIZED,
    "voice.speak": Rule.APPROVAL_UNLESS_AUTHORIZED,
    "voice.speak_online": Rule.APPROVAL_UNLESS_AUTHORIZED,
    "perception.listen": Rule.APPROVAL_UNLESS_AUTHORIZED,
    "fs.read": Rule.APPROVAL_UNLESS_AUTHORIZED,
    "browser.guided": Rule.APPROVAL_UNLESS_AUTHORIZED,
    "browser.read_as_you": Rule.APPROVAL_UNLESS_AUTHORIZED,
    "browser.guided_as_you": Rule.APPROVAL_UNLESS_AUTHORIZED,
    "fs.write": Rule.APPROVAL_UNLESS_POLICY,
    "browser.act": Rule.APPROVAL_UNLESS_POLICY,
    "browser.act_as_you": Rule.APPROVAL_UNLESS_POLICY,
    "terminal.run": Rule.APPROVAL_EVERY_USE,
    "browser.login": Rule.APPROVAL_EVERY_USE,
    "browser.download": Rule.APPROVAL_EVERY_USE,
    "browser.download_as_you": Rule.APPROVAL_EVERY_USE,
    "browser.upload": Rule.APPROVAL_EVERY_USE,
    "browser.upload_as_you": Rule.APPROVAL_EVERY_USE,
}
"""Criterion 7: the row of every capability of the catalogue, written out — a closed world."""


def test_the_row_of_every_capability_of_the_catalogue() -> None:
    assert {spec.id: row_of(spec) for spec in CATALOGUE.specs()} == ROWS


def test_asks_at_every_use_reads_the_capability_and_not_the_level() -> None:
    """A ``HIGH`` that declares terms does not ask at every use; one that declares none does."""
    for spec in CATALOGUE.specs():
        assert asks_at_every_use(spec) is (ROWS[spec.id] is Rule.APPROVAL_EVERY_USE), spec.id


def test_the_new_row_asks_and_no_session_covers_it() -> None:
    """``ASKING_RULES`` gains it — a question when nothing covers —, and the cover of a session
    reaches only «approval unless authorized» (ADR 0063 §1): never a ``HIGH`` with terms."""
    assert Rule.APPROVAL_UNLESS_POLICY in ASKING_RULES
    assert no_session_covers(HIGH_WITH_TERMS) == (
        "test.high_termed is HIGH: a session covers only a row that asks unless authorized"
    )
    assert no_session_of(HIGH_WITH_TERMS) is False


def test_a_critical_with_terms_is_still_deny() -> None:
    """Criterion 2: ``CRITICAL`` stays out, terms or not — only the row of ``HIGH`` turns."""
    assert row_of(CRITICAL_WITH_TERMS) is Rule.DENY
    assert asks_at_every_use(CRITICAL_WITH_TERMS) is False
    assert no_policy_for(CRITICAL_WITH_TERMS) == (
        "test.critical_termed is CRITICAL: its row denies, and no policy covers it"
    )


def test_the_guardian_denies_a_critical_with_terms_and_a_policy_for_it() -> None:
    guardian = PermissionGuardian(
        FakeCapabilityRegistry((CRITICAL_WITH_TERMS,)),
        FakeClock(),
        FakeIdGenerator(),
        FakeAuditLog(),
    )
    policy = policy_for(CRITICAL_WITH_TERMS)

    for authorization in (None, policy):
        decision = guardian.decide(CRITICAL_WITH_TERMS, TERMED_ARGS, authorization=authorization)
        assert decision.outcome is PermissionOutcome.DENIED
        assert decision.metadata["rule"] == Rule.DENY.value


def test_a_program_is_launched_only_by_the_terminal() -> None:
    assert frozenset({"terminal.run"}) == LAUNCHES_A_PROGRAM


def test_the_terminal_with_terms_still_asks_at_every_use() -> None:
    """Decision 5: a capability that launches a program never reads the row of a policy, even
    where a registry admitted its declaration — the catalogue refuses it before."""
    assert row_of(TERMINAL_WITH_TERMS) is Rule.APPROVAL_EVERY_USE
    assert asks_at_every_use(TERMINAL_WITH_TERMS) is True
    assert no_policy_for(TERMINAL_WITH_TERMS) == PROGRAM_REASON
    assert no_policy_for(terminal_run(("git",))) == PROGRAM_REASON


def test_the_guardian_denies_a_policy_of_the_terminal_with_the_program_s_reason() -> None:
    guardian = PermissionGuardian(
        FakeCapabilityRegistry((TERMINAL_WITH_TERMS,)),
        FakeClock(),
        FakeIdGenerator(),
        FakeAuditLog(),
    )
    arguments: dict[str, Any] = {"program": "git", "args": ["status"], "purpose": "la prova"}
    policy = policy_for(TERMINAL_WITH_TERMS)

    asked = guardian.decide(TERMINAL_WITH_TERMS, arguments)
    denied = guardian.decide(TERMINAL_WITH_TERMS, arguments, authorization=policy)

    assert asked.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert asked.metadata["rule"] == Rule.APPROVAL_EVERY_USE.value
    assert denied.outcome is PermissionOutcome.DENIED
    assert denied.metadata["rule"] == Rule.AUTHORIZATION_MISMATCH.value
    assert denied.reason.endswith(PROGRAM_REASON)


@pytest.mark.parametrize(
    ("spec", "reason"),
    [
        (HIGH_WITH_TERMS, None),
        (TERMED, None),
        (
            TERMED.model_copy(update={"policy_terms": None}),
            "no milestone has said what a policy must bound for test.termed",
        ),
        (
            HIGH_WITH_TERMS.model_copy(update={"policy_terms": None}),
            "test.high_termed is HIGH and declares no terms: only a grant born from an approval "
            "covers it",
        ),
        (
            TERMED.model_copy(update={"risk": RiskLevel.SAFE}),
            "test.termed does not ask: it needs no policy",
        ),
        (
            TERMED.model_copy(update={"risk": RiskLevel.LOW}),
            "test.termed does not ask: it needs no policy",
        ),
        (TERMINAL_WITH_TERMS, PROGRAM_REASON),
        (
            CRITICAL_WITH_TERMS,
            "test.critical_termed is CRITICAL: its row denies, and no policy covers it",
        ),
    ],
    ids=[
        "a-high-with-terms",
        "a-medium-with-terms",
        "a-medium-without",
        "a-high-without",
        "a-safe",
        "a-low",
        "the-program",
        "a-critical",
    ],
)
def test_no_policy_for_says_every_reason(spec: Any, reason: str | None) -> None:
    assert no_policy_for(spec) == reason


def test_a_level_the_table_does_not_hold_has_no_row_and_no_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The table is data: a level missing from it has no row — the Guardian denies — and no
    policy covers it."""
    without_high = MappingProxyType(
        {
            level: rule
            for level, rule in rows_module.RISK_POLICY.items()
            if level is not RiskLevel.HIGH
        }
    )
    monkeypatch.setattr(rows_module, "RISK_POLICY", without_high)

    assert row_of(HIGH_WITH_TERMS) is None
    assert no_policy_for(HIGH_WITH_TERMS) == (
        "test.high_termed is HIGH: its row denies, and no policy covers it"
    )
