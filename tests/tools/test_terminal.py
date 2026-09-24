"""``terminal.run``: a command is argv, the programs are the scope, and the question names what
will really run (M13.2, ADR 0047).

What is asserted here and nowhere else. The tool decides **once**, in the function the question
and the run share: a program whose identity is not the one fixed at start-up, a folder that is not
there, an argument no process can receive — each is refused before anybody is asked, and again
immediately before the launch. The command the launcher receives is exactly what the tool decided:
the declared path as ``argv[0]``, the arguments as a list, the closed environment, the folder, the
timeout and the breath, the two halves of the output. And what comes back is kept as head and
tail, with the cut declared in raw bytes.

The launcher here is a fake that records what it is handed: what a real child receives is
asserted on real children, in ``tests/infrastructure/machine/test_launcher.py``.
"""

from __future__ import annotations

import asyncio
import dataclasses
import re
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ela.domain import (
    DecisionId,
    ExecutionStatus,
    PermissionDecision,
    PermissionOutcome,
    RiskLevel,
)
from ela.permissions import TERMINAL_RUN
from ela.ports import Captured, Ending, Invocation, Ran, Target
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeLauncher
from ela.tools.base import ARGUMENTS_INVALID
from ela.tools.fs import NO_ROOT
from ela.tools.paths import PATH_INVALID, PATH_MISSING, PATH_OUTSIDE_ROOT, PATH_SYMLINK
from ela.tools.programs import (
    NO_PROGRAM,
    NOT_DECLARED,
    PROGRAM_CHANGED,
    PROGRAM_GONE,
    ProgramProblem,
    Programs,
    identity_of,
)
from ela.tools.terminal import (
    ARGUMENTS_UNPASSABLE,
    AUDIT_NUMBERS,
    CLOSED_PATH,
    CWD_NOT_A_FOLDER,
    GRACE_SECONDS,
    LANGUAGE,
    NOT_STARTED,
    PROGRAM,
    RUNS,
    STOPPED,
    TIMEOUT,
    ArgumentLimits,
    Terminal,
    TerminalRunTool,
    decoded,
    stream,
)
from tests.tools.support import PERMISSIONS_BITE

NOW = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)
SCRIPT = "#!/bin/sh\necho eco\n"
MARKER = "girasole-7431"


def decision() -> PermissionDecision:
    return PermissionDecision(
        id=DecisionId(FakeIdGenerator().new_uuid()),
        created_at=NOW,
        capability_id=TERMINAL_RUN,
        risk=RiskLevel.HIGH,
        outcome=PermissionOutcome.ALLOWED,
        reason="allowed for this test",
        expires_at=NOW.replace(hour=11),
    )


def entry(path: Path) -> str:
    """How a program is written in ``ELA_TERMINAL_PROGRAMS`` and in a plan: relative to ``/``."""
    return str(path).lstrip("/")


