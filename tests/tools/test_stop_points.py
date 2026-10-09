"""``stop_point``: where a tool listens for the stop of its task (M6.3c, ADR 0054 §3).

Declared by every tool, in two halves and with no default — the form of ``relocatable`` (ADR 0048
§6) —, and proven **tool by tool, on both sides of the point** (decision 2, precisazione C):

* **before the point**: the tool called directly with its task already stopped, and — where the
  tool has a wait before its point — stopped **while a fake port waits at that ``await``**. The
  tool raises ``ToolStopped`` and the port sees no effect. A tool that declares a point and does
  not listen there fails here: its port sees the effect.
* **after the point**: the stop raised the instant after the tool listened there. The effect
  happens, and the result is the tool's own — never ``ToolStopped``.

The set of tools with a ``here`` is read from ``production_tools`` and compared with the set of
tools these tests cover, both ways; ``on_a_node`` is derived from what the orchestrator lets go to a
node, and its three wrong promises are built here with a fake each.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from ela.domain import (
    CapabilityId,
    ExecutionResult,
    ExecutionStatus,
    PermissionDecision,
    RawObservation,
    RawRecognition,
    RawTextLine,
)
from ela.executive import StopOfTask
from ela.permissions import BROWSER_ACT, BROWSER_GUIDED, BROWSER_READ
from ela.ports import (
    ENVELOPE,
    GUIDED_STOPPED,
    NAVIGATION,
    ProbeFamily,
    StopPoint,
    ToolPort,
    ToolStopped,
)
from ela.testing.fakes import (
    FakeBrowser,
    FakeClock,
    FakeIdGenerator,
    FakeLauncher,
    FakeListening,
    FakeModelProvider,
    FakeProbe,
    FakeScreenCapture,
    FakeSpeech,
    FakeStop,
    FakeTextRecognition,
    FakeTool,
    FakeVerifier,
)
from ela.tools import (
    CORE_ECHO,
    FS_READ,
    FS_WRITE,
    MODEL_COMPLETE,
    PERCEPTION_CAPTURE_SCREEN,
    PERCEPTION_LISTEN,
    PERCEPTION_READ_SCREEN_TEXT,
    TERMINAL_RUN,
    VOICE_SPEAK,
    VOICE_SPEAK_ONLINE,
    WORKSPACE_WRITE_NOTE,
    CaptureScreenTool,
    CaptureSettings,
    CaptureStore,
    EchoTool,
    EchoVerifier,
    FsReadTool,
    FsWriteTool,
    ListenTool,
    ReadScreenTextTool,
    SilentStopPointError,
    SpeakOnlineTool,
    SpeakTool,
    Tool,
    ToolRegistry,
    VerifierRegistry,
    WriteNoteTool,
)
from ela.tools.browser import STOPPED as BROWSER_STOPPED
from ela.tools.browser import BrowserActTool, BrowserReadTool
from ela.tools.captures import name_for, text_name_for
from ela.tools.model import ModelCompleteTool
from ela.tools.programs import ProgramProblem, Programs, identity_of
from ela.tools.terminal import STOPPED as TERMINAL_STOPPED
from ela.tools.terminal import TerminalRunTool
from tests.docs.test_adr_travel import travelling
from tests.routing.support import routing_for
from tests.tools.guided import guided_world
from tests.tools.support import allowed
from tests.tools.test_browser_tools import ACT, READ, SITES
from tests.tools.test_browser_tools import decision as browser_decision
from tests.tools.test_captures import png
from tests.tools.test_fs import NOW as FS_NOW
from tests.tools.test_fs import decision as fs_decision
from tests.tools.test_registry import _production
from tests.tools.test_terminal import decision as terminal_decision
from tests.tools.test_terminal import entry, executable, terminal

NOW = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)
CAPTURE_ID = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"


@dataclass
class Subject:
    """One tool on its fakes, the call that makes it act, and how to see that it did."""

    tool: ToolPort
    decision: PermissionDecision
    arguments: dict[str, Any]
    acted: Callable[[], bool]
    """Whether the port saw the effect the call was approved for."""
    hold: Callable[[], Held] | None = None
    """Where the tool waits before its point, held until the test lets it go; ``None`` for a
    tool with no wait of its own before it."""


@dataclass
class Held:
    reached: Callable[[], Awaitable[object]]
    release: Callable[[], None]


class _Gate:
    """A port call held until the test lets it go: shut at first, nothing held."""

    def __init__(self) -> None:
        self.reached: asyncio.Event | None = None
        self.released: asyncio.Event | None = None

    def held(self) -> Held:
        self.reached, self.released = asyncio.Event(), asyncio.Event()
        return Held(self.reached.wait, self.released.set)

    async def passed(self) -> None:
        if self.reached is not None and self.released is not None:
            self.reached.set()
            await self.released.wait()


class _HeldProbe(FakeProbe):
    def __init__(self, answers: list[RawObservation]) -> None:
        super().__init__(answers)
        self.gate = _Gate()

    async def read(self, families: frozenset[ProbeFamily]) -> RawObservation:
        await self.gate.passed()
        return await super().read(families)


class _HeldRecognition(FakeTextRecognition):
    def __init__(self, report: RawRecognition) -> None:
        super().__init__(report=report)
        self.gate = _Gate()

    async def recognise(
        self, source: str, *, languages: tuple[str, ...], region: tuple[float, ...] | None
    ) -> RawRecognition:
        await self.gate.passed()
        return await super().recognise(source, languages=languages, region=region)


# ----------------------------------------------------------------------------------------
# The subjects: every tool with a point, on its fakes
# ----------------------------------------------------------------------------------------


def _note(tmp_path: Path) -> Subject:
    root = tmp_path / "workspace"
    tool = WriteNoteTool(root, FakeClock(), FakeIdGenerator())
    note = "workspace/notes/briefing.md"
    return Subject(
        tool,
        allowed(WORKSPACE_WRITE_NOTE),
        {"path": note, "body": "# Briefing\n"},
        lambda: (root / note).exists(),
    )


def _model(tmp_path: Path) -> Subject:
    provider = FakeModelProvider(FakeClock(), FakeIdGenerator(), reply="una sintesi")
    router, providers = routing_for(provider)
    tool = ModelCompleteTool(router, providers, FakeClock(), FakeIdGenerator())
    return Subject(
        tool,
        allowed(MODEL_COMPLETE),
        {"input": "Riassumi le email della riunione."},
        lambda: bool(provider.requests),
    )


def _store(tmp_path: Path) -> CaptureStore:
    return CaptureStore(CaptureSettings(capture_dir=tmp_path / "captures"))


def _screen(tmp_path: Path) -> Subject:
    helper = FakeScreenCapture(payload=png())
    probe = _HeldProbe([RawObservation(screen_recording_permission=True)])
    tool = CaptureScreenTool(
        _store(tmp_path), helper, probe, FakeClock(datetime.now(tz=UTC)), FakeIdGenerator()
    )
    return Subject(
        tool,
        allowed(PERCEPTION_CAPTURE_SCREEN),
        {"purpose": "reading the failing test output"},
        lambda: bool(helper.calls),
        hold=probe.gate.held,
    )


def _listen(tmp_path: Path) -> Subject:
    listening = FakeListening()
    probe = _HeldProbe([RawObservation(microphone_permission=3)])
    tool = ListenTool(
        _store(tmp_path), listening, probe, FakeClock(), FakeIdGenerator(), enabled=True
    )
    return Subject(
        tool,
        allowed(PERCEPTION_LISTEN),
        {"purpose": "prendere una nota", "seconds": 3},
        lambda: bool(listening.asked),
        hold=probe.gate.held,
    )


def _screen_text(tmp_path: Path) -> Subject:
    store = _store(tmp_path)
    (store.directory / name_for(CAPTURE_ID)).write_bytes(png())
    recognition = _HeldRecognition(
        RawRecognition(
            exit_code=0,
            lines=(RawTextLine(text="riga", confidence=0.9),),
        )
    )
    tool = ReadScreenTextTool(
        store, recognition, FakeClock(), FakeIdGenerator(), languages=("it-IT",)
    )
    return Subject(
        tool,
        allowed(PERCEPTION_READ_SCREEN_TEXT),
        {"capture_id": CAPTURE_ID, "purpose": "x"},
        lambda: (store.directory / text_name_for(CAPTURE_ID)).exists(),
        hold=recognition.gate.held,
    )


def _voice(tmp_path: Path) -> Subject:
    speech = FakeSpeech()
    tool = SpeakTool(speech, FakeClock(), FakeIdGenerator(), voice="Alice", enabled=True)
    return Subject(
        tool,
        allowed(VOICE_SPEAK),
        {"text": "Ho spostato la riunione.", "purpose": "dire l'esito"},
        lambda: bool(speech.said),
    )


def _voice_online(tmp_path: Path) -> Subject:
    speech = FakeSpeech()
    tool = SpeakOnlineTool(
        speech,
        FakeClock(),
        FakeIdGenerator(),
        voice_id="VZOd9FMXDnXRZpGn0thg",
        model="eleven_flash_v2_5",
        enabled=True,
    )
    return Subject(
        tool,
        allowed(VOICE_SPEAK_ONLINE),
        {"text": "No, questa non è una buona idea.", "purpose": "dire l'esito"},
        lambda: bool(speech.said),
    )


def _fs_write(tmp_path: Path) -> Subject:
    root = tmp_path / "files"
    root.mkdir()
    tool = FsWriteTool(root, FakeClock(FS_NOW), FakeIdGenerator())
    return Subject(
        tool,
        fs_decision(FS_WRITE),
        {"path": "note.md", "body": "Giovedì.\n", "overwrite": False},
        lambda: (root / "note.md").exists(),
    )


class _HeldPrograms(Programs):
    """Programs whose comparison — off the loop, in a thread — waits until the test lets it go."""

    def __init__(self, entries: tuple[str, ...]) -> None:
        super().__init__({one: identity_of(one) for one in entries})
        self.reached = threading.Event()
        self.released = threading.Event()

    def problem(self, entry: str) -> ProgramProblem | None:
        self.reached.set()
        if not self.released.wait(5.0):
            raise AssertionError("nobody released the comparison")
        return super().problem(entry)


def _terminal(tmp_path: Path) -> Subject:
    place = tmp_path.resolve()
    root = place / "files"
    (root / "ELA").mkdir(parents=True)
    program = executable(place / "bin" / "eco")
    settings = terminal(root, program)
    launcher = FakeLauncher()
    tool = TerminalRunTool(settings, launcher, FakeClock(NOW), FakeIdGenerator())
    subject = Subject(
        tool,
        terminal_decision(),
        {"program": entry(program), "args": [], "purpose": "la prova"},
        lambda: bool(launcher.commands),
    )

    def hold() -> Held:
        held = _HeldPrograms((entry(program),))
        subject.tool = TerminalRunTool(
            replace(settings, programs=held), launcher, FakeClock(NOW), FakeIdGenerator()
        )
        return Held(lambda: asyncio.to_thread(held.reached.wait), held.released.set)

    subject.hold = hold
    return subject


def _browser_read(tmp_path: Path) -> Subject:
    browser = FakeBrowser()
    return Subject(
        BrowserReadTool(SITES, browser, FakeClock(), FakeIdGenerator()),
        browser_decision(BROWSER_READ),
        dict(READ),
        lambda: bool(browser.opened),
        hold=lambda: _launch(browser),
    )


def _browser_act(tmp_path: Path) -> Subject:
    browser = FakeBrowser()
    return Subject(
        BrowserActTool(SITES, browser, FakeClock(), FakeIdGenerator()),
        browser_decision(BROWSER_ACT),
        dict(ACT),
        lambda: bool(browser.fills or browser.clicks),
        hold=lambda: _launch(browser),
    )


def _guided(tmp_path: Path) -> Subject:
    world = guided_world()
    return Subject(
        world.tool, world.decision, world.arguments, lambda: bool(world.session.launched)
    )


def _launch(browser: FakeBrowser) -> Held:
    browser.launch_reached, browser.launch_released = asyncio.Event(), asyncio.Event()
    return Held(browser.launch_reached.wait, browser.launch_released.set)


SUBJECTS: dict[CapabilityId, Callable[[Path], Subject]] = {
    WORKSPACE_WRITE_NOTE: _note,
    MODEL_COMPLETE: _model,
    PERCEPTION_CAPTURE_SCREEN: _screen,
    PERCEPTION_LISTEN: _listen,
    PERCEPTION_READ_SCREEN_TEXT: _screen_text,
    VOICE_SPEAK: _voice,
    VOICE_SPEAK_ONLINE: _voice_online,
    FS_WRITE: _fs_write,
    TERMINAL_RUN: _terminal,
    BROWSER_READ: _browser_read,
    BROWSER_ACT: _browser_act,
    BROWSER_GUIDED: _guided,
}
WITH_A_WAIT = sorted(
    capability
    for capability, build in SUBJECTS.items()
    if build in {_screen, _listen, _screen_text, _terminal, _browser_read, _browser_act}
)
"""The tools with a wait of their own before the point (proposal 2): the hash of the program, the
probe of the capture and of the microphone, the recognition, the start of the browser."""


# ----------------------------------------------------------------------------------------
# The declaration: no default, silence refused, the values of production
# ----------------------------------------------------------------------------------------


def test_no_tool_inherits_a_stop_point() -> None:
    assert not hasattr(Tool, "stop_point"), "the base gives no default to inherit by mistake"
    assert EchoTool.stop_point == StopPoint(here=None, on_a_node=ENVELOPE)


def test_a_tool_that_says_nothing_is_refused() -> None:
    class _Silent:
        capability_id = CORE_ECHO
        name = "silent"
        idempotent = True
        relocatable = True
        audit_numbers: frozenset[str] = frozenset()

    with pytest.raises(SilentStopPointError) as caught:
        ToolRegistry((_Silent(),))  # type: ignore[arg-type]

    assert "stop_point" in str(caught.value)


@pytest.mark.parametrize(
    "declared",
    [
        ("the envelope", None),
        StopPoint(here="", on_a_node=None),
        StopPoint(here="   ", on_a_node=None),
        StopPoint(here=None, on_a_node=""),
        StopPoint(here=7, on_a_node=None),  # type: ignore[arg-type]
        StopPoint(here=None, on_a_node=True),  # type: ignore[arg-type]
    ],
    ids=repr,
)
def test_a_malformed_stop_point_is_refused_like_silence(declared: object) -> None:
    tool = FakeTool(CORE_ECHO, FakeClock(), FakeIdGenerator())
    tool.stop_point = declared  # type: ignore[assignment]

    with pytest.raises(SilentStopPointError):
        ToolRegistry((tool,))


@pytest.mark.parametrize(
    "declared",
    [StopPoint(None, None), StopPoint("the call", None), StopPoint(None, ENVELOPE)],
    ids=repr,
)
def test_a_sentence_or_none_in_each_half_is_accepted(declared: StopPoint) -> None:
    tool = FakeTool(CORE_ECHO, FakeClock(), FakeIdGenerator(), stop_point=declared)

    assert ToolRegistry((tool,)).get(CORE_ECHO).stop_point == declared


PRODUCTION: dict[str, tuple[str | None, str | None]] = {
    "core.echo": (None, ENVELOPE),
    "workspace.write_note": ("the first write to the disk", None),
    "model.complete": ("the request to the provider", ENVELOPE),
    "perception.capture_screen": ("the capture", None),
    "perception.listen": ("opening the microphone", None),
    "perception.read_screen_text": ("writing the text", None),
    "voice.speak": ("the sound", ENVELOPE),
    "voice.speak_online": ("the request for the synthesis", ENVELOPE),
    "fs.read": (None, ENVELOPE),
    "fs.write": ("the first write to the disk", ENVELOPE),
    "terminal.run": ("the exec of the program", None),
    "browser.read": ("the navigation", None),
    "browser.act": ("the first gesture", None),
    "browser.guided": ("the launch of the session", None),
}
"""The table of proposal 2 of the SPEC, and of ADR 0054 §3 — and since M14.3 the launch of a guided
session (ADR 0060)."""


def test_the_two_halves_of_production_are_the_table(tmp_path: Path) -> None:
    tools, _, _ = _production(tmp_path)

    declared = {
        str(tool.capability_id): (tool.stop_point.here, tool.stop_point.on_a_node)
        for tool in tools.tools()
    }

    assert declared == PRODUCTION
    assert PRODUCTION["browser.read"][0] == NAVIGATION


# ----------------------------------------------------------------------------------------
# on_a_node: derived from what the orchestrator lets go, never promised
# ----------------------------------------------------------------------------------------


def wrong_promises(tools: ToolRegistry, verifiers: VerifierRegistry) -> list[str]:
    """The tools whose ``on_a_node`` does not say what the orchestrator does with them."""
    travels = travelling(tools, verifiers)
    return sorted(
        tool.name
        for tool in tools.tools()
        if tool.stop_point.on_a_node != (ENVELOPE if tool.name in travels else None)
    )


def test_on_a_node_says_the_envelope_for_exactly_what_travels(tmp_path: Path) -> None:
    tools, verifiers, _ = _production(tmp_path)

    assert wrong_promises(tools, verifiers) == []
    assert {name for name, (_, node) in PRODUCTION.items() if node} != set()


def _fake_world(stop_point: StopPoint, *, travels: bool) -> tuple[ToolRegistry, VerifierRegistry]:
    clock, ids = FakeClock(), FakeIdGenerator()
    tools = ToolRegistry(
        (
            EchoTool(clock, ids),
            FakeTool(MODEL_COMPLETE, clock, ids, name="promising", stop_point=stop_point),
        )
    )
    verifiers = VerifierRegistry(
        (EchoVerifier(), FakeVerifier(MODEL_COMPLETE, reads_the_machine=not travels))
    )
    return tools, verifiers


@pytest.mark.parametrize(
    ("stop_point", "travels"),
    [
        (StopPoint(here=None, on_a_node=None), True),
        (StopPoint(here=None, on_a_node=ENVELOPE), False),
        (StopPoint(here=None, on_a_node="listening on the node"), True),
    ],
    ids=["travels-and-says-nothing", "stays-and-says-the-envelope", "promises-to-listen-there"],
)
def test_a_wrong_promise_about_the_node_is_seen(stop_point: StopPoint, travels: bool) -> None:
    tools, verifiers = _fake_world(stop_point, travels=travels)

    assert wrong_promises(tools, verifiers) == ["promising"]


def test_the_right_promise_of_a_fake_is_not_reported() -> None:
    tools, verifiers = _fake_world(StopPoint(here=None, on_a_node=ENVELOPE), travels=True)

    assert wrong_promises(tools, verifiers) == []


# ----------------------------------------------------------------------------------------
# The two sides of the point, tool by tool
# ----------------------------------------------------------------------------------------


def test_every_tool_with_a_point_has_its_two_sides_and_no_other_does(tmp_path: Path) -> None:
    """The derived closure, both ways: a tool that gains a point without its tests fails here, and
    so does a subject left behind by a tool that lost it."""
    tools, _, _ = _production(tmp_path)

    with_a_point = {tool.capability_id for tool in tools.tools() if tool.stop_point.here}

    assert with_a_point == set(SUBJECTS)


@pytest.mark.parametrize("capability", sorted(SUBJECTS))
async def test_before_the_point_the_tool_raises_and_the_port_sees_nothing(
    tmp_path: Path, capability: CapabilityId
) -> None:
    subject = SUBJECTS[capability](tmp_path)
    stop = FakeStop(stopped=True)

    with pytest.raises(ToolStopped):
        await subject.tool.execute(subject.decision, subject.arguments, stop)

    assert not subject.acted()
    assert stop.listened, "it raised without listening"


@pytest.mark.parametrize("capability", WITH_A_WAIT)
async def test_stopped_during_the_wait_before_the_point_the_port_sees_nothing(
    tmp_path: Path, capability: CapabilityId
) -> None:
    """The stop raised while a fake port waits at an ``await`` before the listening: the tool
    did not yet listen when the stop arrived, and it listens after."""
    subject = SUBJECTS[capability](tmp_path)
    assert subject.hold is not None
    held = subject.hold()
    stop = FakeStop()

    running = asyncio.create_task(subject.tool.execute(subject.decision, subject.arguments, stop))
    await held.reached()
    assert stop.listened == []
    stop.event.set()
    held.release()

    with pytest.raises(ToolStopped):
        await running
    assert not subject.acted()


@pytest.mark.parametrize("capability", sorted(SUBJECTS))
async def test_after_the_point_the_effect_happens_and_the_result_is_the_tools(
    tmp_path: Path, capability: CapabilityId
) -> None:
    subject = SUBJECTS[capability](tmp_path)
    here = subject.tool.stop_point.here
    assert here is not None
    stop = FakeStop(after=here)

    result = await subject.tool.execute(subject.decision, subject.arguments, stop)

    assert isinstance(result, ExecutionResult)
    assert subject.acted()
    assert stop.is_set() and here in stop.listened
    assert result.status is not ExecutionStatus.CANCELLED
    assert ok_after_the_point(capability, result)


def ok_after_the_point(capability: CapabilityId, result: ExecutionResult) -> bool:
    """What the tool says when its task stopped right after its point.

    Most tools have nothing between the point and their end, and succeed. ``terminal.run`` runs the
    program and stops it with the task (``ended: stopped_with_the_task``); ``browser.act`` made its
    first gesture and makes no other.
    """
    code = None if result.error is None else result.error.code
    if capability == TERMINAL_RUN:
        return code == TERMINAL_STOPPED and result.output["ended"] == "stopped_with_the_task"
    if capability == BROWSER_ACT:
        return code == BROWSER_STOPPED and result.output["gestures"] == 1
    if capability == BROWSER_GUIDED:
        return code == GUIDED_STOPPED and result.usage is not None
    return result.status is ExecutionStatus.SUCCEEDED


async def test_browser_act_closes_its_page_when_stopped_before_its_first_gesture(
    tmp_path: Path,
) -> None:
    """B-R10 of the re-read: the stop raised in ``_work`` closes the page it opened."""
    browser = FakeBrowser()
    tool = BrowserActTool(SITES, browser, FakeClock(), FakeIdGenerator())
    stop = FakeStop()
    counting = browser.count

    async def stopped_while_counting(page: str, selector: str) -> int:
        stop.event.set()
        return await counting(page, selector)

    browser.count = stopped_while_counting  # type: ignore[method-assign]

    with pytest.raises(ToolStopped):
        await tool.execute(browser_decision(BROWSER_ACT), dict(ACT), stop)

    assert stop.listened == [NAVIGATION, "the first gesture"]
    assert browser.fills == [] and browser.clicks == []
    assert browser.closed == ["page-1"]


async def test_browser_act_opens_through_the_navigation_without_passing_its_point(
    tmp_path: Path,
) -> None:
    """The same stop serves a listening that is not the point (B-R9): the navigation of
    ``browser.act`` is listened to, and does not count as the tool having acted."""
    browser = FakeBrowser()
    tool = BrowserActTool(SITES, browser, FakeClock(), FakeIdGenerator())
    stop = StopOfTask(asyncio.Event(), tool.stop_point.here)
    seen: list[bool] = []
    counting = browser.count

    async def looking(page: str, selector: str) -> int:
        seen.append(stop.passed)
        return await counting(page, selector)

    browser.count = looking  # type: ignore[method-assign]

    result = await tool.execute(browser_decision(BROWSER_ACT), dict(ACT), stop)

    assert result.status is ExecutionStatus.SUCCEEDED
    assert seen and not any(seen), "the navigation was taken for the first gesture"
    assert stop.passed


# ----------------------------------------------------------------------------------------
# The tools whose point is the call: they never listen
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("capability", [CORE_ECHO, FS_READ])
async def test_a_tool_without_a_point_never_listens(tmp_path: Path, capability: str) -> None:
    """For them the point is the call itself (decision 1 of the review): the one listening is the
    executor's, before the grant. Called, they act — whatever the stop says by then."""
    root = tmp_path / "files"
    root.mkdir()
    (root / "a.md").write_text("ciao\n", encoding="utf-8")
    tool: ToolPort
    if capability == CORE_ECHO:
        tool = EchoTool(FakeClock(), FakeIdGenerator())
        decision, arguments = allowed(CORE_ECHO), {"message": "ciao"}
    else:
        tool = FsReadTool(root, FakeClock(FS_NOW), FakeIdGenerator())
        decision, arguments = fs_decision(FS_READ), {"path": "a.md"}
    stop = FakeStop(stopped=True)

    result = await tool.execute(decision, arguments, stop)

    assert tool.stop_point.here is None
    assert result.status is ExecutionStatus.SUCCEEDED
    assert stop.listened == []


