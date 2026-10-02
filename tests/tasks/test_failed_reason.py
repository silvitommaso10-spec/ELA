"""Every transition to ``FAILED`` writes ``code: message`` as its reason (M13.1c, ADR 0055).

``run`` reports the words of the transition that ended a task (decision C of the session), and ADR
0045 §12-bis wants a failure said as ``code: message``. Until M13.1c the transition wrote the
message alone — ``fail`` its ``error.message``, the orphan of ``recover`` the same — and the code
stood beside it, in the ``ErrorMetadata`` of the audit event, where no line a person reads shows it.
The engine writes its transitions' words, as it writes «rejected by» and «approved by»: so the code
arrives there, and the runner passes it.

Closed over the operations of :data:`~ela.tasks.engine.OPERATIONS` whose target is ``FAILED``: a new
one stops the suite here until it has its case.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest

from ela.domain import AuditEventType, ErrorMetadata, TaskId, TaskState
from ela.tasks.engine import OPERATIONS
from tests.tasks.support import ORPHAN_AFTER, Harness, executing, h

__all__ = ["h"]

ERROR = ErrorMetadata(code="probe.failed", message="what the probe says went wrong")


async def failed(h: Harness, error: ErrorMetadata) -> TaskId:
    task = await executing(h)
    await h.engine.fail(task.id, error)
    return task.id


async def orphaned(h: Harness, _: ErrorMetadata) -> TaskId:
    task = await executing(h)
    h.clock.advance(ORPHAN_AFTER)
    await h.engine.recover()
    return task.id


CASES: dict[str, Callable[[Harness, ErrorMetadata], Awaitable[TaskId]]] = {
    "fail": failed,
    "recover": orphaned,
}


def test_every_operation_to_failed_has_a_case() -> None:
    assert {op.name for op in OPERATIONS.values() if op.target is TaskState.FAILED} == set(CASES)


@pytest.mark.parametrize("operation", sorted(CASES))
async def test_a_transition_to_failed_says_its_code_and_its_message(
    h: Harness, operation: str
) -> None:
    task_id = await CASES[operation](h, ERROR)

    audit = (await h.audit.read())[-1]
    change = (await h.repository.events(task_id))[-1]
    assert audit.event_type is AuditEventType.TASK_FAILED
    assert audit.error is not None
    said = f"{audit.error.code}: {audit.error.message}"
    assert change.message == said
    assert audit.payload["reason"] == said
    assert audit.summary == f"{operation}: EXECUTING -> FAILED ({said})"


async def test_an_error_without_a_message_is_said_by_its_code_alone(h: Harness) -> None:
    """The caution of ``_why``, kept: ``code: `` with nothing after the colon is not a sentence."""
    task_id = await failed(h, ErrorMetadata(code="probe.silent", message=""))

    change = (await h.repository.events(task_id))[-1]

    assert change.message == "probe.silent"
