"""The executor refuses a placement it was not given, and leaves nothing behind (ADR 0026 §3).

``tests/devices/test_placement.py`` checks ``ensure_placed`` on its own. This checks the thing
that matters about *where* it is called: a caller that hands the executor somebody else's node —
or a node the orchestrator would refuse today — gets an error before any write, so a run that
never began leaves no audit event, no result, and no step out of RUNNING.

Until M9.1 none of this was true: the executor took a ``DeviceId`` and used it.
"""

from __future__ import annotations

import pytest

from ela.devices import NotPlacedError
from ela.domain import DeviceId, PrivacyLevel, StepId, StepState
from tests.devices.nodes import device_id, node
from tests.executive.support import World, world
from tests.permissions.support import ECHO


@pytest.fixture
def w() -> World:
    return world()


async def test_a_placement_of_another_step_never_reaches_the_tool(w: World) -> None:
    task, step = await w.running(ECHO.id)
    placed = await w.placement(task.id, step.id)
    stolen = placed._replace(step_id=StepId(device_id("some-other-step")))
    before = len(await w.events())

    with pytest.raises(NotPlacedError, match="the placement is for step"):
        await w.execute(task.id, step.id, placement=stolen)

    assert len(await w.events()) == before
    assert w.tool(ECHO.id).calls == ()
    assert await w.step_state(task.id, step.id) is StepState.RUNNING


async def test_a_node_nobody_chose_is_refused_before_anything_is_written(w: World) -> None:
    """The attack the bare ``DeviceId`` allowed: name a node and the executor used it."""
    task, step = await w.running(ECHO.id)
    invented = await w.placement(task.id, step.id)
    forged = invented._replace(
        device=node("somebody-elses", privacy=PrivacyLevel.CLOUD_ALLOWED),
        reason="named by the caller",
    )
    before = len(await w.events())

    with pytest.raises(NotPlacedError, match="refused by its own placement: PRIVACY"):
        await w.execute(task.id, step.id, placement=forged)

    assert len(await w.events()) == before
    assert w.tool(ECHO.id).calls == ()
    assert await w.results.for_step(task.id, step.id) == ()


async def test_a_placement_that_names_nobody_never_runs_anything(w: World) -> None:
    task, step = await w.running(ECHO.id)
    waiting = (await w.placement(task.id, step.id))._replace(device=None, reason="no node")

    with pytest.raises(NotPlacedError, match="no node was chosen"):
        await w.execute(task.id, step.id, placement=waiting)

    assert w.tool(ECHO.id).calls == ()


async def test_an_unknown_device_id_no_longer_buys_an_execution(w: World) -> None:
    """``World.placement`` builds the decision the way the orchestrator does, so an id the
    registry does not hold produces a decision that names nobody — and nothing runs."""
    task, step = await w.running(ECHO.id)
    nowhere = DeviceId(device_id("nowhere"))

    with pytest.raises(NotPlacedError):
        await w.execute(task.id, step.id, device_id=nowhere)

    assert w.tool(ECHO.id).calls == ()


async def test_the_device_the_audit_records_is_the_one_the_decision_names(w: World) -> None:
    """Naming a node nobody chose has stopped being expressible: the id comes from the decision."""
    task, step = await w.running(ECHO.id)
    placement = await w.placement(task.id, step.id)
    assert placement.device is not None

    execution = await w.execute(task.id, step.id, placement=placement)

    assert execution.result is not None
    assert execution.result.device_id == placement.device.id
    executed = [e for e in await w.events(task.id) if e.device_id is not None]
    assert {event.device_id for event in executed} == {placement.device.id}
