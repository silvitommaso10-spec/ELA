"""A router over the providers a test has, for everyone who needs a routed model call.

``tools_v01`` takes a :class:`~ela.ports.ModelRouterPort` and a
:class:`~ela.ports.ProviderRegistryPort` since M7.3, and most tests do not care about routing:
they care that ``model.complete`` reaches *their* provider. :func:`routing_for` gives them the
real :class:`~ela.routing.ModelRouter` over the real policy, with the seven task types of §25
pointed at the providers they built — the profiles stay the ones ADR 0022 §4 prescribes.
"""

from __future__ import annotations

from ela.ports import ModelProvider
from ela.providers.registry import ProviderRegistry
from ela.routing import BALANCED, DEFAULT_ROUTES, ModelRouter, Route, RoutePolicy

__all__ = ["policy_for", "routing_for"]


def policy_for(*names: str, profile: str = BALANCED) -> RoutePolicy:
    """The default table with every route pointed at ``names``, in that order."""
    routes = {
        task_type: Route(providers=names, profile=route.profile)
        for task_type, route in DEFAULT_ROUTES.items()
    }
    return RoutePolicy(routes, Route(providers=names, profile=profile))


def routing_for(
    *providers: ModelProvider, profile: str = BALANCED
) -> tuple[ModelRouter, ProviderRegistry]:
    """A router and the registry it routes over: ``(router, providers)`` for ``tools_v01``."""
    registry = ProviderRegistry(tuple(providers))
    return ModelRouter(
        policy_for(*(p.name for p in providers), profile=profile), registry
    ), registry
