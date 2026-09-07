"""The routing table from the environment (ADR 0001: pydantic-settings + ``.env``; ADR 0022 §8).

Two variables, both JSON, both replacing what they name **in full**:

* ``ELA_MODEL_ROUTES`` — the whole table. Not merged into the default one: a table that was
  partly ELA's opinion and partly the operator's would be a table nobody could read off a single
  document, and ADR 0022 §4 wants the routing of an installation to be one visible thing.
* ``ELA_MODEL_DEFAULT_ROUTE`` — the route of a call that names no ``task_type``, which §6 keeps
  distinct from a call that names a wrong one.

Neither is required: ELA routes sensibly on a machine where nobody has configured anything, which
is the point of shipping a default table at all.
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ela.routing.policy import DEFAULT_ROUTE, DEFAULT_ROUTES, Route, RoutePolicy

__all__ = ["RoutingSettings"]


class RoutingSettings(BaseSettings):
    """Routing configuration, read from ``ELA_*`` variables and an optional ``.env``."""

    model_config = SettingsConfigDict(
        env_prefix="ELA_",
        env_file=".env",
        extra="ignore",
        protected_namespaces=(),
    )
    """``protected_namespaces=()`` because the two fields start with ``model_``, which pydantic
    reserves for its own attributes: without it, declaring ``ELA_MODEL_ROUTES`` under the ``ELA_``
    prefix every other settings class uses would warn on every import. Renaming the variables to
    dodge the warning would name the same thing something else."""

    model_routes: dict[str, Route] = Field(default_factory=lambda: dict(DEFAULT_ROUTES))
    """``ELA_MODEL_ROUTES``: ``{"coding": {"providers": ["anthropic"], "profile": "quality"}}``."""

    model_default_route: Route = DEFAULT_ROUTE
    """``ELA_MODEL_DEFAULT_ROUTE``: the route of a call with no ``task_type``."""

    @field_validator("model_routes")
    @classmethod
    def _named_task_types(cls, value: dict[str, Route]) -> dict[str, Route]:
        """A blank task type is not a task type: it could never be matched by a step, and it
        would sit in the table looking like a route that works."""
        blank = [key for key in value if not key.strip()]
        if blank:
            raise ValueError("a task type may not be blank")
        return value

    def policy(self) -> RoutePolicy:
        """The configured table as the :class:`~ela.routing.policy.RoutePolicy` the router takes.

        :raises RoutingError: :data:`~ela.ports.ROUTING_EMPTY_ROUTES` when ``ELA_MODEL_ROUTES``
            is ``{}``. Replacing the table with **one** route is legitimate — replacing it in
            full is the whole point of the variable — but replacing it with nothing is not a
            policy an operator can have meant: every step naming a task type would fail, one at a
            time, far from the file that caused it (review of M7.3).

        This is where a misconfigured table is caught, next to where a route naming an unknown
        provider is caught (ADR 0022 §7): both when the composition root builds the policy and
        the router, and neither on the step that happens to need them.
        """
        return RoutePolicy(self.model_routes, self.model_default_route)
