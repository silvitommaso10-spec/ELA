"""Contract of ``Clock`` (spec §51, ADR 0003 §4): an aware instant in UTC, nothing more."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ela.ports import Clock


def test_now_is_timezone_aware_utc(clock: Clock) -> None:
    now = clock.now()
    assert isinstance(now, datetime)
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)
    assert now.astimezone(UTC) == now
