"""``terminal.run`` never runs the vault's program — **asked at the launch, not believed from the
start-up** (M13.9c; decision 28 of the review after the red CI of ``56c672c``, 2026-11-10).

The start-up refuses a configuration in which the vault's program is one of the terminal's, by
identity (``tests/composition/test_the_vault_program_is_not_a_terminal_program.py``). But a program
that is not there at the start cannot be compared by identity, and what a path leads to changes
after it: **a check of the start-up is a belief about the launch, and a belief does not decide an
action**. So the terminal's own table of programs is told the vault's program, and asks **every time
it decides** — when the question is composed and again right before the launch — whether the
program, resolved at that instant, is the vault's: by resolved path, or by device and inode.

Measured on the code of before, on 2026-11-10
(``.git/m13.13-reference/review-56c672c/oggi-28.txt``):

* a program of the terminal **absent at the start that becomes a second name of the vault's
  program** was refused already — ``terminal.program_changed``: the table had fixed its absence —,
  and is now refused **as what it is**, with a code of its own;
* a program of the terminal there at the start, with **the vault's program born after it as a
  second name of that same file**, **was launched**: nothing had changed for the table. It is the
  hole this closes.

Files of the test's, in its own folder: no ``bw`` is ever launched, and the launcher launches
nothing.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from ela.domain import ExecutionStatus
from ela.permissions import TERMINAL_RUN
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeLauncher, FakeStop
from ela.tools.programs import PROGRAM_CODES, VAULT_PROGRAM, Programs, same_program
from ela.tools.terminal import ArgumentLimits, Terminal, TerminalRunTool
from ela.tools.verifiers import TERMINAL_PROGRAM_UNCHANGED, TerminalRunVerifier
from tests.tools.test_terminal import NOW, call, decision, entry, executable, refusal_of
from tests.tools.test_verifiers import succeeded

VAULT_SCRIPT = "#!/bin/sh\necho il programma del vault finto\n"


@pytest.fixture
def place(tmp_path: Path) -> Path:
    return tmp_path.resolve()


@pytest.fixture
def root(place: Path) -> Path:
    declared = place / "files"
    (declared / "ELA").mkdir(parents=True)
    return declared


def terminal(root: Path, *programs: Path, vault: Path | None) -> Terminal:
    """The terminal of ``programs``, fixed now, told the vault's program — as the composition
    builds it."""
    return Terminal(
        programs=Programs.fixed(
            (entry(one) for one in programs), never=None if vault is None else str(vault)
        ),
        root=root,
        scope="ELA",
        timeout_seconds=120,
        output_max_bytes=64,
        home="/Users/tu",
        temporary="/private/tmp/tu",
        argument_limits=ArgumentLimits(total=1 << 20, one=1 << 20),
    )


def tool(settings: Terminal, launcher: FakeLauncher) -> TerminalRunTool:
    return TerminalRunTool(settings, launcher, FakeClock(NOW), FakeIdGenerator())


# ----------------------------------------------------------------------------------------
# One program, by identity: the comparison the start-up and the launch share
# ----------------------------------------------------------------------------------------


def test_the_same_path_is_the_same_program_also_when_nothing_is_there(place: Path) -> None:
    assert same_program(str(place / "bin" / "bw"), str(place / "bin" / "bw"))


def test_a_link_to_a_program_is_that_program(place: Path) -> None:
    vault = executable(place / "vault" / "bw", VAULT_SCRIPT)
    (place / "tool").symlink_to(vault)

    assert same_program(str(place / "tool"), str(vault))


def test_a_second_name_of_a_file_is_that_program(place: Path) -> None:
    vault = executable(place / "vault" / "bw", VAULT_SCRIPT)
    os.link(vault, place / "tool")

    assert same_program(str(place / "tool"), str(vault))


def test_a_copy_in_another_file_is_another_program(place: Path) -> None:
    """By identity, not by content and not by name: declared in ADR 0066 §3."""
    vault = executable(place / "vault" / "bw", VAULT_SCRIPT)
    (place / "other").mkdir()
    shutil.copy2(vault, place / "other" / "bw")

    assert not same_program(str(place / "other" / "bw"), str(vault))


def test_a_program_that_is_not_there_is_no_other_program_s_file(place: Path) -> None:
    vault = executable(place / "vault" / "bw", VAULT_SCRIPT)

    assert not same_program(str(place / "absent"), str(vault))
    assert not same_program(str(vault), str(place / "absent"))


# ----------------------------------------------------------------------------------------
# At the launch
# ----------------------------------------------------------------------------------------


async def test_a_program_absent_at_the_start_that_becomes_the_vault_s_is_refused_as_that(
    root: Path, place: Path
) -> None:
    """The scenario of decision 28. The table would refuse it as changed; said as what it is."""
    vault = executable(place / "vault" / "bw", VAULT_SCRIPT)
    later = place / "bin" / "dopo"
    later.parent.mkdir()
    launcher = FakeLauncher()
    runner = tool(terminal(root, later, vault=vault), launcher)
    os.link(vault, later)

    prospected = await runner.prospect(call(later))
    result = await runner.execute(decision(), call(later), FakeStop())

    assert refusal_of(prospected) == VAULT_PROGRAM, "before the question"
    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None and result.error.code == VAULT_PROGRAM
    assert launcher.commands == ()


async def test_the_vault_s_program_born_after_the_start_as_a_second_name_is_never_launched(
    root: Path, place: Path
) -> None:
    """The hole: the terminal's program did not change — the same file, the same content — and
    the vault's program, which was not there at the start, is now that file."""
    program = executable(place / "bin" / "eco")
    vault = place / "vault" / "bw"
    vault.parent.mkdir()
    launcher = FakeLauncher()
    runner = tool(terminal(root, program, vault=vault), launcher)
    os.link(program, vault)

    prospected = await runner.prospect(call(program))
    result = await runner.execute(decision(), call(program), FakeStop())

    assert refusal_of(prospected) == VAULT_PROGRAM
    assert result.error is not None and result.error.code == VAULT_PROGRAM
    assert launcher.commands == (), "the vault's program was launched with a plan's arguments"


