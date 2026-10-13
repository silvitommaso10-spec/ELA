"""The capabilities that look or listen refuse while the sign-in window is open (M13.9, ADR 0063
§7; decision 41).

ELA opens a window for the user to sign in by hand and promises to read nothing of it. That
promise is the browser's; the screen and the microphone are another road, and a photograph, a
reading or a recording made meanwhile would carry what the user types. So the three tools are
handed **one question** by the composition — «not now?», answered with the reason or with
``None`` — and refuse with a code of their own, **in two places**: before the question, because a
yes spent on a call that cannot start is a yes wasted; and in the run, because a call a grant or
a policy already allowed never passes through the question.

The tools do not learn what the reason is about: they say it as it was given.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from ela.domain import ExecutionStatus, RawObservation
from ela.ports import Prospect
from ela.testing.fakes import (
    FakeClock,
    FakeIdGenerator,
    FakeListening,
    FakeProbe,
    FakeScreenCapture,
    FakeStop,
    FakeTextRecognition,
)
from ela.tools import (
    ARGUMENTS_INVALID,
    PERCEPTION_CAPTURE_SCREEN,
    PERCEPTION_LISTEN,
    PERCEPTION_READ_SCREEN_TEXT,
    CaptureScreenTool,
    CaptureSettings,
    CaptureStore,
    ListenTool,
    ReadScreenTextTool,
)
from ela.tools.base import Tool
from ela.tools.listen import LISTEN_LOGIN_WINDOW_OPEN
from ela.tools.screen import SCREEN_LOGIN_WINDOW_OPEN
from tests.tools.support import allowed
from tests.tools.test_captures import png
from tests.tools.test_listen import HEARD
from tests.tools.test_screen_text import CAPTURE_ID
from tests.tools.test_screen_text import capture as a_capture

REASON = "the window where you sign in by hand is open"

NotNow = Callable[[], Awaitable[str | None]]


class Window:
    """The composition's answer, as a test turns it: open, or not — and how often it was asked."""

    def __init__(self, *, open: bool) -> None:
        self.open = open
        self.asked = 0

    async def __call__(self) -> str | None:
        self.asked += 1
        return REASON if self.open else None


@dataclass
class Case:
    """One of the three tools on its fakes: what it is called with, the code it refuses with,
    what it says it does not do — and ``touched``, everything it would have touched."""

    tool: Tool
    arguments: dict[str, Any]
    code: str
    meanwhile: str
    touched: Callable[[], list[object]]
    store: CaptureStore

    def held(self) -> list[str]:
        return sorted(entry.name for entry in self.store.directory.iterdir())


def _store(tmp_path: Path) -> CaptureStore:
    return CaptureStore(CaptureSettings(capture_dir=tmp_path / "captures"))


def the_capture(tmp_path: Path, not_now: NotNow) -> Case:
    helper = FakeScreenCapture(payload=png())
    probe = FakeProbe([RawObservation(screen_recording_permission=True)])
    store = _store(tmp_path)
    tool = CaptureScreenTool(
        store,
        helper,
        probe,
        FakeClock(datetime.now(tz=UTC)),
        FakeIdGenerator(),
        not_now=not_now,
    )
    return Case(
        tool,
        {"purpose": "leggere un errore"},
        SCREEN_LOGIN_WINDOW_OPEN,
        "ELA does not photograph the screen meanwhile",
        lambda: [*helper.calls, *probe.calls],
        store,
    )


def the_reading(tmp_path: Path, not_now: NotNow) -> Case:
    recognition = FakeTextRecognition()
    store = _store(tmp_path)
    a_capture(store)
    tool = ReadScreenTextTool(
        store,
        recognition,
        FakeClock(),
        FakeIdGenerator(),
        languages=("it-IT", "en-US"),
        not_now=not_now,
    )
    return Case(
        tool,
        {"capture_id": CAPTURE_ID, "purpose": "leggere un errore"},
        SCREEN_LOGIN_WINDOW_OPEN,
        "ELA does not read the screen meanwhile",
        lambda: [*recognition.calls],
        store,
    )


def the_listening(tmp_path: Path, not_now: NotNow) -> Case:
    listening = FakeListening(report=HEARD)
    probe = FakeProbe([RawObservation(microphone_permission=3)])
    store = _store(tmp_path)
    tool = ListenTool(store, listening, probe, FakeClock(), FakeIdGenerator(), not_now=not_now)
    return Case(
        tool,
        {"purpose": "prendere una nota", "seconds": 3},
        LISTEN_LOGIN_WINDOW_OPEN,
        "ELA does not listen meanwhile",
        lambda: [*listening.asked, *probe.calls],
        store,
    )


