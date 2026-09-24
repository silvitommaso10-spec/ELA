"""The verifier of ``terminal.run``: it says what it verified, and never that the effect happened.

Decision 9 of M13.2 (ADR 0047). There is no independent source for what a program printed — the
case of ``core.echo``, and the voice's «it does not prove that anybody heard anything» — so the
three conditions are about what *can* be checked: that the program ended by itself with the code
the **plan** expected, that nothing of its output was cut or replaced, and that the file the
declared path leads to, **read now from the disk**, still has the identity of the start-up. Each
has its negative case. And it reads the Core's disk, so it declares ``reads_the_machine`` and the
capability does not travel (decision 11).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from ela.tools.programs import PROGRAM_CHANGED, Programs

from ela.domain import ExecutionId, ExecutionResult, ExecutionStatus
from ela.permissions import TERMINAL_RUN
from ela.tools.verifiers import (
    TERMINAL_EXIT_CODE_MATCHES,
    TERMINAL_EXIT_MISMATCH,
    TERMINAL_OUTPUT_INCOMPLETE,
    TERMINAL_OUTPUT_WHOLE,
    TERMINAL_PROGRAM_UNCHANGED,
    TERMINAL_VERIFIER_NAME,
    TerminalRunVerifier,
)

NOW = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)
MARKER = "girasole-7431"
EVERY = (TERMINAL_EXIT_CODE_MATCHES, TERMINAL_OUTPUT_WHOLE, TERMINAL_PROGRAM_UNCHANGED)


def whole(text: str = "") -> dict[str, Any]:
    size = len(text.encode())
    return {
        "head": text,
        "tail": "",
        "cut_after": size,
        "missing": 0,
        "shown": size,
        "total": size,
        "replaced": 0,
    }


@pytest.fixture
def program(tmp_path: Path) -> Path:
    path = tmp_path.resolve() / "bin" / "eco"
    path.parent.mkdir()
    path.write_text("#!/bin/sh\necho eco\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def entry(path: Path) -> str:
    return str(path).lstrip("/")


def ran(program: Path, **changes: Any) -> ExecutionResult:
    output: dict[str, Any] = {
        "program": str(program),
        "runs": str(program),
        "args": [MARKER],
        "argument_count": 1,
        "cwd": "/Users/tu/Documenti/ELA",
        "expect_exit": 0,
        "ended": "exited",
        "exit_code": 0,
        "signal": None,
        "stdout": whole(MARKER + "\n"),
        "stderr": whole(),
    }
    output.update(changes)
    return ExecutionResult(
        id=ExecutionId(UUID("00000000-0000-4000-8000-00000000c0de")),
        created_at=NOW,
        capability_id=TERMINAL_RUN,
        status=ExecutionStatus.SUCCEEDED,
        tool_name="terminal-run",
        output=output,
    )


def arguments(program: Path, **more: Any) -> dict[str, Any]:
    return {"program": entry(program), "args": [MARKER], "purpose": "la prova", **more}


def verifier(*programs: Path) -> TerminalRunVerifier:
    return TerminalRunVerifier(Programs.fixed(entry(one) for one in programs))


async def failures_of(
    checker: TerminalRunVerifier, condition: str, call: dict[str, Any], result: ExecutionResult
) -> list[str]:
    return [failure.code for failure in await checker.verify((condition,), call, result)]


def test_it_is_named_and_knows_three_conditions_and_reads_the_machine() -> None:
    assert TerminalRunVerifier.reads_the_machine is True
    assert TerminalRunVerifier.conditions == frozenset(EVERY)
    assert verifier().name == TERMINAL_VERIFIER_NAME
    assert verifier().capability_id == TERMINAL_RUN


async def test_a_program_that_ended_by_itself_with_the_expected_code_holds(program: Path) -> None:
    checker = verifier(program)

    assert await checker.verify(EVERY, arguments(program), ran(program)) == ()


async def test_the_expected_code_is_the_plan_s_and_not_the_tool_s(program: Path) -> None:
    """Criterion 13: a ``grep`` that finds nothing exits 1, and a plan that looks for an absence
    says so. The code the tool copied into its result is not the expectation: the plan's is."""
    checker = verifier(program)
    found_nothing = ran(program, exit_code=1, expect_exit=0)

    assert (
        await failures_of(
            checker, TERMINAL_EXIT_CODE_MATCHES, arguments(program, expect_exit=1), found_nothing
        )
        == []
    )
    assert await failures_of(
        checker, TERMINAL_EXIT_CODE_MATCHES, arguments(program), found_nothing
    ) == [TERMINAL_EXIT_MISMATCH]


