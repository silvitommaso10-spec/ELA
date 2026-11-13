"""Contract of ``AuditLog`` (spec §32): append, read, and no way to change what was written."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest

from ela.domain import AuditEvent, AuditEventId, AuditEventType, AuthorizationId
from ela.ports import AlreadyExistsError, AuditLog
from tests.contracts.protocols import members
from tests.domain.examples import AUDIT_EVENT, AUTHORIZATION_ID, LATER, NOW, TASK_ID

MUTATING_WORDS = ("update", "delete", "remove", "clear", "pop", "replace", "truncate", "set")
UNRELATED_EVENT = AUDIT_EVENT.model_copy(
    update={"id": AuditEventId(UUID("00000000-0000-4000-8000-000000000201")), "task_id": None}
)
LATER_EVENT = AUDIT_EVENT.model_copy(
    update={"id": AuditEventId(UUID("00000000-0000-4000-8000-000000000202")), "created_at": LATER}
)
ANOTHER_GRANT = AuthorizationId(UUID("00000000-0000-4000-8000-000000000210"))
DECIDED_EVENT = AuditEvent.model_validate(
    {
        **AUDIT_EVENT.model_dump(),
        "id": AuditEventId(UUID("00000000-0000-4000-8000-000000000203")),
        "event_type": AuditEventType.PERMISSION_DECIDED,
    }
)
"""The same grant on a decision: what a reading of «what this policy did» must leave out."""
OTHER_GRANT_EVENT = AuditEvent.model_validate(
    {
        **AUDIT_EVENT.model_dump(),
        "id": AuditEventId(UUID("00000000-0000-4000-8000-000000000204")),
        "authorization_id": ANOTHER_GRANT,
    }
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


async def test_read_since_is_inclusive(audit_log: AuditLog) -> None:
    """A time boundary is closed everywhere in the system (ADR 0005)."""
    await audit_log.append(AUDIT_EVENT)  # created_at == NOW
    await audit_log.append(LATER_EVENT)  # created_at == LATER
    assert await audit_log.read(since=NOW) == (AUDIT_EVENT, LATER_EVENT)
    assert await audit_log.read(since=LATER) == (LATER_EVENT,)
    assert await audit_log.read(since=LATER + timedelta(microseconds=1)) == ()


async def test_read_limit_keeps_the_first_in_append_order(audit_log: AuditLog) -> None:
    await audit_log.append(UNRELATED_EVENT)
    await audit_log.append(AUDIT_EVENT)
    assert await audit_log.read(limit=1) == (UNRELATED_EVENT,)
    assert await audit_log.read(limit=10) == (UNRELATED_EVENT, AUDIT_EVENT)


@pytest.mark.parametrize("limit", [0, -1])
async def test_a_non_positive_limit_is_a_callers_bug(audit_log: AuditLog, limit: int) -> None:
    """``limit`` is ``None`` or >= 1 (review M2.1): never an empty answer to a wrong question."""
    await audit_log.append(AUDIT_EVENT)
    with pytest.raises(ValueError):
        await audit_log.read(limit=limit)


async def test_newest_first_reads_from_the_other_end(audit_log: AuditLog) -> None:
    """The tuple keeps the order it was read in (ADR 0025 §3): newest to oldest."""
    await audit_log.append(UNRELATED_EVENT)
    await audit_log.append(AUDIT_EVENT)

    assert await audit_log.read(newest_first=True) == (AUDIT_EVENT, UNRELATED_EVENT)
    assert await audit_log.read() == (UNRELATED_EVENT, AUDIT_EVENT)


async def test_newest_first_with_a_limit_keeps_the_last_entries(audit_log: AuditLog) -> None:
    """The debt this parameter pays: ``tail -n 1`` is one entry, not the whole log trimmed."""
    await audit_log.append(UNRELATED_EVENT)
    await audit_log.append(AUDIT_EVENT)
    await audit_log.append(LATER_EVENT)

    assert await audit_log.read(limit=1, newest_first=True) == (LATER_EVENT,)
    assert await audit_log.read(limit=2, newest_first=True) == (LATER_EVENT, AUDIT_EVENT)
    assert await audit_log.read(limit=1) == (UNRELATED_EVENT,)


async def test_newest_first_applies_the_filters_first_as_the_other_direction_does(
    audit_log: AuditLog,
) -> None:
    await audit_log.append(UNRELATED_EVENT)
    await audit_log.append(AUDIT_EVENT)
    await audit_log.append(LATER_EVENT)

    assert await audit_log.read(task_id=TASK_ID, newest_first=True) == (LATER_EVENT, AUDIT_EVENT)
    assert await audit_log.read(task_id=TASK_ID, limit=1, newest_first=True) == (LATER_EVENT,)
    assert await audit_log.read(since=LATER, limit=1, newest_first=True) == (LATER_EVENT,)


async def test_newest_first_of_an_empty_log_is_empty(audit_log: AuditLog) -> None:
    assert await audit_log.read(newest_first=True) == ()


@pytest.mark.parametrize("limit", [0, -1])
async def test_a_non_positive_limit_is_a_callers_bug_in_both_directions(
    audit_log: AuditLog, limit: int
) -> None:
    await audit_log.append(AUDIT_EVENT)
    with pytest.raises(ValueError):
        await audit_log.read(limit=limit, newest_first=True)


async def test_read_filters_apply_before_limit(audit_log: AuditLog) -> None:
    await audit_log.append(UNRELATED_EVENT)
    await audit_log.append(AUDIT_EVENT)
    await audit_log.append(LATER_EVENT)
    assert await audit_log.read(task_id=TASK_ID, limit=1) == (AUDIT_EVENT,)
    assert await audit_log.read(task_id=TASK_ID, since=LATER, limit=5) == (LATER_EVENT,)


async def test_read_filters_by_authorization(audit_log: AuditLog) -> None:
    """The events of one grant (M13.14, ADR 0068; answer 29): a policy's actions are read by its
    id, and an event of another grant, or of none, is left out."""
    await audit_log.append(UNRELATED_EVENT.model_copy(update={"authorization_id": None}))
    await audit_log.append(OTHER_GRANT_EVENT)
    await audit_log.append(AUDIT_EVENT)

    assert await audit_log.read(authorization_id=AUTHORIZATION_ID) == (AUDIT_EVENT,)
    assert await audit_log.read(authorization_id=ANOTHER_GRANT) == (OTHER_GRANT_EVENT,)


async def test_read_filters_by_event_type(audit_log: AuditLog) -> None:
    """The events of one type: the same grant stands on a decision and on an execution."""
    await audit_log.append(DECIDED_EVENT)
    await audit_log.append(AUDIT_EVENT)

    assert await audit_log.read(event_type=AuditEventType.TOOL_EXECUTED) == (AUDIT_EVENT,)
    assert await audit_log.read(event_type=AuditEventType.PERMISSION_DECIDED) == (DECIDED_EVENT,)
    assert await audit_log.read(event_type=AuditEventType.EXECUTION_VERIFIED) == ()


async def test_the_filters_of_a_grant_apply_before_limit_from_either_end(
    audit_log: AuditLog,
) -> None:
    """«The last five actions of a policy» are five ``TOOL_EXECUTED`` of its id, read from the end:
    the two filters apply before ``limit``, as every filter does, in both directions."""
    await audit_log.append(AUDIT_EVENT)
    await audit_log.append(DECIDED_EVENT)
    await audit_log.append(OTHER_GRANT_EVENT)
    await audit_log.append(LATER_EVENT)

    acted = {"authorization_id": AUTHORIZATION_ID, "event_type": AuditEventType.TOOL_EXECUTED}
    assert await audit_log.read(**acted, limit=5, newest_first=True) == (LATER_EVENT, AUDIT_EVENT)
    assert await audit_log.read(**acted, limit=1, newest_first=True) == (LATER_EVENT,)
    assert await audit_log.read(**acted, limit=1) == (AUDIT_EVENT,)


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
    """The port has two members and no more; an implementation may *read* in one more way.

    ``SqlAuditLog.verify`` is that way (M8.2, ADR 0024 §4), and it is why this is a check on what
    each name does rather than a list: what must never appear is a member that changes what was
    written, whatever it is called.
    """
    assert members(AuditLog) == {"append", "read"}
    public = [name for name in dir(audit_log) if not name.startswith("_")]
    assert members(AuditLog) <= set(public)
    for name in public:
        assert not any(word in name.lower() for word in MUTATING_WORDS), name
