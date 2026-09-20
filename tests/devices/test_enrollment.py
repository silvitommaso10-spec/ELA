"""``NodeEnrollment``: a code issued once, spent once, and a secret in clear once (M12.1 dec. D).

On both implementations of the device port (``conftest.py``) and the fake code store. The code and
the secret are real ``secrets.token_urlsafe`` values, so the probe that looks for them in the audit
is looking for something that exists.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from ela.devices import (
    ENROLLMENT_CODE_TTL,
    LOCAL_USER,
    UNAVAILABLE,
    DeviceRegistry,
    NodeEnrollment,
    fingerprint,
)
from ela.domain import (
    AuditEventType,
    DeviceId,
    DeviceRole,
    Enrollment,
    NetworkKind,
    OperatingSystem,
    PerformanceClass,
    PrivacyLevel,
)
from ela.ports import (
    DeviceRegistryPort,
    EnrollmentConsumedError,
    EnrollmentExpiredError,
    EnrollmentRoleError,
    NotFoundError,
)
from ela.testing.fakes import FakeAuditLog, FakeClock, FakeEnrollmentStore, FakeIdGenerator

DECLARED: dict[str, Any] = {
    "name": "pc",
    "os": OperatingSystem.WINDOWS,
    "capabilities": (),
    "available_tools": ("core-echo",),
    "performance": PerformanceClass.HIGH,
}
"""What a Windows node declares of itself when it presents its code."""

AS_WORKER: dict[str, Any] = {"role": DeviceRole.WORKER, **DECLARED}
"""The same declaration, on the enrolment route of the nodes: the role is the route's, not the
node's (M12.5 dec. A)."""


class RecordingStore(FakeEnrollmentStore):
    """The fake store, and every code it was offered — to show what is kept, and that nothing is."""

    def __init__(self) -> None:
        super().__init__()
        self.offered: list[Enrollment] = []

    async def offer(self, enrollment: Enrollment) -> None:
        self.offered.append(enrollment)
        await super().offer(enrollment)


@pytest.fixture
def codes() -> RecordingStore:
    return RecordingStore()


@pytest.fixture
def enrollment(codes: RecordingStore, registry: DeviceRegistry, clock: FakeClock) -> NodeEnrollment:
    return NodeEnrollment(codes, registry, clock, FakeIdGenerator())


# ----------------------------------------------------------------------------------------
# The code
# ----------------------------------------------------------------------------------------


async def test_a_code_is_issued_for_ten_minutes_with_the_level_the_user_chose(
    enrollment: NodeEnrollment, codes: RecordingStore, clock: FakeClock
) -> None:
    issued = await enrollment.issue(PrivacyLevel.TRUSTED, DeviceRole.WORKER)

    assert timedelta(minutes=10) == ENROLLMENT_CODE_TTL
    assert (issued.privacy, issued.expires_at) == (
        PrivacyLevel.TRUSTED,
        clock.now() + ENROLLMENT_CODE_TTL,
    )
    (kept,) = codes.offered
    assert kept.code_hash == fingerprint(issued.code)
    assert issued.code not in kept.model_dump_json()


async def test_local_only_is_refused_before_anything_is_kept(
    enrollment: NodeEnrollment, codes: RecordingStore
) -> None:
    """D18: the type refuses it, so no route and no caller can mint it."""
    with pytest.raises(ValidationError, match="LOCAL_ONLY"):
        await enrollment.issue(PrivacyLevel.LOCAL_ONLY, DeviceRole.WORKER)
    assert codes.offered == []


# ----------------------------------------------------------------------------------------
# The node
# ----------------------------------------------------------------------------------------


async def test_a_node_is_born_with_an_id_and_a_privacy_it_did_not_choose(
    enrollment: NodeEnrollment,
    registry: DeviceRegistry,
    port: DeviceRegistryPort,
    audit: FakeAuditLog,
    clock: FakeClock,
) -> None:
    """Criterion 1, below the route: the privacy is the code's, the network the registry's, and
    the node is never seen — so not available — until its first heartbeat."""
    issued = await enrollment.issue(PrivacyLevel.TRUSTED, DeviceRole.WORKER)

    enrolled = await enrollment.enroll(issued.code, **AS_WORKER)

    node = await registry.get(enrolled.device.id)
    assert node == enrolled.device
    assert (node.privacy, node.network, node.revision) == (
        PrivacyLevel.TRUSTED,
        NetworkKind.REMOTE,
        1,
    )
    assert (node.last_seen_at, node.availability) == (None, UNAVAILABLE)
    assert (node.name, node.os, node.available_tools, node.performance) == (
        "pc",
        OperatingSystem.WINDOWS,
        ("core-echo",),
        PerformanceClass.HIGH,
    )
    assert await port.secret_hash(node.id) == fingerprint(enrolled.secret)
    (event,) = await audit.read()
    assert event.event_type is AuditEventType.DEVICE_ENROLLED
    assert event.actor == LOCAL_USER
    assert event.device_id == node.id
    assert f"code issued at {clock.now().isoformat()}" in event.summary