EVERY = pytest.mark.parametrize(
    "made",
    [
        pytest.param(the_capture, id=PERCEPTION_CAPTURE_SCREEN),
        pytest.param(the_reading, id=PERCEPTION_READ_SCREEN_TEXT),
        pytest.param(the_listening, id=PERCEPTION_LISTEN),
    ],
)
Made = Callable[[Path, NotNow], Case]


@EVERY
async def test_while_the_window_is_open_the_call_would_not_start(
    tmp_path: Path, made: Made
) -> None:
    """Before the question: nobody is asked to approve what ELA already knows it will refuse —
    and nothing is touched to find out, not even the permission."""
    case = made(tmp_path, Window(open=True))
    before = case.held()

    refusal = (await case.tool.prospect(case.arguments)).refusal

    assert refusal is not None
    assert (refusal.code, refusal.retryable) == (case.code, True)
    assert refusal.message == f"{REASON}: {case.meanwhile}"
    assert refusal.tool_name == case.tool.name
    assert case.touched() == [] and case.held() == before


@EVERY
async def test_a_call_already_allowed_is_refused_all_the_same(tmp_path: Path, made: Made) -> None:
    """In the run: a grant or a policy allows a call without a question, and the window is open
    all the same. One fact, one sentence: the run refuses with what the question would have said."""
    case = made(tmp_path, Window(open=True))
    before = case.held()
    said = (await case.tool.prospect(case.arguments)).refusal

    result = await case.tool.execute(allowed(case.tool.capability_id), case.arguments, FakeStop())

    assert result.status is ExecutionStatus.FAILED and result.error is not None
    assert said is not None
    assert (result.error.code, result.error.message) == (case.code, said.message)
    assert result.error.retryable is True, "the window closes: the same call can succeed later"
    assert dict(result.output) == {}
    assert case.touched() == [] and case.held() == before


@EVERY
async def test_with_no_window_there_is_nothing_to_refuse_and_the_call_runs(
    tmp_path: Path, made: Made
) -> None:
    window = Window(open=False)
    case = made(tmp_path, window)

    prospect = await case.tool.prospect(case.arguments)
    result = await case.tool.execute(allowed(case.tool.capability_id), case.arguments, FakeStop())

    assert prospect == Prospect()
    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert case.touched() != []
    assert window.asked == 2, "asked before the question, and again in the run"


@EVERY
async def test_the_window_is_asked_about_at_every_call_and_never_remembered(
    tmp_path: Path, made: Made
) -> None:
    """A window that closes frees the next call; one that opens after a yes stops the run."""
    window = Window(open=True)
    case = made(tmp_path, window)
    decision = allowed(case.tool.capability_id)

    refused = await case.tool.execute(decision, case.arguments, FakeStop())
    window.open = False
    asked_then_opened = await case.tool.prospect(case.arguments)
    window.open = True
    after_the_yes = await case.tool.execute(decision, case.arguments, FakeStop())
    window.open = False
    done = await case.tool.execute(decision, case.arguments, FakeStop())

    assert refused.error is not None and refused.error.code == case.code
    assert asked_then_opened.refusal is None
    assert after_the_yes.error is not None and after_the_yes.error.code == case.code
    assert done.status is ExecutionStatus.SUCCEEDED, done.error


@EVERY
async def test_a_call_that_is_not_one_is_said_before_the_window(tmp_path: Path, made: Made) -> None:
    """Malformed is malformed whatever is open: the arguments first, and then nobody is asked
    whether this is the moment."""
    window = Window(open=True)
    case = made(tmp_path, window)

    result = await case.tool.execute(
        allowed(case.tool.capability_id), {**case.arguments, "purpose": ""}, FakeStop()
    )

    assert result.error is not None and result.error.code == ARGUMENTS_INVALID
    assert window.asked == 0


@EVERY
async def test_a_tool_built_with_no_question_refuses_nothing(tmp_path: Path, made: Made) -> None:
    """The default of the three constructors: a tool nobody handed a question to looks and
    listens as it did before M13.9 — the composition is where the question comes from."""
    asked = made(tmp_path, Window(open=False)).tool
    default = type(asked).__init__.__kwdefaults__["not_now"]

    assert await default() is None


def test_each_tool_declares_its_code_and_the_screen_s_two_share_one() -> None:
    assert SCREEN_LOGIN_WINDOW_OPEN == "screen.login_window_open"
    assert LISTEN_LOGIN_WINDOW_OPEN == "listen.login_window_open"
    assert SCREEN_LOGIN_WINDOW_OPEN in CaptureScreenTool.error_codes
    assert SCREEN_LOGIN_WINDOW_OPEN in ReadScreenTextTool.error_codes
    assert LISTEN_LOGIN_WINDOW_OPEN in ListenTool.error_codes
    assert LISTEN_LOGIN_WINDOW_OPEN not in CaptureScreenTool.error_codes
    assert SCREEN_LOGIN_WINDOW_OPEN not in ListenTool.error_codes
