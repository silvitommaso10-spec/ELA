"""Contract of ``DeviceRegistryPort`` (spec §16): nodes by id, added once, updated explicitly.

Since M12.1 (ADR 0037 §8, §9): a node enrolled with the hash of its secret, and one write for
each half of its row — the announcement conditional on the revision, the observation on the
columns it carries, the revocation once.
"""

from __future__ import annotations

from enum import Enum
from hashlib import sha256
from uuid import UUID

import pytest

from ela.domain import Device, DeviceId, DeviceStatus
from ela.ports import (
    ANNOUNCED_FIELDS,
    AlreadyExistsError,
    DeviceRegistryPort,
    DeviceRevokedError,
    IdentityConflictError,
    NotFoundError,
)
from tests.domain.examples import DEVICE, ENROLLED_DEVICE, LATER, MUCH_LATER, SECRET_HASH

OTHER_DEVICE = DEVICE.model_copy(
    update={"id": DeviceId(UUID("00000000-0000-4000-8000-000000000301")), "name": "Windows"}
)


async def test_register_then_get(device_registry: DeviceRegistryPort) -> None:
    await device_registry.register(DEVICE)
    assert await device_registry.get(DEVICE.id) == DEVICE


async def test_register_twice_is_rejected(device_registry: DeviceRegistryPort) -> None:
    await device_registry.register(DEVICE)
    with pytest.raises(AlreadyExistsError):
        await device_registry.register(DEVICE.model_copy(update={"name": "clone"}))
    assert await device_registry.get(DEVICE.id) == DEVICE


async def test_get_unknown_is_not_found(device_registry: DeviceRegistryPort) -> None:
    with pytest.raises(NotFoundError):
        await device_registry.get(DEVICE.id)


async def test_update_replaces(device_registry: DeviceRegistryPort) -> None:
    await device_registry.register(DEVICE)
    idle = DEVICE.model_copy(update={"status": DeviceStatus.IDLE})
    await device_registry.update(idle)
    assert await device_registry.get(DEVICE.id) == idle


async def test_update_unknown_is_not_found(device_registry: DeviceRegistryPort) -> None:
    with pytest.raises(NotFoundError):
        await device_registry.update(DEVICE)


async def test_devices_in_registration_order_as_a_tuple(
    device_registry: DeviceRegistryPort,
) -> None:
    assert await device_registry.devices() == ()
    await device_registry.register(OTHER_DEVICE)
    await device_registry.register(DEVICE)
    devices = await device_registry.devices()
    assert isinstance(devices, tuple)
    assert devices == (OTHER_DEVICE, DEVICE)


ENROLLED = ENROLLED_DEVICE
OTHER_HASH = sha256(b"another secret, never a real one either").hexdigest()


def _other[E: Enum](member: E) -> E:
    """Another member of the same enum: a value that differs, whatever the enum holds."""
    return next(candidate for candidate in type(member) if candidate is not member)


def _everything_changed(device: Device) -> Device:
    """``device`` with every field an announcement could be asked to write, changed."""
    return device.model_copy(
        update={
            "name": "renamed",
            "os": _other(device.os),
            "capabilities": (),
            "available_tools": ("browser",),
            "performance": _other(device.performance),
            "availability": _other(device.availability),
            "status": _other(device.status),
            "current_workload": 0.9,
            "network": _other(device.network),
            "power_source": _other(device.power_source),
            "privacy": _other(device.privacy),
            "created_at": MUCH_LATER,
            "last_seen_at": MUCH_LATER,
            "metadata": {"forged": True},
            "revision": 99,
            "revoked_at": MUCH_LATER,
        }
    )


async def test_an_enrolled_node_keeps_its_hash_and_a_registered_one_has_none(
    device_registry: DeviceRegistryPort,
) -> None:
    await device_registry.register(DEVICE)
    await device_registry.enroll(ENROLLED, secret_hash=SECRET_HASH)
    assert await device_registry.get(ENROLLED.id) == ENROLLED
    assert await device_registry.secret_hash(ENROLLED.id) == SECRET_HASH
    assert await device_registry.secret_hash(DEVICE.id) is None


async def test_the_hash_of_an_unknown_node_is_not_found(
    device_registry: DeviceRegistryPort,
) -> None:
    with pytest.raises(NotFoundError):
        await device_registry.secret_hash(ENROLLED.id)


async def test_an_id_is_enrolled_once_and_keeps_its_first_hash(
    device_registry: DeviceRegistryPort,
) -> None:
    await device_registry.register(DEVICE)
    await device_registry.enroll(ENROLLED, secret_hash=SECRET_HASH)
    with pytest.raises(AlreadyExistsError):
        await device_registry.enroll(
            ENROLLED.model_copy(update={"name": "clone"}), secret_hash=OTHER_HASH
        )
    with pytest.raises(AlreadyExistsError):
        await device_registry.enroll(DEVICE, secret_hash=OTHER_HASH)
    assert await device_registry.secret_hash(ENROLLED.id) == SECRET_HASH
    assert await device_registry.secret_hash(DEVICE.id) is None


