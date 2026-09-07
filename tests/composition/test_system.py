"""``SystemClock`` and ``UuidGenerator`` (ADR 0023 §4): the first real implementations.

Until M8.1 the only ``Clock`` and ``IdGenerator`` in the repository were the fakes of
``ela.testing``, which no production module may import (contract 5): ELA could be tested but not
run. The port contracts themselves live in ``tests/contracts`` and now run on these two as well
(``tests/contracts/implementations.py``); what is left here is what only these two say.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ela.composition import SystemClock, UuidGenerator


def test_now_is_aware_and_in_utc() -> None:
    """A naive instant compared with a stored one is two different questions (ADR 0003 §4)."""
    now = SystemClock().now()

    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_now_is_the_wall_clock_and_moves_forward() -> None:
    clock = SystemClock()
    before = datetime.now(UTC)

    first, second = clock.now(), clock.now()

    assert before <= first <= second
    assert second - before < timedelta(seconds=10)


def test_ids_are_random_and_never_repeat() -> None:
    ids = UuidGenerator()

    minted = {ids.new_uuid() for _ in range(100)}

    assert len(minted) == 100
    assert all(one.version == 4 for one in minted)  # nothing of this machine in them (§57)
