"""The ``ela`` command: every sub-command, and nothing else (ADR 0024 §3).

Seventeen commands over fourteen routes plus the two that are not calls at all — ``init``, which
prepares the machine, and ``serve``, which starts the process. Nothing is composed here: the app
holds commands, and each command opens a client when it runs.
"""

from __future__ import annotations

import typer

from ela.cli import audit, nodes, serve, setup, system, tasks

__all__ = ["app", "main"]

app = typer.Typer(
    name="ela",
    no_args_is_help=True,
    add_completion=False,
    help="ELA — talk to the assistant running on this machine.",
)

app.add_typer(tasks.app, name="task")
app.add_typer(audit.app, name="audit")
app.add_typer(nodes.devices, name="device")
app.add_typer(nodes.providers, name="provider")

app.command("health")(system.health)
app.command("diagnostics")(system.diagnostics)
app.command("approvals")(system.approvals)
app.command("init")(setup.init)
app.command("serve")(serve.serve)


def main() -> None:
    """``ela``: what the console script and ``python -m ela.cli`` both call."""
    app()
