"""The Model Router: the first ``AVAILABLE`` provider of the route, and the profile (§25).

Two of the seven criteria of §25 are used in v0.1 — **tipo di task** and **disponibilità** — and
the other five (qualità, latenza, costo, privacy, capacità) are declared out of scope until there
is a second provider to compare (ADR 0022 §11). Two criteria are enough to make the choice a
*policy* instead of a string somebody typed into a plan.

The router **never calls a provider**. It reads :class:`~ela.domain.ProviderStatus`, which is a
property of the configuration and not of the network (ADR 0020 §2), so falling back costs nothing
and no provider that is down ever receives the user's content (§57). A failure *after* a call
does not move the call elsewhere: that would pay twice for an answer that might still arrive, send
the content out a second time, and stack on top of the retry the adapter already does
(ADR 0020 §8).
"""

from __future__ import annotations

from ela.domain import ModelRoute, ProviderStatus
from ela.ports import (
    PROVIDER_UNAVAILABLE,
    ROUTING_UNKNOWN_PROVIDER,
    ProviderRegistryPort,
    RoutingError,
)
from ela.routing.policy import RoutePolicy

__all__ = ["ModelRouter"]


class ModelRouter:
    """Routes by task type, falls back on availability (port ``ModelRouterPort``).

    **Every provider the policy names must be in the registry**, and it is checked here, once,
    when the router is built: a route pointing at a name ELA does not have is a configuration
    error, and a configuration error is caught at start-up, not on the step that happens to need
    it. The alternative — skipping an unknown name like an unavailable one — would let a typo in
    ``ELA_MODEL_ROUTES`` quietly divert calls to whatever comes next in the list (ADR 0022 §7).
    """

    __slots__ = ("_policy", "_providers")

    def __init__(self, policy: RoutePolicy, providers: ProviderRegistryPort) -> None:
        registered = set(providers.names())
        unknown = [name for name in policy.provider_names() if name not in registered]
        if unknown:
            raise RoutingError(
                ROUTING_UNKNOWN_PROVIDER,
                f"the routing table names {unknown}, which the provider registry does not have: "
                f"it has {list(providers.names())}",
            )
        self._policy = policy
        self._providers = providers

    def route(self, task_type: str | None, model_hint: str | None) -> ModelRoute:
        """The first usable provider of the route, with the profile to ask it for.

        ``model_hint`` wins over the route's profile (ADR 0022 §3): whoever wrote a hint has
        chosen, and the table is there to fill the silence of whoever has not. The **provider**
        stays the one the task type chose — a hint names a profile, not a vendor. A blank hint is
        no hint, the way a blank API key is no key (ADR 0020 §3).

        :raises RoutingError: :data:`~ela.ports.ROUTING_UNKNOWN_TASK_TYPE` from the policy, or
            :data:`~ela.ports.PROVIDER_UNAVAILABLE` when no provider of the route is usable. In
            both cases nothing has been sent anywhere.
        """
        route = self._policy.route_for(task_type)
        skipped: list[str] = []
        for name in route.providers:
            if self._providers.get(name).status is ProviderStatus.AVAILABLE:
                return ModelRoute(
                    task_type=task_type,
                    provider=name,
                    profile=model_hint if model_hint else route.profile,
                    skipped=tuple(skipped),
                )
            skipped.append(name)
        raise RoutingError(
            PROVIDER_UNAVAILABLE,
            f"no provider of the route is available: tried {list(route.providers)}",
        )