def executable(path: Path, text: str = SCRIPT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture
def place(tmp_path: Path) -> Path:
    """A resolved folder: the programs are named by their real path, as a user would write it."""
    return tmp_path.resolve()


@pytest.fixture
def root(place: Path) -> Path:
    """``ELA_FS_ROOT``, with the folder of the scope in it: the one a command starts from."""
    declared = place / "files"
    (declared / "ELA").mkdir(parents=True)
    return declared


@pytest.fixture
def program(place: Path) -> Path:
    return executable(place / "bin" / "eco")


def terminal(
    root: Path,
    *programs: Path,
    timeout: int = 120,
    output: int = 64,
    limits: ArgumentLimits | None = None,
) -> Terminal:
    return Terminal(
        programs=Programs.fixed(entry(one) for one in programs),
        root=root,
        scope="ELA",
        timeout_seconds=timeout,
        output_max_bytes=output,
        home="/Users/tu",
        temporary="/private/tmp/tu",
        argument_limits=ArgumentLimits(total=1 << 20, one=1 << 20) if limits is None else limits,
    )


def tool(settings: Terminal, launcher: FakeLauncher | None = None) -> TerminalRunTool:
    return TerminalRunTool(
        settings,
        FakeLauncher() if launcher is None else launcher,
        FakeClock(NOW),
        FakeIdGenerator(),
    )


def call(program: Path | str, *args: str, **more: object) -> dict[str, object]:
    written = entry(program) if isinstance(program, Path) else program
    return {"program": written, "args": list(args), "purpose": "la prova", **more}


def refusal_of(prospected: object) -> str | None:
    refusal = getattr(prospected, "refusal", None)
    return None if refusal is None else refusal.code


# ----------------------------------------------------------------------------------------
# The question: what a call would meet now, read by the same function the run reads
# ----------------------------------------------------------------------------------------


async def test_the_question_names_the_program_the_file_the_folder_and_every_argument(
    root: Path, program: Path
) -> None:
    """Decision 12: the facts of a question about a command, and the tool's own words for them."""
    prospected = await tool(terminal(root, program)).prospect(
        call(program, "la parola di prova è", MARKER)
    )

    assert prospected.refusal is None
    assert prospected.target == Target(resolved=str(program), exists=True, does=RUNS, label=PROGRAM)
    assert prospected.invocation == Invocation(
        program=str(program),
        runs=str(program),
        arguments=("la parola di prova è", MARKER),
        folder=str(root / "ELA"),
        timeout_seconds=120,
        expect_exit=0,
    )


def test_the_sentence_says_the_folder_is_not_a_boundary() -> None:
    """Decision 6: what a yes lets a program do, said where the yes is given."""
    assert "whatever you can" in RUNS
    assert "not what it changes" in RUNS


async def test_a_declared_link_is_asked_about_and_the_question_names_where_it_leads(
    root: Path, place: Path, program: Path
) -> None:
    """Domanda 1, decisa: a declared link is the user's choice, even when it leads outside the list.

    The Guardian compares what the plan writes; the question says what the disk resolves.
    """
    link = place / "links" / "eco"
    link.parent.mkdir()
    link.symlink_to(program)

    prospected = await tool(terminal(root, link)).prospect(call(link))

    assert prospected.refusal is None
    assert prospected.invocation is not None
    assert prospected.invocation.program == str(link)
    assert prospected.invocation.runs == str(program)


async def test_the_expected_code_and_the_folder_are_the_plan_s_when_it_gives_them(
    root: Path, program: Path
) -> None:
    (root / "ELA" / "progetto").mkdir()

    prospected = await tool(terminal(root, program, timeout=30)).prospect(
        call(program, cwd="progetto", expect_exit=1)
    )

    assert prospected.invocation is not None
    assert prospected.invocation.folder == str(root / "ELA" / "progetto")
    assert prospected.invocation.expect_exit == 1
    assert prospected.invocation.timeout_seconds == 30


# ----------------------------------------------------------------------------------------
# Refused before anybody is asked (decision 5): what can be known without launching
# ----------------------------------------------------------------------------------------


async def test_a_path_below_a_declared_program_is_not_a_declared_program(
    root: Path, program: Path
) -> None:
    """Decision 3: ``usr/bin/git/x`` passes the Guardian's prefix, and a file has no children."""
    prospected = await tool(terminal(root, program)).prospect(call(entry(program) + "/x"))

    assert refusal_of(prospected) == NOT_DECLARED


async def test_a_program_that_was_never_there_is_refused_before_the_question(
    root: Path, place: Path
) -> None:
    """Domanda 3, decisa: an entry that is not there does not stop the start-up, nor asks."""
    missing = place / "bin" / "assente"

    prospected = await tool(terminal(root, missing)).prospect(call(missing))

    assert refusal_of(prospected) == NO_PROGRAM


async def test_a_program_deleted_after_the_start_is_gone_and_not_changed(
    root: Path, program: Path
) -> None:
    """Review of M13.2, decision 4: a file that is not there is absent, not «changed» — there is
    nothing to compare. And it was there at the start, which is what tells it from an entry that
    never was (``terminal.no_program``)."""
    settings = terminal(root, program)
    program.unlink()

    prospected = await tool(settings).prospect(call(program))

    assert refusal_of(prospected) == PROGRAM_GONE
    assert prospected.refusal is not None
    assert "was there when ELA started" in prospected.refusal.message
    assert "is not there now" in prospected.refusal.message


async def test_a_declared_link_whose_file_was_deleted_is_gone_too(
    root: Path, place: Path, program: Path
) -> None:
    link = place / "links" / "eco"
    link.parent.mkdir()
    link.symlink_to(program)
    settings = terminal(root, link)
    program.unlink()

    assert refusal_of(await tool(settings).prospect(call(link))) == PROGRAM_GONE


async def test_a_program_that_stopped_being_executable_is_refused(
    root: Path, program: Path
) -> None:
    settings = terminal(root, program)
    program.chmod(0o644)

    assert refusal_of(await tool(settings).prospect(call(program))) == NO_PROGRAM


async def test_a_program_changed_after_the_start_is_refused_and_told_to_restart(
    root: Path, program: Path
) -> None:
    """Decision 4: the identity of the start, compared when the question is composed."""
    settings = terminal(root, program)
    executable(program, "#!/bin/sh\necho altro\n")

    prospected = await tool(settings).prospect(call(program))

    assert refusal_of(prospected) == PROGRAM_CHANGED
    assert prospected.refusal is not None
    assert "changed after ELA started" in prospected.refusal.message
    assert "restart ELA" in prospected.refusal.message


async def test_a_declared_link_pointed_elsewhere_after_the_start_is_refused(
    root: Path, place: Path, program: Path
) -> None:
    """Domanda 1: not the Guardian's to see — it does not read the disk — so the tool's."""
    other = executable(place / "bin" / "altro", "#!/bin/sh\necho altro\n")
    link = place / "links" / "eco"
    link.parent.mkdir()
    link.symlink_to(program)
    settings = terminal(root, link)
    link.unlink()
    link.symlink_to(other)

    assert refusal_of(await tool(settings).prospect(call(link))) == PROGRAM_CHANGED


async def test_a_program_that_appeared_after_the_start_is_a_change_too(
    root: Path, place: Path
) -> None:
    later = place / "bin" / "dopo"
    settings = terminal(root, later)
    executable(later)

    assert refusal_of(await tool(settings).prospect(call(later))) == PROGRAM_CHANGED


@pytest.mark.parametrize(
    ("cwd", "code"),
    [
        ("../fuori", PATH_INVALID),
        ("assente", PATH_MISSING),
        ("collegamento", PATH_SYMLINK),
        ("file.txt", CWD_NOT_A_FOLDER),
    ],
)
async def test_a_folder_that_a_program_cannot_start_from_is_refused_before_the_question(
    root: Path, program: Path, cwd: str, code: str
) -> None:
    """Decision 6: the same classification as ``fs.*``, with the answer turned round."""
    (root / "ELA" / "file.txt").write_text("x", encoding="utf-8")
    (root / "ELA" / "altrove").mkdir()
    (root / "ELA" / "collegamento").symlink_to(root / "ELA" / "altrove")

    prospected = await tool(terminal(root, program)).prospect(call(program, cwd=cwd))

    assert refusal_of(prospected) == code


async def test_a_folder_that_leaves_the_scope_through_the_root_is_refused(
    root: Path, program: Path
) -> None:
    (root / "ELA" / "giù").mkdir()
    (root / "ELA" / "giù" / "su").symlink_to(root)

    prospected = await tool(terminal(root, program)).prospect(call(program, cwd="giù/su"))

    assert refusal_of(prospected) == PATH_OUTSIDE_ROOT


async def test_without_the_folder_of_the_scope_nothing_starts(root: Path, program: Path) -> None:
    (root / "ELA").rmdir()

    assert refusal_of(await tool(terminal(root, program)).prospect(call(program))) == PATH_MISSING


async def test_without_the_root_nothing_starts(root: Path, program: Path) -> None:
    settings = terminal(root, program)
    (root / "ELA").rmdir()
    root.rmdir()

    assert refusal_of(await tool(settings).prospect(call(program))) == NO_ROOT


async def test_an_argument_with_a_nul_byte_cannot_reach_a_process(
    root: Path, program: Path
) -> None:
    prospected = await tool(terminal(root, program)).prospect(call(program, f"a\0{MARKER}"))

    assert refusal_of(prospected) == ARGUMENTS_UNPASSABLE
    assert prospected.refusal is not None
    assert MARKER not in prospected.refusal.message, "the argument never enters a message (§57)"


async def test_an_argument_that_is_not_text_cannot_reach_a_process(
    root: Path, program: Path
) -> None:
    """A lone surrogate has no bytes: refused as unpassable before the question, never raised."""
    prospected = await tool(terminal(root, program)).prospect(call(program, f"{MARKER}\ud800"))

    assert refusal_of(prospected) == ARGUMENTS_UNPASSABLE
    assert prospected.refusal is not None
    assert MARKER not in prospected.refusal.message


async def test_a_folder_that_is_not_text_is_not_a_path(root: Path, program: Path) -> None:
    prospected = await tool(terminal(root, program)).prospect(call(program, cwd="a\ud800b"))

    assert refusal_of(prospected) == PATH_INVALID


async def test_arguments_past_the_total_of_the_system_are_refused_before_the_question(
    root: Path, program: Path
) -> None:
    """Review of M13.2, 5b: the limit is known, so no yes is asked for what would not start — and
    the refusal says which limit, and by how much."""
    limits = ArgumentLimits(total=512, one=1 << 20)

    prospected = await tool(terminal(root, program, limits=limits)).prospect(
        call(program, MARKER * 40)
    )

    assert refusal_of(prospected) == ARGUMENTS_UNPASSABLE
    assert prospected.refusal is not None
    message = prospected.refusal.message
    assert MARKER not in message
    found = re.search(
        r"take (\d+) bytes.* at most (\d+) to a program in all: (\d+) bytes too many", message
    )
    assert found is not None, message
    size, limit, over = (int(one) for one in found.groups())
    assert (limit, over) == (512, size - 512)


async def test_one_argument_past_the_limit_of_one_is_refused_before_the_question(
    root: Path, program: Path
) -> None:
    """Linux passes at most 32 pages in **one** argument, whatever the total allows: a second
    limit, checked apart, and named apart. The size counts the argument's closing NUL, as the
    kernel does."""
    limits = ArgumentLimits(total=1 << 20, one=64)

    prospected = await tool(terminal(root, program, limits=limits)).prospect(
        call(program, "corto", MARKER * 8)
    )

    assert refusal_of(prospected) == ARGUMENTS_UNPASSABLE
    assert prospected.refusal is not None
    message = prospected.refusal.message
    assert MARKER not in message
    assert "argument 2 takes 105 bytes" in message
    assert "at most 64 in one argument: 41 bytes too many" in message


async def test_an_argument_exactly_at_the_limit_of_one_is_asked_about(
    root: Path, program: Path
) -> None:
    limits = ArgumentLimits(total=1 << 20, one=64)

    prospected = await tool(terminal(root, program, limits=limits)).prospect(
        call(program, "x" * 63)
    )

    assert prospected.refusal is None


class Held(Programs):
    """Programs whose comparison waits until the loop releases it.

    In a thread it is released at once. On the loop nothing can release it — the loop is the one
    waiting —, and it gives up after ``HELD_SECONDS`` saying so.
    """

    def __init__(self, entries: tuple[str, ...]) -> None:
        super().__init__({one: identity_of(one) for one in entries})
        self.released = threading.Event()

    def problem(self, entry: str) -> ProgramProblem | None:
        if not self.released.wait(HELD_SECONDS):
            raise AssertionError("the program was compared on the loop: nobody could release it")
        return super().problem(entry)


HELD_SECONDS = 5.0


async def test_the_program_is_hashed_off_the_loop(root: Path, program: Path) -> None:
    """Review of M13.2, 5a: a declared program can be as large as it likes — 357 MB hash in
    120 ms on this Mac —, and a loop that waits for it stops every other request of ELA, the
    phone's answer included. Asserted as a fact, not a time: the loop answers while it hashes."""
    held = Held((entry(program),))
    settings = dataclasses.replace(terminal(root, program), programs=held)

    async def release() -> None:
        held.released.set()

    prospected, _ = await asyncio.gather(tool(settings).prospect(call(program)), release())

    assert prospected.refusal is None


@pytest.mark.parametrize(
    "arguments",
    [
        {"program": 3, "args": [], "purpose": "x"},
        {"program": "bin/eco", "args": "echo x", "purpose": "x"},
        {"program": "bin/eco", "args": ["a", 1], "purpose": "x"},
        {"program": "bin/eco", "args": [], "purpose": "x", "cwd": 2},
        {"program": "bin/eco", "args": [], "purpose": "x", "expect_exit": True},
        {"program": "bin/eco", "args": [], "purpose": "x", "expect_exit": "0"},
    ],
)
async def test_a_tool_never_trusts_its_caller(
    root: Path, program: Path, arguments: dict[str, object]
) -> None:
    """§28: the Guardian validated the schema; the tool checks again."""
    assert refusal_of(await tool(terminal(root, program)).prospect(arguments)) == ARGUMENTS_INVALID


# ----------------------------------------------------------------------------------------
# The run: what the launcher is handed, and what comes back
# ----------------------------------------------------------------------------------------


async def test_the_launcher_receives_exactly_what_the_tool_decided(
    root: Path, program: Path
) -> None:
    """Decisions 1, 3, 6, 7, 8: argv as a list, the closed environment, the folder, the times."""
    launcher = FakeLauncher()
    runner = tool(terminal(root, program, timeout=30, output=64), launcher)

    await runner.execute(decision(), call(program, "a b", "'$HOME'", '"x"'))

    (command,) = launcher.commands
    assert command.argv == (str(program), "a b", "'$HOME'", '"x"')
    assert dict(command.environment) == {
        "PATH": CLOSED_PATH,
        "HOME": "/Users/tu",
        "TMPDIR": "/private/tmp/tu",
        "LANG": LANGUAGE,
    }
    assert command.folder == str(root / "ELA")
    assert command.timeout == 30
    assert command.grace == GRACE_SECONDS
    assert (command.head, command.tail) == (32, 32)


def test_the_closed_environment_is_the_four_names_and_nothing_else() -> None:
    assert CLOSED_PATH == "/usr/bin:/bin:/usr/sbin:/sbin"
    assert LANGUAGE == "C.UTF-8"
    assert GRACE_SECONDS == 2


async def test_a_program_changed_between_the_yes_and_the_launch_never_launches(
    root: Path, program: Path
) -> None:
    """Decision 4, second moment: the identity is compared again immediately before the exec."""
    launcher = FakeLauncher()
    runner = tool(terminal(root, program), launcher)
    assert (await runner.prospect(call(program))).refusal is None
    executable(program, "#!/bin/sh\necho cambiato\n")

    result = await runner.execute(decision(), call(program))

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None and result.error.code == PROGRAM_CHANGED
    assert launcher.commands == ()


async def test_a_program_deleted_between_the_yes_and_the_launch_is_gone_and_never_launches(
    root: Path, program: Path
) -> None:
    """The same distinction for a question already open: the file vanished, it did not change."""
    launcher = FakeLauncher()
    runner = tool(terminal(root, program), launcher)
    assert (await runner.prospect(call(program))).refusal is None
    program.unlink()

    result = await runner.execute(decision(), call(program))

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None and result.error.code == PROGRAM_GONE
    assert launcher.commands == ()


async def test_a_program_that_ended_by_itself_is_a_success_whatever_its_code(
    root: Path, program: Path
) -> None:
    """Decision 9: the tool does not decide what a code means; the verifier compares it."""
    launcher = FakeLauncher(
        Ran(Ending.EXITED, code=1, stdout=Captured(head=b"trovato\n", total=8), stderr=Captured())
    )

    result = await tool(terminal(root, program), launcher).execute(
        decision(), call(program, "a", "b")
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    output = result.output
    assert output["program"] == str(program)
    assert output["runs"] == str(program)
    assert output["args"] == ("a", "b"), "a list, frozen as the domain freezes every array"
    assert output["argument_count"] == 2
    assert output["cwd"] == str(root / "ELA")
    assert output["expect_exit"] == 0
    assert output["ended"] == "exited"
    assert output["exit_code"] == 1
    assert output["signal"] is None
    assert output["stdout"] == {
        "head": "trovato\n",
        "tail": "",
        "cut_after": 8,
        "missing": 0,
        "shown": 8,
        "total": 8,
        "replaced": 0,
    }


async def test_a_program_stopped_by_a_signal_says_which(root: Path, program: Path) -> None:
    launcher = FakeLauncher(Ran(Ending.SIGNALLED, signal=9))

    result = await tool(terminal(root, program), launcher).execute(decision(), call(program))

    assert result.status is ExecutionStatus.SUCCEEDED
    assert (result.output["ended"], result.output["signal"]) == ("signalled", 9)
    assert result.output["exit_code"] is None


@pytest.mark.parametrize(
    ("ending", "code"), [(Ending.TIMED_OUT, TIMEOUT), (Ending.STOPPED, STOPPED)]
)
async def test_what_ela_stopped_is_a_failure_that_carries_its_partial_output(
    root: Path, program: Path, ending: Ending, code: str
) -> None:
    """Decision 7, and «La ripresa»: a half answer that says it is one, and never retried."""
    launcher = FakeLauncher(Ran(ending, signal=15, stdout=Captured(head=b"mezza", total=5)))

    result = await tool(terminal(root, program), launcher).execute(decision(), call(program))

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert result.error.code == code
    assert result.error.retryable is False, "running a HIGH again is a new question"
    assert result.output["ended"] == "stopped_by_ela"
    assert result.output["stdout"]["head"] == "mezza"


async def test_what_the_kernel_refused_is_the_one_refusal_after_a_yes(
    root: Path, program: Path
) -> None:
    """Decision 5: an exec format nobody could have known about without trying."""
    launcher = FakeLauncher(Ran(Ending.NOT_STARTED, failure="OSError: [Errno 8] Exec format error"))

    result = await tool(terminal(root, program), launcher).execute(decision(), call(program))

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None and result.error.code == NOT_STARTED
    assert "Exec format error" in result.error.message


async def test_neither_the_arguments_nor_the_output_enter_an_error_message(
    root: Path, program: Path
) -> None:
    """Decision 8: an error message enters the audit, several times over."""
    launcher = FakeLauncher(
        Ran(
            Ending.TIMED_OUT,
            stdout=Captured(head=MARKER.encode(), total=13),
            stderr=Captured(head=MARKER.encode(), total=13),
        )
    )

    result = await tool(terminal(root, program), launcher).execute(
        decision(), call(program, MARKER)
    )

    assert result.error is not None
    assert MARKER not in result.error.message


def test_the_tool_is_not_idempotent_and_declares_its_numbers() -> None:
    """Decision 7: a STARTED record before the launch; decision 10: the numbers of the audit."""
    assert TerminalRunTool.idempotent is False
    assert (
        frozenset(
            {
                "argument_count",
                "exit_code",
                "signal",
                "stdout.shown",
                "stdout.total",
                "stderr.shown",
                "stderr.total",
            }
        )
        == AUDIT_NUMBERS
        == TerminalRunTool.audit_numbers
    )
    assert {key.partition(".")[0] for key in AUDIT_NUMBERS} <= TerminalRunTool.output_keys


# ----------------------------------------------------------------------------------------
# Head and tail: the cut on a character boundary, and declared in raw bytes (decision 8)
# ----------------------------------------------------------------------------------------


def test_what_fits_is_kept_whole_in_the_head() -> None:
    kept = stream(Captured(head=b"uno\n", tail=b"due\n", total=8))

    assert (kept.head, kept.tail) == ("uno\ndue\n", "")
    assert (kept.cut_after, kept.missing, kept.shown, kept.total) == (8, 0, 8, 8)


def test_a_cut_says_where_it_is_and_how_much_is_missing() -> None:
    kept = stream(Captured(head=b"1\n2\n", tail=b"9\n10\n", total=100))

    assert (kept.head, kept.tail) == ("1\n2\n", "9\n10\n")
    assert kept.cut_after == 4
    assert kept.shown == 9
    assert kept.missing == 91
    assert kept.total == 100


def test_the_cut_falls_on_a_character_and_the_bytes_it_leaves_are_counted_missing() -> None:
    """«è» is two bytes: a head that ends in its first one gives it back, and so does a tail."""
    accent = "è".encode()
    kept = stream(Captured(head=b"ab" + accent[:1], tail=accent[1:] + b"cd", total=50))

    assert (kept.head, kept.tail) == ("ab", "cd")
    assert kept.replaced == 0
    assert kept.cut_after == 2
    assert kept.shown == 4
    assert kept.missing == 46


def test_bytes_that_are_not_text_are_replaced_and_counted() -> None:
    kept = stream(Captured(head=b"a\xffb\xfe", total=4))

    assert kept.head == "a\ufffdb\ufffd"
    assert kept.replaced == 2
    assert kept.shown == 4, "the numbers count raw bytes, so a replacement does not bend them"


@given(st.binary(max_size=200))
def test_the_decoder_says_what_python_says_and_counts_what_it_replaced(data: bytes) -> None:
    text, replaced = decoded(data)

    assert text == data.decode("utf-8", errors="replace")
    # Each replacement adds one U+FFFD; the ones the program printed itself survive ``ignore``.
    printed = data.decode("utf-8", errors="ignore").count("\ufffd")
    assert replaced == text.count("\ufffd") - printed


def test_a_sequence_that_the_program_really_printed_as_a_replacement_is_not_counted() -> None:
    """U+FFFD written by the program is text, not a byte ELA failed to read."""
    _, replaced = decoded("\ufffd".encode())

    assert replaced == 0


def test_the_numbers_of_the_two_streams_go_in_the_result_as_the_model_dumps_them() -> None:
    kept = stream(Captured(head=b"x" * 3, tail=b"y" * 3, total=10))

    assert kept.model_dump(mode="json") == {
        "head": "xxx",
        "tail": "yyy",
        "cut_after": 3,
        "missing": 4,
        "shown": 6,
        "total": 10,
        "replaced": 0,
    }


def test_a_head_of_bytes_that_continue_nothing_is_left_as_it_is() -> None:
    """Binary output: no character to cut on, so the head is kept and its bytes replaced."""
    kept = stream(Captured(head=b"\x80\x81\x82\x83", tail=b"z", total=20))

    assert kept.head == "\ufffd" * 4
    assert kept.cut_after == 4
    assert kept.replaced == 4


@pytest.mark.skipif(not PERMISSIONS_BITE, reason="this user reads files whatever their mode")
async def test_a_program_that_cannot_be_read_is_one_whose_identity_nobody_can_vouch_for(
    root: Path, program: Path
) -> None:
    program.chmod(0o111)
    try:
        prospected = await tool(terminal(root, program)).prospect(call(program))
    finally:
        program.chmod(0o755)

    assert refusal_of(prospected) == NO_PROGRAM
