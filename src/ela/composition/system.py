"""The clock and the id source of a running ELA (ports ``Clock`` and ``IdGenerator``).

Until M8.1 the only implementations of these two ports were the fakes in :mod:`ela.testing`,
which no production module may import (contract 5): ELA could be tested but not run. These are
the two the composition root builds, and they are as small as the ports are — a real clock and a
real source of ids, with no policy of their own.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

__all__ = ["SystemClock", "UuidGenerator"]


class SystemClock:
    """The wall clock, always **aware and in UTC** (ADR 0003 §4).

    Never ``datetime.now()`` without a timezone: a naive instant compared with a stored one is a
    comparison between two different questions, and the domain refuses to hold one at all.
    """

    __slots__ = ()

    def now(self) -> datetime:
        return datetime.now(UTC)


class UuidGenerator:
    """Random ids (``uuid4``): no host address, no sequence, nothing to correlate (§57)."""

    __slots__ = ()

    def new_uuid(self) -> UUID:
        return uuid4()
