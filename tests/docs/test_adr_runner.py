"""The tables of ADR 0019 and ``ela.executive.runner`` say the same thing.

Same pattern as the other ADR tests: §4 (where ``device_id`` goes), §5 (the two properties that
make the loop re-entrant, and the test that fixes each), §8 (the crash windows) and §10 (the
outcomes of a run) are read from the document and checked against the code and the tests. Each
table has a distinctive row shape, so no table is mistaken for another.

Without this file the ADR would describe a walk the code no longer takes — and §8 in particular
would claim repairs nobody tests.
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.domain import TaskState
from ela.executive import OUTCOMES, RUNNABLE_STATES, RunOutcome
from tests.executive import test_runner_recovery

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0019-task-runner.md"
ADR_0038 = ADR_PATH.with_name("0038-work-protocol.md")
"""ADR 0019 is immutable, so the outcome M12.2 adds lives in the ADR that added it, and §10 is
read as the **union** of the two tables (:func:`documented_outcomes`)."""
RECOVERY_TESTS = Path(test_runner_recovery.__file__)

WINDOW_ROW = re.compile(r"^\| (R\d) \| (.+?) \| (.+?) \| (.+?) \| (.+?) \|$")
"""§8: the crash windows, named ``R<n>`` — the only table whose first cell is one."""
OUTCOME_ROW = re.compile(
    r"^\| `(COMPLETED|FAILED|DENIED|CANCELLED|EXPIRED|WAITING_\w+)` \| (.+?) \|$"
)
"""§10: an outcome in backticks and one cell of prose; two columns, unlike every other table."""
WORK_OUTCOME_ROW = re.compile(r"^\| `([A-Z_]+)` \| ([^|]+?) \| ([^|]+?) \|$")
"""ADR 0038 §10: the outcome M12.2 adds, with what it means for the task and the step beside it."""
PROPERTY_ROW = re.compile(r"^\| (uno step .+?) \| (.+?) \| ((?:`test_\w+`(?:, )?)+) \|$")
"""§5: the two re-entrancy properties, each with the tests that fix it."""
DEVICE_ROW = re.compile(r"^\| ([^|]+?) \| ((?:[^|]|\\\|)+?) \| ([^|]+?) \|$")
"""§4: who receives the node and what they do with it; read from §4, so the shape can be loose."""

REPAIRED = re.compile(r"\*\*Riparato\.?\*\*")
NOT_REPAIRED = re.compile(r"\*\*Non riparato")


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def section(title: str) -> str:
    """The body of the ``### <title>`` section, up to the next heading of any level."""
    text = adr_text()
    start = text.index(f"### {title}")
    rest = text[start + 4 :]
    end = rest.find("\n### ")
    tail = rest.find("\n## ")
    if tail != -1 and (end == -1 or tail < end):
        end = tail
    return rest if end == -1 else rest[:end]


def rows(pattern: re.Pattern[str], body: str) -> list[re.Match[str]]:
    return [m for m in (pattern.match(line) for line in body.splitlines()) if m is not None]


# --------------------------------------------------------------------------------------
# §10: the outcomes of a run
# --------------------------------------------------------------------------------------


def work_section() -> str:
    """ADR 0038 §10, the section that adds an outcome: up to the next heading."""
    text = ADR_0038.read_text(encoding="utf-8")
    rest = text[text.index("## 10. ") :]
    end = rest.find("\n## ", 1)
    return rest if end == -1 else rest[:end]


def documented_outcomes() -> set[str]:
    """Every outcome the two ADRs name, in union: ADR 0019 §10 and ADR 0038 §10.

    The negative of the union is the one that matters and it is unchanged: an outcome with a row
    in **neither** table fails the equality below, whichever table somebody forgot.
    """
    later = {m.group(1) for m in rows(WORK_OUTCOME_ROW, work_section())}
    assert later, "ADR 0038 §10 must contain the row of the outcome it adds"
    return {m.group(1) for m in rows(OUTCOME_ROW, section("10."))} | later


