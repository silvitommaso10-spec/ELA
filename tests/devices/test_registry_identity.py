"""What the registry writes when a node speaks for itself, and when the user revokes it (M12.1).

On both implementations of the port (``conftest.py``): the flows are the service's, and a flow
that held only on the fake would be holding on the wrong thing. Four of the five facts of an
identity (ADR 0037 §13), each with the actor it belongs to; the fifth, the enrollment, is in
``test_enrollment.py``, with the code that gives birth to the node.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from ela.devices import (
    LOCAL_DEVICE_ID,
    LOCAL_USER,
    REGISTRY_ACTOR,
    DeviceRegistry,
    LocalDeviceNotRevocableError,
    Rejection,
)
from ela.domain import ActorKind, AuditEventType, PerformanceClass, PowerSource
from ela.ports import DeviceRegistryPort, DeviceRevokedError, IdentityConflictError, NotFoundError
from ela.testing.fakes import FakeAuditLog, FakeClock
from tests.domain.examples import ENROLLED_DEVICE, LATER, SECRET_HASH

NODE = ENROLLED_DEVICE


def declared(**changes: Any) -> dict[str, Any]:
    """The five keywords of an announcement, as ``NODE`` declares them, with ``changes`` applied."""
    return {
        "name": NODE.name,
        "os": NODE.os,
        "capabilities": NODE.capabilities,
        "available_tools": NODE.available_tools,
        "performance": NODE.performance,
        **changes,
    }


@pytest.fixture
async def enrolled(port: DeviceRegistryPort) -> DeviceRegistryPort:
    """The port with ``NODE`` enrolled at revision 1, written without the service: no event yet."""
    await port.enroll(NODE, secret_hash=SECRET_HASH)
    return port


# ----------------------------------------------------------------------------------------
# The announcement (ADR 0037 §9, §10)
# ----------------------------------------------------------------------------------------


async def test_an_announcement_that_changes_something_is_signed_by_the_node(
    registry: DeviceRegistry, enrolled: DeviceRegistryPort, audit: FakeAuditLog
) -> None:
    announced = await registry.announce(
        NODE.id,
        **declared(name="renamed", performance=PerformanceClass.LOW),
        expected_revision=1,
    )

    assert (announced.name, announced.performance, announced.revision) == (
        "renamed",
        PerformanceClass.LOW,
        2,
    )
    (event,) = await audit.read()
    assert event.event_type is AuditEventType.DEVICE_ANNOUNCED
    assert (event.actor.kind, event.actor.id) == (ActorKind.DEVICE, str(NODE.id))
    assert event.device_id == NODE.id
    assert f"name {NODE.name} -> renamed" in event.summary
    assert event.payload["changed"] == ("name", "performance")


async def test_an_announcement_that_changes_nothing_moves_the_revision_and_writes_nothing(
    registry: DeviceRegistry, enrolled: DeviceRegistryPort, audit: FakeAuditLog
) -> None:
    """The node is told the revision to use next; the log is not told that nothing happened."""
    assert (await registry.announce(NODE.id, **declared(), expected_revision=1)).revision == 2
    assert await audit.read() == ()


async def test_a_stale_revision_is_written_as_a_conflict_and_refused(
    registry: DeviceRegistry, enrolled: DeviceRegistryPort, audit: FakeAuditLog
) -> None:
    with pytest.raises(IdentityConflictError):
        await registry.announce(NODE.id, **declared(name="clone"), expected_revision=0)

    (event,) = await audit.read()
    assert event.event_type is AuditEventType.DEVICE_IDENTITY_CONFLICT
    assert (event.actor.kind, event.device_id) == (ActorKind.DEVICE, NODE.id)
    assert (event.payload["expected_revision"], event.payload["actual_revision"]) == (0, 1)
    assert (await registry.get(NODE.id)).name == NODE.name


async def test_a_revoked_node_announces_nothing_and_writes_nothing(
    registry: DeviceRegistry, enrolled: DeviceRegistryPort, audit: FakeAuditLog
) -> None:
    """The middleware stops it first and writes the rejection (ADR 0037 §12); here the port's
    condition is what holds, and the registry does not write a second account of it."""
    await enrolled.revoke(NODE.id, at=LATER)
    with pytest.raises(DeviceRevokedError):
        await registry.announce(NODE.id, **declared(name="ghost"), expected_revision=1)
    assert await audit.read() == ()


async def test_an_announcement_of_an_unknown_node_is_not_found(
    registry: DeviceRegistry, audit: FakeAuditLog
) -> None:
    with pytest.raises(NotFoundError):
        await registry.announce(NODE.id, **declared(), expected_revision=1)
    assert await audit.read() == ()


async def test_a_heartbeat_writes_the_power_source_it_reports(
    registry: DeviceRegistry, enrolled: DeviceRegistryPort
) -> None:
    power = next(member for member in PowerSource if member is not NODE.power_source)

    beaten = await registry.heartbeat(NODE.id, power_source=power)

    assert beaten.power_source is power
    assert (await registry.get(NODE.id)).power_source is power


# ----------------------------------------------------------------------------------------
# The revocation (ADR 0037 §12)
# ----------------------------------------------------------------------------------------


async def test_a_revocation_is_signed_by_the_user_once_and_keeps_the_row(
    registry: DeviceRegistry, enrolled: DeviceRegistryPort, audit: FakeAuditLog, clock: FakeClock
) -> None:
    revoked = await registry.revoke(NODE.id, by=LOCAL_USER)
    assert revoked.revoked_at == clock.now()

    clock.advance(timedelta(minutes=1))
    again = await registry.revoke(NODE.id, by=LOCAL_USER)

    assert again.revoked_at == revoked.revoked_at
    (event,) = await audit.read()
    assert event.event_type is AuditEventType.DEVICE_REVOKED
    assert event.actor == LOCAL_USER
    assert event.device_id == NODE.id
    assert [device.id for device in await registry.devices()] == [NODE.id]


async def test_local_cannot_be_revoked(registry: DeviceRegistry, audit: FakeAuditLog) -> None:
    await registry.ensure_local(system="Darwin")
    before = await audit.read()

    with pytest.raises(LocalDeviceNotRevocableError):
        await registry.revoke(LOCAL_DEVICE_ID, by=LOCAL_USER)

    assert (await registry.get(LOCAL_DEVICE_ID)).revoked_at is None
    assert await audit.read() == before


async def test_a_revocation_of_an_unknown_node_is_not_found(
    registry: DeviceRegistry, audit: FakeAuditLog
) -> None:
    with pytest.raises(NotFoundError):
        await registry.revoke(NODE.id, by=LOCAL_USER)
    assert await audit.read() == ()


# ----------------------------------------------------------------------------------------
# The rejection (ADR 0037 §13)
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("reason", list(Rejection), ids=[reason.value for reason in Rejection])
async def test_a_rejection_names_the_node_as_a_claim_and_is_signed_by_the_system(
    registry: DeviceRegistry, enrolled: DeviceRegistryPort, audit: FakeAuditLog, reason: Rejection
) -> None:
    await registry.reject(NODE.id, reason)

    (event,) = await audit.read()
    assert event.event_type is AuditEventType.DEVICE_REJECTED
    assert event.actor == REGISTRY_ACTOR
    assert event.device_id is None
    assert dict(event.payload) == {"reason": reason.value, "named_device_id": str(NODE.id)}
    assert reason.value in event.summary


async def test_a_rejection_of_a_node_that_does_not_exist_writes_nothing(
    registry: DeviceRegistry, audit: FakeAuditLog
) -> None:
    """Only a request that names a node that exists is written: the rest are anonymous."""
    with pytest.raises(NotFoundError):
        await registry.reject(NODE.id, Rejection.BAD_SECRET)
    assert await audit.read() == ()