async def test_an_announcement_writes_the_declared_half_and_nothing_else(
    device_registry: DeviceRegistryPort,
) -> None:
    await device_registry.enroll(ENROLLED, secret_hash=SECRET_HASH)
    announced = _everything_changed(ENROLLED)
    assert await device_registry.announce(announced, expected_revision=1) == 2
    declared = {field: getattr(announced, field) for field in ANNOUNCED_FIELDS}
    assert await device_registry.get(ENROLLED.id) == ENROLLED.model_copy(
        update={**declared, "revision": 2}
    )


async def test_a_stale_revision_is_a_conflict_of_identity_and_writes_nothing(
    device_registry: DeviceRegistryPort,
) -> None:
    await device_registry.enroll(ENROLLED, secret_hash=SECRET_HASH)
    with pytest.raises(IdentityConflictError) as caught:
        await device_registry.announce(_everything_changed(ENROLLED), expected_revision=0)
    assert (caught.value.device_id, caught.value.expected, caught.value.actual) == (
        ENROLLED.id,
        0,
        1,
    )
    assert await device_registry.get(ENROLLED.id) == ENROLLED


async def test_of_two_announcements_at_one_revision_the_second_loses(
    device_registry: DeviceRegistryPort,
) -> None:
    """Not by order of arrival: the second believed something false about the row (ADR 0035 §5)."""
    await device_registry.enroll(ENROLLED, secret_hash=SECRET_HASH)
    await device_registry.announce(
        ENROLLED.model_copy(update={"name": "first"}), expected_revision=1
    )
    with pytest.raises(IdentityConflictError):
        await device_registry.announce(
            ENROLLED.model_copy(update={"name": "second"}), expected_revision=1
        )
    assert (await device_registry.get(ENROLLED.id)).name == "first"


async def test_an_announcement_of_an_unknown_node_is_not_found(
    device_registry: DeviceRegistryPort,
) -> None:
    with pytest.raises(NotFoundError):
        await device_registry.announce(ENROLLED, expected_revision=1)


async def test_a_revoked_node_announces_nothing(device_registry: DeviceRegistryPort) -> None:
    await device_registry.enroll(ENROLLED, secret_hash=SECRET_HASH)
    await device_registry.revoke(ENROLLED.id, at=LATER)
    with pytest.raises(DeviceRevokedError) as caught:
        await device_registry.announce(_everything_changed(ENROLLED), expected_revision=1)
    assert (caught.value.device_id, caught.value.revoked_at) == (ENROLLED.id, LATER)
    assert await device_registry.get(ENROLLED.id) == ENROLLED.model_copy(
        update={"revoked_at": LATER}
    )


async def test_a_revoked_node_is_told_it_is_revoked_before_it_is_told_it_is_stale(
    device_registry: DeviceRegistryPort,
) -> None:
    await device_registry.enroll(ENROLLED, secret_hash=SECRET_HASH)
    await device_registry.revoke(ENROLLED.id, at=LATER)
    with pytest.raises(DeviceRevokedError):
        await device_registry.announce(ENROLLED, expected_revision=0)


async def test_an_observation_writes_the_observed_half_and_nothing_else(
    device_registry: DeviceRegistryPort,
) -> None:
    await device_registry.enroll(ENROLLED, secret_hash=SECRET_HASH)
    availability = _other(ENROLLED.availability)
    status = _other(ENROLLED.status)
    power_source = _other(ENROLLED.power_source)
    await device_registry.observe(
        ENROLLED.id,
        seen_at=MUCH_LATER,
        availability=availability,
        status=status,
        current_workload=0.9,
        power_source=power_source,
    )
    assert await device_registry.get(ENROLLED.id) == ENROLLED.model_copy(
        update={
            "last_seen_at": MUCH_LATER,
            "availability": availability,
            "status": status,
            "current_workload": 0.9,
            "power_source": power_source,
        }
    )


async def test_an_observation_that_says_nothing_keeps_what_was_known(
    device_registry: DeviceRegistryPort,
) -> None:
    """A heartbeat that says nothing about the workload must not erase what was known."""
    await device_registry.enroll(ENROLLED, secret_hash=SECRET_HASH)
    await device_registry.observe(
        ENROLLED.id, seen_at=MUCH_LATER, availability=ENROLLED.availability
    )
    assert await device_registry.get(ENROLLED.id) == ENROLLED.model_copy(
        update={"last_seen_at": MUCH_LATER}
    )


async def test_an_observation_of_an_unknown_node_is_not_found(
    device_registry: DeviceRegistryPort,
) -> None:
    with pytest.raises(NotFoundError):
        await device_registry.observe(
            ENROLLED.id, seen_at=LATER, availability=ENROLLED.availability
        )


async def test_a_node_is_revoked_once_and_its_row_stays(
    device_registry: DeviceRegistryPort,
) -> None:
    """The row stays: an investigation must be able to tell which nodes existed (ADR 0016 §6)."""
    await device_registry.enroll(ENROLLED, secret_hash=SECRET_HASH)
    assert await device_registry.revoke(ENROLLED.id, at=LATER) is True
    assert await device_registry.revoke(ENROLLED.id, at=MUCH_LATER) is False
    assert await device_registry.devices() == (ENROLLED.model_copy(update={"revoked_at": LATER}),)
    assert await device_registry.secret_hash(ENROLLED.id) == SECRET_HASH


async def test_a_revocation_of_an_unknown_node_is_not_found(
    device_registry: DeviceRegistryPort,
) -> None:
    with pytest.raises(NotFoundError):
        await device_registry.revoke(ENROLLED.id, at=LATER)
