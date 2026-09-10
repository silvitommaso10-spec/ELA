"""``perception.listen``: the microphone, and the two things that keep silence from becoming words.

Two of these tests assert on the adapter's ``asked`` rather than on a file, and that is the point
rather than a style: **not opening the microphone** is the behaviour under test in both, and a
behaviour is only proven by watching for it. Asserting "no transcript appeared" would pass equally
well for a tool that opened the device and threw the answer away — which is not the same thing at
all when the device is a microphone in somebody's room.

And one of them is the milestone in a single line:
:func:`test_a_denied_microphone_never_becomes_a_transcript`. Measured on 2026-09-09, opening a
refused microphone *succeeds* and delivers zeros, and a transcriber turns thirty seconds of zeros
into «Grazie a tutti.» — so without the preflight a denied permission would produce a result
shaped like a success, containing words nobody said.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ela.domain import (
    ExecutionStatus,
    RawHeardSegment,
    RawHeardToken,
    RawObservation,
    RawTranscript,
)
from ela.ports import (
    LISTEN_DENIED_BY_SYSTEM,
    LISTEN_DISABLED,
    LISTEN_NO_SIGNAL,
    LISTEN_PERMISSION_UNREADABLE,
    LISTEN_TIMEOUT,
)
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeListening, FakeProbe
from ela.tools import (
    ARGUMENTS_INVALID,
    PERCEPTION_LISTEN,
    CaptureSettings,
    CaptureStore,
    ListenTool,
)
from ela.tools.captures import CAPTURE_UNREADABLE, jsonl_segments
from ela.tools.screen import SCREEN_STORE_FULL
from tests.tools.support import allowed

DECISION = allowed(PERCEPTION_LISTEN)
HELD_ID = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"

GRANTED = RawObservation(microphone_permission=3)
DENIED = RawObservation(microphone_permission=2)
NOT_DETERMINED = RawObservation(microphone_permission=0)
UNREADABLE = RawObservation(microphone_permission=None)
NONSENSE = RawObservation(microphone_permission=99)

HEARD = RawTranscript(
    exit_code=0,
    recorded_seconds=3.21,
    peak=3330,
    language="it",
    segments=(
        RawHeardSegment(
            text=" Ela, sposta la call di domani.",
            start_ms=0,
            end_ms=1840,
            tokens=(
                RawHeardToken(text=" Ela", probability=0.543607),
                RawHeardToken(text=" sposta", probability=0.9),
                RawHeardToken(text=" domani", probability=0.99),
            ),
        ),
    ),
)


def tool_for(
    tmp_path: Path,
    *,
    observed: RawObservation = GRANTED,
    report: RawTranscript | None = None,
    enabled: bool = True,
) -> tuple[ListenTool, FakeListening, CaptureStore]:
    store = CaptureStore(CaptureSettings(capture_dir=tmp_path / "captures"))
    listening = FakeListening(report=report if report is not None else HEARD)
    tool = ListenTool(
        store,
        listening,
        FakeProbe([observed]),
        FakeClock(),
        FakeIdGenerator(),
        enabled=enabled,
    )
    return tool, listening, store


async def run(tool: ListenTool, **arguments: object) -> object:
    return await tool.execute(DECISION, {"purpose": "prendere una nota", "seconds": 3, **arguments})


# ----------------------------------------------------------------------------------------
# The arguments, refused before anything opens
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("purpose", [None, "", 7])
async def test_a_purpose_that_is_not_a_sentence_is_refused(tmp_path: Path, purpose: object) -> None:
    tool, listening, _ = tool_for(tmp_path)

    result = await run(tool, purpose=purpose)

    assert result.error is not None
    assert result.error.code == ARGUMENTS_INVALID
    assert listening.asked == ()


@pytest.mark.parametrize("seconds", [None, "3", 0, 31, True, 3.5])
async def test_a_length_outside_the_ceiling_is_refused(tmp_path: Path, seconds: object) -> None:
    """The ceiling is the voice's read back: ELA does not listen longer than it may speak."""
    tool, listening, _ = tool_for(tmp_path)

    result = await run(tool, seconds=seconds)

    assert result.error is not None
    assert result.error.code == ARGUMENTS_INVALID
    assert listening.asked == ()


