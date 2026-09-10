"""The crash-window table of ADR 0015 §8 and the recovery tests describe the same repairs.

Every row the ADR marks **Riparato.** is a window ``tests/executive/test_executor_recovery.py``
crashes at and retries — one ``test_window_<n>_…`` per window, listed in its ``REPAIRED`` — and
every window that module repairs is a row the ADR marks so. A row that cites another milestone
cannot claim a repair; a row demoted, or a test removed, is noticed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ela.domain import AuditEventType, CapabilityId, JsonMapping, TaskState
from ela.tasks.engine import ORPHANED, RecoverySummary
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeModelProvider
from ela.tools import NotIdempotentError, Outcome, Tool, ToolRegistry, tools_v01
from tests.executive import test_executor_recovery as recovery
from tests.routing.support import routing_for

ADR_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "adr" / "0015-approval-and-result-persistence.md"
)
ADR_DIR = ADR_PATH.parent
WINDOW_ROW = re.compile(r"^\| ([0-9A-Za-z]+) \| (.+?) \| (.+?) \| (.+?) \| (.+) \|$")
TABLE_HEADER = "| # | Il processo muore dopo… | …e prima di | Stato che resta | Retry |"
"""What a crash-window table is, structurally. **The tables are found and not listed** (M11.2
dec. L): a hand-written list of which ADRs carry one would stop covering at the third document
without failing, which is the exact shape of the defect the derivation exists against — the same
lesson ADR 0030 §6 learnt for rule 33's subject."""
REPAIRED_MARK = "**Riparato.**"
MILESTONE = re.compile(r"M\d+\.\d+")


def tables_in(text: str) -> list[list[str]]:
    """Every crash-window table in ``text``: the rows under each header, until the table ends."""
    tables: list[list[str]] = []
    rows: list[str] | None = None
    for line in text.splitlines():
        if line.strip() == TABLE_HEADER:
            rows = []
            continue
        if rows is None:
            continue
        if WINDOW_ROW.match(line):
            rows.append(line)
        elif not line.startswith("|"):
            tables.append(rows)
            rows = None
    if rows is not None:
        tables.append(rows)
    return tables


def documented_in(text: str) -> dict[str, str]:
    """Window id -> the "Retry" cell, for one document."""
    return {
        match.group(1): match.group(5)
        for rows in tables_in(text)
        for line in rows
        if (match := WINDOW_ROW.match(line)) is not None
    }


def every_documented_window() -> dict[tuple[str, str], str]:
    """``(adr, window)`` -> the "Retry" cell, across **every** ADR that carries a table.

    Keyed by the pair and not by the window alone: two documents using the same id would
    overwrite each other in a dictionary, which is one more silent way to lose a row.
    """
    found: dict[tuple[str, str], str] = {}
    for path in sorted(ADR_DIR.glob("0*.md")):
        for window, retry in documented_in(path.read_text(encoding="utf-8")).items():
            found[(path.stem[:4], window)] = retry
    assert found, "some ADR must carry a crash-window table, or this derivation is vacuous"
    return found


def documented_windows(text: str) -> dict[str, str]:
    """Window id -> the "Retry" cell of the crash-window table."""
    rows = documented_in(text)
    assert rows, "ADR 0015 must contain the crash-window table"
    return rows


def repaired_windows(text: str) -> frozenset[str]:
    return frozenset(w for w, retry in documented_windows(text).items() if REPAIRED_MARK in retry)


def windows_under_test() -> frozenset[str]:
    names = [n for n in dir(recovery) if n.startswith("test_window_")]
    return frozenset(n.removeprefix("test_window_").split("_")[0] for n in names)


def test_every_repaired_row_has_a_retry_test_and_vice_versa() -> None:
    repaired = repaired_windows(ADR_PATH.read_text(encoding="utf-8"))
    assert repaired == recovery.REPAIRED
    assert windows_under_test() >= recovery.REPAIRED


def test_every_declared_window_has_a_test_of_its_own_too() -> None:
    """A window that is not repaired still has a test that pins what the retry does.

    The set is **derived** from the table and no longer written here (M9.4). Until then it was
    ``{"5c", "7a", "9"}`` — three of the ten rows the ADR leaves declared — and the other seven
    made verifiable claims that nothing checked: what a retry does after a crash at that write
    was, for those rows, a sentence in a document. A hand-written list cannot notice a row it
    was never told about; a derived one fails the moment the table grows.
    """
    documented = set(documented_windows(ADR_PATH.read_text(encoding="utf-8")))
    declared = documented - recovery.REPAIRED
    assert declared, "the table must leave some window declared, or this test is vacuous"
    assert declared <= windows_under_test()


