"""How the audition reaches a provider, and what it answers when it cannot (ADR 0034 §9).

These two closures are the only place in ELA where a voice is chosen by a caller, so they are
also the only place where "which voice" could go wrong. What they must do is small and exact:
name what is missing before touching anything, and never let a failure arrive as an exception.
"""

from __future__ import annotations

import stat
from pathlib import Path

import httpx
from pydantic import SecretStr

from ela.composition import Ela
from ela.composition.root import _audition_speaker, _sample
from ela.infrastructure.perception import OnlineSpeechCommand
from ela.ports import SPEECH_NO_KEY, SPEECH_NO_PLAYER, SPEECH_UNKNOWN_VOICE
from ela.providers.elevenlabs import ElevenLabsSettings, ElevenLabsVoice
from ela.tools import DIRECTORY_MODE

PHRASE = "No, questa non è una buona idea."
VOICE = "VZOd9FMXDnXRZpGn0thg"
AUDIO = b"ID3\x04audio"


class Player:
    """An :class:`OnlineSpeechCommand` whose child is a function: no process, no sound."""

    def __init__(self, tmp_path: Path, code: int = 0, *, binary: str = "/bin/sh") -> None:
        self.played: list[bytes] = []
        self._code = code

        async def run(argv: object, audio: bytes, timeout: float, *, directory: str | None = None):
            self.played.append(audio)
            return self._code, ""

        self.command = OnlineSpeechCommand(
            synthesise=self._never,
            unconfigured=lambda: None,
            directory=tmp_path,
            runner=run,  # type: ignore[arg-type]
            binary=binary,  # ``/bin/sh`` exists, so ``available`` is true unless a test says not
        )

    async def _never(self, text: str) -> object:  # pragma: no cover - never called here
        raise AssertionError("the audition synthesises through the provider, not the port")


def provider(
    *, key: str | None = "sk_key", answers: httpx.Response | None = None
) -> ElevenLabsVoice:
    def handle(request: httpx.Request) -> httpx.Response:
        assert answers is not None, "no request was expected"
        return answers

    return ElevenLabsVoice(
        ElevenLabsSettings(
            elevenlabs_api_key=None if key is None else SecretStr(key),
            elevenlabs_voice_id=None,
            _env_file=None,  # type: ignore[call-arg]
        ),
        transport=httpx.MockTransport(handle),
    )


async def test_the_key_comes_before_the_player_here_too(tmp_path: Path) -> None:
    """Two absences, one order, and the same one everywhere (2026-09-09).

    Both halves are constructed: no key, and a player whose binary is a path nobody has. The
    answer is the key, because it is the one the person reading it can do something about.
    """
    mute = Player(tmp_path, binary="/usr/bin/definitely-not-here")
    speak = _audition_speaker(provider(key=None), mute.command)
    play = _sample(provider(key=None), mute.command)

    assert (await speak(PHRASE, VOICE, "eleven_flash_v2_5")).error == SPEECH_NO_KEY
    assert (await play(VOICE)).error == SPEECH_NO_KEY


async def test_a_machine_that_cannot_play_is_named_once_the_key_is_there(tmp_path: Path) -> None:
    mute = Player(tmp_path, binary="/usr/bin/definitely-not-here")

    said = await _audition_speaker(provider(key="sk_key"), mute.command)(
        PHRASE, VOICE, "eleven_flash_v2_5"
    )
    sampled = await _sample(provider(key="sk_key"), mute.command)(VOICE)

    assert said.error == SPEECH_NO_PLAYER
    assert sampled.error == SPEECH_NO_PLAYER, "the preview answers the same way, or it is a hole"
    assert mute.played == []


async def test_without_a_key_nothing_is_sent(tmp_path: Path) -> None:
    player = Player(tmp_path)
    speak = _audition_speaker(provider(key=None), player.command)
    play = _sample(provider(key=None), player.command)

    assert (await speak(PHRASE, VOICE, "eleven_flash_v2_5")).error == SPEECH_NO_KEY
    assert (await play(VOICE)).error == SPEECH_NO_KEY
    assert player.played == [], "nothing was played, because nothing was ever asked for"