# ----------------------------------------------------------------------------------------
# The four things that must be true before a microphone opens
# ----------------------------------------------------------------------------------------


async def test_the_switch_being_off_is_not_the_same_as_having_no_microphone(
    tmp_path: Path,
) -> None:
    """ADR 0033 §9's split, on the other channel: two facts, two codes, two answers."""
    tool, listening, _ = tool_for(tmp_path, enabled=False)

    result = await run(tool)

    assert result.error is not None
    assert result.error.code == LISTEN_DISABLED
    assert listening.asked == ()


async def test_a_denied_microphone_never_becomes_a_transcript(tmp_path: Path) -> None:
    """The milestone in one test, and it asserts on the **calls**.

    A refused microphone opens, delivers zeros, and a transcriber turns those zeros into a
    sentence. So the only thing that can be checked is that ELA did not try, and the only way to
    check it is to watch.
    """
    tool, listening, store = tool_for(tmp_path, observed=DENIED)

    result = await run(tool)

    assert listening.asked == ()
    assert result.error is not None
    assert result.error.code == LISTEN_DENIED_BY_SYSTEM
    assert "System Settings" in result.error.message
    assert list(store.directory.glob("*")) == []


@pytest.mark.parametrize("observed", [NOT_DETERMINED, NONSENSE])
async def test_a_permission_that_is_not_granted_is_not_attempted(
    tmp_path: Path, observed: RawObservation
) -> None:
    """Not determined is not granted, and a status ELA does not know is not optimistic (§33)."""
    tool, listening, _ = tool_for(tmp_path, observed=observed)

    result = await run(tool)

    assert listening.asked == ()
    assert result.error is not None
    assert result.error.code in {LISTEN_DENIED_BY_SYSTEM, LISTEN_PERMISSION_UNREADABLE}


async def test_a_permission_that_could_not_be_read_is_a_doubt_and_not_a_denial(
    tmp_path: Path,
) -> None:
    """ "The system refuses me" and "I could not find out" are different facts (§33)."""
    tool, listening, _ = tool_for(tmp_path, observed=UNREADABLE)

    result = await run(tool)

    assert listening.asked == ()
    assert result.error is not None
    assert result.error.code == LISTEN_PERMISSION_UNREADABLE
    assert result.error.retryable is True


async def test_the_permission_is_read_at_the_instant_and_not_believed(tmp_path: Path) -> None:
    """ADR 0029 §7: a periodic belief never decides an action."""
    tool, _, _ = tool_for(tmp_path)
    probe = tool._probe  # noqa: SLF001 — the call is the property under test

    await run(tool)

    assert len(probe.calls) == 1


async def test_a_full_store_refuses_before_the_microphone_opens(tmp_path: Path) -> None:
    """The ceiling refuses, it never evicts (ADR 0029 §15) — and it refuses before the device."""
    settings = CaptureSettings(capture_dir=tmp_path / "captures", capture_max_count=1)
    store = CaptureStore(settings)
    store.directory.mkdir(parents=True, exist_ok=True)
    (store.directory / f"{HELD_ID}.heard.jsonl").write_bytes(b"")
    listening = FakeListening(report=HEARD)
    tool = ListenTool(store, listening, FakeProbe([GRANTED]), FakeClock(), FakeIdGenerator())

    result = await tool.execute(DECISION, {"purpose": "una nota", "seconds": 3})

    assert result.error is not None
    assert result.error.code == SCREEN_STORE_FULL
    assert listening.asked == ()


# ----------------------------------------------------------------------------------------
# What comes back
# ----------------------------------------------------------------------------------------