def test_a_repaired_row_never_defers_to_another_milestone() -> None:
    for window, retry in documented_windows(ADR_PATH.read_text(encoding="utf-8")).items():
        if REPAIRED_MARK in retry:
            assert MILESTONE.search(retry) is None, window


def test_the_table_lists_every_window_of_the_earlier_adrs() -> None:
    windows = set(documented_windows(ADR_PATH.read_text(encoding="utf-8")))
    numbered = {str(n) for n in range(11)} - {"7"}  # 7 became 7a and 7b
    assert windows >= numbered | {"5b", "5c", "7a", "7b", "8a", "8b", "8c", "9a"}


def test_a_demoted_row_or_a_removed_test_is_detected() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")
    demoted = text.replace(
        "→ scritto ora con `recovered`, poi si prosegue (§5). Il tool non gira. **Riparato.** |",
        "→ scritto ora con `recovered`, poi si prosegue (§5). Il tool non gira. |",
        1,
    )
    assert demoted != text
    assert repaired_windows(demoted) != recovery.REPAIRED
    deferred = text.replace(
        "`fail_step` + `fail` con l'`error` dell'evento. **Riparato.** |",
        "`fail_step` + `fail` con l'`error` dell'evento → M6.2. **Riparato.** |",
        1,
    )
    assert deferred != text
    with pytest.raises(AssertionError):
        for window, retry in documented_windows(deferred).items():
            if REPAIRED_MARK in retry:
                assert MILESTONE.search(retry) is None, window
    assert "5" in windows_under_test() and "zz" not in windows_under_test()


def test_a_window_added_to_the_table_without_a_test_is_detected() -> None:
    """The other half of the derivation: a row nobody tested cannot be added quietly."""
    text = ADR_PATH.read_text(encoding="utf-8")
    grown = text.replace(
        "| 10 | `fail_step` per",
        "| 11 | il processo muore in un modo nuovo | qualsiasi scrittura | nulla | ignoto |\n"
        "| 10 | `fail_step` per",
        1,
    )
    assert grown != text
    documented = set(documented_windows(grown))
    assert "11" in documented
    assert not (documented - recovery.REPAIRED) <= windows_under_test()


def test_a_missing_table_is_detected() -> None:
    with pytest.raises(AssertionError, match="crash-window table"):
        documented_windows("nothing")


# --------------------------------------------------------------------------------------
# The two rules of recover(), and the guard of window 7a (review of M5.3)
# --------------------------------------------------------------------------------------

RULE_ROW = re.compile(r"^\| (EXECUTING|WAITING_APPROVAL) \| (.+?) \| (.+?) \| (.+) \|$")


def documented_recovery_rules(text: str) -> dict[str, str]:
    """Task state -> outcome cell of the two-rule table of ADR 0015 §6."""
    rows = {
        state: outcome
        for line in text.splitlines()
        for state, _, _, outcome in [m.groups() for m in [RULE_ROW.match(line)] if m is not None]
    }
    assert rows, "ADR 0015 must contain the recovery-rules table"
    return rows


def test_the_two_recovery_rules_name_the_states_the_codes_and_the_events() -> None:
    rules = documented_recovery_rules(ADR_PATH.read_text(encoding="utf-8"))
    assert set(rules) == {TaskState.EXECUTING.value, TaskState.WAITING_APPROVAL.value}
    assert ORPHANED in rules[TaskState.EXECUTING.value]
    assert TaskState.FAILED.value in rules[TaskState.EXECUTING.value]
    assert AuditEventType.TASK_EXPIRED.value in rules[TaskState.WAITING_APPROVAL.value]
    assert TaskState.EXPIRED.value in rules[TaskState.WAITING_APPROVAL.value]
    assert RecoverySummary._fields == ("failed", "skipped", "expired")


def test_an_executing_task_with_an_expired_request_belongs_to_the_orphan_rule() -> None:
    """The confirmation of the review, written in the ADR next to the table."""
    text = ADR_PATH.read_text(encoding="utf-8")
    assert "cade nella **prima** riga" in text
    assert "la regola degli orfani lo fallisce" in text
    assert "guarda solo\nWAITING_APPROVAL" in text


