"""The routing table: which providers, and which profile, for a kind of task (§25; ADR 0022).

§25 asks that ELA choose a model «in base a: tipo di task; qualità necessaria; latenza; costo;
privacy; capacità; disponibilità», and gives two examples — a powerful model for planning,
coding, reasoning and analysis; a cheaper one for classification, extraction, small tasks and
routine. :data:`DEFAULT_ROUTES` is those two lists turned into code, and it is **an opinion**: a
reasonable reading of the spec, not a measurement. ADR 0022 §4 holds the same table, dated, and
``tests/docs/test_adr_routing.py`` keeps the two equal.

A route names a **profile**, never a model id: `quality`, `balanced`, `cheap` are the vocabulary
of ADR 0020 §5, and turning one into ``claude-opus-5`` is the adapter's job — the Core that named
a vendor's model would be the Core §26 forbids.

The table is **closed**: a ``task_type`` nobody mapped is
:data:`~ela.ports.ROUTING_UNKNOWN_TASK_TYPE` and no call is made (ADR 0022 §6). The default route
is not a safety net for a wrong type; it is the route of a step that names **no** type at all,
which is a different thing. And the table is never **empty**: a policy with no route is refused
where it is built, not one failed step at a time (ADR 0022 §8).
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from pydantic import BaseModel, ConfigDict, field_validator

from ela.ports import ROUTING_EMPTY_ROUTES, ROUTING_UNKNOWN_TASK_TYPE, RoutingError

__all__ = [
    "BALANCED",
    "CHEAP",
    "DEFAULT_ROUTE",
    "DEFAULT_ROUTES",
    "QUALITY",
    "Route",
    "RoutePolicy",
]

QUALITY: Final = "quality"
BALANCED: Final = "balanced"
CHEAP: Final = "cheap"

ANTHROPIC: Final = "anthropic"
"""The one provider ELA has (M7.1). A **name**, not an import: ``ela.routing`` may not import
``ela.providers`` (contract 4), and a registry key is all the Core needs to know about a vendor.
``tests/routing/test_policy.py`` checks that this string is the name the adapter registers under,
which is the only place the two can be compared without breaking the contract."""


class Route(BaseModel):
    """Where a kind of task goes: the providers to try, in order, and the profile to ask for."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    providers: tuple[str, ...]
    profile: str

    @field_validator("providers")
    @classmethod
    def _ordered_and_distinct(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """At least one provider, no blanks, no repeats: the order is the fallback (ADR 0022 §7).

        A repeated name would mean trying the same provider twice in a row, which after a
        ``ProviderStatus`` that does not change within a call is the same answer twice.
        """
        if not value:
            raise ValueError("a route must name at least one provider")
        if any(not name.strip() for name in value):
            raise ValueError("a route may not name a blank provider")
        if len(set(value)) != len(value):
            raise ValueError(f"a route may not name a provider twice: {list(value)}")
        return value

    @field_validator("profile")
    @classmethod
    def _named_profile(cls, value: str) -> str:
        """The router always chooses. "No profile, let the provider decide" is a choice
        not taken, and ADR 0022 §3 says the choice is the router's."""
        if not value.strip():
            raise ValueError("a route must name a profile")
        return value


DEFAULT_ROUTES: Final[Mapping[str, Route]] = MappingProxyType(
    {
        "planning": Route(providers=(ANTHROPIC,), profile=QUALITY),
        "coding": Route(providers=(ANTHROPIC,), profile=QUALITY),
        "reasoning": Route(providers=(ANTHROPIC,), profile=QUALITY),
        "analysis": Route(providers=(ANTHROPIC,), profile=QUALITY),
        "classification": Route(providers=(ANTHROPIC,), profile=CHEAP),
        "extraction": Route(providers=(ANTHROPIC,), profile=CHEAP),
        "routine": Route(providers=(ANTHROPIC,), profile=CHEAP),
    }
)
"""The seven task types of §25, four expensive and three cheap.

§25's cheap list reads «classificazione, estrazione, piccoli task, routine»: "piccoli task" is
read as ``routine`` rather than given an entry of its own, because a size is not a kind of task
and the two would have named the same route (ADR 0022 §4).
"""

DEFAULT_ROUTE: Final = Route(providers=(ANTHROPIC,), profile=BALANCED)
"""What answers a step that names no ``task_type``: the balanced profile, for the reason ADR 0020
§4 gives the same answer — what runs when nobody has thought about cost must not be the most
expensive thing available."""


class RoutePolicy:
    """The table, frozen at construction: a task type in, a :class:`Route` out.

    Holds no provider and reads no status — that is :class:`~ela.routing.router.ModelRouter`'s
    half of the work. This half is a pure function of a table, which is what makes the policy
    something a test can state in one line and a verifier can recompute.
    """

    __slots__ = ("_default", "_routes")

    def __init__(
        self,
        routes: Mapping[str, Route] = DEFAULT_ROUTES,
        default: Route = DEFAULT_ROUTE,
    ) -> None:
        """The table, and the route of a call that names no ``task_type``.

        :raises RoutingError: :data:`~ela.ports.ROUTING_EMPTY_ROUTES` if ``routes`` is empty.
            Replacing the table in full is the operator's right (ADR 0022 §8); replacing it with
            nothing is not a narrower policy but a policy that fails every step naming a task
            type, one at a time, far from the file that caused it. ELA ships a default table so
            that a machine nobody configured still routes, and the refusal says how to get it
            back (review of M7.3).
        """
        if not routes:
            raise RoutingError(
                ROUTING_EMPTY_ROUTES,
                "the routing table is empty: every task type would fail with "
                f"{ROUTING_UNKNOWN_TASK_TYPE}. Name at least one route, or unset "
                "ELA_MODEL_ROUTES to use the default table of spec §25 "
                f"({', '.join(sorted(DEFAULT_ROUTES))})",
            )
        self._routes: Mapping[str, Route] = MappingProxyType(dict(routes))
        self._default = default

    @property
    def default(self) -> Route:
        """The route of a call that names no ``task_type``."""
        return self._default

    def task_types(self) -> tuple[str, ...]:
        """The task types this policy knows, sorted. The vocabulary is exactly these."""
        return tuple(sorted(self._routes))

    def provider_names(self) -> tuple[str, ...]:
        """Every provider name any route mentions, the default route included, sorted."""
        named = {name for route in self._routes.values() for name in route.providers}
        return tuple(sorted(named | set(self._default.providers)))

    def route_for(self, task_type: str | None) -> Route:
        """The route for ``task_type``; the default route when there is none to route on.

        :raises RoutingError: :data:`~ela.ports.ROUTING_UNKNOWN_TASK_TYPE` when ``task_type`` is
            given and the table does not know it. A type the table does not know is a bug in
            whoever planned the step (ADR 0022 §6), and answering it with the default route would
            send the user's content to a model nobody chose, without a trace (§33).
        """
        if task_type is None:
            return self._default
        try:
            return self._routes[task_type]
        except KeyError:
            raise RoutingError(
                ROUTING_UNKNOWN_TASK_TYPE,
                f"no route for task type {task_type!r}: the policy knows {list(self.task_types())}",
            ) from None
