"""Contract of ``AuditLog`` (spec §32): append, read, and no way to change what was written."""

from __future__ import annotations

from uuid import UUID

import pytest

from ela.domain import AuditEventId
from ela.ports import AlreadyExistsError, AuditLog
from tests.contracts.protocols import members
from tests.domain.examples import AUDIT_EVENT, TASK_ID

MUTATING_WORDS = ("update", "delete", "remove", "clear", "pop", "replace", "truncate", "set")
UNRELATED_EVENT = AUDIT_EVENT.model_copy(
    update={"id": AuditEventId(UUID("00000000-0000-4000-8000-000000000201")), "task_id": None}
)


async def test_append_then_read(audit_log: AuditLog) -> None:
    await audit_log.append(AUDIT_EVENT)
    assert await audit_log.read() == (AUDIT_EVENT,)


async def test_read_is_in_append_order(audit_log: AuditLog) -> None:
    await audit_log.append(UNRELATED_EVENT)
    await audit_log.append(AUDIT_EVENT)
    assert await audit_log.read() == (UNRELATED_EVENT, AUDIT_EVENT)


async def test_read_filters_by_task(audit_log: AuditLog) -> None:
    await audit_log.append(UNRELATED_EVENT)
    await audit_log.append(AUDIT_EVENT)
    assert await audit_log.read(task_id=TASK_ID) == (AUDIT_EVENT,)


async def test_read_returns_a_tuple(audit_log: AuditLog) -> None:
    assert isinstance(await audit_log.read(), tuple)
    await audit_log.append(AUDIT_EVENT)
    assert isinstance(await audit_log.read(), tuple)
    assert isinstance(await audit_log.read(task_id=TASK_ID), tuple)


async def test_duplicate_append_is_rejected_and_log_unchanged(audit_log: AuditLog) -> None:
    await audit_log.append(AUDIT_EVENT)
    rewritten = AUDIT_EVENT.model_copy(update={"summary": "rewritten history"})
    with pytest.raises(AlreadyExistsError):
        await audit_log.append(rewritten)
    assert await audit_log.read() == (AUDIT_EVENT,)


async def test_a_read_snapshot_does_not_change(audit_log: AuditLog) -> None:
    await audit_log.append(UNRELATED_EVENT)
    before = await audit_log.read()
    await audit_log.append(AUDIT_EVENT)
    assert before == (UNRELATED_EVENT,)


def test_no_mutating_member_on_protocol_or_implementation(audit_log: AuditLog) -> None:
    assert members(AuditLog) == {"append", "read"}
    public = [name for name in dir(audit_log) if not name.startswith("_")]
    assert sorted(public) == ["append", "read"]
    for name in public:
        assert not any(word in name.lower() for word in MUTATING_WORDS), name
