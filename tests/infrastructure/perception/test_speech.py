"""The speech adapter, tested without speakers (M11.1, ADR 0033).

The port's hardest promise is **it does not fail, it reports**, and every way of failing is
something a fake spawn produces: a helper that timed out, one killed by a signal, one that could
not be started at all. None of them needs audio hardware, which is what every CI runner has.

The argv is asserted too, and that is not pedantry: it is where rule 40 could be broken and where
a sentence beginning with a hyphen would become a flag.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from ela.infrastructure.perception import SAY, SaySpeechCommand, UnsupportedSpeech
from ela.infrastructure.perception.darwin import TIMED_OUT
from ela.infrastructure.perception.speech import END_OF_OPTIONS

SENTENCE = "Ho spostato la riunione a giovedì."


def answering(code: int) -> tuple[SaySpeechCommand, list[Sequence[str]]]:
    """A command whose helper ends exactly like this, and the argv it was asked to run."""
    seen: list[Sequence[str]] = []

    async def spawn(argv: Sequence[str], timeout: float) -> tuple[int, str]:
        del timeout
        seen.append(argv)
        return code, ""

    return SaySpeechCommand(timeout=timedelta(seconds=1), voice="Alice", runner=spawn), seen


async def test_a_helper_that_finishes_reports_a_clean_exit_and_a_duration() -> None:
    command, _ = answering(0)

    report = await command.speak(SENTENCE)

    assert report.exit_code == 0
    assert not report.timed_out
    assert report.spoken_seconds is not None
    assert report.spoken_seconds >= 0


async def test_the_argv_names_the_voice_and_ends_the_options_before_the_text() -> None:
    """``--`` is not politeness: without it a sentence starting with a hyphen is read as a flag,
    which is argument injection into the one command whose flags rule 40 cares about — and the
    text comes from a model."""
    command, seen = answering(0)

    await command.speak(SENTENCE)

    assert seen == [[SAY, "-v", "Alice", END_OF_OPTIONS, SENTENCE]]


async def test_a_sentence_that_looks_like_a_flag_is_still_a_sentence() -> None:
    command, seen = answering(0)

    await command.speak("-o /tmp/stolen.aiff")

    assert seen[0].index(END_OF_OPTIONS) < seen[0].index("-o /tmp/stolen.aiff")


async def test_a_helper_that_overstayed_is_reported_as_timed_out() -> None:
    command, _ = answering(TIMED_OUT)

    report = await command.speak(SENTENCE)

    assert report.timed_out
    assert report.exit_code == TIMED_OUT


async def test_a_helper_that_exited_badly_carries_its_status_and_no_verdict() -> None:
    command, _ = answering(3)

    report = await command.speak(SENTENCE)

    assert (report.exit_code, report.timed_out) == (3, False)


async def test_a_spawn_that_cannot_start_at_all_is_not_an_exception_either() -> None:
    """The helper vanished between ``available()`` and here. The port reports, it does not raise."""

    async def spawn(argv: Sequence[str], timeout: float) -> tuple[int, str]:
        del argv, timeout
        raise FileNotFoundError(SAY)

    command = SaySpeechCommand(timeout=timedelta(seconds=1), voice="Alice", runner=spawn)

    report = await command.speak(SENTENCE)

    assert report.exit_code is None
    assert report.spoken_seconds is None


async def test_the_timeout_reaches_the_spawn_in_seconds() -> None:
    seen: list[float] = []

    async def spawn(argv: Sequence[str], timeout: float) -> tuple[int, str]:
        del argv
        seen.append(timeout)
        return 0, ""

    command = SaySpeechCommand(timeout=timedelta(seconds=60), voice="Alice", runner=spawn)

    await command.speak(SENTENCE)

    assert seen == [60.0]


async def test_available_is_false_when_the_binary_is_not_there() -> None:
    command = SaySpeechCommand(
        timeout=timedelta(seconds=1), voice="Alice", binary="/nowhere/at/all"
    )

    assert await command.available() is False


async def test_an_operating_system_without_a_voice_says_so_and_reports_nothing() -> None:
    """ "ELA on Linux says nothing" is an object with a name and a test, not a gap."""
    command = UnsupportedSpeech()

    assert await command.available() is False
    report = await command.speak(SENTENCE)
    assert (report.exit_code, report.timed_out, report.spoken_seconds) == (None, False, None)
