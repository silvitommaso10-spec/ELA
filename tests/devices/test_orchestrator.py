"""The pure half of the Device Orchestrator: who is eligible, who scores what, who wins (§17).

Two halves that never mix (ADR 0017): :func:`refusals` decides *whether* a node may be used and
:func:`score` decides *which* of the usable ones is best. The tests keep them apart — a filter
test says nothing about points, a score test starts from nodes that all pass — and the invariants
that tie them together (a refused node is never chosen, an unknown fact is never a bonus) get
tests of their own.
"""

from __future__ import annotations

import pytest

from ela.devices import (
    NETWORK_POINTS,
    PERFORMANCE_POINTS,
    POWER_POINTS,
    PRIVACY_ORDER,
    STATUS_POINTS,
    TRAIT_POINTS,
    UNGUARDED_RISK,
    WORKLOAD_POINTS,
    Refusal,
    choose,
    refusals,
    score,
)
from ela.domain import (
    DeviceAvailability,
    DeviceStatus,
    NetworkKind,
    PerformanceClass,
    PowerSource,
    PrivacyLevel,
    RiskLevel,
)
from tests.devices.nodes import needs, node, trait
from tests.domain.examples import (
    LATER,
)

GPU = "gpu.cuda"
NOTES = "workspace_notes"


# ----------------------------------------------------------------------------------------
# Eligibility: the hard filters (ADR 0017 §4)
# ----------------------------------------------------------------------------------------


def test_an_available_node_that_has_what_the_step_needs_is_eligible() -> None:
    assert refusals(node("local", tools=(NOTES,)), needs(tools=[NOTES])) == ()


@pytest.mark.parametrize(
    "availability",
    [DeviceAvailability.UNREACHABLE, DeviceAvailability.OFFLINE, DeviceAvailability.UNKNOWN],
)
def test_a_node_that_has_not_reported_is_discarded(availability: DeviceAvailability) -> None:
    """The case §17 cares about first: silence is not availability (ADR 0016 §3)."""
    assert refusals(node("stale", availability=availability), needs()) == (Refusal.UNAVAILABLE,)


@pytest.mark.parametrize(
    ("privacy", "expected"),
    [
        (PrivacyLevel.LOCAL_ONLY, ()),
        (PrivacyLevel.TRUSTED, (Refusal.PRIVACY,)),
        (PrivacyLevel.CLOUD_ALLOWED, (Refusal.PRIVACY,)),
    ],
)
def test_a_local_only_step_refuses_every_node_that_may_send_data_out(
    privacy: PrivacyLevel, expected: tuple[Refusal, ...]
) -> None:
    """Privacy alta → solo device locale: the filter is the node's own declared level (§57)."""
    assert refusals(node("cloud", privacy=privacy), needs()) == expected


def test_a_more_tolerant_step_accepts_a_stricter_node() -> None:
    """The order is one-directional: a step that allows the cloud still accepts a local node."""
    for privacy in PrivacyLevel:
        assert refusals(node("n", privacy=privacy), needs(max_privacy=privacy)) == ()
    assert refusals(node("local"), needs(max_privacy=PrivacyLevel.CLOUD_ALLOWED)) == ()


def test_the_privacy_order_runs_from_local_only_to_cloud_allowed() -> None:
    assert [level for level, _ in sorted(PRIVACY_ORDER.items(), key=lambda pair: pair[1])] == [
        PrivacyLevel.LOCAL_ONLY,
        PrivacyLevel.TRUSTED,
        PrivacyLevel.CLOUD_ALLOWED,
    ]


def test_a_node_without_the_tool_is_discarded() -> None:
    assert refusals(node("bare"), needs(tools=[NOTES])) == (Refusal.MISSING_TOOL,)


def test_a_node_missing_one_of_two_tools_is_discarded() -> None:
    every = node("half", tools=(NOTES,))
    assert refusals(every, needs(tools=[NOTES, "browser"])) == (Refusal.MISSING_TOOL,)


def test_a_capability_no_tool_implements_refuses_every_node() -> None:
    """Nobody can run it, so nowhere does: the task waits instead of trying somewhere (§33)."""
    complete = node("local", tools=(NOTES,))
    assert refusals(complete, needs(unresolved=["model.complete"])) == (Refusal.UNKNOWN_CAPABILITY,)


