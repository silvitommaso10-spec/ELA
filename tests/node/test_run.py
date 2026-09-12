"""Coming up as a node: the identity first, then the cycle (M12.3 dec. C, dec. B).

The order is the decision. The enrollment answer is the one time ELA ever says a node's secret, so
it is written down **before** anything else happens: a secret received and not stored is a row
nobody can revoke, because nobody can name it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ela.node import NodeError, NodeRevoked, NotEnrolled, read_identity, run
from ela.node.state import STATE_FILE
from tests.node.support import CORE, config, ok, refused, replies, status, world

BORN = {
    "device_id": "0b1d3c5e-0000-4000-8000-000000000003",
    "secret": "un-segreto-abbastanza-lungo-da-sembrare-vero",  # pragma: allowlist secret
    "revision": 1,
}


async def test_a_first_run_enrols_writes_the_identity_and_then_starts_asking(
    tmp_path: Path,
) -> None:
    """The whole start-up in one pass, ending at the one answer that stops a node on purpose."""
    script = replies(
        status(201, BORN),  # enroll
        ok({}, ETag='"1"'),  # GET /nodes/me
        ok({}, ETag='"2"'),  # PUT /nodes/me
        ok({}),  # heartbeat, at start-up
        ok({}),  # heartbeat, before the first ask — every pass says "I am here"
        status(401),  # the first ask: revoked
    )
    built = world(tmp_path)

    with pytest.raises(NodeRevoked):
        await run(built.config, join="un-codice", world=built, transport=script.transport())

    kept = read_identity(tmp_path)
    assert kept is not None
    assert kept.device_id == BORN["device_id"]
    assert [path for _, path in script.seen] == [
        "/nodes/enroll",
        "/nodes/me",
        "/nodes/me",
        "/nodes/heartbeat",
        "/nodes/heartbeat",
        "/nodes/work",
    ]


async def test_a_machine_that_never_enrolled_and_was_offered_no_code_says_what_to_do(
    tmp_path: Path,
) -> None:
    """``NotEnrolled`` and not a traceback: whoever reads this is at a terminal, and the sentence
    has to contain the two commands that fix it."""
    built = world(tmp_path)

    with pytest.raises(NotEnrolled, match="ela node enroll"):
        await run(built.config, world=built, transport=replies().transport())


async def test_a_code_that_does_not_work_says_so_and_writes_nothing(tmp_path: Path) -> None:
    """A code is good once and for ten minutes (ADR 0037 §5). Nothing is written on the way out:
    a state file half-created would make the next attempt fail on ``O_EXCL`` instead."""
    built = world(tmp_path)

    with pytest.raises(NodeError, match="did not enrol"):
        await run(
            built.config,
            join="vecchio",
            world=built,
            transport=replies(refused(401, "code_reused")).transport(),
        )

    assert read_identity(tmp_path) is None


async def test_a_node_that_already_has_an_identity_does_not_enrol_again(tmp_path: Path) -> None:
    """Even when a code is offered. Re-enrolling would mint a second identity for one machine,
    and the Core would keep a row for the first that nobody can name any more."""
    (tmp_path / STATE_FILE).write_text(
        json.dumps({"device_id": BORN["device_id"], "secret": BORN["secret"]}), encoding="utf-8"
    )
    script = replies(ok({}, ETag='"3"'), ok({}, ETag='"4"'), ok({}), ok({}), status(401))
    built = world(tmp_path)

    with pytest.raises(NodeRevoked):
        await run(built.config, join="un-codice", world=built, transport=script.transport())

    assert "/nodes/enroll" not in [path for _, path in script.seen]


def test_the_core_s_address_is_the_node_s_own_variable(tmp_path: Path) -> None:
    """Open question 1: on this machine loopback is the address, because the middleware classifies
    by identity and never by address. A node on another machine sets the tailnet one, and then the
    declared constraint of ADR 0037 §2 is about it."""
    assert config(tmp_path).node.node_core_url == CORE
    assert world(tmp_path).config.node.node_core_url == CORE