async def test_a_companion_is_born_from_a_companion_code(
    enrollment: NodeEnrollment,
    registry: DeviceRegistry,
    audit: FakeAuditLog,
) -> None:
    """M12.5 dec. A: the role is the code's, like the privacy, and the row is born with it.

    The audit says which of the two entered ELA's world: an identity that answers pages and one
    that takes work are not the same admission, and the log is what somebody reads a year later.
    """
    issued = await enrollment.issue(PrivacyLevel.TRUSTED, DeviceRole.COMPANION)

    enrolled = await enrollment.enroll(
        issued.code,
        role=DeviceRole.COMPANION,
        name="iPhone",
        os=OperatingSystem.IOS,
        capabilities=(),
        available_tools=(),
        performance=PerformanceClass.UNKNOWN,
    )

    assert issued.role is DeviceRole.COMPANION
    node = await registry.get(enrolled.device.id)
    assert node.role is DeviceRole.COMPANION
    assert (node.os, node.available_tools, node.capabilities) == (OperatingSystem.IOS, (), ())
    assert node.availability is UNAVAILABLE
    (event,) = await audit.read()
    assert "role COMPANION" in event.summary


@pytest.mark.parametrize(
    ("minted", "presented"),
    [
        (DeviceRole.COMPANION, DeviceRole.WORKER),
        (DeviceRole.WORKER, DeviceRole.COMPANION),
    ],
    ids=["a companion code on the nodes' route", "a node's code on the companion's route"],
)
async def test_a_code_of_the_other_role_is_refused_and_stays_spendable(
    minted: DeviceRole,
    presented: DeviceRole,
    enrollment: NodeEnrollment,
    registry: DeviceRegistry,
    audit: FakeAuditLog,
) -> None:
    """M12.5 dec. C.5: the role is a condition of the ``UPDATE``, so nothing is spent.

    Both ways round, because the two routes are not symmetrical in anything else: what they share
    is that a code pasted in the wrong place costs the user nothing — the code still works where
    it belongs, and no row, no hash and no event were written in between.
    """
    issued = await enrollment.issue(PrivacyLevel.TRUSTED, minted)

    with pytest.raises(EnrollmentRoleError) as refused:
        await enrollment.enroll(issued.code, **{**AS_WORKER, "role": presented})

    assert (refused.value.carried, refused.value.expected) == (minted, presented)
    assert issued.code not in str(refused.value)
    assert await audit.read() == ()
    assert await registry.devices() == ()

    enrolled = await enrollment.enroll(issued.code, **{**AS_WORKER, "role": minted})

    assert enrolled.device.role is minted


async def test_the_code_and_the_secret_are_in_clear_nowhere_but_the_answer(
    enrollment: NodeEnrollment, port: DeviceRegistryPort, audit: FakeAuditLog
) -> None:
    """Criterion 6, below the route: not in the audit, not in the entity — and not their hashes
    either. It proves what this test exercises and nothing more."""
    issued = await enrollment.issue(PrivacyLevel.TRUSTED, DeviceRole.WORKER)
    enrolled = await enrollment.enroll(issued.code, **AS_WORKER)

    written = " ".join(event.model_dump_json() for event in await audit.read())
    stored = (await port.get(enrolled.device.id)).model_dump_json()
    for value in (
        issued.code,
        enrolled.secret,
        fingerprint(issued.code),
        fingerprint(enrolled.secret),
    ):
        assert value not in written
        assert value not in stored


async def test_a_code_presented_twice_names_the_node_it_gave_birth_to(
    enrollment: NodeEnrollment, registry: DeviceRegistry, audit: FakeAuditLog
) -> None:
    issued = await enrollment.issue(PrivacyLevel.TRUSTED, DeviceRole.WORKER)
    first = await enrollment.enroll(issued.code, **AS_WORKER)

    with pytest.raises(EnrollmentConsumedError):
        await enrollment.enroll(issued.code, **AS_WORKER)

    _, rejected = await audit.read()
    assert rejected.event_type is AuditEventType.DEVICE_REJECTED
    assert dict(rejected.payload) == {
        "reason": "code_reused",
        "named_device_id": str(first.device.id),
    }
    assert [device.id for device in await registry.devices()] == [first.device.id]


async def test_in_the_crash_window_a_reused_code_names_nobody(
    enrollment: NodeEnrollment,
    codes: RecordingStore,
    registry: DeviceRegistry,
    audit: FakeAuditLog,
    clock: FakeClock,
) -> None:
    """Dec. D §6: the code spent and the row never born. Presenting it again is refused, and
    there is no node to name — a rejection is written only about a node that exists."""
    issued = await enrollment.issue(PrivacyLevel.TRUSTED, DeviceRole.WORKER)
    lost = DeviceId(UUID("00000000-0000-4000-8000-000000000501"))
    await codes.consume(
        fingerprint(issued.code), device_id=lost, now=clock.now(), role=DeviceRole.WORKER
    )

    with pytest.raises(EnrollmentConsumedError):
        await enrollment.enroll(issued.code, **AS_WORKER)

    assert await audit.read() == ()
    assert await registry.devices() == ()


async def test_a_code_nobody_issued_leaves_nothing(
    enrollment: NodeEnrollment, registry: DeviceRegistry, audit: FakeAuditLog
) -> None:
    with pytest.raises(NotFoundError):
        await enrollment.enroll("not-a-code", **AS_WORKER)
    assert await audit.read() == ()
    assert await registry.devices() == ()


async def test_a_code_expires_ten_minutes_after_it_was_issued(
    enrollment: NodeEnrollment, registry: DeviceRegistry, audit: FakeAuditLog, clock: FakeClock
) -> None:
    issued = await enrollment.issue(PrivacyLevel.TRUSTED, DeviceRole.WORKER)
    clock.advance(ENROLLMENT_CODE_TTL)

    with pytest.raises(EnrollmentExpiredError):
        await enrollment.enroll(issued.code, **AS_WORKER)

    assert await audit.read() == ()
    assert await registry.devices() == ()
