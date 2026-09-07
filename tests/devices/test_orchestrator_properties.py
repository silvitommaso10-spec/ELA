"""What must hold for *every* registry and every step, not only for the tables (§17, ADR 0017).

The example tests fix the policy; these fix the shape of the answer. A placement that sometimes
chose a refused node, or that answered differently on two identical calls, would be a policy
nobody can audit — and §17 exists precisely so that "where did this run, and why" has an answer.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from ela.devices import Requirements, choose, refusals
from ela.domain import Device, PrivacyLevel, RiskLevel
from tests.domain.strategies import capability_ids, device_capability_names, devices

registries = st.lists(devices, max_size=5, unique_by=lambda device: device.id)

requirements = st.builds(
    Requirements,
    tools=st.lists(st.sampled_from(["notes", "browser", "shell"]), max_size=3).map(frozenset),
    traits=st.lists(device_capability_names, max_size=3).map(tuple),
    risk=st.sampled_from(RiskLevel),
    max_privacy=st.sampled_from(PrivacyLevel),
    unresolved=st.lists(capability_ids, max_size=2).map(tuple),
)


# ``deadline=None`` as in the other property tests: Hypothesis fails an example that takes
# longer than 200ms, and a runner under load is not a bug in the code under test.
@settings(deadline=None)
@given(nodes=registries, needed=requirements)
def test_choose_is_deterministic(nodes: list[Device], needed: Requirements) -> None:
    """Same registry, same step, same answer: no dictionary order, no clock, no randomness."""
    first, second = choose(nodes, needed), choose(nodes, needed)
    assert first == second


@settings(deadline=None)
@given(nodes=registries, needed=requirements)
def test_choose_never_returns_a_refused_node(nodes: list[Device], needed: Requirements) -> None:
    placement = choose(nodes, needed)
    if placement.device is not None:
        assert refusals(placement.device, needed) == ()


@settings(deadline=None)
@given(nodes=registries, needed=requirements)
def test_choose_waits_exactly_when_nobody_is_eligible(
    nodes: list[Device], needed: Requirements
) -> None:
    eligible = [device for device in nodes if not refusals(device, needed)]
    assert choose(nodes, needed).waits is (eligible == [])


@settings(deadline=None)
@given(nodes=registries, needed=requirements)
def test_the_chosen_node_scores_at_least_as_much_as_every_other_eligible_one(
    nodes: list[Device], needed: Requirements
) -> None:
    placement = choose(nodes, needed)
    if placement.device is None:
        return
    best = next(s for s in placement.scores if s.device_id == placement.device.id)
    assert all(s.points <= best.points for s in placement.scores if s.eligible)


@settings(deadline=None)
@given(nodes=registries, needed=requirements)
def test_every_node_is_judged_once_in_registration_order(
    nodes: list[Device], needed: Requirements
) -> None:
    """The audit payload is built from ``scores``: a node missing from it is a node whose
    rejection nobody can explain afterwards."""
    placement = choose(nodes, needed)
    assert [candidate.device_id for candidate in placement.scores] == [n.id for n in nodes]


@settings(deadline=None)
@given(nodes=registries, needed=requirements)
def test_a_placement_is_never_an_error(nodes: list[Device], needed: Requirements) -> None:
    """The property that makes "no node" an *attesa* and not a failure (ADR 0017 §6)."""
    placement = choose(nodes, needed)
    assert placement.waits or placement.device in nodes
