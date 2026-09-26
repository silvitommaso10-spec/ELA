"""What ``local`` runs on decides where a step goes, and it is read again on every run (M12.3c).

The numbers are the ones that decide the end criterion of the Windows node (M12.4, «Da portare
all'utente» 9). With the weights of §17 ``local`` scores 20 for the network — its heartbeats carry
no status and no workload — plus 10 on ``AC``; a remote node, idle and on ``AC``, scores
5 + 10 + 10. **A Mac unplugged loses, 20 to 25; plugged in it wins, 30 to 25.** Until M12.3c
``local`` was ``UNKNOWN`` whatever the machine did, so the first of the two runs below could not
keep its step.
"""

from __future__ import annotations

from httpx import AsyncClient

from ela.composition import Ela
from ela.devices.local import LOCAL_DEVICE_ID
from ela.domain import AuditEventType, PowerSource
from ela.executive import RunOutcome
from ela.testing.fakes import FakePower
from tests.api.support import echo_plan, queued
from tests.api.test_nodes import enrolled, written


def power_of(ela: Ela) -> FakePower:
    """The reading this ELA was built with: ``tests/composition/support.py`` names a fake."""
    assert isinstance(ela.power, FakePower)
    return ela.power


async def test_a_run_asks_the_machine_again_before_it_places_anything(
    client: AsyncClient, ela: Ela
) -> None:
    """``local``'s heartbeats are the start-up and every ``run``: the reading is taken at both, so a
    Mac unplugged after the Core started is unplugged by the time a step is placed."""
    power = power_of(ela)
    power.source = PowerSource.BATTERY
    asked = power.asked
    task_id = await queued(client, echo_plan())

    run = await client.post(f"/tasks/{task_id}/run")

    assert run.json()["outcome"] == RunOutcome.COMPLETED.value, run.text
    assert power.asked == asked + 1
    assert (await ela.devices.get(LOCAL_DEVICE_ID)).power_source is PowerSource.BATTERY


async def test_a_plugged_in_mac_keeps_the_step_and_an_unplugged_one_hands_it_to_the_pc(
    client: AsyncClient, ela: Ela
) -> None:
    """The table of M12.4, played: no ``HIGH`` and no trait, a node idle on ``AC``, and the only
    thing that changes between the two runs is what ``local``'s machine answers.

    The numbers are M13.3's (ADR 0048 §13): ``local`` beats ``IDLE`` now, observed by the Core, and
    ``AC`` is worth 20 — the Mac on the mains 50 against the PC's 35, on battery 30 against 35.
    Until M13.3 they were 30 and 20 against 25: the same outcome, for the wrong reason — nobody
    observed the Mac's status."""
    node_id, headers = await enrolled(
        client,
        "TRUSTED",
        available_tools=[tool.name for tool in ela.tools.tools()],
        performance="UNKNOWN",
    )
    beat = await client.post(
        "/nodes/heartbeat", json={"status": "IDLE", "power_source": "AC"}, headers=headers
    )
    assert beat.status_code == 200, beat.text
    power = power_of(ela)

    power.source = PowerSource.AC
    kept = await client.post(f"/tasks/{await queued(client, echo_plan(), privacy='TRUSTED')}/run")
    power.source = PowerSource.BATTERY
    handed = await client.post(f"/tasks/{await queued(client, echo_plan(), privacy='TRUSTED')}/run")

    assert kept.json()["outcome"] == RunOutcome.COMPLETED.value, kept.text
    assert handed.json()["outcome"] == RunOutcome.ASSIGNED.value, handed.text
    placed = [
        {candidate["device_id"]: candidate["points"] for candidate in event.payload["candidates"]}
        for event in await written(ela, AuditEventType.DEVICE_SELECTED)
    ]
    assert placed == [
        {str(LOCAL_DEVICE_ID): 50, node_id: 35},
        {str(LOCAL_DEVICE_ID): 30, node_id: 35},
    ]
