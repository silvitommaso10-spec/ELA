"""The ``ela`` command: every sub-command, and nothing else (ADR 0024 §3).

Twenty-six commands, of three kinds (ADR 0024 §3, ADR 0039 §4): the ones whose life *is* one
request, the two that are not calls at all — ``init``, which prepares the machine, and ``serve``,
which starts the process — and, since M12.3, the one whose life is not one request: ``node run``,
which opens a client and then stays. Nothing is composed here: the app holds commands, and each
command opens a client, or a whole node, when it runs.
"""

from __future__ import annotations

import typer

from ela.cli import audit, context, node, nodes, serve, setup, system, tasks, voice

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
nodes.node.command("run")(node.run_node)
app.add_typer(nodes.node, name="node")
app.add_typer(nodes.providers, name="provider")
app.add_typer(voice.app, name="voice")

app.command("health")(system.health)
app.command("diagnostics")(system.diagnostics)
app.command("approvals")(system.approvals)
app.command("context")(context.context)
app.command("perception")(system.perception)
app.command("init")(setup.init)
app.command("serve")(serve.serve)


def main() -> None:
    """``ela``: what the console script and ``python -m ela.cli`` both call."""
    app()
