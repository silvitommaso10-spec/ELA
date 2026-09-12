"""Coming up as a node: the identity first, then the cycle (M12.3 dec. C, dec. B).

The order is the decision. The enrollment answer is the one time ELA ever says a node's secret, so
it is written down **before** anything else happens: a secret received and not stored is a row
nobody can revoke, because nobody can name it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ela.node import (
    CoreUnreachable,
    NodeError,
    NodeRevoked,
    NotEnrolled,
    read_identity,
    run,
)
from ela.node.state import STATE_FILE
from tests.node.support import dropped, ok, refused, replies, status, world

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
        ok({}),  # heartbeat: every pass says "I am here" before it asks
        status(401),  # the first ask: revoked
    )
    built = world(tmp_path)

    with pytest.raises(NodeRevoked):
        await run(built.config, join="un-codice", world=built, transport=script.transport())

    kept = read_identity(tmp_path)
    assert kept is not None
    assert kept.device_id == BORN["device_id"]
    # The order is the property, not just the set: the revision is **read** before it is used
    # (dec. L), and the node says it is here before it asks for anything. This is where the
    # production start-up is pinned — the conformance kit builds its own and cannot pin this.
    assert [path for _, path in script.seen] == [
        "/nodes/enroll",
        "/nodes/me",
        "/nodes/me",
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
    script = replies(ok({}, ETag='"3"'), ok({}, ETag='"4"'), ok({}), status(401))
    built = world(tmp_path)

    with pytest.raises(NodeRevoked):
        await run(built.config, join="un-codice", world=built, transport=script.transport())

    assert "/nodes/enroll" not in [path for _, path in script.seen]


async def test_a_node_started_before_the_core_waits_for_it_instead_of_dying_on_it(
    tmp_path: Path,
) -> None:
    """Dec. D's second row, at the one moment it is most likely to happen.

    A reboot brings both terminals back and nothing says which goes first, so "the Core is not
    listening yet" is the ordinary way a node starts — not an edge case. Before the coming-up moved
    inside the retry, ``httpx.ConnectError`` escaped ``run``, escaped the command's three
    ``except`` clauses and escaped ``@handled``, and a person got a traceback and exit ``1`` where
    dec. D says "wait and retry" and ADR 0039 §4 says exit ``3``.
    """
    (tmp_path / "node.json").write_text(
        json.dumps({"device_id": BORN["device_id"], "secret": BORN["secret"]}), encoding="utf-8"
    )
    script = replies(dropped(), dropped(), dropped())
    built = world(tmp_path, node_retry_ceiling=3, node_retry_seconds=0.001)

    with pytest.raises(CoreUnreachable, match="3 tries"):
        await run(
            built.config,
            world=built,
            transport=script.transport(),
        )


async def test_enrolling_against_a_core_that_is_not_there_is_a_sentence_and_not_a_traceback(
    tmp_path: Path,
) -> None:
    """The one act that is not retried in the background: a code is good once and for ten minutes,
    and the person who pasted it is standing there. So it gets the sentence and exit ``3``."""
    built = world(tmp_path)

    with pytest.raises(CoreUnreachable, match="not running"):
        await run(
            built.config,
            join="un-codice",
            world=built,
            transport=replies(dropped()).transport(),
        )


async def test_a_node_with_no_world_handed_to_it_builds_its_own(tmp_path: Path) -> None:
    """The arm production takes, and the only test that takes it.

    Everything else hands ``run`` a world already built, so without this the line that builds one
    from the configuration would never run — and, until it stopped being a ternary, would have
    been reported as covered anyway (rule 37's argument, one package over).
    """
    (tmp_path / "node.json").write_text(
        json.dumps({"device_id": BORN["device_id"], "secret": BORN["secret"]}), encoding="utf-8"
    )
    built = world(tmp_path, node_retry_ceiling=1, node_retry_seconds=0.001)

    with pytest.raises(CoreUnreachable):
        await run(built.config, transport=replies(dropped()).transport())