async def test_a_transcript_carries_the_probability_of_every_token_and_no_word(
    tmp_path: Path,
) -> None:
    tool, listening, store = tool_for(tmp_path)

    result = await run(tool, seconds=5)

    assert result.status is ExecutionStatus.SUCCEEDED
    assert listening.asked == (5,)
    assert result.output["segments"] == 1
    assert result.output["peak"] == 3330
    assert result.output["seconds_recorded"] == 3.21
    assert result.output["language"] == "it"
    assert result.output["confidence_min"] == pytest.approx(0.543607)
    assert result.output["confidence_median"] == pytest.approx(0.9)
    assert result.output["characters"] == len(" Ela, sposta la call di domani.")
    assert "Ela" not in json.dumps(dict(result.output)), "the words never enter a stored result"

    written = store.directory / str(result.output["path"])
    segments = jsonl_segments(written.read_bytes())
    assert segments is not None
    assert segments[0].text == " Ela, sposta la call di domani."
    assert segments[0].probabilities == (0.543607, 0.9, 0.99)


async def test_a_recording_with_no_words_is_a_true_answer_and_carries_no_confidence(
    tmp_path: Path,
) -> None:
    """Empty is a reading — nobody spoke — once peak and error have ruled the others out."""
    quiet = RawTranscript(exit_code=0, recorded_seconds=3.0, peak=120, language="it")
    tool, _, store = tool_for(tmp_path, report=quiet)

    result = await run(tool)

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.output["segments"] == 0
    assert result.output["confidence_min"] is None
    assert result.output["confidence_median"] is None
    assert (store.directory / str(result.output["path"])).read_bytes() == b""


async def test_silence_arrives_as_its_own_code_and_not_as_an_empty_transcript(
    tmp_path: Path,
) -> None:
    """``listen.no_signal`` is the second defence, and it is a fact rather than a threshold."""
    silent = RawTranscript(exit_code=0, recorded_seconds=3.0, peak=0, error=LISTEN_NO_SIGNAL)
    tool, _, store = tool_for(tmp_path, report=silent)

    result = await run(tool)

    assert result.error is not None
    assert result.error.code == LISTEN_NO_SIGNAL
    assert list(store.directory.glob("*.heard.jsonl")) == []


async def test_a_failure_the_adapter_named_travels_through_unchanged(tmp_path: Path) -> None:
    """ADR 0020 §7: the caller tells the failures apart without knowing who produced them."""
    late = RawTranscript(timed_out=True, error=LISTEN_TIMEOUT, retryable=True)
    tool, _, _ = tool_for(tmp_path, report=late)

    result = await run(tool)

    assert result.error is not None
    assert result.error.code == LISTEN_TIMEOUT
    assert result.error.retryable is True
    assert result.error.message == f"the listening ended with {LISTEN_TIMEOUT}"


async def test_a_denial_from_the_adapter_says_where_to_click(tmp_path: Path) -> None:
    """Nothing ELA can do fixes a permission, so the only useful answer is where the human goes."""
    refused = RawTranscript(error=LISTEN_DENIED_BY_SYSTEM)
    tool, _, _ = tool_for(tmp_path, report=refused)

    result = await run(tool)

    assert result.error is not None
    assert "System Settings" in result.error.message


async def test_a_store_that_cannot_be_written_is_a_named_failure(tmp_path: Path) -> None:
    tool, _, store = tool_for(tmp_path)
    store.directory.mkdir(parents=True, exist_ok=True)
    store.directory.chmod(0o500)

    try:
        result = await run(tool)
    finally:
        store.directory.chmod(0o700)

    assert result.error is not None
    assert result.error.code == CAPTURE_UNREADABLE


async def test_two_recordings_are_two_rooms_and_the_tool_says_so(tmp_path: Path) -> None:
    tool, _, _ = tool_for(tmp_path)

    assert tool.idempotent is False
