"""``ela vault``: the state of the vault, the key handed over a pipe, and the lock (M13.9,
ADR 0063; decisions 16 and 32).

The passwords stay in the vault, and **the master password never enters ELA**: the unlock is done
by the user, in their terminal, with the vault's own program — which prints a session key on its
stdout. That key reaches ELA through a pipe::

    <the vault's program> unlock --raw | <ELA's own command> vault open

``open`` reads it **from its stdin and refuses a terminal**: a key is not typed and not pasted —
typed, it would be in the scrollback; pasted as an argument, in the shell's history. It is sent to
the Core alone and is never printed, accepted or refused. ``status`` prints what the vault is and,
for a locked one, **that whole line** — composed by ELA with the program it vouches for and with
the command it runs with, **each by its absolute path** and never with a placeholder: the ``bw``
to run is the declared one and the ``ela`` that receives the key is this one, neither the first
of a ``PATH`` (decision 98).
``close`` locks the vault and makes ELA forget the key.
"""

from __future__ import annotations

import sys
from typing import Any, Final

import typer

from ela.cli import client
from ela.cli.errors import CONFIGURATION, fail, handled
from ela.cli.output import Json, emit, fields

__all__ = ["app", "stdin_is_a_terminal"]

app = typer.Typer(
    no_args_is_help=True, help="The vault of your passwords: its state, its key, its lock."
)

FROM_A_TERMINAL: Final = (
    "the key of the vault is read from a pipe, never typed or pasted: `vault status` of this "
    "command prints the whole line to paste, with the path of your vault's program and of this "
    "command"
)
NO_KEY: Final = (
    "no key arrived on the pipe: the vault's program printed none (a wrong master password?). "
    "Nothing was sent to ELA"
)


def stdin_is_a_terminal() -> bool:
    """Whether the key would come from a keyboard. The stdin alone: the pipe is on the stdin, and
    what this command prints may well go to a terminal."""
    return sys.stdin.isatty()


def _status(payload: dict[str, Any]) -> str:
    rows = fields(
        [
            ("state", payload["state"]),
            ("program", payload["program"]),
            ("forgets the key at", payload["forgets_at"]),
        ]
    )
    said = [rows]
    if payload["message"]:
        said.append(payload["message"])
    if payload["opens_with"]:
        # On a line of its own, with nothing around it: it is copied whole.
        said.extend(["to open it, paste this line in your terminal:", payload["opens_with"]])
    return "\n".join(said)


@app.command("status")
@handled
def status(as_json: Json = False) -> None:
    """What the vault is now — asked of its program, never remembered — and, when it is locked,
    the whole line to paste to open it."""
    with client.connect() as api:
        payload = api.get("/vault")
    emit(payload, as_json, _status(payload))


@app.command("open")
@handled
def open_() -> None:
    """Read the session key from the stdin — a pipe, never a terminal — and hand it to ELA, which
    keeps it for an hour. Nothing is printed of it."""
    if stdin_is_a_terminal():
        fail(CONFIGURATION, FROM_A_TERMINAL)
    key = sys.stdin.read().strip()
    if not key:
        fail(CONFIGURATION, NO_KEY)
    with client.connect() as api:
        opened = api.post("/vault/session", {"key": key})
    typer.echo(f"the vault is open: ELA forgets the key at {opened['forgets_at']}")


@app.command("close")
@handled
def close() -> None:
    """Lock the vault — for every program on this machine, your terminal's included — and make
    ELA forget the key."""
    with client.connect() as api:
        api.post("/vault/lock")
    typer.echo("the vault is locked, and ELA forgot the key")
