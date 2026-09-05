"""Contract of ``AuthorizationStore`` (spec §30, §59): grants by id, a use counter each, and
``consume`` that spends a use only when the grant can still be spent (ADR 0012)."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest

from ela.domain import AuthorizationId
from ela.ports import (
    AlreadyExistsError,
    AuthorizationExhaustedError,
    AuthorizationExpiredError,
    AuthorizationNotUsableError,
    AuthorizationStore,
    NotFoundError,
    PortError,
)
from tests.domain.examples import (
    LATER,
    MODEL_COMPLETE,
    NOW,
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


@pytest.mark.parametrize("method", ["get", "uses"])
async def test_unknown_id_is_not_found(
    authorization_store: AuthorizationStore, method: str
) -> None:
    with pytest.raises(NotFoundError):
        await getattr(authorization_store, method)(SINGLE_USE_AUTHORIZATION.id)


async def test_consume_of_an_unknown_id_is_not_found(
    authorization_store: AuthorizationStore,
) -> None:
    with pytest.raises(NotFoundError):
        await authorization_store.consume(SINGLE_USE_AUTHORIZATION.id, now=NOW)


async def test_uses_start_at_zero_and_consume_counts_up(
    authorization_store: AuthorizationStore,
) -> None:
    await authorization_store.grant(POLICY_AUTHORIZATION)
    assert await authorization_store.uses(POLICY_AUTHORIZATION.id) == 0
    assert await authorization_store.consume(POLICY_AUTHORIZATION.id, now=NOW) == 1
    assert await authorization_store.consume(POLICY_AUTHORIZATION.id, now=NOW) == 2
    assert await authorization_store.uses(POLICY_AUTHORIZATION.id) == 2


async def test_without_a_use_limit_consume_never_exhausts(
    authorization_store: AuthorizationStore,
) -> None:
    assert POLICY_AUTHORIZATION.max_uses is None and POLICY_AUTHORIZATION.expires_at is None
    await authorization_store.grant(POLICY_AUTHORIZATION)
    totals = [await authorization_store.consume(POLICY_AUTHORIZATION.id, now=NOW) for _ in range(5)]
    assert totals == [1, 2, 3, 4, 5]


async def test_a_single_use_grant_consumed_twice_is_an_error_the_second_time(
    authorization_store: AuthorizationStore,
) -> None:
    """§30: one yes, one action."""
    assert SINGLE_USE_AUTHORIZATION.max_uses == 1
    await authorization_store.grant(SINGLE_USE_AUTHORIZATION)
    assert await authorization_store.consume(SINGLE_USE_AUTHORIZATION.id, now=NOW) == 1
    with pytest.raises(AuthorizationExhaustedError) as caught:
        await authorization_store.consume(SINGLE_USE_AUTHORIZATION.id, now=NOW)
    assert caught.value.authorization_id == SINGLE_USE_AUTHORIZATION.id
    assert (caught.value.uses, caught.value.max_uses) == (1, 1)
    assert await authorization_store.uses(SINGLE_USE_AUTHORIZATION.id) == 1


async def test_a_limited_grant_is_consumed_exactly_max_uses_times(
    authorization_store: AuthorizationStore,
) -> None:
    three = POLICY_AUTHORIZATION.model_copy(update={"max_uses": 3})
    await authorization_store.grant(three)
    assert [await authorization_store.consume(three.id, now=NOW) for _ in range(3)] == [1, 2, 3]
    with pytest.raises(AuthorizationExhaustedError):
        await authorization_store.consume(three.id, now=NOW)
    assert await authorization_store.uses(three.id) == 3


async def test_an_expired_grant_cannot_be_consumed(
    authorization_store: AuthorizationStore,
) -> None:
    assert SINGLE_USE_AUTHORIZATION.expires_at == LATER
    await authorization_store.grant(SINGLE_USE_AUTHORIZATION)
    with pytest.raises(AuthorizationExpiredError) as caught:
        await authorization_store.consume(
            SINGLE_USE_AUTHORIZATION.id, now=LATER + timedelta(seconds=1)
        )
    assert caught.value.expires_at == LATER
    assert await authorization_store.uses(SINGLE_USE_AUTHORIZATION.id) == 0


async def test_expiry_is_closed_at_the_exact_instant(
    authorization_store: AuthorizationStore,
) -> None:
    """ADR 0005 §2-bis: ``expires_at <= now`` is expired; one microsecond before is not."""
    await authorization_store.grant(SINGLE_USE_AUTHORIZATION)
    with pytest.raises(AuthorizationExpiredError):
        await authorization_store.consume(SINGLE_USE_AUTHORIZATION.id, now=LATER)
    assert await authorization_store.uses(SINGLE_USE_AUTHORIZATION.id) == 0
    just_before = LATER - timedelta(microseconds=1)
    assert await authorization_store.consume(SINGLE_USE_AUTHORIZATION.id, now=just_before) == 1


async def test_expired_is_reported_before_exhausted(
    authorization_store: AuthorizationStore,
) -> None:
    await authorization_store.grant(SINGLE_USE_AUTHORIZATION)
    await authorization_store.consume(SINGLE_USE_AUTHORIZATION.id, now=NOW)
    with pytest.raises(AuthorizationExpiredError):
        await authorization_store.consume(SINGLE_USE_AUTHORIZATION.id, now=LATER)


async def test_a_refused_consume_is_a_named_port_error(
    authorization_store: AuthorizationStore,
) -> None:
    await authorization_store.grant(SINGLE_USE_AUTHORIZATION)
    await authorization_store.consume(SINGLE_USE_AUTHORIZATION.id, now=NOW)
    with pytest.raises(AuthorizationNotUsableError) as caught:
        await authorization_store.consume(SINGLE_USE_AUTHORIZATION.id, now=NOW)
    assert isinstance(caught.value, PortError)
    assert str(SINGLE_USE_AUTHORIZATION.id) in str(caught.value)
    assert "1 of 1" in caught.value.reason


async def test_consume_changes_nothing_but_the_count(
    authorization_store: AuthorizationStore,
) -> None:
    await authorization_store.grant(SINGLE_USE_AUTHORIZATION)
    await authorization_store.consume(SINGLE_USE_AUTHORIZATION.id, now=NOW)
    assert await authorization_store.get(SINGLE_USE_AUTHORIZATION.id) == SINGLE_USE_AUTHORIZATION
    grants = await authorization_store.for_capability(SINGLE_USE_AUTHORIZATION.capability_id)
    assert grants == (SINGLE_USE_AUTHORIZATION,)


async def test_uses_are_counted_per_grant(authorization_store: AuthorizationStore) -> None:
    await authorization_store.grant(SINGLE_USE_AUTHORIZATION)
    await authorization_store.grant(POLICY_AUTHORIZATION)
    await authorization_store.consume(SINGLE_USE_AUTHORIZATION.id, now=NOW)
    assert await authorization_store.uses(POLICY_AUTHORIZATION.id) == 0


async def test_the_unconditional_counter_is_gone(authorization_store: AuthorizationStore) -> None:
    """ADR 0012 §4: ``record_use`` was replaced by ``consume``; no way around the conditions."""
    assert not hasattr(authorization_store, "record_use")
    assert "record_use" not in AuthorizationStore.__protocol_attrs__


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
