"""``SqlDeviceRegistry``: the nodes survive the process, and every field survives the round trip.

The behaviour of the port is under contract in ``tests/contracts/test_device_registry.py``, which
now runs against this adapter too. What is here is what only a real database can show: a file
closed and reopened, and a node with all eleven aspects of §16 filled in.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from ela.infrastructure.persistence import SqlDeviceRegistry, make_engine
from ela.infrastructure.persistence.orm import Base
from ela.ports import (
    AlreadyExistsError,
    IdentityConflictError,
    NotFoundError,
)
from tests.domain.examples import (
    DEVICE,
    ENROLLED_DEVICE,
    MUCH_LATER,
    SECRET_HASH,
)
from tests.infrastructure.persistence.concurrency import Meeting
from tests.infrastructure.persistence.conftest import Recorder, create_schema

OTHER = DEVICE.model_copy(update={"name": "Windows"})


async def test_a_device_survives_a_reopen(file_url: str) -> None:
    """On a file, not in memory: a registry that forgets on restart is not a registry."""
    engine = make_engine(file_url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await SqlDeviceRegistry(engine).register(DEVICE)
    finally:
        await engine.dispose()

    reopened = make_engine(file_url)
    try:
        assert await SqlDeviceRegistry(reopened).get(DEVICE.id) == DEVICE
    finally:
        await reopened.dispose()


async def test_every_field_survives_a_round_trip(engine: AsyncEngine) -> None:
    """All eleven aspects of §16, including the traits and the tool names."""
    registry = SqlDeviceRegistry(engine)
    await registry.register(DEVICE)
    stored = await registry.get(DEVICE.id)
    assert stored == DEVICE
    assert stored.capabilities == DEVICE.capabilities
    assert stored.capabilities[0].attributes == {"vram_gb": 24, "families": ("ada", "hopper")}
    assert stored.available_tools == DEVICE.available_tools
    assert stored.current_workload == DEVICE.current_workload
    assert stored.metadata == DEVICE.metadata


async def test_a_second_registration_is_refused_by_the_database(engine: AsyncEngine) -> None:
    """The UNIQUE on ``id``, not a read-then-write check."""
    registry = SqlDeviceRegistry(engine)
    await registry.register(DEVICE)
    with pytest.raises(AlreadyExistsError):
        await registry.register(OTHER)
    assert (await registry.get(DEVICE.id)).name == DEVICE.name


async def test_update_of_an_unknown_device_writes_nothing(engine: AsyncEngine) -> None:
    registry = SqlDeviceRegistry(engine)
    with pytest.raises(NotFoundError):
        await registry.update(DEVICE)
    assert await registry.devices() == ()


def test_the_registry_exposes_its_engine(engine: AsyncEngine) -> None:
    registry = SqlDeviceRegistry(engine)
    assert registry.engine is engine


Attach = Callable[[AsyncEngine], Recorder]
WRITE = "UPDATE devices"


async def test_two_processes_that_claim_one_node_do_not_overwrite_each_other(
    file_url: str,
) -> None:
    """Criterion 11 (ADR 0037 §9): two connections, a barrier before the write, two announcements
    at the same revision — one ``rowcount`` is one and the other zero, and the row is the winner's.

    *Fails with* the unconditional ``update``: both statements match, both ``rowcount`` values are
    one, and whoever arrives last wins.
    """
    first, second = make_engine(file_url), make_engine(file_url)
    try:
        await create_schema(first)
        await SqlDeviceRegistry(first).enroll(ENROLLED_DEVICE, secret_hash=SECRET_HASH)
        meeting = Meeting(WRITE)
        meeting.attend(first)
        meeting.attend(second)
        claims = [ENROLLED_DEVICE.model_copy(update={"name": name}) for name in ("one", "two")]
        outcomes = await asyncio.gather(
            SqlDeviceRegistry(first).announce(claims[0], expected_revision=1),
            SqlDeviceRegistry(second).announce(claims[1], expected_revision=1),
            return_exceptions=True,
        )
        assert sorted(meeting.rowcounts) == [0, 1]
        winner = outcomes.index(2)
        loser = outcomes[1 - winner]
        assert isinstance(loser, IdentityConflictError)
        assert (loser.expected, loser.actual) == (1, 2)
        stored = await SqlDeviceRegistry(first).get(ENROLLED_DEVICE.id)
        assert (stored.name, stored.revision) == (claims[winner].name, 2)
    finally:
        await first.dispose()
        await second.dispose()


async def test_an_announcement_beside_a_heartbeat_is_not_lost(file_url: str) -> None:
    """Criterion 12: the same two connections, an announcement and an observation — both write,
    on disjoint columns, and the row keeps the declared half **and** the sign of life."""
    first, second = make_engine(file_url), make_engine(file_url)
    try:
        await create_schema(first)
        await SqlDeviceRegistry(first).enroll(ENROLLED_DEVICE, secret_hash=SECRET_HASH)
        meeting = Meeting(WRITE)
        meeting.attend(first)
        meeting.attend(second)
        await asyncio.gather(
            SqlDeviceRegistry(first).announce(
                ENROLLED_DEVICE.model_copy(update={"name": "announced"}), expected_revision=1
            ),
            SqlDeviceRegistry(second).observe(
                ENROLLED_DEVICE.id, seen_at=MUCH_LATER, availability=ENROLLED_DEVICE.availability
            ),
        )
        assert meeting.rowcounts == [1, 1]
        stored = await SqlDeviceRegistry(first).get(ENROLLED_DEVICE.id)
        assert (stored.name, stored.last_seen_at, stored.revision) == ("announced", MUCH_LATER, 2)
    finally:
        await first.dispose()
        await second.dispose()


async def test_each_half_of_the_row_is_its_own_statement(
    engine: AsyncEngine, statements: Attach
) -> None:
    """The announcement is conditional on the revision and names no observed or imposed column;
    the observation names no declared one and no revision (ADR 0037 §9, §10)."""
    registry = SqlDeviceRegistry(engine)
    await registry.enroll(ENROLLED_DEVICE, secret_hash=SECRET_HASH)
    recorded = statements(engine)
    await registry.announce(ENROLLED_DEVICE, expected_revision=1)
    await registry.observe(
        ENROLLED_DEVICE.id, seen_at=MUCH_LATER, availability=ENROLLED_DEVICE.availability
    )
    announce, observe = (s for s in recorded() if s.startswith(WRITE))
    assert "devices.revision = ?" in announce
    assert "devices.revoked_at IS NULL" in announce
    for column in ("privacy", "network", "last_seen_at", "availability", "secret_hash"):
        assert column not in announce, column
    written = observe.split(" WHERE ")[0]
    for column in ("name", "os", "capabilities", "performance", "privacy", "revision"):
        assert f"{column}=" not in written, column
