"""``/audit`` and ``/audit/verify`` (spec §32, §58; ADR 0005, ADR 0023 §6, ADR 0024 §4).

The trail, read-only and free of content: what leaves through this route carries no argument of a
call and no output of a tool — not because the route strips them, but because an ``AuditEvent``
never holds them (architecture rule 23). And the second question, added in M8.2: whether what is
in there still hangs together, which is what makes reading it worth anything.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from ela.composition import Ela
from ela.domain import AuditEventType
from tests.api.support import (
    ECHO_MESSAGE,
    NOTE_BODY,
    echo_plan,
    note_plan,
    queued,
    tamper_with_the_trail,
)


async def test_the_trail_of_a_task_is_readable(client: AsyncClient) -> None:
    task_id = await queued(client, echo_plan())
    await client.post(f"/tasks/{task_id}/run")

    events = (await client.get("/audit", params={"task_id": task_id})).json()

    kinds = [event["event_type"] for event in events]
    assert kinds[0] == AuditEventType.TASK_CREATED.value
    assert AuditEventType.PERMISSION_DECIDED.value in kinds
    assert AuditEventType.TOOL_EXECUTED.value in kinds
    assert AuditEventType.EXECUTION_VERIFIED.value in kinds
    assert all(event["task_id"] == task_id for event in events)


async def test_the_trail_of_another_task_is_not_mixed_in(client: AsyncClient) -> None:
    first = await queued(client, echo_plan(), text="una")
    await queued(client, echo_plan(), text="due")

    events = (await client.get("/audit", params={"task_id": first})).json()

    assert {event["task_id"] for event in events} == {first}


async def test_the_filters_are_the_port_s(client: AsyncClient) -> None:
    await queued(client, echo_plan())
    everything = (await client.get("/audit")).json()

    first = (await client.get("/audit", params={"limit": 1})).json()
    future = (await client.get("/audit", params={"since": "2099-01-01T00:00:00Z"})).json()
    since = datetime.now(UTC) - timedelta(hours=1)
    recent = (await client.get("/audit", params={"since": since.isoformat()})).json()

    assert len(everything) > 1
    assert first == everything[:1]
    assert future == []
    assert len(recent) == len(everything)


async def test_newest_first_reads_the_other_end_and_limits_there(client: AsyncClient) -> None:
    """ADR 0025 §3: the route says which end, and ``limit`` takes its rows from that end."""
    await queued(client, echo_plan())
    everything = (await client.get("/audit")).json()

    last = (await client.get("/audit", params={"limit": 2, "newest_first": True})).json()
    reversed_whole = (await client.get("/audit", params={"newest_first": True})).json()

    assert len(everything) > 2
    assert last == list(reversed(everything))[:2]
    assert reversed_whole == list(reversed(everything))


async def test_without_the_flag_the_route_answers_exactly_as_it_did(client: AsyncClient) -> None:
    """The default is the behaviour ADR 0023 §6 documented: no caller changes under M8.3."""
    await queued(client, echo_plan())

    default = (await client.get("/audit", params={"limit": 2})).json()
    explicit = (await client.get("/audit", params={"limit": 2, "newest_first": False})).json()
    everything = (await client.get("/audit")).json()

    assert default == explicit == everything[:2]


async def test_newest_first_keeps_the_filters_of_the_port(client: AsyncClient) -> None:
    await queued(client, echo_plan())
    other = await queued(client, echo_plan(), text="un'altra cosa")

    tail = (await client.get("/audit", params={"task_id": other, "newest_first": True})).json()
    forwards = (await client.get("/audit", params={"task_id": other})).json()

    assert tail == list(reversed(forwards))
    assert all(event["task_id"] == other for event in tail)


async def test_a_limit_of_zero_is_a_caller_s_bug(client: AsyncClient) -> None:
    assert (await client.get("/audit", params={"limit": 0})).status_code == 422


async def test_an_unknown_task_has_an_empty_trail(client: AsyncClient) -> None:
    assert (await client.get("/audit", params={"task_id": str(uuid.uuid4())})).json() == []


async def test_no_argument_and_no_output_ever_leaves_through_the_audit(
    client: AsyncClient, ela: Ela
) -> None:
    """The whole point of rule 23, checked from outside: the trail records *targets*, never what
    was passed and never what came back (§57)."""
    echo = await queued(client, echo_plan(), text="echo")
    await client.post(f"/tasks/{echo}/run")
    note = await queued(client, note_plan(), text="note")
    await client.post(f"/tasks/{note}/run")
    approval = (await client.get("/approvals")).json()[0]
    await client.post(f"/tasks/{note}/approve", json={"approval_id": approval["id"]})
    await client.post(f"/tasks/{note}/run")

    trail = (await client.get("/audit")).text

    assert NOTE_BODY not in trail  # what the tool wrote
    assert ECHO_MESSAGE not in trail  # what the tool was told to say
    assert "workspace/notes/briefing.md" in trail  # the target *is* recorded (§32)
    assert (ela.settings.workspace.workspace_dir / "workspace" / "notes" / "briefing.md").exists()


# ----------------------------------------------------------------------------------------
# ``/audit/verify`` (ADR 0024 §4): the second question the trail exists to answer
# ----------------------------------------------------------------------------------------


async def test_the_chain_verifies_and_reports_what_to_anchor(client: AsyncClient, ela: Ela) -> None:
    await queued(client, echo_plan())

    summary = (await client.get("/audit/verify")).json()

    assert summary["length"] == len(await ela.audit.read())
    assert len(summary["head_hash"]) == 64


async def test_a_fresh_log_holds_the_registration_of_the_node_ela_runs_on(
    client: AsyncClient, ela: Ela
) -> None:
    """No longer a chain of length zero, and M6.1b is why (ADR 0035 §3).

    Building ELA writes down the machine it is running on, so the first entry of every database
    is a ``DEVICE_REGISTERED`` — which is what §32 asks for: whoever investigates an action must
    be able to reconstruct which nodes could do what then, and the first answer is the moment
    there was a node at all. The genesis of an actually empty chain is
    ``tests/audit/test_chain.py``'s, where it can be asked without building a world first.
    """
    summary = (await client.get("/audit/verify")).json()

    assert summary["length"] == 1
    (event,) = await ela.audit.read()
    assert event.event_type is AuditEventType.DEVICE_REGISTERED


async def test_a_rewritten_entry_is_reported_with_its_position(
    client: AsyncClient, ela: Ela
) -> None:
    """409, and *where*: "something is wrong with the log" is not something anyone can act on."""
    await queued(client, echo_plan())
    await tamper_with_the_trail(ela)

    answer = await client.get("/audit/verify")

    assert answer.status_code == 409
    assert answer.json()["error"]["code"] == "tampered"
    assert "1" in answer.json()["error"]["message"]