def test_the_adr_lists_every_outcome_the_code_can_return() -> None:
    assert documented_outcomes() == {outcome.name for outcome in RunOutcome}


def test_adr_0019_still_lists_seven_and_adr_0038_adds_the_eighth() -> None:
    """ADR 0019 as history: ``ASSIGNED`` is M12.2's, and the ADR that brought it says so alone."""
    assert {m.group(1) for m in rows(OUTCOME_ROW, section("10."))} == {
        outcome.name for outcome in RunOutcome
    } - {RunOutcome.ASSIGNED.name}
    assert {m.group(1) for m in rows(WORK_OUTCOME_ROW, work_section())} == {
        RunOutcome.ASSIGNED.name
    }


def test_the_outcome_table_is_the_one_the_code_maps_states_through() -> None:
    """Every closed or waiting state of ``OUTCOMES`` is an outcome the ADRs name — and the one
    M12.2 adds comes from no state at all: ``ASSIGNED`` is the outcome of a call (ADR 0038 §10)."""
    assert {outcome.name for outcome in OUTCOMES.values()} <= documented_outcomes()
    assert RunOutcome.ASSIGNED not in set(OUTCOMES.values())


def test_no_two_states_share_an_outcome() -> None:
    """One state, one outcome (review of M6.3): a task somebody stopped and one whose deadline
    passed are two facts, and an outcome that merged them could not be split later."""
    assert len(set(OUTCOMES.values())) == len(OUTCOMES)
    assert OUTCOMES[TaskState.CANCELLED] is not OUTCOMES[TaskState.EXPIRED]
    assert "Uno stato, un esito" in section("10.")


def test_the_states_a_plan_is_walked_from_are_the_two_the_adr_names() -> None:
    body = section("10.")
    assert "`QUEUED` o `EXECUTING`" in body
    assert frozenset({TaskState.QUEUED, TaskState.EXECUTING}) == RUNNABLE_STATES
    assert not RUNNABLE_STATES & set(OUTCOMES)


def test_every_state_is_walkable_an_outcome_or_refused_at_the_door() -> None:
    """A state cannot mean "keep going" and "stop" at once, and none may mean neither: the two
    left over are the ones §10 says are refused, because they have no plan to walk yet."""
    assert set(OUTCOMES) & RUNNABLE_STATES == set()
    refused = set(TaskState) - set(OUTCOMES) - RUNNABLE_STATES
    assert refused == {TaskState.CREATED, TaskState.PLANNING}
    assert "`CREATED` e\n`PLANNING`" in section("10.")


# --------------------------------------------------------------------------------------
# §8: the crash windows
# --------------------------------------------------------------------------------------


def test_the_windows_the_adr_calls_repaired_are_the_ones_with_a_test() -> None:
    """The rule of ADR 0015 §8, applied here: **Riparato** in the document and
    ``test_window_<n>_…`` in the tests are two names for the same fact."""
    repaired = {m.group(1) for m in rows(WINDOW_ROW, section("8.")) if REPAIRED.search(m.group(5))}
    assert repaired == test_runner_recovery.REPAIRED


def test_every_repaired_window_has_a_test_named_after_it() -> None:
    source = RECOVERY_TESTS.read_text(encoding="utf-8")
    for window in sorted(test_runner_recovery.REPAIRED):
        assert f"async def test_window_{window.lower()}_" in source, window


def test_every_declared_window_has_a_test_too() -> None:
    """A window nobody repairs still has a test: what a retry does there is a fact, not a guess."""
    source = RECOVERY_TESTS.read_text(encoding="utf-8")
    declared = {
        m.group(1) for m in rows(WINDOW_ROW, section("8.")) if NOT_REPAIRED.search(m.group(5))
    }
    assert declared == {"R1", "R7", "R9"}
    for window in sorted(declared):
        assert f"async def test_window_{window.lower()}_" in source, window


def test_the_windows_are_numbered_without_gaps() -> None:
    numbered = [m.group(1) for m in rows(WINDOW_ROW, section("8."))]
    assert numbered == [f"R{n}" for n in range(1, len(numbered) + 1)]