@pytest.mark.parametrize(
    ("risk", "expected"),
    [
        (RiskLevel.SAFE, ()),
        (RiskLevel.LOW, ()),
        (RiskLevel.MEDIUM, ()),
        (RiskLevel.HIGH, (Refusal.DEGRADED,)),
        (RiskLevel.CRITICAL, (Refusal.DEGRADED,)),
    ],
)
def test_a_degraded_node_is_discarded_only_from_high_risk_up(
    risk: RiskLevel, expected: tuple[Refusal, ...]
) -> None:
    """Risk raises the bar of evidence; it never grants anything (ADR 0017 §4)."""
    assert refusals(node("sick", status=DeviceStatus.DEGRADED), needs(risk=risk)) == expected


def test_an_unobserved_status_stays_eligible_at_any_risk() -> None:
    """``UNKNOWN`` is not ``DEGRADED``: in v0.1 nobody observes ``local``, and a rule that
    refused an unobserved node would make every high-risk step impossible to run."""
    for status in (DeviceStatus.UNKNOWN, DeviceStatus.IDLE, DeviceStatus.BUSY):
        assert refusals(node("n", status=status), needs(risk=RiskLevel.CRITICAL)) == ()


def test_the_risk_threshold_is_high() -> None:
    assert UNGUARDED_RISK is RiskLevel.HIGH


def test_a_node_can_fail_every_filter_at_once() -> None:
    """The refusals are reported all together, in the declaration order of ``Refusal``."""
    hopeless = node(
        "hopeless",
        availability=DeviceAvailability.UNREACHABLE,
        privacy=PrivacyLevel.CLOUD_ALLOWED,
        status=DeviceStatus.DEGRADED,
    )
    assert refusals(hopeless, needs(tools=[NOTES], risk=RiskLevel.HIGH, unresolved=["a.b"])) == (
        Refusal.UNAVAILABLE,
        Refusal.PRIVACY,
        Refusal.UNKNOWN_CAPABILITY,
        Refusal.MISSING_TOOL,
        Refusal.DEGRADED,
    )


# ----------------------------------------------------------------------------------------
# Score: the criteria of §17 (ADR 0017 §5)
# ----------------------------------------------------------------------------------------


def test_a_node_that_declares_nothing_scores_nothing() -> None:
    judged = score(node("blank"), needs())
    assert judged.points == 0
    assert dict(judged.components) == {
        "traits": 0,
        "network": 0,
        "performance": 0,
        "power": 0,
        "workload": 0,
        "status": 0,
    }


def test_the_traits_component_is_proportional_to_what_the_node_offers() -> None:
    both = node("gpu", traits=[trait(GPU), trait("camera")])
    assert score(both, needs(traits=[GPU, "camera"])).components["traits"] == TRAIT_POINTS
    assert score(both, needs(traits=[GPU, "microphone"])).components["traits"] == TRAIT_POINTS // 2
    assert score(both, needs(traits=["microphone"])).components["traits"] == 0


def test_a_trait_the_node_reports_as_unavailable_does_not_count() -> None:
    """``DeviceCapability.available`` is the node's own word about a trait it lists."""
    broken = node("gpu", traits=[trait(GPU, available=False)])
    assert score(broken, needs(traits=[GPU])).components["traits"] == 0


def test_a_step_that_prefers_nothing_gives_nobody_trait_points() -> None:
    assert score(node("gpu", traits=[trait(GPU)]), needs()).components["traits"] == 0


@pytest.mark.parametrize("kind", list(NetworkKind))
def test_the_network_component_follows_the_table(kind: NetworkKind) -> None:
    assert score(node("n", network=kind), needs()).components["network"] == NETWORK_POINTS[kind]


@pytest.mark.parametrize("performance", list(PerformanceClass))
def test_the_performance_component_follows_the_table(performance: PerformanceClass) -> None:
    judged = score(node("n", performance=performance), needs())
    assert judged.components["performance"] == PERFORMANCE_POINTS[performance]


@pytest.mark.parametrize("power", list(PowerSource))
def test_the_power_component_follows_the_table(power: PowerSource) -> None:
    assert score(node("n", power_source=power), needs()).components["power"] == POWER_POINTS[power]


@pytest.mark.parametrize("status", list(DeviceStatus))
def test_the_status_component_follows_the_table(status: DeviceStatus) -> None:
    assert score(node("n", status=status), needs()).components["status"] == STATUS_POINTS[status]


