"""The routing table read against the provider's models, at startup (M14.6b, ADR 0067).

The table — ``ELA_MODEL_ROUTES`` and ``ELA_MODEL_DEFAULT_ROUTE`` — is written in a ``.env``, and a
``.env`` outlives the models it names: on the day a model leaves the list, a route that pinned its
id names nothing. The Core and a node build the same table (M12.2 dec. L), so both read it here,
with the same function, and stop with the variable named, not by refusing every call a step later.

**A belief, not the defence.** What this module reads is the table and the provider's two maps,
without the network and without the key; the defence is the refusal at the call, where the provider
cannot bound a hint that names no model and the gate does not let the call out (ADR 0057 §2). Both
are tested. The vocabulary is the one of ELA's only provider, and ADR 0067 says so. It does not
revise ADR 0022 §3, which is about the Core: a hint that names nothing is still refused by the
provider, never filtered by the Planner or the router.
"""

from __future__ import annotations

from ela.composition.errors import ConfigurationError
from ela.permissions import UNDECLARED_MODEL
from ela.ports import RoutingError
from ela.providers.anthropic.models import MODELS, PROFILES, model_for_hint
from ela.routing import RoutePolicy

__all__ = ["default_route_model", "every_route_names_a_model"]


def default_route_model(policy: RoutePolicy, task_type: str | None) -> str:
    """The model the route of ``task_type`` reads today — the default route for ``None`` (M13.12,
    ADR 0062; decision 16; M14.6b).

    Read from the routing table and the provider's profiles, without the network and without the
    key: the same answer the tool gets when it asks the provider for the worst case of one call. A
    task type the table does not know, or a profile no model answers, is :data:`UNDECLARED_MODEL`:
    no policy can be born under it, because the tool's prospect would refuse first.
    """
    try:
        route = policy.route_for(task_type)
    except RoutingError:
        return UNDECLARED_MODEL
    model = model_for_hint(route.profile)
    return UNDECLARED_MODEL if model is None else model.id


def every_route_names_a_model(policy: RoutePolicy) -> None:
    """Stop ELA if a route of the table has a profile no model answers (M14.6b, decision 7).

    Every task type of the table, then the default route. The message names the variable, the task
    type, the profile written, and the profiles and the model ids there are — read from the
    provider's maps and sorted, never written by hand.

    :raises ConfigurationError: on the first route that names nothing.
    """
    for task_type in (*policy.task_types(), None):
        if default_route_model(policy, task_type) == UNDECLARED_MODEL:
            raise ConfigurationError(_names_nothing(policy, task_type))


def _names_nothing(policy: RoutePolicy, task_type: str | None) -> str:
    profile = policy.route_for(task_type).profile
    if task_type is None:
        where = "ELA_MODEL_DEFAULT_ROUTE cannot be used: the default route"
    else:
        where = f"ELA_MODEL_ROUTES cannot be used: the route of task type {task_type!r}"
    return (
        f"{where} names the profile {profile!r}, which no model answers. "
        f"The profiles are {', '.join(sorted(PROFILES))}; "
        f"the model ids are {', '.join(sorted(MODELS))}."
    )
