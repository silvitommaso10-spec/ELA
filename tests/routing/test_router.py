"""``ModelRouter``: the first usable provider of the route, and never a call (ADR 0022 §7).

Every test here asserts the same thing twice: *which* provider was chosen, and that **nobody**
received a request. The second half is the point of decision 6a — the criterion §25 calls
"disponibilità" is read from a declared status, so falling back costs nothing and no provider
that is down ever gets the user's content only to hand it back (§57).
"""

from __future__ import annotations

import pytest

from ela.domain import ProviderStatus
from ela.ports import (
    PROVIDER_UNAVAILABLE,
    ROUTING_UNKNOWN_PROVIDER,
    ROUTING_UNKNOWN_TASK_TYPE,
    RoutingError,
)
from ela.providers.registry import ProviderRegistry
from ela.routing import BALANCED, CHEAP, QUALITY, ModelRouter, Route, RoutePolicy
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeModelProvider

DOWN = "down"
UP = "up"
LAST = "last"


def provider(name: str, *, available: bool = True) -> FakeModelProvider:
    return FakeModelProvider(
        FakeClock(),
        FakeIdGenerator(),
        name=name,
        status=ProviderStatus.AVAILABLE if available else ProviderStatus.UNAVAILABLE,
    )


def router_over(*providers: FakeModelProvider, route: tuple[str, ...] | None = None) -> ModelRouter:
    """A router whose ``coding`` route is ``route`` (or every provider, in order)."""
    names = route if route is not None else tuple(p.name for p in providers)
    policy = RoutePolicy(
        {"coding": Route(providers=names, profile=QUALITY)},
        Route(providers=names, profile=BALANCED),
    )
    return ModelRouter(policy, ProviderRegistry(providers))


def test_the_first_available_provider_of_the_route_answers() -> None:
    first, second = provider(UP), provider(LAST)

    route = router_over(first, second).route("coding", None)

    assert route.provider == UP
    assert route.profile == QUALITY
    assert route.skipped == ()
    assert first.requests == () and second.requests == ()


def test_a_provider_that_is_down_is_skipped_and_named() -> None:
    """Decision 6a: ``down`` is registered, declares UNAVAILABLE, and receives nothing."""
    down, up = provider(DOWN, available=False), provider(UP)

    route = router_over(down, up).route("coding", None)

    assert route.provider == UP
    assert route.skipped == (DOWN,)
    assert down.requests == ()


def test_the_order_of_the_route_is_the_order_of_the_fallback() -> None:
    down, second, third = provider(DOWN, available=False), provider(UP), provider(LAST)

    route = router_over(down, second, third).route("coding", None)

    assert route.provider == UP  # the first available, not the last one standing
    assert route.skipped == (DOWN,)


def test_no_provider_of_the_route_is_available() -> None:
    down, other = provider(DOWN, available=False), provider(UP, available=False)
    router = router_over(down, other)

    with pytest.raises(RoutingError) as raised:
        router.route("coding", None)

    assert raised.value.code == PROVIDER_UNAVAILABLE
    assert DOWN in raised.value.message and UP in raised.value.message
    assert down.requests == () and other.requests == ()


def test_an_unknown_task_type_never_reaches_a_provider() -> None:
    up = provider(UP)
    router = router_over(up)

    with pytest.raises(RoutingError) as raised:
        router.route("telepathy", None)

    assert raised.value.code == ROUTING_UNKNOWN_TASK_TYPE
    assert up.requests == ()


def test_no_task_type_takes_the_default_route() -> None:
    up = provider(UP)

    route = router_over(up).route(None, None)

    assert route.provider == UP
    assert route.profile == BALANCED
    assert route.task_type is None


def test_an_explicit_hint_wins_over_the_profile_and_not_over_the_provider() -> None:
    """Decision 5a: the hint names a profile, the task type still names the vendor."""
    down, up = provider(DOWN, available=False), provider(UP)

    route = router_over(down, up).route("coding", CHEAP)

    assert route.profile == CHEAP
    assert route.provider == UP
    assert route.skipped == (DOWN,)


@pytest.mark.parametrize("hint", [None, ""])
def test_a_blank_hint_is_no_hint(hint: str | None) -> None:
    """The way a blank API key is no key (ADR 0020 §3)."""
    assert router_over(provider(UP)).route("coding", hint).profile == QUALITY


def test_a_route_naming_a_provider_the_registry_does_not_have_is_refused_at_construction() -> None:
    """The answer to question 3 of the SPEC: a typo in ``ELA_MODEL_ROUTES`` stops ELA before it
    works, instead of diverting calls in silence or failing a step hours later."""
    registry = ProviderRegistry((provider(UP),))
    policy = RoutePolicy(
        {"coding": Route(providers=("typo", UP), profile=QUALITY)},
        Route(providers=(UP,), profile=BALANCED),
    )

    with pytest.raises(RoutingError) as raised:
        ModelRouter(policy, registry)

    assert raised.value.code == ROUTING_UNKNOWN_PROVIDER
    assert "typo" in raised.value.message
    assert UP in raised.value.message  # and what the registry does have


def test_a_provider_named_only_by_the_default_route_is_checked_too() -> None:
    registry = ProviderRegistry((provider(UP),))
    policy = RoutePolicy(
        {"coding": Route(providers=(UP,), profile=QUALITY)},
        Route(providers=("typo",), profile=BALANCED),
    )

    with pytest.raises(RoutingError, match="typo"):
        ModelRouter(policy, registry)


def test_a_registered_provider_with_no_credentials_is_not_a_typo() -> None:
    """ "Absent" and "UNAVAILABLE" are different things (ADR 0022 §7): a provider with no key is
    known, so the router builds — and skips it when it routes."""
    down = provider(DOWN, available=False)
    up = provider(UP)

    route = ModelRouter(
        RoutePolicy(
            {"coding": Route(providers=(DOWN, UP), profile=QUALITY)},
            Route(providers=(UP,), profile=BALANCED),
        ),
        ProviderRegistry((down, up)),
    ).route("coding", None)

    assert route.provider == UP


def test_the_router_answers_the_same_question_the_same_way() -> None:
    """What ``model.routed_as_asked`` rests on: no state between two calls, and a status that
    does not move (ADR 0020 §2)."""
    router = router_over(provider(DOWN, available=False), provider(UP))

    assert router.route("coding", None) == router.route("coding", None)


def test_the_router_is_frozen() -> None:
    router = router_over(provider(UP))
    assert not hasattr(router, "__dict__")
    with pytest.raises(AttributeError):
        router.extra = 1  # type: ignore[attr-defined]