@pytest.mark.parametrize(
    ("workload", "expected"), [(0.0, WORKLOAD_POINTS), (0.5, WORKLOAD_POINTS // 2), (1.0, 0)]
)
def test_the_workload_component_rewards_a_free_node(workload: float, expected: int) -> None:
    assert score(node("n", workload=workload), needs()).components["workload"] == expected


def test_a_node_that_does_not_report_its_workload_gets_no_points_for_it() -> None:
    """Silence is not a claim (§33): an unreported workload scores zero, not "idle"."""
    assert score(node("quiet", workload=None), needs()).components["workload"] == 0


def test_unknown_facts_score_zero_and_never_a_bonus() -> None:
    """The invariant behind every table: what nobody observed never beats what somebody did."""
    for points, unknown in (
        (NETWORK_POINTS, NetworkKind.UNKNOWN),
        (PERFORMANCE_POINTS, PerformanceClass.UNKNOWN),
        (POWER_POINTS, PowerSource.UNKNOWN),
        (STATUS_POINTS, DeviceStatus.UNKNOWN),
    ):
        assert points[unknown] == 0, unknown
        assert points[unknown] == min(value for value in points.values() if value >= 0), unknown


def test_the_points_are_the_sum_of_the_components() -> None:
    judged = score(
        node(
            "power",
            traits=[trait(GPU)],
            network=NetworkKind.LOCAL,
            performance=PerformanceClass.HIGH,
            power_source=PowerSource.AC,
            status=DeviceStatus.IDLE,
            workload=0.0,
        ),
        needs(traits=[GPU]),
    )
    assert judged.points == sum(judged.components.values())
    assert judged.points == TRAIT_POINTS + 20 + 15 + 10 + WORKLOAD_POINTS + 10


def test_a_refused_node_is_scored_too() -> None:
    """The audit log must be able to say "it would have won, but it was not answering"."""
    judged = score(
        node("gpu", availability=DeviceAvailability.UNREACHABLE, performance=PerformanceClass.HIGH),
        needs(),
    )
    assert judged.refusals == (Refusal.UNAVAILABLE,)
    assert not judged.eligible
    assert judged.points > 0


# ----------------------------------------------------------------------------------------
# The choice (ADR 0017 §5)
# ----------------------------------------------------------------------------------------


def test_the_gpu_node_wins_when_the_step_prefers_the_trait() -> None:
    """§15's example: the render goes to the Power Node because the step prefers its trait."""
    mac = node("mac", tools=(NOTES,), performance=PerformanceClass.HIGH)
    windows = node("windows", tools=(NOTES,), traits=[trait(GPU)])

    placement = choose([mac, windows], needs(tools=[NOTES], traits=[GPU]))

    assert placement.device is windows
    assert not placement.waits


def test_without_the_preference_the_other_criteria_decide() -> None:
    mac = node("mac", tools=(NOTES,), performance=PerformanceClass.HIGH)
    windows = node("windows", tools=(NOTES,), traits=[trait(GPU)])

    assert choose([mac, windows], needs(tools=[NOTES])).device is mac


def test_the_node_without_the_trait_still_runs_when_it_is_the_only_one() -> None:
    """A preference is not a requirement (§13): a one-node system runs everything it can."""
    mac = node("mac", tools=(NOTES,))
    assert choose([mac], needs(tools=[NOTES], traits=[GPU])).device is mac


def test_a_node_that_has_not_reported_is_never_chosen() -> None:
    stale = node("stale", availability=DeviceAvailability.UNREACHABLE, traits=[trait(GPU)])
    fresh = node("fresh")

    placement = choose([stale, fresh], needs(traits=[GPU]))

    assert placement.device is fresh
    assert placement.scores[0].refusals == (Refusal.UNAVAILABLE,)


def test_the_score_never_rescues_a_refused_node() -> None:
    """Filters and points are two steps, not a sum with a threshold."""
    best = node(
        "cloud",
        privacy=PrivacyLevel.CLOUD_ALLOWED,
        traits=[trait(GPU)],
        network=NetworkKind.LOCAL,
        performance=PerformanceClass.HIGH,
        power_source=PowerSource.AC,
        status=DeviceStatus.IDLE,
        workload=0.0,
    )
    modest = node("local")

    placement = choose([best, modest], needs(traits=[GPU]))

    assert placement.device is modest
    assert placement.scores[0].points > placement.scores[1].points


def test_a_local_only_step_waits_rather_than_go_to_the_cloud() -> None:
    cloud = node("cloud", privacy=PrivacyLevel.CLOUD_ALLOWED, performance=PerformanceClass.HIGH)

    placement = choose([cloud], needs())

    assert placement.device is None
    assert placement.waits
    assert "1 PRIVACY" in placement.reason


def test_the_tie_break_is_registration_order() -> None:
    first, second = node("first", tools=(NOTES,)), node("second", tools=(NOTES,))

    assert choose([first, second], needs(tools=[NOTES])).device is first
    assert choose([second, first], needs(tools=[NOTES])).device is second


def test_every_candidate_is_scored_even_the_refused_ones() -> None:
    nodes = [node("a"), node("b", privacy=PrivacyLevel.TRUSTED), node("c")]

    placement = choose(nodes, needs())

    assert [candidate.device_id for candidate in placement.scores] == [n.id for n in nodes]
    assert [candidate.eligible for candidate in placement.scores] == [True, False, True]


def test_no_eligible_node_counts_the_refusals_in_the_reason() -> None:
    nodes = [
        node("stale", availability=DeviceAvailability.UNREACHABLE),
        node("cloud", privacy=PrivacyLevel.CLOUD_ALLOWED),
        node("bare"),
    ]

    placement = choose(nodes, needs(tools=[NOTES]))

    assert placement.waits
    assert placement.reason == (
        f"no eligible node among 3: 1 UNAVAILABLE, 1 PRIVACY, 3 MISSING_TOOL ({NOTES})"
    )


def test_an_empty_registry_says_so() -> None:
    """Nothing registered is a different sentence from "everybody was refused"."""
    placement = choose([], needs())
    assert placement.waits
    assert placement.scores == ()
    assert placement.reason == "no node is registered"


def test_the_reason_of_a_choice_names_the_node_and_the_field() -> None:
    mac = node("mac", tools=(NOTES,), network=NetworkKind.LOCAL)
    cloud = node("cloud", privacy=PrivacyLevel.CLOUD_ALLOWED)

    placement = choose([mac, cloud], needs(tools=[NOTES]))

    assert placement.reason == f"mac ({mac.id}) with 20 points, 1 of 2 node(s) eligible"


# ----------------------------------------------------------------------------------------
# The reason, for every refusal there is (M6.1b dec. F)
# ----------------------------------------------------------------------------------------

REFUSED_BY = {
    Refusal.UNAVAILABLE: (
        node("stale", availability=DeviceAvailability.UNREACHABLE),
        needs(),
    ),
    Refusal.PRIVACY: (node("cloud", privacy=PrivacyLevel.CLOUD_ALLOWED), needs()),
    Refusal.UNKNOWN_CAPABILITY: (node("bare"), needs(unresolved=["core.rm_rf"])),
    Refusal.MISSING_TOOL: (node("bare"), needs(tools=[NOTES])),
    Refusal.DEGRADED: (
        node("tired", status=DeviceStatus.DEGRADED),
        needs(risk=UNGUARDED_RISK),
    ),
    Refusal.REVOKED: (node("gone", revoked_at=LATER), needs()),
    Refusal.UNVERIFIABLE: (node("far"), needs(verified_here=["workspace.write_note"])),
}
"""One node and one requirement per member of :class:`Refusal`: the smallest thing that fires it.

Written as a table keyed on the enum so the parametrisation below can iterate over ``Refusal``
itself. A member added tomorrow has no row here and fails at the door, before the assertion — the
discipline of the self-verifying lists, applied to an enum.
"""


@pytest.mark.parametrize("refusal", list(Refusal), ids=[r.value for r in Refusal])
def test_every_refusal_produces_a_reason_that_names_it(refusal: Refusal) -> None:
    """Criterion 5: a node discarded for *any* reason reaches whoever is waiting with that reason.

    Nothing had to be built for this — ``_summary`` already iterates over the whole enum — and
    that is exactly why it needs a test: what is guaranteed by nobody having thought about it is
    guaranteed until somebody does. A member added without a rendering fails here.
    """
    assert refusal in REFUSED_BY, f"{refusal.value} has no row in REFUSED_BY"
    candidate, requirements = REFUSED_BY[refusal]

    placement = choose([candidate], requirements)

    assert placement.waits
    assert refusal.value in placement.reason
    assert refusals(candidate, requirements) == (refusal,)


def test_the_reason_names_the_tool_nobody_had() -> None:
    """The one thing dec. F had to build: ``MISSING_TOOL`` alone does not say *which*.

    With seven tools on a node, "a tool is missing" is not a diagnosis and "``voice-speak-online``
    is missing" is the whole of one. The names come from where the reason is born — the
    requirements minus what the node has — which is the only place holding both halves.
    """
    placement = choose([node("bare"), node("other")], needs(tools=[NOTES, GPU]))

    assert placement.waits
    assert f"MISSING_TOOL ({GPU}, {NOTES})" in placement.reason


def test_a_tool_one_node_has_and_another_lacks_is_still_named() -> None:
    """The union, not the intersection: what is missing is missing *somewhere*."""
    placement = choose([node("half", tools=(NOTES,)), node("bare")], needs(tools=[NOTES, GPU]))

    assert placement.waits
    assert GPU in placement.reason and NOTES in placement.reason
