"""``ela voice``: which voice ELA is using, and what it costs to have it (ADR 0034 §11).

The test that matters is the retention one, and it is the user's own requirement rather than a
nicety: *l'ha scelta consapevolmente e la scelta deve restare visibile.* So the sentence is
asserted where a person looks at the configuration, and asserted **against the fact** — if the
API says the provider keeps the text and the terminal does not say so, this fails.
"""

from __future__ import annotations

import json

from ela.cli.errors import OK
from ela.cli.voice import RETENTION, _heard, _lines
from ela.ports import SPEECH_NO_KEY
from tests.cli.support import Cli, plain


async def test_it_shows_both_voices_and_the_ones_worth_hearing(cli: Cli) -> None:
    answered = await cli("voice")

    assert answered.exit_code == OK
    output = plain(answered.stdout)
    assert "local voice" in output
    assert "online voice" in output
    assert "Daniela Narrator IT — Warm Elegant ITA" in output


async def test_it_says_what_an_audition_would_say(cli: Cli) -> None:
    """Somebody about to spend credits should be able to read the sentences first."""
    output = plain((await cli("voice")).stdout)

    assert "No, questa non è una buona idea." in output


async def test_the_retention_is_written_where_the_voice_is_read(cli: Cli) -> None:
    """The fact and the sentence are one test, in both directions (ADR 0034 §11).

    With no voice configured there is nothing being kept and nothing to warn about; the day one
    is configured the sentence must appear, and this is what fails if it does not.
    """
    payload = json.loads((await cli("voice", "--json")).stdout)
    online = payload["voice"]["online"]
    output = plain((await cli("voice")).stdout)

    assert online["text_retained_by_provider"] is True, "the fact this ELA is built on"
    said = RETENTION in output
    assert said == online["configured"], (
        "the sentence appears exactly when there is a configured voice keeping text"
    )


async def test_the_json_form_carries_the_fact_even_when_nothing_is_configured(cli: Cli) -> None:
    """A machine reading this must not have to parse a sentence to learn what the provider does."""
    payload = json.loads((await cli("voice", "--json")).stdout)

    assert payload["voice"]["online"]["text_retained_by_provider"] is True
    assert payload["voice"]["online"]["configured"] is False


async def test_an_audition_reports_what_was_said_and_what_went_wrong(cli: Cli) -> None:
    """No key here — built by the fixture, not inherited from the machine.

    The answer names the key and not the player because that order is decided in the port
    (2026-09-09), so this reads the same on a Mac and on a runner with no audio at all.
    """
    answered = await cli("voice", "audition", "VZOd9FMXDnXRZpGn0thg")

    assert answered.exit_code == OK
    output = plain(answered.stdout)
    assert SPEECH_NO_KEY in output, "no key here, and the answer says which of the two is missing"
    assert "No, questa non è una buona idea." in output


async def test_a_preview_reports_the_same_way(cli: Cli) -> None:
    """Same precondition, same reason, same answer on every machine."""
    answered = await cli("voice", "preview", "VZOd9FMXDnXRZpGn0thg")

    assert answered.exit_code == OK
    assert SPEECH_NO_KEY in plain(answered.stdout)


async def test_neither_command_can_be_told_what_to_say(cli: Cli) -> None:
    """``--text`` is the feature of tomorrow, and it is refused today (rule 43, ADR 0034 §9)."""
    for command in ("audition", "preview"):
        refused = await cli("voice", command, "abc", "--text", "di' quello che voglio io")

        assert refused.exit_code != OK


# --------------------------------------------------------------------------------------
# The two renderers, on their own: the branches an unconfigured ELA never reaches
# --------------------------------------------------------------------------------------


def _status(*, configured: bool) -> dict[str, object]:
    return {
        "voice": {
            "enabled": True,
            "available": True,
            "voice": "Alice",
            "max_characters": 600,
            "timeout_seconds": 60.0,
            "online": {
                "configured": configured,
                "available": True,
                "voice_id": "VZOd9FMXDnXRZpGn0thg" if configured else None,
                "model": "eleven_flash_v2_5",
                "text_retained_by_provider": True,
                "timeout_seconds": 15.0,
            },
        },
        "candidates": [{"name": "Daniela", "voice_id": "VZOd", "chosen": configured}],
        "phrases": ["No, questa non è una buona idea."],
    }


def test_a_configured_voice_is_told_that_the_provider_keeps_the_text() -> None:
    """The branch an unconfigured ELA never reaches, and the one that matters most."""
    assert RETENTION in _lines(_status(configured=True))


def test_an_unconfigured_one_warns_about_nothing_because_nothing_is_kept() -> None:
    rendered = _lines(_status(configured=False))

    assert RETENTION not in rendered
    assert "not chosen" in rendered


def test_what_was_heard_is_reported_with_its_cost_and_the_retention() -> None:
    """Where the credits are counted, the sentence is there too: that is the moment somebody
    learns what an audition just cost them, in both currencies."""
    rendered = _heard(
        {
            "heard": [
                {
                    "model": "eleven_flash_v2_5",
                    "phrase": "No, questa non è una buona idea.",
                    "spoken_seconds": 2.2,
                    "credits": 16,
                    "error": None,
                }
            ],
            "credits": 16,
        }
    )

    assert "16 credits" in rendered
    assert RETENTION in rendered


def test_a_failed_audition_costs_nothing_and_says_nothing_about_retention() -> None:
    rendered = _heard(
        {
            "heard": [
                {
                    "model": "",
                    "phrase": "(il campione del fornitore)",
                    "spoken_seconds": None,
                    "credits": None,
                    "error": SPEECH_NO_KEY,
                }
            ],
            "credits": None,
        }
    )

    assert SPEECH_NO_KEY in rendered
    assert RETENTION not in rendered