async def test_a_program_stopped_by_a_signal_did_not_end_by_itself(program: Path) -> None:
    checker = verifier(program)
    signalled = ran(program, ended="signalled", exit_code=None, signal=9)

    assert await failures_of(
        checker, TERMINAL_EXIT_CODE_MATCHES, arguments(program), signalled
    ) == [TERMINAL_EXIT_MISMATCH]


async def test_the_sentence_says_what_was_verified_and_nothing_more(program: Path) -> None:
    """§63: «finito da solo con il codice atteso», never «the command worked»."""
    (failure,) = await verifier(program).verify(
        (TERMINAL_EXIT_CODE_MATCHES,), arguments(program), ran(program, exit_code=2)
    )

    assert "did not end by itself with the expected code" in failure.message
    assert "worked" not in failure.message and "succeeded" not in failure.message
    assert MARKER not in failure.message, "never the arguments nor the output (§57)"
    assert failure.details["expected"] == 0 and failure.details["exit_code"] == 2


@pytest.mark.parametrize(
    "stdout",
    [
        {**whole("12"), "tail": "89", "missing": 6, "shown": 4, "total": 10, "cut_after": 2},
        {**whole("a\ufffd"), "cut_after": 2, "shown": 2, "total": 2, "replaced": 1},
    ],
    ids=["cut", "replaced"],
)
async def test_an_output_cut_or_replaced_is_not_whole(
    program: Path, stdout: dict[str, Any]
) -> None:
    checker = verifier(program)

    assert await failures_of(
        checker, TERMINAL_OUTPUT_WHOLE, arguments(program), ran(program, stdout=stdout)
    ) == [TERMINAL_OUTPUT_INCOMPLETE]
    assert await failures_of(
        checker, TERMINAL_OUTPUT_WHOLE, arguments(program), ran(program, stderr=stdout)
    ) == [TERMINAL_OUTPUT_INCOMPLETE]


async def test_a_program_changed_on_the_disk_is_caught_by_reading_the_disk(program: Path) -> None:
    checker = verifier(program)
    program.write_text("#!/bin/sh\necho altro\n", encoding="utf-8")

    assert await failures_of(
        checker, TERMINAL_PROGRAM_UNCHANGED, arguments(program), ran(program)
    ) == [PROGRAM_CHANGED]


async def test_a_result_that_names_another_file_than_the_start_is_caught(
    program: Path, tmp_path: Path
) -> None:
    checker = verifier(program)

    assert await failures_of(
        checker,
        TERMINAL_PROGRAM_UNCHANGED,
        arguments(program),
        ran(program, runs=str(tmp_path / "altrove")),
    ) == [PROGRAM_CHANGED]


async def test_a_result_with_numbers_that_are_not_a_stream_is_not_verified(program: Path) -> None:
    """A verifier trusts neither the Guardian nor the tool (§28)."""
    checker = verifier(program)
    broken = ran(program, stdout={"head": 3})
    spelled = ran(program, exit_code="0")

    assert await failures_of(checker, TERMINAL_OUTPUT_WHOLE, arguments(program), broken)
    assert await failures_of(checker, TERMINAL_EXIT_CODE_MATCHES, arguments(program), spelled)
