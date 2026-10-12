"""``ela browser``: the state of ELA's browser with your accounts, its window, and the window
where you sign in by hand (M13.9, ADR 0063 §8; decisions 18 and 34).

``status`` prints what the profile is — looked at again at every call —: usable or not and why,
free or held and by whom, with a window or without, and whether the browser knows an account of
its maker's. ``window show`` and ``window hide`` turn **your** switch: no capability has an
argument for it and no tool decides it, and it is off again at every start of ELA. ``open`` opens
the window where you sign in to a site with your own hands, on a site you declared or on none:
**ELA reads nothing of that window**, and while it is open it does not begin to look at the
screen or to listen. ``close`` ends that browser: the red button of its window closes the window
and leaves the browser running, and the profile stays held until the process ends.
"""

from __future__ import annotations

from typing import Annotated, Any

import typer

from ela.cli import client
from ela.cli.errors import handled
from ela.cli.output import Json, emit, fields

__all__ = ["app", "window"]

app = typer.Typer(
    no_args_is_help=True,
    help="ELA's browser with your accounts: its state, its window, and signing in by hand.",
)
window = typer.Typer(
    no_args_is_help=True, help="Whether the browser of the next step has a window: yours to say."
)
app.add_typer(window, name="window")

NOT_READ = "not read"
"""What a fact of the folder is when the folder could not be read: not «no», and not «none»."""
ONLY_ONE_IS_ELA_S = "ELA prepares and uses one, and counts the passwords saved in all of them"
"""What is said of a folder that holds more than one profile of the browser's (decision 79)."""
CLOSED = {
    "quit": "it quit when told: the profile is free",
    "killed": "it did not quit when told, and was killed: the profile is free",
    "told": (
        "it was told to quit, and ELA cannot say that it did — it was not killed: look at "
        "`ela browser status`, and quit it yourself if it is still there"
    ),
    "nothing": "no browser was open on the profile: nobody was told",
}
"""What ``close`` says, by what became of the browser."""


def _status(payload: dict[str, Any]) -> str:
    linked, saved, profiles = payload["linked"], payload["saved"], payload.get("profiles")
    said: list[tuple[str, Any]] = [
        ("state", payload["state"]),
        ("steps run", "with a window" if payload["window"] else "without a window"),
        ("linked to an account", NOT_READ if linked is None else ("yes" if linked else "no")),
        ("saved passwords", NOT_READ if saved is None else saved),
    ]
    if profiles is not None and profiles > 1:
        # One profile is the browser's own first, and nothing to be told.
        said.append(("profiles in the folder", f"{profiles} — {ONLY_ONE_IS_ELA_S}"))
    said.append(("sites", ", ".join(payload["sites"]) or None))
    rows = fields(said)
    return f"{rows}\n{payload['message']}" if payload["message"] else rows


@app.command("status")
@handled
def status(as_json: Json = False) -> None:
    """What the profile is now: usable or not and why, free or held and by whom, with a window
    or without, and what the browser says of itself — read again at every call."""
    with client.connect() as api:
        payload = api.get("/browser")
    emit(payload, as_json, _status(payload))


def _turn(shown: bool) -> None:
    with client.connect() as api:
        turned = api.post("/browser/window", {"shown": shown})
    said = "a window" if turned["shown"] else "no window"
    typer.echo(f"the steps with your accounts start with {said} from now, until ELA stops")


@window.command("show")
@handled
def show() -> None:
    """Give the browser of the next steps a window. It opens nothing now."""
    _turn(True)


@window.command("hide")
@handled
def hide() -> None:
    """Take the window away again: what every start of ELA does."""
    _turn(False)


@app.command("open")
@handled
def open_(
    site: Annotated[
        str | None,
        typer.Argument(help="One of the sites you declared; none opens the browser's own page."),
    ] = None,
) -> None:
    """Open the window where you sign in by hand. ELA reads nothing of it, and does not begin
    to look at the screen or to listen while it is open; you end it, by quitting that browser."""
    with client.connect() as api:
        opened = api.post("/browser/open", {} if site is None else {"site": site})
    where = "" if opened["site"] is None else f" on {opened['site']}"
    typer.echo(
        f"the window is open{where}: sign in, then quit that browser (Cmd-Q — closing the window "
        "alone leaves it running). ELA reads nothing of it"
    )


@app.command("close")
@handled
def close() -> None:
    """End the browser where you sign in by hand: told to quit, waited for, and killed only if
    it does not. The red button of its window leaves it running — this does not."""
    with client.connect() as api:
        closed = api.post("/browser/close", {})
    typer.echo(CLOSED.get(closed["outcome"], closed["outcome"]))
