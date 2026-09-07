"""How the CLI ends, and what it says on the way out (ADR 0024 §6).

Four exit codes, and they are a **contract for whoever writes a script**: "ELA is not running"
and "ELA said no" are different facts, and a script that retries the first must not retry the
second. Nothing is invented here — the message of a refusal is the API's own, the message of a
misconfiguration is the one ``python -m ela.api`` prints — because two vocabularies for one
failure is one too many.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Final, NoReturn

import typer

from ela.cli.client import ApiRefusal, Unreachable
from ela.composition import ConfigurationError

__all__ = ["CONFIGURATION", "OK", "REFUSED", "UNREACHABLE", "fail", "handled"]

OK: Final = 0
"""It worked."""
REFUSED: Final = 1
"""ELA answered, and the answer was an error (4xx, 5xx)."""
CONFIGURATION: Final = 2
"""The invocation or the configuration is wrong: nothing was sent to ELA.

It is also click's own code for a bad command line, and deliberately the same one: from the
outside both mean "what you gave me is wrong", and ELA never reached.
"""
UNREACHABLE: Final = 3
"""Nothing answered at the address: ELA is not running."""


def fail(code: int, message: str) -> NoReturn:
    """Say why on stderr and leave with ``code``. Never a traceback: this is for a person."""
    typer.echo(f"ela: {message}", err=True)
    raise typer.Exit(code)


def handled[**P](command: Callable[P, None]) -> Callable[P, None]:
    """Turn the three failures a command can meet into the three exit codes.

    A decorator on every command rather than a handler somewhere central: click has no hook that
    wraps a command's body, and a command that forgot to be wrapped would exit ``1`` with a
    traceback — which is precisely what the table exists to prevent. The decorator keeps the
    wrapped signature, which is what typer reads to build the options.
    """

    @functools.wraps(command)
    def guarded(*args: P.args, **kwargs: P.kwargs) -> None:
        try:
            command(*args, **kwargs)
        except ApiRefusal as refused:
            fail(REFUSED, f"{refused.code}: {refused.message}")
        except Unreachable as away:
            fail(UNREACHABLE, str(away))
        except ConfigurationError as wrong:
            fail(CONFIGURATION, str(wrong))

    return guarded
