"""The audition: two sentences from the repository, in the voices offered (ADR 0034 §9).

The tests here are about the property that makes an audition acceptable without a capability:
**it can only say what is written in the repository.** Rule 43 proves the shape; these prove the
behaviour, which is the other half — a module can have no ``text`` parameter and still contrive
to say something else.
"""

from __future__ import annotations

from ela.domain import RawSpeech
from ela.infrastructure.machine import AUDITION_PHRASES, CANDIDATES, Audition
from ela.ports import SPEECH_RATE_LIMITED, SPEECH_UNKNOWN_VOICE

VOICE = "VZOd9FMXDnXRZpGn0thg"
FLASH = "eleven_flash_v2_5"
MULTI = "eleven_multilingual_v2"


class Heardable:
    def __init__(self, *answers: RawSpeech) -> None:
        self.asked: list[tuple[str, str, str]] = []
        self.previewed: list[str] = []
        self._answers = list(answers) or [RawSpeech(exit_code=0, spoken_seconds=2.0)]

    async def speak(self, phrase: str, voice_id: str, model: str) -> RawSpeech:
        self.asked.append((phrase, voice_id, model))
        return self._answers.pop(0) if len(self._answers) > 1 else self._answers[0]

    async def play(self, voice_id: str) -> RawSpeech:
        self.previewed.append(voice_id)
        return self._answers[0]


def audition(recorder: Heardable) -> Audition:
    return Audition(speak=recorder.speak, play=recorder.play)


async def test_it_says_the_two_sentences_of_9_and_nothing_else() -> None:
    """§9 gives ELA these words as what she must be able to say; they are the test of a voice."""
    recorder = Heardable()

    heard = await audition(recorder).run(VOICE, (FLASH,))

    assert [one.phrase for one in heard] == list(AUDITION_PHRASES)
    assert [phrase for phrase, _, _ in recorder.asked] == list(AUDITION_PHRASES)
    assert AUDITION_PHRASES == (
        "No, questa non è una buona idea.",
        "Stai cercando di risolvere il problema sbagliato.",
    )


async def test_more_than_one_model_means_the_same_sentences_twice() -> None:
    """Because the choice between the models is the user's: 5,6 seconds of silence against 1,2,
    and if the difference in quality can be heard it is theirs to weigh (ADR 0034 §5)."""
    recorder = Heardable()

    heard = await audition(recorder).run(VOICE, (FLASH, MULTI))

    assert [one.model for one in heard] == [FLASH, FLASH, MULTI, MULTI]
    assert len({one.phrase for one in heard}) == 2


async def test_it_stops_at_the_first_failure() -> None:
    """Paying to be told the same thing four times is not an audition."""
    recorder = Heardable(
        RawSpeech(error=SPEECH_RATE_LIMITED, retryable=True),
        RawSpeech(exit_code=0, spoken_seconds=2.0),
    )

    heard = await audition(recorder).run(VOICE, (FLASH, MULTI))

    assert len(heard) == 1
    assert len(recorder.asked) == 1


async def test_a_preview_sends_nothing_and_names_what_it_could_not_get() -> None:
    recorder = Heardable(RawSpeech(error=SPEECH_UNKNOWN_VOICE))

    said = await audition(recorder).preview(VOICE)

    assert said.error == SPEECH_UNKNOWN_VOICE
    assert recorder.previewed == [VOICE]
    assert recorder.asked == [], "a preview synthesises nothing"


def test_the_candidates_are_the_six_and_the_one_in_use_is_marked() -> None:
    listed = audition(Heardable()).candidates(VOICE)

    assert len(listed) == len(CANDIDATES) == 6
    assert [one.voice_id for one in listed if one.chosen] == [VOICE]


def test_a_voice_nobody_listed_is_still_shown_as_the_one_in_use() -> None:
    """Somebody who chose a voice of their own must see it, or ``ela voice`` would show six
    candidates and no answer to "which one am I using"."""
    listed = audition(Heardable()).candidates("una-voce-mia")

    assert listed[0].chosen and listed[0].voice_id == "una-voce-mia"
    assert len(listed) == len(CANDIDATES) + 1


def test_with_no_voice_chosen_nothing_is_marked() -> None:
    assert not any(one.chosen for one in audition(Heardable()).candidates(None))


def test_the_phrases_can_be_read_before_they_are_paid_for() -> None:
    assert audition(Heardable()).phrases == AUDITION_PHRASES
