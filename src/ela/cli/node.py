"""``ela node run``: this machine as a node, in the foreground, until you stop it (M12.3 dec. C).

**A third kind of command** (dec. M). ADR 0024 §2 knew two: the callers, whose life *is* one
request and which end in one of four ways, and the two locals — ``init`` and ``serve`` — which open
no client and so can only work or be misconfigured. This is neither. It opens a client, so it can
be refused and can find nobody there; but its life is not a request, so nothing here returns when
an answer arrives. The criterion that names it is exactly that: **a command whose life is not one
request.**

It composes nothing itself — architecture rule 28 lets no module of ``cli/`` name ``build``,
``Ela``, ``build_node`` or ``NodeWorld``, ``serve.py`` included — it calls ``ela.node.run(...)``,
which is outside ``cli/`` and does the composing there. The same shape ``ela serve`` has had since
M8.1, and for the same reason.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from ela.cli.errors import REFUSED, handled
from ela.composition import NodeConfig
from ela.node import NodeError, run

__all__ = ["run_node"]

JOIN_PROMPT = "Enrollment code"
"""Asked for, never taken as an argument. ADR 0037 §5 in its own words: "on the node's side the
code is read from stdin without echo, never as an argument", citing ADR 0024 §2 — "a secret on the
command line ends up in the shell's history and in ``ps``". M12.1 dec. D had already tabulated the
argument as the branch that was refused."""


@handled
def run_node(
    join: Annotated[
        bool,
        typer.Option(
            "--join",
            help="Enrol this machine first: asks for the code, and does not echo it.",
        ),
    ] = False,
) -> None:
    """Run as a node: take the Core's calls, run them here, hand back what came out.

    Leave it open. ``Ctrl-C`` stops it, and for the Core a node that stopped is a node that has
    gone quiet — which the protocol already handles as an assignment that expires, not as a case of
    its own. There is no ``launchd`` plist and this milestone writes none: ADR 0029 §16 walls that
    off until ELA has a signed executable, and the Keychain measurement of M12.3 found the same
    wall around the secret. One wall, brought down once.

    The first run needs ``--join`` and a code from ``ela node enroll`` on the Core. After that the
    node knows who it is, and running it again just runs it.
    """
    code = typer.prompt(JOIN_PROMPT, hide_input=True) if join else None
    try:
        asyncio.run(run(NodeConfig.load(), join=code))
    except NodeError as stopped:
        raise typer.Exit(REFUSED) from stopped
    except KeyboardInterrupt:  # pragma: no cover - the terminal's own way of ending this
        typer.echo("")
