"""``ela serve``: the command that starts the process (ADR 0024 §2).

**The one module of this package allowed to import ``ela.api``** (architecture rule 28), because
it is the one command that is not a client: there is nothing to talk to until it runs. It adds no
behaviour of its own — the address, the token and the whole wiring come from the settings, and
``python -m ela.api`` remains exactly the same thing under a longer name.
"""

from __future__ import annotations

from ela.api import server
from ela.cli.errors import handled
from ela.composition import Settings

__all__ = ["serve"]


@handled
def serve() -> None:
    """Start ELA and serve it on the loopback address the settings declare.

    A configuration ELA cannot use stops here, with the name of the variable and what to do with
    it — never a traceback, because whoever reads it wrote the ``.env``.
    """
    server.serve(Settings.load())
