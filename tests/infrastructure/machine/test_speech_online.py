"""The online voice: a provider says the words, this machine plays them (ADR 0034 §6, §7).

No socket and no sound: the synthesis is a function the test writes and the player is a spawn the
test writes, which is what lets the two properties that matter be checked on any runner — that
the playback timeout is **derived from the audio** and that ``spoken_seconds`` is the sound and
never the round-trip.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ela.domain import RawSpeech
from ela.infrastructure.machine import TIMED_OUT, OnlineSpeechCommand
from ela.ports import (
    SPEECH_NO_KEY,
    SPEECH_NO_PLAYER,
    SPEECH_PLAYBACK_FAILED,
    SPEECH_PLAYBACK_TIMEOUT,
    SPEECH_RATE_LIMITED,
)
from ela.providers.elevenlabs import AUDIO_BYTES_PER_SECOND, PLAYBACK_SLACK_SECONDS, Synthesis
from ela.providers.elevenlabs.errors import Failure

SENTENCE = "No, questa non è una buona idea."
AUDIO = b"x" * 32_000  # two seconds at the format ELA asks for


class Spawned:
    """A player that makes no sound and remembers what it was given."""

    def __init__(self, code: int = 0, *, boom: bool = False) -> None:
        self.calls: list[tuple[tuple[str, ...], bytes, float, str | None]] = []
        self._code = code
        self._boom = boom

    async def __call__(
        self, argv: Any, audio: bytes, timeout: float, *, directory: str | None = None
    ) -> tuple[int, str]:
        if self._boom:
            raise OSError("no such binary")
        self.calls.append((tuple(argv), audio, timeout, directory))
        return self._code, ""


def command(
    spawned: Spawned,
    *,
    said: Synthesis | None = None,
    missing: str | None = None,
    tmp_path: Path | None = None,
) -> OnlineSpeechCommand:
    answer = said if said is not None else Synthesis(audio=AUDIO, seconds=0.42, credits=16)

    async def synthesise(text: str) -> Synthesis:
        return answer

    return OnlineSpeechCommand(
        synthesise=synthesise,
        unconfigured=lambda: missing,
        directory=tmp_path or Path("/tmp"),
        runner=spawned,
        binary="/bin/sh",
    )


async def test_the_audio_is_handed_to_the_player_and_the_sound_is_timed(tmp_path: Path) -> None:
    spawned = Spawned()

    said = await command(spawned, tmp_path=tmp_path).speak(SENTENCE)

    assert said.error is None
    assert said.audio_bytes == len(AUDIO)
    assert said.credits == 16
    assert said.spoken_seconds is not None
    argv, audio, _, directory = spawned.calls[0]
    assert audio == AUDIO
    assert directory == str(tmp_path)
    assert argv == ("/bin/sh",), "the audio's path is the spawner's to add, and it has no name"


async def test_the_playback_timeout_is_the_length_of_the_audio_and_not_a_knob() -> None:
    """ADR 0034 §1.4: the format is fixed, so the bytes *are* the duration — no number to guess."""
    spawned = Spawned()

    await command(spawned).speak(SENTENCE)

    expected = len(AUDIO) / AUDIO_BYTES_PER_SECOND + PLAYBACK_SLACK_SECONDS
    assert spawned.calls[0][2] == expected


async def test_the_synthesis_is_never_counted_as_speaking() -> None:
    """The verifier weighs ``spoken_seconds`` against the length of the words; a number carrying
    a round-trip would make a sentence that never played look like one that did (ADR 0034 §6)."""
    spawned = Spawned()

    said = await command(spawned, said=Synthesis(audio=AUDIO, seconds=5.0)).speak(SENTENCE)

    assert said.synthesis_seconds == 5.0
    assert said.spoken_seconds is not None and said.spoken_seconds < 1.0


async def test_the_key_comes_before_the_player_when_both_are_missing() -> None:
    """**The decision of 2026-09-09**, and the test that constructs both halves instead of
    inheriting one from the runner.

    A machine with no player and an ELA with no key are both true here — the binary is a path
    nobody has — and the answer is the **key**: it is configuration, something the person reading
    it can go and fix, while the player is a property of the machine they are on. ADR 0033 §9's
    own reason for a pair it did not have yet.

    Before this, the order came out differently on a Mac and on a Linux runner, and four tests
    asserted the Mac's answer on both. Nothing here asks the machine anything.
    """
    absent = OnlineSpeechCommand(
        synthesise=_never,
        unconfigured=lambda: SPEECH_NO_KEY,
        directory=Path("/tmp"),
        binary="/usr/bin/definitely-not-here",
    )

    assert (await absent.speak(SENTENCE)).error == SPEECH_NO_KEY


async def test_a_machine_that_cannot_play_says_so_once_the_key_is_there() -> None:
    """The other half, constructed the same way: everything configured, no player."""
    absent = OnlineSpeechCommand(
        synthesise=_never,
        unconfigured=lambda: None,
        directory=Path("/tmp"),
        binary="/usr/bin/definitely-not-here",
    )

    said = await absent.speak(SENTENCE)

    assert said.error == SPEECH_NO_PLAYER
    assert said.synthesis_seconds is None, "nothing was asked for, so nothing was paid for"


async def test_the_two_absences_answer_before_anything_is_asked_for() -> None:
    spawned = Spawned()

    said = await command(spawned, missing=SPEECH_NO_KEY).speak(SENTENCE)

    assert said.error == SPEECH_NO_KEY
    assert spawned.calls == [], "nothing was played, and nothing was synthesised"


async def test_a_provider_failure_keeps_its_code_and_its_nature() -> None:
    refused = Synthesis(
        seconds=0.2, failure=Failure(SPEECH_RATE_LIMITED, "429 rate", retryable=True)
    )
    spawned = Spawned()

    said = await command(spawned, said=refused).speak(SENTENCE)

    assert (said.error, said.retryable) == (SPEECH_RATE_LIMITED, True)
    assert said.synthesis_seconds == 0.2
    assert spawned.calls == []


async def test_a_player_that_ends_badly_is_a_failure_with_a_name() -> None:
    said = await command(Spawned(code=1)).speak(SENTENCE)

    assert said.error == SPEECH_PLAYBACK_FAILED
    assert said.retryable


async def test_a_player_that_overstays_means_ela_stopped_mid_word() -> None:
    """Not "nothing happened" — for whoever was listening these are two different things."""
    said = await command(Spawned(code=TIMED_OUT)).speak(SENTENCE)

    assert said.error == SPEECH_PLAYBACK_TIMEOUT
    assert said.timed_out


async def test_a_player_that_cannot_be_started_does_not_raise() -> None:
    """The port's hardest promise: it does not fail, it reports."""
    said = await command(Spawned(boom=True)).speak(SENTENCE)

    assert said.error == SPEECH_PLAYBACK_FAILED


async def test_available_is_about_the_machine_and_not_about_the_configuration() -> None:
    """One boolean for both questions is the ambiguity ADR 0030 §8 exists to split."""
    here = command(Spawned(), missing=SPEECH_NO_KEY)

    assert await here.available() is True, "no key, and the machine can still play audio"


async def test_a_machine_without_the_player_says_no() -> None:
    absent = OnlineSpeechCommand(
        synthesise=_never,
        unconfigured=lambda: None,
        directory=Path("/tmp"),
        binary="/usr/bin/definitely-not-here",
    )

    assert await absent.available() is False


async def _never(text: str) -> Synthesis:  # pragma: no cover - the guard of the test above
    raise AssertionError("nothing is synthesised when the machine cannot play")


def test_the_report_carries_the_receipt_and_never_the_words() -> None:
    """``RawSpeech`` has no field for the sentence: the decision of ADR 0033, kept by 0034."""
    assert "text" not in RawSpeech.model_fields
    assert {"credits", "history_item_id"} <= set(RawSpeech.model_fields)
