"""Sentire una voce prima di sceglierla, senza che diventi un task (M11.3, ADR 0034 §9).

The problem this module exists for is not technical. ``voice.speak_online`` requires an
authorization, so trying six voices through the capability would be six approvals — and the user
said plainly that hearing a few voices must not cost a task per attempt. So an audition is not a
capability: it is a person at a terminal, listening.

**What makes that defensible is what leaves the machine.** During an audition ELA sends a
sentence that is written in this file, in the repository, readable in ``git`` by anybody — never
a word of the user's, never a line of §44 context, never a goal. And the shape that keeps it true
is not a comment but an **absence**: no function here takes text. Architecture rule 43 is that
absence, made checkable, and it can fire — ``--text`` is the obvious feature of tomorrow.

The two sentences are §9's own, and they were chosen for a reason that is about ELA and not about
audio quality:

    La domanda non è come suona una voce: è come suona ELA quando ti contraddice.

**Why this is not in the CLI**, where a chooser would naturally live: architecture rule 27 says
only the composition root may name a provider or an adapter, and rule 28 says the CLI is a client
of the local API. So the audition runs here, behind a route, and the CLI asks for it. It came out
better for a reason nobody planned: the route has **no field for text at all**, so "only the
repository's words" is in the schema before it is in a rule.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Final

from ela.domain import RawSpeech

__all__ = ["AUDITION_PHRASES", "CANDIDATES", "Audition", "Candidate", "Heard", "Play", "Speak"]

AUDITION_PHRASES: Final = (
    "No, questa non è una buona idea.",
    "Stai cercando di risolvere il problema sbagliato.",
)
"""Le due frasi di §9, alla lettera.

§9 gives ELA these words as the example of what she must be able to say — *ELA non deve essere
una semplice assistente servile* — so they are the right test of a voice: a voice that sounds
wrong saying them is the wrong voice, however pleasant it is reading a paragraph.

They are literals, and a tuple, and nothing computes them. That is the whole of rule 43's subject.
"""

CANDIDATES: Final = (
    ("VZOd9FMXDnXRZpGn0thg", "Daniela Narrator IT — Warm Elegant ITA"),
    ("kavPiGHUq62Aokyp5Tui", "Daniela — Giovane ed elegante"),
    ("UnOINkXZ3yK4vVg3Iayj", "Beatrice AI Agent"),
    ("3LTv5xMEHTJYUIMl1jBR", "Aurora — Clear and Supportive"),
    ("MuTiG4dbrEGYEy3XP4iP", "Rossana — Warm Italian Conversational"),
    ("mT0eqrjKfAPl6gQBlfBa", "Chiara — Professional and Versatile"),
)
"""The six voices worth hearing, out of the twenty-five this workspace can reach.

Chosen on 2026-09-08 against §9 — *una presenza femminile e professionale*, and the user's own
words, *elegante e moderna* — and not against a ranking: the first is described by its own author
as *warm, elegant and modern*, and the last two are declared for voice agents and assistants.

A list in the repository and not a search, because a roster that changed under the user between
one listening and the next would make "the third one" mean nothing. If none of the six convinces,
the list changes here, in a diff, and the audition is run again.
"""


@dataclass(frozen=True, slots=True)
class Candidate:
    """One voice offered for listening: what it is called, and whether ELA is using it."""

    voice_id: str
    name: str
    chosen: bool


@dataclass(frozen=True, slots=True)
class Heard:
    """One thing that was played, and what it cost. Never the words — they are in this file."""

    voice_id: str
    model: str
    phrase: str
    """Which of :data:`AUDITION_PHRASES` this was. A constant of the repository, echoed back so
    that whoever is listening can read what they just heard — never something a caller chose."""
    said: RawSpeech


Speak = Callable[[str, str, str], Awaitable[RawSpeech]]
"""Say one phrase with one voice on one model, and report. The audition's whole dependency."""
Play = Callable[[str], Awaitable[RawSpeech]]
"""Play the sample a provider already holds for a voice. Sends nothing of ELA's."""


class Audition:
    """Plays the two sentences of §9 in the voices offered, so a person can choose (ADR 0034 §9).

    Holds two callables and no state. It cannot be asked to say anything else: that is not a
    policy of this class, it is the shape of its methods.
    """

    __slots__ = ("_play", "_speak")

    def __init__(self, *, speak: Speak, play: Play) -> None:
        self._speak = speak
        self._play = play

    @property
    def phrases(self) -> tuple[str, ...]:
        """What an audition says, for whoever is about to listen to it."""
        return AUDITION_PHRASES

    async def run(self, voice_id: str, models: Sequence[str]) -> tuple[Heard, ...]:
        """Say both sentences with ``voice_id``, once per model, in order.

        More than one model because the choice between them is the user's and not a default of
        ours: at the 600-character ceiling one of them leaves 5,6 seconds of silence and the other
        1,2, and if the difference in quality can be heard, paying that silence is a decision
        somebody should make with their ears (ADR 0034 §5).
        """
        heard: list[Heard] = []
        for model in models:
            for phrase in AUDITION_PHRASES:
                said = await self._speak(phrase, voice_id, model)
                heard.append(Heard(voice_id=voice_id, model=model, phrase=phrase, said=said))
                if said.error is not None:
                    return tuple(heard)
        return tuple(heard)

    async def preview(self, voice_id: str) -> RawSpeech:
        """Play the sample the provider already holds. **No characters are sent, none are paid.**

        Best effort, and measured why: the metadata of a library voice answered ``voice_not_found``
        for one voice and ``200`` for the same voice minutes later, on 2026-09-08. A sample that
        cannot be had is a named outcome, not a broken command — and the audition is the step that
        always works.
        """
        return await self._play(voice_id)

    def candidates(self, chosen: str | None) -> tuple[Candidate, ...]:
        """The six, plus the one in use if it is not among them."""
        offered = tuple(
            Candidate(voice_id=voice_id, name=name, chosen=voice_id == chosen)
            for voice_id, name in CANDIDATES
        )
        if chosen is None or any(one.chosen for one in offered):
            return offered
        return (Candidate(voice_id=chosen, name="(la voce configurata)", chosen=True), *offered)