# ----------------------------------------------------------------------------------------
# StopOfTask: the stop the executor hands to a call
# ----------------------------------------------------------------------------------------


def test_listen_raises_once_the_task_is_stopped() -> None:
    event = asyncio.Event()
    stop = StopOfTask(event, "the capture")
    event.set()

    with pytest.raises(ToolStopped) as caught:
        stop.listen("the capture")

    assert caught.value.where == "the capture"
    assert not stop.passed
    assert stop.is_set()


def test_listen_records_the_point_only_where_it_was_declared() -> None:
    stop = StopOfTask(asyncio.Event(), "the first gesture")

    stop.listen(NAVIGATION)
    assert not stop.passed
    stop.listen("the first gesture")
    assert stop.passed
    assert not stop.is_set()


def test_a_tool_whose_point_is_the_call_has_passed_it_when_called() -> None:
    assert StopOfTask(asyncio.Event(), None).passed


async def test_stopped_resolves_when_the_task_is_stopped() -> None:
    event = asyncio.Event()
    stop = StopOfTask(event, None)
    waiting = stop.stopped()

    event.set()

    await waiting
    assert stop.is_set()


async def test_browser_act_makes_no_gesture_after_the_stop_between_two_fields(
    tmp_path: Path,
) -> None:
    """Past its point, ``browser.act`` looks at the stop before every gesture (decision 5): the
    first field is filled, the second is not, and the result says one gesture was made."""
    browser = FakeBrowser()
    tool = BrowserActTool(SITES, browser, FakeClock(), FakeIdGenerator())
    two = {**ACT, "fill": [*ACT["fill"], ["input[name=custtel]", "0123"]]}
    stop = FakeStop(after="the first gesture")

    result = await tool.execute(browser_decision(BROWSER_ACT), two, stop)

    assert result.error is not None and result.error.code == BROWSER_STOPPED
    assert result.output["gestures"] == 1
    assert len(browser.fills) == 1 and browser.clicks == []
