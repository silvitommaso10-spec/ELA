"""How a node's cycle ends when it ends badly, and what each ending means (M12.3 dec. D).

Four, and they are four because the command above them owes a person four different answers. A
node that stopped for any of these reasons stopped **on purpose**: the failure a node must never
have is the silent one, where the process is up and asking nobody for work that will never come.
"""

from __future__ import annotations

from typing import Final

__all__ = ["CoreUnreachable", "NodeError", "NodeRevoked", "NotEnrolled", "TwinNode"]


class NodeError(Exception):
    """A node stopped, and the reason is worth a sentence to whoever is looking at the terminal."""


class NotEnrolled(NodeError):
    """There is no identity on this machine and no code was offered to get one."""


class NodeRevoked(NodeError):
    """``401``: the Core no longer knows this node (M12.1 D13).

    Nothing to retry. A revoked node that kept asking would write a ``DEVICE_REJECTED`` on every
    cycle — an audit log filled by a process nobody told to stop.
    """


class TwinNode(NodeError):
    """``412`` twice in a row: a second process is announcing with this identity (ADR 0035 §5).

    Once is a revision that moved while this node was not looking, and the answer to that is to
    read it again. Twice, straight after reading it, is somebody else writing — and the node says
    so and stops, the way the loser of story 5 does. A node that instead announced harder would
    take from ADR 0035 §5 its only proof: two processes would chase each other forever, each
    winning one announcement and losing the next, and neither would ever tell anybody.
    """


class CoreUnreachable(NodeError):
    """Nobody answered at the address, for as many tries in a row as the ceiling allows.

    A ceiling and not an infinite wait, for the reason ADR 0023 §3 gives about TTLs: a process that
    never gives up on a Core that is never coming back is a process nobody will notice is useless.
    """


TWIN: Final = (
    "a second process is announcing as this node: its revision moved again immediately after "
    "this one read it. One of the two must stop, and this one is stopping (ADR 0035 §5)."
)
REVOKED: Final = "this node has been revoked: the Core no longer accepts its identity."
UNCONDITIONAL: Final = (
    "this node announced itself without the revision it last saw, and the Core refused the "
    "announcement as unconditional (428). That is a defect in the node, not in the Core."
)
UNENROLLED: Final = (
    "this machine is not enrolled as a node. Issue a code on the Core with "
    "`ela node enroll --privacy TRUSTED`, then run `ela node run --join` and paste it."
)
