"""Hearing a voice, and seeing what it costs to keep it (M11.3, ADR 0034 §9, §11).

Three routes, none of which is a capability, and the reason is worth reading because it is not
the obvious one. Choosing a voice **could** have been done through ``voice.speak_online``: it is
already the capability that speaks. It is not, because that capability requires an authorization,
and six voices would be six approvals — precisely the cost the user refused when they asked for a
way to try voices that is not a task per attempt.

What makes that safe is not this module's care: it is that **nothing on this path can carry a
sentence of the user's.** ``AuditionIn`` has no field for text; the words are two literals in
:mod:`ela.infrastructure.machine.audition`, written in §9 and readable in ``git``; and
architecture rule 43 fails the build if a function on that path ever grows a parameter for words.

And this is where the audition ended up rather than in the CLI, which is where a chooser would
naturally live: architecture rule 27 keeps adapters out of everything but the composition root,
and rule 28 keeps the CLI a client of this API. It came out better than the plan — the property
"only the repository's words" is in the schema before it is in a rule.
"""

from __future__ import annotations

from fastapi import APIRouter

from ela.api.deps import ElaDep
from ela.api.schemas import (
    AuditionIn,
    AuditionOut,
    HeardOut,
    PreviewIn,
    VoiceCandidateOut,
    VoiceStatusOut,
)
from ela.api.system import voice_of

__all__ = ["router"]

router = APIRouter(tags=["voice"])


@router.get("/voice")
async def voice(ela: ElaDep) -> VoiceStatusOut:
    """Which voices ELA has, which one it is using, and what the provider keeps.

    The retention is stated here and not only in ``/diagnostics`` because this is the route a
    person reads when they are *choosing* a voice, which is the moment the cost is worth knowing
    (ADR 0034 §11).
    """
    chosen = ela.settings.elevenlabs.elevenlabs_voice_id
    return VoiceStatusOut(
        voice=await voice_of(ela),
        candidates=tuple(
            VoiceCandidateOut(voice_id=one.voice_id, name=one.name, chosen=one.chosen)
            for one in ela.audition.candidates(chosen)
        ),
        phrases=ela.audition.phrases,
    )


@router.post("/voice/audition")
async def audition(ela: ElaDep, asked: AuditionIn) -> AuditionOut:
    """Say the two sentences of §9 in one voice, and report what was played and what it cost.

    Stops at the first failure: an audition that kept spending after the provider refused would
    be paying to be told the same thing four times.
    """
    settings = ela.settings.elevenlabs
    models = settings.both_models if asked.both_models else (settings.elevenlabs_model,)
    heard = await ela.audition.run(asked.voice_id, models)
    rows = tuple(
        HeardOut(
            voice_id=one.voice_id,
            model=one.model,
            phrase=one.phrase,
            spoken_seconds=one.said.spoken_seconds,
            synthesis_seconds=one.said.synthesis_seconds,
            credits=one.said.credits,
            history_item_id=one.said.history_item_id,
            error=one.said.error,
        )
        for one in heard
    )
    charged = [row.credits for row in rows if row.credits is not None]
    return AuditionOut(heard=rows, credits=sum(charged) if charged else None)


@router.post("/voice/preview")
async def preview(ela: ElaDep, asked: PreviewIn) -> AuditionOut:
    """Play the sample the provider already holds. **No characters are sent, none are paid.**

    Best effort by nature, and measured why (ADR 0034 §9): the metadata of a library voice
    answered ``voice_not_found`` for one voice and ``200`` for the same voice minutes later. A
    sample that cannot be had comes back as a named error, not as a broken command.
    """
    said = await ela.audition.preview(asked.voice_id)
    return AuditionOut(
        heard=(
            HeardOut(
                voice_id=asked.voice_id,
                model="",
                phrase="(il campione del fornitore)",
                spoken_seconds=said.spoken_seconds,
                error=said.error,
            ),
        ),
        credits=None,
    )
