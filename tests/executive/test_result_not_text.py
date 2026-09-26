"""A result that is not text, on this machine and on a node (M13.3, form I; ADR 0047 §16 paid).

A lone surrogate is a string for the JSON parser and text for nobody else. The check is one —
``ela.domain.is_text`` — and it is read where a result is kept, whichever machine produced it: the
same answer on ``local`` and on a node, which is the parity ADR 0038 §3 measures.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from ela.domain import AuditEventType, ExecutionStatus, StepState, TaskState, is_text
from ela.executive import RESULT_NOT_TEXT, Delivery, Envelope, RunOutcome
from tests.executive.support import world
from tests.executive.test_executor_remote import answered, handed
from tests.permissions.support import ECHO

LONE = "x\ud800y"


@pytest.mark.parametrize(
    ("value", "text"),
    [
        ("ciao", True),
        ("perché — città 🌍", True),
        (LONE, False),
        ({"a": {"b": ("ok", LONE)}}, False),
        ({LONE: "key"}, False),
        (["ok", ["deep", LONE]], False),
        ({"n": 3, "f": 1.5, "b": True, "none": None}, True),
    ],
)
def test_one_definition_of_text(value: object, text: bool) -> None:
    assert is_text(value) is text


def strict_digest(envelope: Envelope) -> str:
    """The digest as it was until M13.3: a strict encoding, which a lone surrogate made raise."""
    return hashlib.sha256(
        json.dumps(
            {
                "form": envelope.form.value,
                "status": None if envelope.status is None else envelope.status.value,
                "output": dict(envelope.output),
                "error": None,
                "usage": None,
                "duration_ms": envelope.duration_ms,
                "exception": envelope.exception,
                "node": dict(envelope.node),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


@pytest.mark.parametrize(
    "output",
    [{"message": "ciao"}, {"message": "perché — città 🌍"}, {"n": 3, "list": ["a", "é"]}],
)
def test_the_digest_of_an_envelope_of_text_is_the_one_it_was(output: dict[str, object]) -> None:
    envelope = answered(output=output)

    assert envelope.digest == strict_digest(envelope)


def test_an_envelope_holding_a_lone_surrogate_has_a_digest_and_not_an_exception() -> None:
    envelope = answered(output={"message": LONE})

    assert len(envelope.digest) == 64
    assert envelope.digest != answered(output={"message": "xy"}).digest


async def test_a_local_tool_that_answers_with_a_lone_surrogate_fails_its_step_by_name() -> None:
    w = world()
    w.tool(ECHO.id).output = {"message": LONE}
    task, (step,) = await w.queued(ECHO.id)

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.FAILED
    (result,) = [r for r in await w.results.for_step(task.id, step.id)]
    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None and result.error.code == RESULT_NOT_TEXT
    assert "output" in result.error.message and "\ud800" not in result.error.message
    assert result.output == {}
    assert (await w.engine.graph(task.id)).states[step.id] is StepState.FAILED


async def test_a_node_that_delivers_a_lone_surrogate_ends_its_step_the_same_way() -> None:
    w = world()
    step, remote, assignment = await handed(w)
    task_id = assignment.task_id  # type: ignore[attr-defined]
    await w.executor.begin(assignment.id, remote.id)  # type: ignore[attr-defined]

    delivered = await w.executor.deliver(  # type: ignore[attr-defined]
        assignment.id,  # type: ignore[attr-defined]
        remote.id,  # type: ignore[attr-defined]
        answered(output={"message": LONE}, node={"ran_at": LONE}),
    )

    assert delivered.step_state is StepState.FAILED
    (result,) = [r for r in await w.results.for_step(task_id, step.id)]
    assert result.error is not None and result.error.code == RESULT_NOT_TEXT
    assert "output, node" in result.error.message
    assert result.metadata.get("node") is None
    assert AuditEventType.TOOL_EXECUTED in await w.event_types(task_id)
    assert (await w.runner.run(task_id)).task.state is TaskState.FAILED


async def test_a_replay_of_that_envelope_is_the_same_answer() -> None:
    w = world()
    _, remote, assignment = await handed(w)
    await w.executor.begin(assignment.id, remote.id)  # type: ignore[attr-defined]
    envelope = answered(output={"message": LONE})
    first = await w.executor.deliver(assignment.id, remote.id, envelope)  # type: ignore[attr-defined]

    again = await w.executor.deliver(assignment.id, remote.id, envelope)  # type: ignore[attr-defined]

    assert again.step_state is first.step_state is StepState.FAILED
    assert Delivery.RESULT is envelope.form