def test_the_idempotence_guard_of_window_7a_is_documented_and_coded() -> None:
    """ADR 0015 §8 declared the guard; what it still guards, after M7.2, is silence.

    The guard was written so that the first tool that could not promise "twice is once" could
    not be registered without bringing the STARTED protocol. It did its job: the tool arrived
    (``model.complete``) and the protocol arrived with it (ADR 0021). So a declared ``False`` is
    now legal, and a tool that declares *nothing* is still refused — which is what the guard was
    about, a doubt never reading as a yes.
    """
    text = ADR_PATH.read_text(encoding="utf-8")
    assert "`idempotent: ClassVar[bool]` **senza default**" in text
    assert "`NotIdempotentError`" in text
    assert "STARTED" in text
    assert "M7.2 `model.complete`" in text  # the ADR named the tool that would carry it
    assert "idempotent" not in vars(Tool)  # no default to inherit by mistake
    router, providers = routing_for(FakeModelProvider(FakeClock(), FakeIdGenerator()))
    registry = tools_v01(
        root="/tmp/ela-adr-0015",
        clock=FakeClock(),
        ids=FakeIdGenerator(),
        router=router,
        providers=providers,
    )
    declared = {tool.name: tool.idempotent for tool in registry.tools()}
    assert declared == {"core-echo": True, "workspace-notes": True, "model-complete": False}
    with pytest.raises(NotIdempotentError):
        ToolRegistry((SilentTool(CapabilityId("core.echo"), FakeClock(), FakeIdGenerator()),))


class SilentTool(Tool):
    """A tool that declares no ``idempotent`` at all: what the guard still refuses (ADR 0021 §1)."""

    async def _run(self, arguments: JsonMapping) -> Outcome:  # pragma: no cover - never runs
        return Outcome({})

    def __init__(self, capability_id: CapabilityId, clock: FakeClock, ids: FakeIdGenerator) -> None:
        super().__init__(capability_id, clock, ids, name="silent")


def test_a_drifted_recovery_table_is_detected() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")
    swapped = text.replace("| EXPIRED, `TASK_EXPIRED` |", "| FAILED, `TASK_FAILED` |", 1)
    assert swapped != text
    rules = documented_recovery_rules(swapped)
    assert AuditEventType.TASK_EXPIRED.value not in rules[TaskState.WAITING_APPROVAL.value]
    with pytest.raises(AssertionError, match="recovery-rules table"):
        documented_recovery_rules("nothing")


# ----------------------------------------------------------------------------------------
# The tables are found, not listed (M11.2 dec. L)
# ----------------------------------------------------------------------------------------


def test_the_derivation_finds_the_table_of_adr_0015() -> None:
    """The regression guard: if the header or the row shape drifts, this notices."""
    found = every_documented_window()

    assert {window for adr, window in found if adr == "0015"} == set(
        documented_windows(ADR_PATH.read_text(encoding="utf-8"))
    )


def test_the_derivation_finds_the_table_m11_2_added() -> None:
    """ADR 0036 §11 carries one of its own, and nothing had to be added here for it to count."""
    found = every_documented_window()

    assert ("0036", "L1") in found
    assert "Non riparabile per costruzione" in found[("0036", "L1")]


def test_a_table_in_a_document_nobody_named_is_found(tmp_path: Path) -> None:
    """The negative case, and the whole point: the derivation finds a table it has never seen.

    A hand-written list of documents would pass this file's other tests and quietly stop covering
    at the next ADR — which is the failure it exists to prevent, so it is the failure that has to
    be demonstrated (``CLAUDE.md``: everything in ``make check`` has a test of its negative case).
    """
    invented = tmp_path / "0099-something-nobody-listed.md"
    invented.write_text(
        f"# 0099. A document this test has never heard of\n\n{TABLE_HEADER}\n"
        "|---|---|---|---|---|\n"
        "| Z9 | one thing | another thing | what is left | **Riparato.** |\n\n"
        "And prose after it, which ends the table.\n",
        encoding="utf-8",
    )

    rows = documented_in(invented.read_text(encoding="utf-8"))

    assert rows == {"Z9": "**Riparato.**"}


def test_prose_that_looks_like_a_row_outside_a_table_is_not_one() -> None:
    """The header is what opens a table, so a five-column line elsewhere is just a line."""
    stray = "| 7 | a | b | c | d |\n"

    assert documented_in(stray) == {}
