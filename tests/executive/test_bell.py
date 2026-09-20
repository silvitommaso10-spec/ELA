"""The bell on the path of the run (M12.5 dec. E; ADR 0043 §8).

Where it rings, what it writes, and what happens when it does not ring. What it *says* is the
adapter's, and it is proved in ``tests/providers/ntfy/``; here the bell is a fake, because what
this file is about is the executor's side of the decision: a question is stored, the task waits on
it, and only then is the user disturbed.
"""

from __future__ import annotations

import inspect

import pytest

from ela.domain import ActorKind, AuditEventType, RiskLevel
from ela.ports import Bell
from ela.providers.ntfy import VOICES
from ela.testing.fakes import FakeBell
from tests.design.tree import tokens
from tests.executive.support import World, world
from tests.permissions.support import NOTE


@pytest.fixture
def w() -> World:
    """An ELA where nobody configured a bell: what every machine is until somebody does."""
    return world()


@pytest.fixture
def ringing() -> tuple[World, FakeBell]:
    """A world whose bell is configured — the ELA of somebody who set a topic up."""
    bell = FakeBell()
    return world(bell=bell), bell


async def test_a_question_that_waits_rings_once_with_the_risk_of_the_catalogue(
    ringing: tuple[World, FakeBell],
) -> None:
    """Dec. E: one voice, and the risk is the catalogue's — the one the Guardian used, never the
    one a plan declares."""
    w, bell = ringing
    task, step = await w.running(NOTE.id, requires_authorization=True)

    execution = await w.execute(task.id, step.id)

    assert execution.approval is not None
    assert bell.rung == [NOTE.risk]


async def test_the_bell_rings_after_the_question_is_stored_and_the_task_waits(
    ringing: tuple[World, FakeBell],
) -> None:
    """The order is the decision: a bell never announces a question that is not there. Read from
    the trail — ``APPROVAL_REQUESTED`` is the engine's, and ``BELL_RUNG`` comes after it."""
    w, _ = ringing
    task, step = await w.running(NOTE.id, requires_authorization=True)

    await w.execute(task.id, step.id)

    assert (await w.event_types(task.id))[-2:] == [
        AuditEventType.APPROVAL_REQUESTED,
        AuditEventType.BELL_RUNG,
    ]


async def test_the_audit_says_who_rang_what_and_whether_it_arrived(
    ringing: tuple[World, FakeBell],
) -> None:
    """§57 wants the four answers about data that leaves: which provider, which data, why, what
    policy. What is **not** there is as deliberate: the topic is a credential, and the URL says
    where this ELA lives."""
    w, bell = ringing
    task, step = await w.running(NOTE.id, requires_authorization=True)

    execution = await w.execute(task.id, step.id)

    assert execution.approval is not None
    rung = (await w.events(task.id))[-1]
    assert rung.event_type is AuditEventType.BELL_RUNG
    assert rung.actor.kind is ActorKind.SYSTEM
    assert rung.payload == {
        "provider": bell.name,
        "risk": NOTE.risk.value,
        "approval_id": str(execution.approval.id),
        "delivered": True,
    }
    assert rung.task_id == task.id and rung.step_id == step.id
    assert "voice" not in rung.payload, "one voice would be one value, and the id says what rang"


async def test_a_bell_that_does_not_arrive_changes_nothing_but_the_trail() -> None:
    """Dec. E: the question waits on the page and in the CLI all the same, and the run goes on."""
    bell = FakeBell(delivers=False)
    w = world(bell=bell)
    task, step = await w.running(NOTE.id, requires_authorization=True)

    execution = await w.execute(task.id, step.id)

    assert execution.approval is not None
    assert execution.task.state.value == "WAITING_APPROVAL"
    rung = (await w.events(task.id))[-1]
    assert rung.payload["delivered"] is False
    assert "not delivered" in rung.summary


async def test_an_ela_with_no_bell_configured_rings_nothing_and_writes_nothing(
    w: World,
) -> None:
    """The default of every machine until somebody sets a topic: silence, and no event about it.

    An event for a bell nobody configured would be a line per question saying that nothing
    happened — the audit records what ELA did, not what it was not asked to do.
    """
    task, step = await w.running(NOTE.id, requires_authorization=True)

    await w.execute(task.id, step.id)

    assert AuditEventType.BELL_RUNG not in await w.event_types(task.id)


def test_every_voice_of_the_port_has_a_row_and_the_rows_are_keys_of_the_design_system() -> None:
    """The census of dec. E, in the shape of ``tests/api/test_wire_codes.py``.

    Three lists walked together: the voices of the port, the rows of the adapter's table, and the
    keys of ``tokens.json``. A voice with no row would be a bell with nothing to say; a row with
    no voice would be a text nobody can emit; a key the design system does not have would be a
    body that means nothing on the phone (the state it names is the one the sphere shows).
    """
    voices = {
        name
        for name, member in inspect.getmembers(Bell, inspect.isfunction)
        if inspect.iscoroutinefunction(member)
    }

    assert set(VOICES) == voices
    assert set(VOICES.values()) <= set(tokens()["state"])


def test_no_voice_of_the_port_can_carry_a_sentence() -> None:
    """«Niente dell'utente nel testo», as a property of the types: architecture rule 56 reports a
    parameter annotated ``str``, and this says the same thing from the other side — every voice
    takes what the catalogue knows, and nothing a caller could have written."""
    for voice in VOICES:
        signature = inspect.signature(getattr(Bell, voice))
        annotations = [
            parameter.annotation
            for name, parameter in signature.parameters.items()
            if name != "self"
        ]
        assert annotations == [RiskLevel.__name__], voice
