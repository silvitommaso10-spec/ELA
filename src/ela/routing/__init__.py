"""The Model Router (spec §25; ADR 0022).

Which model answers is a **policy**, not a string in a plan: a table maps a ``task_type`` to a
list of providers and a profile, and the router takes the first provider that is usable. The
package is Core — it holds no provider and imports none (contract 4) — and reaches the providers
it chooses between through :class:`~ela.ports.ProviderRegistryPort`.
"""

from __future__ import annotations

from ela.routing.policy import (
    BALANCED,
    CHEAP,
    DEFAULT_ROUTE,
    DEFAULT_ROUTES,
    QUALITY,
    Route,
    RoutePolicy,
)
from ela.routing.router import ModelRouter
from ela.routing.settings import RoutingSettings

__all__ = [
    "BALANCED",
    "CHEAP",
    "DEFAULT_ROUTE",
    "DEFAULT_ROUTES",
    "QUALITY",
    "ModelRouter",
    "Route",
    "RoutePolicy",
    "RoutingSettings",
]
