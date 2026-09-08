"""The voice in ``/diagnostics``, and the two things M11.1 promises leave no trace (ADR 0033).

``/diagnostics`` says *what ELA is connected to*, not *what ELA is doing* (ADR 0028 §8), so
whether ELA has a voice here belongs beside ``providers`` and ``tools``. There is deliberately
**no route that says whether ELA is speaking**: a sentence lasts as long as a sentence, and a
status true for thirty seconds is not one anybody can act on.
"""

from __future__ import annotations

from httpx import AsyncClient

from ela.composition import Ela
from ela.tools.settings import MAX_SPOKEN_CHARACTERS


async def test_diagnostics_says_whether_ela_has_a_voice_here(client: AsyncClient, ela: Ela) -> None:
    body = (await client.get("/diagnostics")).json()

    assert body["voice"] == {
        "enabled": ela.settings.voice.voice_enabled,
        "available": await ela.speech.available(),
        "voice": ela.settings.voice.voice_name,
        "max_characters": MAX_SPOKEN_CHARACTERS,
        "timeout_seconds": ela.settings.voice.voice_timeout_seconds,
    }


async def test_the_switch_and_the_machine_are_two_fields(client: AsyncClient) -> None:
    """ "You turned it off" and "this machine has no voice" must be separately readable, or a
    reader cannot tell which one to do something about (ADR 0030 §8)."""
    voice = (await client.get("/diagnostics")).json()["voice"]

    assert "enabled" in voice
    assert "available" in voice


async def test_there_is_no_route_that_says_whether_ela_is_speaking(client: AsyncClient) -> None:
    """Asserted rather than assumed: the absence is a decision (ADR 0033 §10), and an absence
    nobody tests is an absence somebody adds back without noticing."""
    assert (await client.get("/voice")).status_code == 404


def test_the_voice_writes_nothing_anywhere_it_could(ela: Ela) -> None:
    """Criterion 3 of M11.1, and the reason rule 40 exists: there is no store to design because
    there is nothing to keep.

    Asserted against the two directories a voice could plausibly have leaked into — the capture
    store, which is the only place ELA keeps content, and the workspace — plus the absence of a
    setting that would name a third.
    """
    assert not hasattr(ela.settings.voice, "voice_dir")
    assert set(type(ela.settings.voice).model_fields) == {
        "voice_enabled",
        "voice_name",
        "voice_timeout_seconds",
    }
