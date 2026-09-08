"""``ela voice``: which voice ELA speaks with, what it costs, and how to change it (M11.3).

Three commands, and the first one is the one that matters most. ``ela voice`` is where a person
looks to see which voice ELA is using — so it is where the sentence about retention belongs: **what
ELA says with the online voice is kept by the provider.** The user accepted that knowingly, and
the decision was that the choice must stay visible (ADR 0034 §11). Not a warning before every
sentence, which is a warning people learn to skip: a fact, where the configuration is read.

The other two are how a voice gets chosen without a task per attempt:

* ``ela voice preview`` plays the sample the provider already holds — nothing of ELA's is sent and
  no credit is spent, so twenty voices cost nothing;
* ``ela voice audition`` makes a voice say the **two sentences of §9**, because the question is
  not how a voice sounds, it is how ELA sounds when she contradicts you.

Neither command can be asked to say anything else. There is no ``--text`` here and there is no
field for one on the route either, which is the same decision written twice on purpose.
"""

from __future__ import annotations

from typing import Annotated, Any

import typer

from ela.cli import client
from ela.cli.errors import handled
from ela.cli.output import Json, emit, fields, table, text

__all__ = ["app", "audition", "preview", "voice"]

app = typer.Typer(
    help="Which voice ELA speaks with, and how to change it.", invoke_without_command=True
)

RETENTION = (
    "il testo che ELA dice con questa voce è conservato da ElevenLabs e resta leggibile "
    "nella dashboard del tuo account"
)
"""The sentence, in one place. It is printed whenever the online voice is configured, and a test
fails if the fact is true and the sentence is missing (ADR 0034 §11)."""


def _lines(payload: dict[str, Any]) -> str:
    """The two voices, and what the online one costs to have."""
    spoken, online = payload["voice"], payload["voice"]["online"]
    rows: list[tuple[str, Any]] = [
        ("enabled", spoken["enabled"]),
        ("local voice", spoken["voice"] if spoken["available"] else "not available here"),
        ("online voice", online["voice_id"] or "not chosen"),
        ("online model", online["model"]),
        ("online available", online["available"]),
        ("max characters", spoken["max_characters"]),
    ]
    rendered = fields([(name, text(value)) for name, value in rows])
    if online["text_retained_by_provider"] and online["configured"]:
        rendered += f"\n\nattenzione: {RETENTION}."
    listed = table(
        ["voice", "id", "in use"],
        [
            [one["name"], one["voice_id"], "yes" if one["chosen"] else ""]
            for one in payload["candidates"]
        ],
    )
    said = "\n".join(f"  {phrase}" for phrase in payload["phrases"])
    return f"{rendered}\n\n{listed}\n\nan audition says:\n{said}"


@app.callback(invoke_without_command=True)
@handled
def voice(ctx: typer.Context, as_json: Json = False) -> None:
    """Which voice ELA is using, which ones it could use, and what the provider keeps.

    The group's own command, so that the bare ``ela voice`` answers instead of printing help:
    this is the place a person looks to see which voice is in use, and therefore the place the
    retention has to be written (ADR 0034 §11).
    """
    if ctx.invoked_subcommand is not None:
        return
    with client.connect() as api:
        payload = api.get("/voice")
    emit(payload, as_json, _lines(payload))


@app.command("preview")
@handled
def preview(
    voice_id: Annotated[str, typer.Argument(help="The voice whose own sample to play.")],
    as_json: Json = False,
) -> None:
    """Play a voice's own sample. Nothing of ELA's is sent and no credit is spent.

    Best effort: for some library voices the provider does not hand over a sample, and it changes
    its mind about which (measured). When that happens the answer says so, and the audition is
    the step that always works.
    """
    with client.connect() as api:
        payload = api.post("/voice/preview", {"voice_id": voice_id})
    emit(payload, as_json, _heard(payload))


@app.command("audition")
@handled
def audition(
    voice_id: Annotated[str, typer.Argument(help="The voice to hear.")],
    both_models: Annotated[
        bool, typer.Option("--both-models", help="Hear it on both models, not only the one in use.")
    ] = False,
    as_json: Json = False,
) -> None:
    """Make a voice say the two sentences of §9, and report what it cost.

    The sentences are written in ELA's repository and cannot be changed from here: an audition
    that accepted a sentence would be a way to say anything out loud, and send it to a provider,
    with no capability in sight.
    """
    with client.connect() as api:
        payload = api.post("/voice/audition", {"voice_id": voice_id, "both_models": both_models})
    emit(payload, as_json, _heard(payload))


def _heard(payload: dict[str, Any]) -> str:
    """What was played, in order, with the receipt of each thing the provider kept."""
    rows = [
        [
            one["model"] or "—",
            one["phrase"],
            text(one["spoken_seconds"]),
            text(one["credits"]),
            one["error"] or "",
        ]
        for one in payload["heard"]
    ]
    rendered = table(["model", "said", "seconds", "credits", "error"], rows)
    total = payload.get("credits")
    if total is not None:
        rendered += f"\n\n{total} credits — and {RETENTION}."
    return rendered
