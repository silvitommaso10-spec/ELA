"""Contract of ``IdGenerator`` (spec §49, ADR 0003 §2): fresh UUIDs, never the same twice."""

from __future__ import annotations

from uuid import UUID

from ela.ports import IdGenerator


def test_returns_uuids(ids: IdGenerator) -> None:
    assert isinstance(ids.new_uuid(), UUID)


def test_never_repeats(ids: IdGenerator) -> None:
    issued = [ids.new_uuid() for _ in range(100)]
    assert len(set(issued)) == len(issued)
