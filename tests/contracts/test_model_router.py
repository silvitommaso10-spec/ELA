"""Contract of ``ModelRouterPort`` (spec §25; ADR 0022): a route out, no call made.

Every implementation is built by ``implementations.py`` over the same one provider, ``fake``, so
the contract can say where a call goes without knowing whose table decided it.

What every router promises is here: an answer that names a provider and a profile, a hint that
wins over the table, and a decision taken **without calling anybody**. What a *policy* decides —
which task types exist, when a provider is skipped — is not part of the port and is tested
against the real one in ``tests/routing/``: a fake with a table of its own would be a second
policy, and the port would then promise something no implementation could keep.
"""

from __future__ import annotations

import pytest

from ela.domain import ModelRoute
from ela.ports import ModelRouterPort

PROVIDER = "fake"


@pytest.mark.parametrize("task_type", [None, "coding", "routine"])
def test_a_route_names_a_provider_and_a_profile(
    model_router: ModelRouterPort, task_type: str | None
) -> None:
    route = model_router.route(task_type, None)

    assert isinstance(route, ModelRoute)
    assert route.provider == PROVIDER
    assert route.profile != ""
    assert route.task_type == task_type


def test_an_explicit_hint_is_the_profile(model_router: ModelRouterPort) -> None:
    """ADR 0022 §3: whoever wrote a hint has chosen; the table fills the silence of whoever did
    not. The provider is still the task type's — a hint names a profile, not a vendor."""
    routed = model_router.route("coding", "cheap")

    assert routed.profile == "cheap"
    assert routed.provider == PROVIDER


def test_a_blank_hint_is_no_hint(model_router: ModelRouterPort) -> None:
    """The way a blank API key is no key (ADR 0020 §3): an empty string names no profile."""
    assert model_router.route("coding", "") == model_router.route("coding", None)


def test_routing_twice_answers_the_same(model_router: ModelRouterPort) -> None:
    """A router keeps no state between two calls: it is what lets the verifier recompute the
    route of a run that already happened (ADR 0022 §10)."""
    assert model_router.route("analysis", None) == model_router.route("analysis", None)


def test_the_route_is_frozen(model_router: ModelRouterPort) -> None:
    route = model_router.route(None, None)
    with pytest.raises(Exception, match="frozen|immutable"):
        route.provider = "somebody-else"  # type: ignore[misc]