async def test_a_phrase_is_synthesised_with_the_voice_that_was_chosen(tmp_path: Path) -> None:
    """The audition is the one caller allowed to choose, and this is where the choice travels."""
    asked: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        return httpx.Response(200, content=AUDIO, headers={"character-cost": "16"})

    voice = ElevenLabsVoice(
        ElevenLabsSettings(elevenlabs_api_key=SecretStr("sk_key"), _env_file=None),  # type: ignore[call-arg]
        transport=httpx.MockTransport(handle),
    )
    player = Player(tmp_path)

    said = await _audition_speaker(voice, player.command)(PHRASE, VOICE, "eleven_flash_v2_5")

    assert said.error is None
    assert said.credits == 16
    assert player.played == [AUDIO]
    assert VOICE in asked[0]


async def test_a_provider_failure_arrives_as_a_named_error_and_not_an_exception(
    tmp_path: Path,
) -> None:
    refused = httpx.Response(404, json={"detail": {"status": "voice_not_found"}})
    player = Player(tmp_path)

    said = await _audition_speaker(provider(answers=refused), player.command)(
        PHRASE, VOICE, "eleven_flash_v2_5"
    )

    assert said.error == SPEECH_UNKNOWN_VOICE
    assert player.played == []


async def test_a_sample_that_cannot_be_had_is_a_named_outcome(tmp_path: Path) -> None:
    """Best effort by measurement, not by choice (ADR 0034 §9)."""
    refused = httpx.Response(400, json={"detail": {"status": "voice_not_found"}})
    player = Player(tmp_path)

    said = await _sample(provider(answers=refused), player.command)(VOICE)

    assert said.error == SPEECH_UNKNOWN_VOICE
    assert player.played == []


async def test_a_sample_is_played_when_the_provider_hands_one_over(tmp_path: Path) -> None:
    answers = iter(
        [
            httpx.Response(
                200,
                json={"preview_url": "https://storage.googleapis.com/eleven/sample.mp3"},
            ),
            httpx.Response(200, content=AUDIO),
        ]
    )
    voice = ElevenLabsVoice(
        ElevenLabsSettings(elevenlabs_api_key=SecretStr("sk_key"), _env_file=None),  # type: ignore[call-arg]
        transport=httpx.MockTransport(lambda request: next(answers)),
    )
    player = Player(tmp_path)

    said = await _sample(voice, player.command)(VOICE)

    assert said.error is None
    assert player.played == [AUDIO]


def test_the_scratch_directory_is_not_the_workspace(tmp_path: Path) -> None:
    """ADR 0029 §1's permanent constraint, and it applies to audio as much as to a screenshot:
    what lands in a folder something may sync leaves the machine with nobody deciding it."""
    from ela.tools.settings import default_workspace_dir, speech_dir_beside

    beside = speech_dir_beside(tmp_path / "captures")

    assert beside == tmp_path / "speech"
    assert default_workspace_dir() not in beside.parents


async def test_the_scratch_directory_exists_before_the_first_sentence(ela: Ela) -> None:
    """The bug this test was written for, found by the machine and not by the suite (M11.3).

    ``mkstemp`` on a directory that is not there raises, the adapter turns that into
    ``speech.playback_failed``, and what a person sees is "the player ended badly" for a player
    that was never started. The whole audio path worked; the folder did not exist.

    So the composition root creates it, with the mode every private directory of ELA has — the
    same constant, imported and not repeated (ADR 0029 §1).
    """
    assert ela.speech_dir.is_dir()
    assert stat.S_IMODE(ela.speech_dir.stat().st_mode) == DIRECTORY_MODE
    assert list(ela.speech_dir.iterdir()) == [], "it is a floor, not a store"