def test_every_window_is_either_repaired_or_declared() -> None:
    for row in rows(WINDOW_ROW, section("8.")):
        retry = row.group(5)
        assert bool(REPAIRED.search(retry)) != bool(NOT_REPAIRED.search(retry)), row.group(1)


# --------------------------------------------------------------------------------------
# §5: the two properties that make the loop re-entrant
# --------------------------------------------------------------------------------------


def test_the_re_entrancy_properties_name_tests_that_exist() -> None:
    """Both properties were asked for explicitly in the review of the M6.3 spec: they are to be
    tested, not only implemented, so the ADR names the tests and this checks they are there."""
    listed = rows(PROPERTY_ROW, section("5."))
    assert len(listed) == 2
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in RECOVERY_TESTS.parent.glob("test_runner*.py")
    )
    named = [name for row in listed for name in re.findall(r"`(test_\w+)`", row.group(3))]
    assert len(named) >= 3
    for name in named:
        assert f"async def {name}(" in sources, name


def test_the_runner_picks_a_running_step_before_a_ready_one() -> None:
    """The property itself, read off the source: ``ready()`` is the fallback, not the first
    choice. The behaviour has its own tests; this keeps the ADR from drifting from the code."""
    source = (
        Path(__file__).resolve().parents[2] / "src" / "ela" / "executive" / "runner.py"
    ).read_text(encoding="utf-8")
    assert "return running[0] if running else graph.ready()[0]" in source


# --------------------------------------------------------------------------------------
# §4: where the node goes, and where it must not go
# --------------------------------------------------------------------------------------


def test_the_adr_says_the_node_reaches_no_rule_of_the_guardian() -> None:
    body = section("4.")
    assert "non entra in nessuna regola del Guardian" in body
    guardian = (
        Path(__file__).resolve().parents[2] / "src" / "ela" / "permissions" / "guardian.py"
    ).read_text(encoding="utf-8")
    start = guardian.index("    def decide(")
    decide = guardian[start : guardian.index("    async def authorize(")]
    assert "device" not in decide, "decide() must not see a node: it would be a second policy"


def test_the_adr_lists_the_four_places_the_node_reaches() -> None:
    """Four recipients and no fifth: whoever adds one must say so in the ADR first."""
    listed = [
        m.group(1)
        for m in rows(DEVICE_ROW, section("4."))
        if m.group(1) not in {"Chi"} and not m.group(1).startswith("-")
    ]
    assert listed == [
        "`Executor.execute`",
        "`AuditEvent` di `TOOL_EXECUTED` e `EXECUTION_VERIFIED`",
        "`ErrorMetadata` di una verifica fallita",
        "`AuthorizingGuardianPort.authorize`",
    ]


def test_the_local_device_placeholder_is_gone_and_what_came_back_is_an_id() -> None:
    """ADR 0019 §4 killed a placeholder *device*; M12.2 brings back an **id**, and only that.

    The two are not the same thing and the difference is the decision: a constant standing in for
    a node nobody chose was a lie the executor told itself, while ``LOCAL_DEVICE_ID`` is the one id
    of the system that is deterministic *because it is this machine* (ADR 0016 §4) — and it is the
    criterion of where a call runs (ADR 0038 §3, dec. A). So the placeholder must stay dead: every
    mention in the executor is of the id, and none of a device.
    """
    executor = (
        Path(__file__).resolve().parents[2] / "src" / "ela" / "executive" / "executor.py"
    ).read_text(encoding="utf-8")
    assert "La costante sparisce." in section("4.")
    assert "LOCAL_DEVICE_ID" in executor
    assert re.findall(r"LOCAL_DEVICE\w*", executor) == ["LOCAL_DEVICE_ID"] * executor.count(
        "LOCAL_DEVICE_ID"
    )
    assert "in-process se e solo se il nodo scelto è `LOCAL_DEVICE_ID`" in ADR_0038.read_text(
        encoding="utf-8"
    )
