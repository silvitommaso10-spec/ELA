"""Contract of ``EnrollmentStore`` (§16; M12.1 dec. D, G): a code is spent once, until it expires.

On the fake and on the SQL adapter in memory. What needs two real connections — criterion 3, one
code presented by two nodes at once — is in ``tests/infrastructure/persistence``, because an
in-memory database has one connection by construction.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from uuid import UUID

import pytest

from ela.domain import DeviceId, DeviceRole, Enrollment
from ela.ports import (
    AlreadyExistsError,
    EnrollmentConsumedError,
    EnrollmentExpiredError,
    EnrollmentNotUsableError,
    EnrollmentRoleError,
    EnrollmentStore,
    NotFoundError,
)
from tests.domain.examples import LATER, WAITING_ENROLLMENT

CODE = WAITING_ENROLLMENT
ROLE = CODE.role
"""The role the code was minted for: the store spends it only on the route that asks for it."""
OTHER_ROLE = next(role for role in DeviceRole if role is not CODE.role)
NODE = DeviceId(UUID("00000000-0000-4000-8000-000000000401"))
OTHER_NODE = DeviceId(UUID("00000000-0000-4000-8000-000000000402"))
INSTANT = timedelta(microseconds=1)


async def test_a_code_offered_is_spent_by_the_node_that_presents_it(
    enrollment_store: EnrollmentStore,
) -> None:
    await enrollment_store.offer(CODE)
    spent = await enrollment_store.consume(CODE.code_hash, device_id=NODE, now=LATER, role=ROLE)
    assert spent == CODE.model_copy(update={"consumed_at": LATER, "device_id": NODE})


async def test_a_code_is_offered_once(enrollment_store: EnrollmentStore) -> None:
    await enrollment_store.offer(CODE)
    with pytest.raises(AlreadyExistsError):
        await enrollment_store.offer(
            CODE.model_copy(update={"expires_at": CODE.expires_at + INSTANT})
        )
    spent = await enrollment_store.consume(CODE.code_hash, device_id=NODE, now=LATER, role=ROLE)
    assert spent.expires_at == CODE.expires_at


async def test_an_unknown_code_is_not_found(enrollment_store: EnrollmentStore) -> None:
    with pytest.raises(NotFoundError):
        await enrollment_store.consume(CODE.code_hash, device_id=NODE, now=LATER, role=ROLE)


async def test_a_spent_code_names_the_node_it_gave_birth_to(
    enrollment_store: EnrollmentStore,
) -> None:
    """The second presentation is refused, and the refusal says which node the code made — what
    ``DEVICE_REJECTED`` ``code_reused`` reports (ADR 0037 §13)."""
    await enrollment_store.offer(CODE)
    await enrollment_store.consume(CODE.code_hash, device_id=NODE, now=LATER, role=ROLE)
    with pytest.raises(EnrollmentConsumedError) as caught:
        await enrollment_store.consume(CODE.code_hash, device_id=OTHER_NODE, now=LATER, role=ROLE)
    assert caught.value.device_id == NODE


async def test_a_code_is_expired_at_the_instant_of_its_expiry(
    enrollment_store: EnrollmentStore,
) -> None:
    """Closed bound (ADR 0005 §2-bis): at ``expires_at`` the code is expired, and the refusal
    writes nothing — the same code still works an instant earlier."""
    await enrollment_store.offer(CODE)
    with pytest.raises(EnrollmentExpiredError) as caught:
        await enrollment_store.consume(
            CODE.code_hash, device_id=NODE, now=CODE.expires_at, role=ROLE
        )
    assert caught.value.expires_at == CODE.expires_at
    before = CODE.expires_at - INSTANT
    spent = await enrollment_store.consume(CODE.code_hash, device_id=NODE, now=before, role=ROLE)
    assert spent.consumed_at == before


async def test_a_code_spent_and_then_expired_says_it_was_spent(
    enrollment_store: EnrollmentStore,
) -> None:
    await enrollment_store.offer(CODE)
    await enrollment_store.consume(CODE.code_hash, device_id=NODE, now=LATER, role=ROLE)
    with pytest.raises(EnrollmentConsumedError):
        await enrollment_store.consume(
            CODE.code_hash, device_id=OTHER_NODE, now=CODE.expires_at, role=ROLE
        )


async def test_no_refusal_carries_the_hash(enrollment_store: EnrollmentStore) -> None:
    """An error can reach a response body: none of them prints what the store keeps."""
    refusals: list[Exception] = []
    for attempt in (
        enrollment_store.consume(CODE.code_hash, device_id=NODE, now=LATER, role=ROLE),
        enrollment_store.offer(CODE),
        enrollment_store.offer(CODE),
        enrollment_store.consume(CODE.code_hash, device_id=NODE, now=LATER, role=OTHER_ROLE),
        enrollment_store.consume(CODE.code_hash, device_id=NODE, now=CODE.expires_at, role=ROLE),
        enrollment_store.consume(CODE.code_hash, device_id=NODE, now=LATER, role=ROLE),
        enrollment_store.consume(CODE.code_hash, device_id=NODE, now=LATER, role=ROLE),
    ):
        try:
            await attempt
        except (NotFoundError, AlreadyExistsError, EnrollmentNotUsableError) as refused:
            refusals.append(refused)
    assert [type(refused) for refused in refusals] == [
        NotFoundError,
        AlreadyExistsError,
        EnrollmentRoleError,
        EnrollmentExpiredError,
        EnrollmentConsumedError,
    ]
    assert all(CODE.code_hash not in str(refused) for refused in refusals)


async def test_a_code_of_the_other_role_is_refused_and_left_spendable(
    enrollment_store: EnrollmentStore,
) -> None:
    """M12.5 dec. C.5: the role is a condition of the statement, so the refusal writes nothing.

    The other half of the promise is the line after it: the same code, on the route of the role it
    was minted for, is still spendable — which is what makes a code pasted in the wrong place cost
    the user nothing.
    """
    await enrollment_store.offer(CODE)

    with pytest.raises(EnrollmentRoleError) as refused:
        await enrollment_store.consume(CODE.code_hash, device_id=NODE, now=LATER, role=OTHER_ROLE)

    assert (refused.value.carried, refused.value.expected) == (ROLE, OTHER_ROLE)
    spent = await enrollment_store.consume(CODE.code_hash, device_id=NODE, now=LATER, role=ROLE)
    assert spent.consumed_at == LATER


async def test_two_presentations_of_one_code_let_one_node_be_born(
    enrollment_store: EnrollmentStore,
) -> None:
    await enrollment_store.offer(CODE)
    outcomes = await asyncio.gather(
        enrollment_store.consume(CODE.code_hash, device_id=NODE, now=LATER, role=ROLE),
        enrollment_store.consume(CODE.code_hash, device_id=OTHER_NODE, now=LATER, role=ROLE),
        return_exceptions=True,
    )
    born = [outcome for outcome in outcomes if isinstance(outcome, Enrollment)]
    refused = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
    assert len(born) == 1
    assert [type(outcome) for outcome in refused] == [EnrollmentConsumedError]