async def test_the_vault_s_program_that_becomes_a_link_to_a_terminal_program_is_never_launched(
    root: Path, place: Path
) -> None:
    """By resolved path: the vault's line now leads to the terminal's program."""
    program = executable(place / "bin" / "eco")
    vault = place / "vault" / "bw"
    vault.parent.mkdir()
    launcher = FakeLauncher()
    runner = tool(terminal(root, program, vault=vault), launcher)
    vault.symlink_to(program)

    result = await runner.execute(decision(), call(program), FakeStop())

    assert result.error is not None and result.error.code == VAULT_PROGRAM
    assert launcher.commands == ()


async def test_a_program_that_becomes_the_vault_s_between_the_yes_and_the_launch_never_launches(
    root: Path, place: Path
) -> None:
    """Before the question when it can be, **and in any case before the launch**."""
    program = executable(place / "bin" / "eco")
    vault = place / "vault" / "bw"
    vault.parent.mkdir()
    launcher = FakeLauncher()
    runner = tool(terminal(root, program, vault=vault), launcher)
    assert (await runner.prospect(call(program))).refusal is None, "a question is asked"
    os.link(program, vault)

    result = await runner.execute(decision(), call(program), FakeStop())

    assert result.error is not None and result.error.code == VAULT_PROGRAM
    assert launcher.commands == ()


async def test_a_copy_of_the_vault_s_program_is_another_program_and_runs(
    root: Path, place: Path
) -> None:
    """The negative case: another file with the same bytes is not recognised (declared)."""
    vault = executable(place / "vault" / "bw", VAULT_SCRIPT)
    program = executable(place / "bin" / "eco", VAULT_SCRIPT)
    launcher = FakeLauncher()
    runner = tool(terminal(root, program, vault=vault), launcher)

    result = await runner.execute(decision(), call(program), FakeStop())

    assert result.error is None or result.error.code != VAULT_PROGRAM
    assert len(launcher.commands) == 1


async def test_with_no_vault_s_program_declared_nothing_is_compared(
    root: Path, place: Path
) -> None:
    program = executable(place / "bin" / "eco")
    launcher = FakeLauncher()

    await tool(terminal(root, program, vault=None), launcher).execute(
        decision(), call(program), FakeStop()
    )

    assert len(launcher.commands) == 1


def test_the_code_is_one_of_the_terminal_s_and_the_tool_declares_it() -> None:
    assert VAULT_PROGRAM == "terminal.vault_program"
    assert VAULT_PROGRAM in PROGRAM_CODES
    assert VAULT_PROGRAM in TerminalRunTool.error_codes


async def test_the_verifier_says_it_too_of_a_program_that_became_the_vault_s_after_the_run(
    root: Path, place: Path
) -> None:
    """The verifier reads the same table after the run: what ran cannot be vouched for."""
    program = executable(place / "bin" / "eco")
    vault = place / "vault" / "bw"
    vault.parent.mkdir()
    settings = terminal(root, program, vault=vault)
    os.link(program, vault)

    (failure,) = await TerminalRunVerifier(settings.programs).verify(
        [TERMINAL_PROGRAM_UNCHANGED],
        call(program),
        succeeded(TERMINAL_RUN, output={"runs": str(program)}),
    )

    assert failure.code == VAULT_PROGRAM
    assert VAULT_PROGRAM in TerminalRunVerifier.failure_codes
