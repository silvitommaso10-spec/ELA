"""This machine as a **node**: a process that runs the Core's calls and decides nothing (M12.3).

A node enrols with a code a person carried, reads its own row, says what it is, says it is here,
and then does one thing forever: asks for work, runs it with its own tools, hands back what came
out. It holds an id and a secret on disk, an envelope in memory until the Core has it, and a clock
of its own. It holds no database, no task, no decision and no deadline — **the Core decides the
time** (M12.1 D6, D14), and this package may not so much as mint an expiry (architecture rule 53).

Where the code lives is a decision of its own (dec. A, ADR 0039 §1): inside ``src/ela`` and not in
the ``nodes/macos/`` of spec §48, because out there it would be outside ``mypy --strict``, outside
the coverage gate, outside the fourteen import contracts and outside all fifty-three architecture
rules — the least verified code in ELA, holding a secret and executing tools. What is common to
macOS and Windows lives here; what is not goes behind a port, in the shape of
``infrastructure/machine/darwin.py``, so M12.4 adds a module and not a branch.
"""

from __future__ import annotations

import httpx

from ela.composition.node import NodeWorld, build_node
from ela.composition.settings import NodeConfig
from ela.node.client import NodeClient, Reply, open_node_client
from ela.node.errors import (
    UNENROLLED,
    CoreUnreachable,
    NodeError,
    NodeRevoked,
    NotEnrolled,
    TwinNode,
)
from ela.node.runner import Node, declaration, envelope_of, forever
from ela.node.state import NodeIdentity, read_identity, write_identity

__all__ = [
    "CoreUnreachable",
    "Node",
    "NodeClient",
    "NodeError",
    "NodeIdentity",
    "NodeRevoked",
    "NodeWorld",
    "NotEnrolled",
    "Reply",
    "TwinNode",
    "build_node",
    "declaration",
    "envelope_of",
    "forever",
    "open_node_client",
    "read_identity",
    "run",
    "write_identity",
]


async def join_or_read(
    world: NodeWorld,
    *,
    code: str | None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> NodeClient:
    """The node's identity: the one on disk, or a new one bought with ``code`` and written down.

    Written **before** anything else happens, and with ``O_EXCL``: the enrollment answer is the one
    time ELA ever says a node's secret, so a secret received and not stored is a row nobody can
    revoke because nobody can name it. And a second enrollment over a file that already exists
    fails rather than replacing an identity the Core still has a row for.
    """
    directory = world.config.node.node_state_dir
    identity = read_identity(directory)
    if identity is not None:
        return open_node_client(world.config.node.node_core_url, identity, transport)
    if code is None:
        raise NotEnrolled(UNENROLLED)
    client = open_node_client(world.config.node.node_core_url, None, transport)
    answered = await client.enroll(code, declaration(world))
    if answered.status != httpx.codes.CREATED:
        raise NodeError(
            f"this code did not enrol the node ({answered.code or answered.status}). A code is "
            "good once and for ten minutes: ask the Core for another one."
        )
    assert client.identity is not None  # noqa: S101 — a 201 carries the identity or the DTO failed
    write_identity(directory, client.identity)
    return client


async def run(
    config: NodeConfig,
    *,
    join: str | None = None,
    world: NodeWorld | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Be a node until something says to stop (dec. C).

    In the foreground, in a terminal somebody leaves open, and **not** under ``launchd``: ADR 0029
    §16 walls that off until ELA has a signed executable of its own, and the Keychain measurement
    of this milestone found the same wall for the secret. The price is declared — the node lives as
    long as the window — and it is payable because for the Core a closed window is a node that has
    gone quiet, which the protocol already handles as an assignment that expires.

    ``world`` and ``transport`` are the seams, and they are the **tests'**: the conformance kit
    drives the acts one at a time and builds its own :class:`Node`, so the caller of this function
    is the command — and, in ``tests/node/``, whatever is driving the whole cycle at once.
    """
    # An ``if`` and not ``build_node(config) if world is None else world``: a ternary carries no
    # arc, so the arm **production** takes — building the world from the configuration — would be
    # reported as covered by tests that all pass one in. It is rule 37's argument, one package
    # over: the side that does not run costs the 100% branch gate nothing.
    built: NodeWorld
    if world is None:  # noqa: SIM108 — a ternary carries no arc; see above
        built = build_node(config)
    else:
        built = world
    built.sweep_speech()
    try:
        client = await join_or_read(built, code=join, transport=transport)
    except httpx.TransportError as away:
        # Enrolment is the one act that cannot simply be retried in the background: a code is good
        # once and for ten minutes, and the person who pasted it is standing right there. So it
        # gets the sentence and the exit code of "nobody is at that address" rather than a
        # traceback — and an already-enrolled node never reaches here at all, because reading its
        # own file touches no network.
        raise CoreUnreachable(
            f"nobody answered at {built.config.node.node_core_url}: the Core is not running "
            "there. Start it first, then run this again with the same code."
        ) from away
    # Everything else that talks to the Core is inside ``forever``, coming-up included: a node
    # started before the Core waits for it instead of dying on it (dec. D).
    await forever(
        Node(built, client),
        wait=config.node.node_retry_seconds,
        ceiling=config.node.node_retry_ceiling,
    )
