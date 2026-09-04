"""Contract of ``AuthorizationStore`` (spec §30, §59): grants by id, with a use counter each."""

from __future__ import annotations

from uuid import UUID

import pytest

from ela.domain import AuthorizationId
from ela.ports import AlreadyExistsError, AuthorizationStore, NotFoundError
from tests.domain.examples import (
    MODEL_COMPLETE,
    POLICY_AUTHORIZATION,
    SINGLE_USE_AUTHORIZATION,
)

MODEL_AUTHORIZATION = POLICY_AUTHORIZATION.model_copy(
    update={
        "id": AuthorizationId(UUID("00000000-0000-4000-8000-000000000401")),
        "capability_id": MODEL_COMPLETE,
        "scope": (),
    }
)


async def test_grant_then_get(authorization_store: AuthorizationStore) -> None:
    await authorization_store.grant(SINGLE_USE_AUTHORIZATION)
    assert await authorization_store.get(SINGLE_USE_AUTHORIZATION.id) == SINGLE_USE_AUTHORIZATION


async def test_grant_twice_is_rejected(authorization_store: AuthorizationStore) -> None:
    await authorization_store.grant(SINGLE_USE_AUTHORIZATION)
    with pytest.raises(AlreadyExistsError):
        await authorization_store.grant(SINGLE_USE_AUTHORIZATION.model_copy(update={"max_uses": 9}))
    assert await authorization_store.get(SINGLE_USE_AUTHORIZATION.id) == SINGLE_USE_AUTHORIZATION


@pytest.mark.parametrize("method", ["get", "uses", "record_use"])
async def test_unknown_id_is_not_found(
    authorization_store: AuthorizationStore, method: str
) -> None:
    with pytest.raises(NotFoundError):
        await getattr(authorization_store, method)(SINGLE_USE_AUTHORIZATION.id)


async def test_uses_start_at_zero_and_count_up(authorization_store: AuthorizationStore) -> None:
    await authorization_store.grant(SINGLE_USE_AUTHORIZATION)
    assert await authorization_store.uses(SINGLE_USE_AUTHORIZATION.id) == 0
    assert await authorization_store.record_use(SINGLE_USE_AUTHORIZATION.id) == 1
    assert await authorization_store.record_use(SINGLE_USE_AUTHORIZATION.id) == 2
    assert await authorization_store.uses(SINGLE_USE_AUTHORIZATION.id) == 2


async def test_uses_are_counted_per_grant(authorization_store: AuthorizationStore) -> None:
    await authorization_store.grant(SINGLE_USE_AUTHORIZATION)
    await authorization_store.grant(POLICY_AUTHORIZATION)
    await authorization_store.record_use(SINGLE_USE_AUTHORIZATION.id)
    assert await authorization_store.uses(POLICY_AUTHORIZATION.id) == 0


async def test_for_capability_filters_in_grant_order(
    authorization_store: AuthorizationStore,
) -> None:
    await authorization_store.grant(POLICY_AUTHORIZATION)
    await authorization_store.grant(MODEL_AUTHORIZATION)
    await authorization_store.grant(SINGLE_USE_AUTHORIZATION)
    grants = await authorization_store.for_capability(SINGLE_USE_AUTHORIZATION.capability_id)
    assert isinstance(grants, tuple)
    assert grants == (POLICY_AUTHORIZATION, SINGLE_USE_AUTHORIZATION)
    assert await authorization_store.for_capability(MODEL_COMPLETE) == (MODEL_AUTHORIZATION,)
