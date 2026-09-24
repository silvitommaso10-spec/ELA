"""``terminal.run`` through the executor, and the channel of numbers into ``TOOL_EXECUTED`` (M13.2).

Two things this milestone adds to the pipeline, asserted where the pipeline is.

**The numbers of a command enter the audit, and only numbers** (decision 10, Domanda 2; ADR 0047).
The executor is the only writer of ``TOOL_EXECUTED`` and the only caller of a tool, so it is where
a value that is not an integer is refused: a tool of this machine that produces one fails the step
with :data:`~ela.executive.AUDIT_NUMBER_INVALID` and nothing of it reaches the trail; a node that
delivers one is refused at the gate, before any write.

**The HIGH grant is spent before the action for the terminal too** (ADR 0046 §3, «La ripresa»):
the real tool, a launcher that counts its launches, and the window of a crash between the spend and
the launch — which asks again and launches nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ela.composition.system import UuidGenerator
from ela.domain import (
    AuditEventType,
    ExecutionStatus,
    PermissionOutcome,
    StepState,
    Task,
    TaskState,
    TaskStep,
)
from ela.executive import AUDIT_NUMBER_INVALID, EXECUTION_INTERRUPTED, VERIFICATION_FAILED
from ela.permissions import TERMINAL_RUN, terminal_run
from ela.ports import Captured, Command, Ending, Ran
from ela.testing.fakes import FakeClock, FakeLauncher
from ela.tools.programs import PROGRAM_GONE, Programs
from ela.tools.terminal import ArgumentLimits, Terminal, TerminalRunTool
from ela.tools.verifiers import (
    TERMINAL_EXIT_CODE_MATCHES,
    TERMINAL_PROGRAM_UNCHANGED,
    TerminalRunVerifier,
)
from tests.executive.support import (
    Crashes,
    SimulatedCrash,
    World,
    crashing_world,
    world,
)
from tests.executive.test_executor_remote import answered, handed
from tests.permissions.support import ECHO

E = AuditEventType
MARKER = "girasole-7431"


async def executed(w: World, task_id: object) -> dict[str, object]:
    (event,) = [e for e in await w.events(task_id) if e.event_type is E.TOOL_EXECUTED]
    return dict(event.payload)


# ----------------------------------------------------------------------------------------
# The channel of numbers
# ----------------------------------------------------------------------------------------


async def test_the_declared_numbers_of_a_result_enter_tool_executed() -> None:
    w = world()
    w.tool(ECHO.id).audit_numbers = frozenset({"count", "stream.total"})
    w.tool(ECHO.id).output = {"count": 3, "stream": {"total": 40, "head": MARKER}}
    task, step = await w.running(ECHO.id)

    await w.execute(task.id, step.id)

    assert (await executed(w, task.id))["numbers"] == {"count": 3, "stream.total": 40}
    assert MARKER not in json.dumps([e.model_dump(mode="json") for e in await w.events(task.id)])


async def test_a_tool_that_declares_no_numbers_writes_no_numbers() -> None:
    """``fs.read`` does not adopt the channel (Domanda 2): its ``TOOL_EXECUTED`` keeps its keys."""
    w = world()
    task, step = await w.running(ECHO.id)

    await w.execute(task.id, step.id)

    assert "numbers" not in await executed(w, task.id)


@pytest.mark.parametrize("value", [MARKER, 3.5, True, [1]])
async def test_a_value_that_is_not_an_integer_fails_the_step_and_never_reaches_the_trail(
    value: object,
) -> None:
    """The negative case of the channel: a string cannot pass, and neither can a lookalike."""
    w = world()
    w.tool(ECHO.id).audit_numbers = frozenset({"count"})
    w.tool(ECHO.id).output = {"count": value}
    task, step = await w.running(ECHO.id)

    execution = await w.execute(task.id, step.id)

    assert execution.result is not None
    assert execution.result.status is ExecutionStatus.FAILED
    assert execution.result.error is not None
    assert execution.result.error.code == AUDIT_NUMBER_INVALID
    assert await w.step_state(task.id, step.id) is StepState.FAILED
    assert (await executed(w, task.id))["numbers"] == {"count": None}
    trail = json.dumps([e.model_dump(mode="json") for e in await w.events(task.id)])
    assert MARKER not in trail


async def test_a_node_that_delivers_a_value_that_is_not_an_integer_is_refused_at_the_gate() -> None:
    """A ``ValueError`` is a ``422`` (ADR 0038 §4), and nothing is written."""
    w = world()
    w.tool(ECHO.id).audit_numbers = frozenset({"count"})
    step, remote, assignment = await handed(w)
    await w.executor.begin(assignment.id, remote.id)  # type: ignore[attr-defined]

    with pytest.raises(ValueError, match="count"):
        await w.executor.deliver(  # type: ignore[attr-defined]
            assignment.id, remote.id, answered(output={"count": MARKER})
        )

    assert await w.results.for_step(assignment.task_id, step.id) == ()  # type: ignore[attr-defined]


# ----------------------------------------------------------------------------------------
# The terminal, with its real tool and its real verifier
# ----------------------------------------------------------------------------------------


class Uninstaller(FakeLauncher):
    """A program that deletes itself while it runs — what an uninstaller does."""

    def __init__(self, program: Path, ran: Ran) -> None:
        super().__init__(ran)
        self.program = program

    async def run(self, command: Command) -> Ran:
        self.program.unlink()
        return await super().run(command)


def terminal_parts(
    tmp_path: Path, *, uninstalls: bool = False
) -> tuple[str, TerminalRunTool, TerminalRunVerifier, FakeLauncher]:
    place = tmp_path.resolve()
    (place / "files" / "ELA").mkdir(parents=True)
    program = place / "bin" / "eco"
    program.parent.mkdir()
    program.write_text("#!/bin/sh\necho eco\n", encoding="utf-8")
    program.chmod(0o755)
    entry = str(program).lstrip("/")
    programs = Programs.fixed([entry])
    ran = Ran(Ending.EXITED, code=0, stdout=Captured(head=b"eco\n", total=4))
    launcher = Uninstaller(program, ran) if uninstalls else FakeLauncher(ran)
    settings = Terminal(
        programs=programs,
        root=place / "files",
        scope="ELA",
        timeout_seconds=120,
        output_max_bytes=64,
        home="/Users/tu",
        temporary="/tmp/tu",
        argument_limits=ArgumentLimits(total=1 << 20, one=1 << 20),
    )
    tool = TerminalRunTool(settings, launcher, FakeClock(), UuidGenerator())
    return entry, tool, TerminalRunVerifier(programs), launcher


def terminal_world(tmp_path: Path) -> tuple[World, str, FakeLauncher]:
    entry, tool, verifier, launcher = terminal_parts(tmp_path)
    w = world(catalogue=(terminal_run((entry,)),), tools=(tool,), verifiers=(verifier,))
    return w, entry, launcher


def crashing_terminal_world(tmp_path: Path) -> tuple[World, Crashes, str, FakeLauncher]:
    entry, tool, verifier, launcher = terminal_parts(tmp_path)
    w, crashes = crashing_world(
        catalogue=(terminal_run((entry,)),), tools=(tool,), verifiers=(verifier,)
    )
    return w, crashes, entry, launcher


async def asked_and_approved(
    w: World, entry: str, conditions: tuple[str, ...] = (TERMINAL_EXIT_CODE_MATCHES,)
) -> tuple[Task, TaskStep]:
    task, step = await w.running(
        TERMINAL_RUN,
        arguments={"program": entry, "args": [MARKER], "purpose": "la prova"},
        conditions=conditions,
    )
    asked = await w.execute(task.id, step.id)
    assert asked.approval is not None, "a HIGH asks at every use"
    await w.engine.approve(task.id, await w.answered(asked.approval))
    await w.engine.start(task.id)
    return task, step


async def test_an_approved_command_spends_its_grant_and_every_record_names_it(
    tmp_path: Path,
) -> None:
    w, entry, launcher = terminal_world(tmp_path)
    task, step = await asked_and_approved(w, entry)

    execution = await w.execute(task.id, step.id)

    assert execution.decision is not None
    assert execution.decision.outcome is PermissionOutcome.ALLOWED
    (grant,) = await w.store.for_capability(TERMINAL_RUN)
    assert await w.store.uses(grant.id) == 1
    stored = await w.results.for_step(task.id, step.id)
    assert [r.status for r in stored] == [ExecutionStatus.STARTED, ExecutionStatus.SUCCEEDED]
    assert [r.authorization_id for r in stored] == [grant.id, grant.id]
    payload = await executed(w, task.id)
    assert payload["uses"] == 1
    assert payload["numbers"] == {
        "argument_count": 1,
        "exit_code": 0,
        "signal": None,
        "stderr.shown": 0,
        "stderr.total": 0,
        "stdout.shown": 4,
        "stdout.total": 4,
    }
    assert len(launcher.commands) == 1


async def test_a_program_gone_after_its_run_fails_the_step_unverified_and_keeps_what_it_printed(
    tmp_path: Path,
) -> None:
    """Review of M13.2, decision 4, through the executor. The program ran and deleted itself: its
    result is ``SUCCEEDED`` and keeps what it printed, because that happened. The step is
    ``FAILED``, ``verification.failed`` naming ``terminal.program_gone``, **not retryable**: ELA
    cannot vouch that what ran was the program declared, and a HIGH action run again is a new
    question, not a retry."""
    entry, tool, verifier, launcher = terminal_parts(tmp_path, uninstalls=True)
    w = world(catalogue=(terminal_run((entry,)),), tools=(tool,), verifiers=(verifier,))
    task, step = await asked_and_approved(
        w, entry, (TERMINAL_EXIT_CODE_MATCHES, TERMINAL_PROGRAM_UNCHANGED)
    )

    execution = await w.execute(task.id, step.id)

    assert len(launcher.commands) == 1
    assert execution.result is not None
    assert execution.result.status is ExecutionStatus.SUCCEEDED
    assert execution.result.output["stdout"]["head"] == "eco\n"
    assert execution.graph.states[step.id] is StepState.FAILED
    assert (await w.task(task.id)).state is TaskState.FAILED
    error = execution.verification.error if execution.verification else None
    assert error is not None and error.code == VERIFICATION_FAILED
    assert error.retryable is False
    (failure,) = error.details["failures"]
    assert (failure["condition"], failure["code"]) == (TERMINAL_PROGRAM_UNCHANGED, PROGRAM_GONE)


async def test_a_crash_between_the_spend_and_the_launch_asks_again_and_launches_nothing(
    tmp_path: Path,
) -> None:
    """Window 6 of ADR 0015 §8, for the terminal: the yes is gone, and so is nothing else."""
    w, crashes, entry, launcher = crashing_terminal_world(tmp_path)
    task, step = await asked_and_approved(w, entry)

    crashes.authorizations.arm("consume", after=True)
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)
    crashes.disarm()
    retry = await w.execute(task.id, step.id)

    assert retry.decision is not None
    assert retry.decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert retry.approval is not None
    assert launcher.commands == ()


async def test_an_interrupted_command_is_closed_as_interrupted_and_never_launched_again(
    tmp_path: Path,
) -> None:
    """Decision 7: ``idempotent = False``, so a STARTED record before the launch, and a retry that
    finds it without an outcome fails the step instead of launching a second time."""
    w, crashes, entry, launcher = crashing_terminal_world(tmp_path)
    task, step = await asked_and_approved(w, entry)

    crashes.results.arm("add", lambda result: result.status is not ExecutionStatus.STARTED)
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)
    crashes.disarm()
    retry = await w.execute(task.id, step.id)

    assert len(launcher.commands) == 1, "launched once, and never again"
    assert retry.result is not None and retry.result.status is ExecutionStatus.STARTED
    assert await w.step_state(task.id, step.id) is StepState.FAILED
    events = await w.events(task.id)
    (failed,) = [e for e in events if e.event_type is E.STEP_FAILED]
    assert failed.error is not None and failed.error.code == EXECUTION_INTERRUPTED
