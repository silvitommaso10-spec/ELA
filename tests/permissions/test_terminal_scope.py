"""``terminal.run`` in the catalogue and before the Guardian: the programs are the scope (M13.2).

Decision 3 of M13.2 (ADR 0047): a program is written relative to ``/`` in the grammar of today, so
**the four comparisons that read a scope do not change** and none of their tests does — this file
only adds. And the reading of the link, decided at the resumption (Domanda 1): the Guardian denies
with ``Rule.SCOPE`` **what the plan writes** — an undeclared program, every ``..`` — and never what
the disk resolves. A declared link is the user's choice, whatever it leads to.
"""

from __future__ import annotations

import pytest

from ela.domain import PermissionOutcome, RiskLevel, TaskStep
from ela.permissions import (
    FS_READ,
    TERMINAL_RUN,
    UNDECLARED_PROGRAMS,
    InvalidCapabilityError,
    PermissionGuardian,
    Rule,
    check_capability,
    fs_read,
    production_catalogue,
    terminal_run,
)
from ela.testing.fakes import FakeAuditLog, FakeCapabilityRegistry, FakeClock, FakeIdGenerator
from tests.domain.examples import NOW, STEP_ID

DECLARED = ("usr/bin/git", "opt/homebrew/bin/rg")
"""Two programs: one a regular file, one a link that ``brew upgrade`` repoints — the Guardian
cannot tell them apart, and must not need to."""


def guardian(programs: tuple[str, ...] = DECLARED) -> PermissionGuardian:
    return PermissionGuardian(
        FakeCapabilityRegistry((terminal_run(programs),)),
        FakeClock(),
        FakeIdGenerator(),
        FakeAuditLog(),
    )


def step(program: str) -> TaskStep:
    return TaskStep(
        id=STEP_ID,
        created_at=NOW,
        goal="far girare un programma",
        required_capabilities=(TERMINAL_RUN,),
        arguments=call(program),
        risk=RiskLevel.HIGH,
        expected_result="la sua uscita",
        requires_authorization=True,
    )


def call(program: str) -> dict[str, object]:
    return {"program": program, "args": ["status"], "purpose": "la prova"}


def decide(
    program: str, programs: tuple[str, ...] = DECLARED
) -> tuple[PermissionOutcome, str, str]:
    decision = guardian(programs).decide(terminal_run(programs), call(program), step=step(program))
    return decision.outcome, str(decision.metadata["rule"]), decision.reason


# ----------------------------------------------------------------------------------------
# The catalogue
# ----------------------------------------------------------------------------------------


def test_the_terminal_is_high_scoped_on_the_program_and_asks_for_the_purpose() -> None:
    spec = terminal_run(DECLARED)

    assert spec.id == TERMINAL_RUN == "terminal.run"
    assert spec.risk is RiskLevel.HIGH
    assert spec.scope == DECLARED
    assert spec.scoped_arguments == ("program",)
    assert spec.prompt_arguments == ("purpose",)
    assert spec.requires_authorization
    schema = spec.input_schema
    assert set(schema["required"]) == {"program", "args", "purpose"}
    assert set(schema["properties"]) == {"program", "args", "purpose", "cwd", "expect_exit"}
    assert schema["properties"]["args"]["type"] == "array"
    assert schema["properties"]["args"]["items"] == {"type": "string"}
    assert schema["properties"]["expect_exit"]["type"] == "integer"
    assert schema["additionalProperties"] is False


def test_it_is_in_the_catalogue_the_composition_builds_last() -> None:
    """In the order the ADRs added them: ADR 0047 comes after ADR 0045."""
    assert production_catalogue().specs()[-1].id == TERMINAL_RUN


def test_the_default_of_the_factory_is_a_placeholder_and_not_an_empty_list() -> None:
    """Decision 16: ``()`` would be a declaration, and a forgotten wiring must not read as one."""
    assert terminal_run().scope == UNDECLARED_PROGRAMS
    assert UNDECLARED_PROGRAMS != ()


def test_an_empty_scope_is_admitted_only_for_the_capability_that_declares_it() -> None:
    """Decision 16: ``ELA_TERMINAL_PROGRAMS=[]`` is an answer — «no program» — and not a doubt.

    Everywhere else a scoped argument with no scope stays what it was: a doubt (§33).
    """
    check_capability(terminal_run(()))

    with pytest.raises(InvalidCapabilityError):
        check_capability(fs_read().model_copy(update={"scope": ()}))
    assert fs_read().id == FS_READ


# ----------------------------------------------------------------------------------------
# The Guardian: what the plan writes
# ----------------------------------------------------------------------------------------


def test_a_declared_program_is_asked_about_every_time() -> None:
    outcome, rule, _ = decide("usr/bin/git")

    assert (outcome, rule) == (PermissionOutcome.REQUIRES_APPROVAL, Rule.APPROVAL_EVERY_USE)


def test_a_program_nobody_declared_is_denied_by_the_scope_before_any_question() -> None:
    outcome, rule, reason = decide("usr/bin/whoami")

    assert (outcome, rule) == (PermissionOutcome.DENIED, Rule.SCOPE)
    assert "usr/bin/whoami" in reason


def test_a_climb_out_of_a_declared_program_never_reaches_a_resolution() -> None:
    """Decision 3: ``within_scope`` refuses every ``..`` segment, as a shape."""
    outcome, rule, _ = decide("usr/bin/git/../../bin/sh")

    assert (outcome, rule) == (PermissionOutcome.DENIED, Rule.SCOPE)


def test_an_absolute_path_is_not_the_grammar_and_is_denied() -> None:
    """The first thing somebody writing a plan by hand gets wrong: the scope is shown without the
    slash, in the reason, so the reader sees how to write it."""
    outcome, rule, reason = decide("/usr/bin/git")

    assert (outcome, rule) == (PermissionOutcome.DENIED, Rule.SCOPE)
    assert "'usr/bin/git'" in reason


def test_a_link_nobody_declared_is_denied_even_when_it_leads_to_a_declared_program() -> None:
    """A link does not carry the declaration of its target: the Guardian compares the string."""
    outcome, rule, _ = decide("usr/local/bin/git")

    assert (outcome, rule) == (PermissionOutcome.DENIED, Rule.SCOPE)


def test_a_declared_link_is_not_denied_by_the_scope_wherever_it_leads() -> None:
    """Domanda 1, decisa: the Guardian never reads the disk. ``opt/homebrew/bin/rg`` leads into
    ``Cellar``, which nobody declared — and it is asked about, not denied: the question names the
    file it leads to, and a repointed link is the tool's to refuse, with
    ``terminal.program_changed``."""
    outcome, rule, _ = decide("opt/homebrew/bin/rg")

    assert outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert rule != Rule.SCOPE


def test_no_program_declared_denies_every_call_with_the_empty_scope_in_the_reason() -> None:
    """Decision 16: ``[]`` makes ELA start, and the Guardian already knows how to say no to it."""
    outcome, rule, reason = decide("usr/bin/git", programs=())

    assert (outcome, rule) == (PermissionOutcome.DENIED, Rule.SCOPE)
    assert "scope []" in reason
