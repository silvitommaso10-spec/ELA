"""The listening adapter, with no microphone and no permission (M11.2, ADR 0036).

Every branch is produced with an injected spawn: a recorder that timed out, one that opened
nothing, one that heard only silence, a transcriber that wrote nonsense. No runner has a
microphone, and the one thing a runner could never produce — a room with somebody talking in it —
is not what these tests are about.

The test that carries the milestone is
:func:`test_silence_never_reaches_the_transcriber`: it asserts on the **calls**, not on the
answer. A transcriber has no way to say "I heard nothing" — measured, thirty seconds of zeros come
back as «Grazie a tutti.» — so not running it is the behaviour, and behaviour is only tested by
watching for it.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from ela.infrastructure.machine.darwin import TIMED_OUT, TranscribeArgv
from ela.infrastructure.machine.listening import DarwinListening, UnsupportedListening, digest_of
from ela.ports import (
    LISTEN_ERROR_CODES,
    LISTEN_FAILED,
    LISTEN_LANGUAGE_UNSUPPORTED,
    LISTEN_NO_INPUT_DEVICE,
    LISTEN_NO_SIGNAL,
    LISTEN_TIMEOUT,
    LISTEN_TRANSCRIPTION_FAILED,
    LISTEN_TRANSCRIPTION_UNAVAILABLE,
    LISTEN_UNSUPPORTED,
)

HEARD = {
    "result": {"language": "it"},
    "transcription": [
        {
            "text": " Ela, sposta la call di domani.",
            "offsets": {"from": 0, "to": 1840},
            "tokens": [
                {"text": " Ela", "p": 0.543607},
                {"text": ",", "p": 0.988116},
                {"text": " sposta", "p": 0.9},
            ],
        }
    ],
}


class Spy:
    """A spawn that answers what the test wrote down, and remembers what it was asked."""

    def __init__(
        self,
        recorded: tuple[int, str],
        report: tuple[int, str] | None = None,
        *,
        honour_gate: bool = True,
    ) -> None:
        self.recorded = recorded
        self.report = report
        self.honour_gate = honour_gate
        self.transcribed = 0
        self.record_argv: Sequence[str] = ()

    async def __call__(
        self,
        record_argv: Sequence[str],
        transcribe: TranscribeArgv,
        should_transcribe: Any,
        record_timeout: float,
        transcribe_timeout: float,
        *,
        directory: str | None = None,
    ) -> tuple[tuple[int, str], tuple[int, str] | None]:
        del record_timeout, transcribe_timeout, directory
        self.record_argv = record_argv
        if self.honour_gate and (self.recorded[0] != 0 or not should_transcribe(self.recorded[1])):
            return self.recorded, None
        self.transcribed += 1
        transcribe("/dev/fd/9", "/tmp/prefix")  # the flags are the adapter's, and they are used
        return self.recorded, self.report


def said(*, opened: bool = True, peak: int = 3330, seconds: float = 3.0) -> str:
    return json.dumps({"opened": opened, "peak": peak, "bytes": 96000, "recorded_seconds": seconds})


def ear(spawn: Spy, tmp_path: Path, *, language: str = "it") -> DarwinListening:
    """An adapter whose two files exist and match, so ``available`` is not what is under test."""
    binary, model = tmp_path / "whisper-cli", tmp_path / "model.bin"
    binary.write_bytes(b"#!/bin/sh\n")
    model.write_bytes(b"weights")
    return DarwinListening(
        binary=binary,
        model=model,
        expected=(digest_of(binary), digest_of(model)),
        language=language,
        transcribe_timeout=30.0,
        spawn=spawn,
    )


async def test_unsupported_hears_nothing_and_says_which_thing_is_missing() -> None:
    listening = UnsupportedListening()

    assert await listening.available() is False
    assert (await listening.listen(3)).error == LISTEN_UNSUPPORTED


async def test_a_missing_transcriber_is_not_a_silent_recording(tmp_path: Path) -> None:
    """What decides what ELA believes was said is checked before the microphone is opened."""
    spy = Spy((0, said()))
    listening = DarwinListening(
        binary=tmp_path / "nowhere",
        model=tmp_path / "nothing",
        expected=("", ""),
        language="it",
        transcribe_timeout=1.0,
        spawn=spy,
    )

    heard = await listening.listen(3)

    assert heard.error == LISTEN_TRANSCRIPTION_UNAVAILABLE
    assert spy.record_argv == (), "the microphone must not be opened to find this out"


async def test_a_swapped_model_is_no_longer_the_one_ela_was_told_to_expect(tmp_path: Path) -> None:
    spy = Spy((0, said()))
    listening = ear(spy, tmp_path)
    assert await listening.available() is True

    (tmp_path / "model.bin").write_bytes(b"something else entirely")

    assert await listening.available() is False


async def test_silence_never_reaches_the_transcriber(tmp_path: Path) -> None:
    """The measurement of 2026-09-09 made structural: zeros in, and nothing interprets them."""
    spy = Spy((0, said(peak=0)), (0, json.dumps(HEARD)))
    listening = ear(spy, tmp_path)

    heard = await listening.listen(3)

    assert spy.transcribed == 0, "a transcriber given silence does not say so — it invents"
    assert heard.error == LISTEN_NO_SIGNAL
    assert heard.peak == 0
    assert heard.segments == ()
    assert heard.recorded_seconds == 3.0


async def test_a_recorder_that_opened_nothing_is_not_a_silent_room(tmp_path: Path) -> None:
    heard = await ear(Spy((0, said(opened=False))), tmp_path).listen(3)

    assert heard.error == LISTEN_NO_INPUT_DEVICE
    assert heard.retryable is False


async def test_a_recorder_that_timed_out_says_so_and_is_worth_retrying(tmp_path: Path) -> None:
    heard = await ear(Spy((TIMED_OUT, "")), tmp_path).listen(3)

    assert (heard.error, heard.timed_out, heard.retryable) == (LISTEN_TIMEOUT, True, True)


@pytest.mark.parametrize("answer", [(1, said()), (0, "not json at all")])
async def test_a_recorder_that_ended_badly_is_a_failure_and_not_a_reading(
    answer: tuple[int, str], tmp_path: Path
) -> None:
    heard = await ear(Spy(answer), tmp_path).listen(3)

    assert heard.error == LISTEN_FAILED
    assert heard.segments == ()


async def test_a_transcriber_that_timed_out_keeps_what_the_recording_measured(
    tmp_path: Path,
) -> None:
    heard = await ear(Spy((0, said()), (TIMED_OUT, "")), tmp_path).listen(3)

    assert heard.error == LISTEN_TIMEOUT
    assert (heard.peak, heard.recorded_seconds) == (3330, 3.0)


@pytest.mark.parametrize("answer", [(1, "{}"), (0, "}{")])
async def test_a_transcriber_that_ended_badly_says_which_half_failed(
    answer: tuple[int, str], tmp_path: Path
) -> None:
    heard = await ear(Spy((0, said()), answer), tmp_path).listen(3)

    assert heard.error == LISTEN_TRANSCRIPTION_FAILED
    assert heard.retryable is True


async def test_a_language_that_is_not_the_one_asked_for_is_not_an_empty_room(
    tmp_path: Path,
) -> None:
    """ADR 0030 §8: without this, "configured wrongly" would arrive as "you said nothing"."""
    heard = await ear(Spy((0, said()), (0, json.dumps(HEARD))), tmp_path, language="en").listen(3)

    assert heard.error == LISTEN_LANGUAGE_UNSUPPORTED
    assert heard.language == "it"


async def test_what_was_heard_arrives_with_the_probability_of_every_token(
    tmp_path: Path,
) -> None:
    spy = Spy((0, said()), (0, json.dumps(HEARD)))

    heard = await ear(spy, tmp_path).listen(3)

    assert spy.transcribed == 1
    assert heard.error is None
    assert (heard.language, heard.peak) == ("it", 3330)
    assert [segment.text for segment in heard.segments] == [" Ela, sposta la call di domani."]
    tokens = heard.segments[0].tokens
    assert [token.text for token in tokens] == [" Ela", ",", " sposta"]
    assert tokens[0].probability == pytest.approx(0.543607)
    assert min(token.probability for token in tokens) < 0.6, "the hard word is the unsure one"


async def test_a_transcript_with_no_segments_is_a_true_answer(tmp_path: Path) -> None:
    """Empty is a reading — *nobody spoke* — once the other three ways of arriving empty are out."""
    empty = json.dumps({"result": {"language": "it"}, "transcription": []})

    heard = await ear(Spy((0, said()), (0, empty)), tmp_path).listen(3)

    assert heard.error is None
    assert heard.segments == ()
    assert heard.peak == 3330


async def test_a_report_shaped_wrongly_is_read_without_raising(tmp_path: Path) -> None:
    """A helper's output is not ELA's to trust: it is parsed defensively or it is a failure."""
    odd = json.dumps({"result": {"language": "it"}, "transcription": "not a list"})

    heard = await ear(Spy((0, said()), (0, odd)), tmp_path).listen(3)

    assert heard.error is None
    assert heard.segments == ()


async def test_every_error_this_adapter_can_name_is_in_the_ports_vocabulary(
    tmp_path: Path,
) -> None:
    """A second implementation reports these codes or it is not interchangeable (ADR 0020 §7)."""
    answers = [
        Spy((TIMED_OUT, "")),
        Spy((1, said())),
        Spy((0, said(opened=False))),
        Spy((0, said(peak=0))),
        Spy((0, said()), (1, "{}")),
    ]
    errors = {(await ear(spy, tmp_path).listen(3)).error for spy in answers}

    assert errors <= LISTEN_ERROR_CODES
    assert len(errors) == len(answers), "each of these is a different fact"
