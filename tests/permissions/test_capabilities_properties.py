"""Properties of the registry over random catalogues (ADR 0010 §1–§2).

A registry built from valid specifications reads back exactly what it was given, in order;
one HIGH or CRITICAL specification anywhere in the input means no registry at all.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ela.domain import CapabilityId, CapabilitySpec, RiskLevel
from ela.permissions import MAX_RISK, CapabilityRegistry, RiskNotAllowedError
from tests.domain.examples import NOW

ADMITTED = tuple(level for level in RiskLevel if level <= MAX_RISK)
REFUSED = tuple(level for level in RiskLevel if level > MAX_RISK)

names = st.from_regex(r"[a-z][a-z0-9_]{0,8}", fullmatch=True)
capability_ids = st.tuples(names, names).map(lambda pair: CapabilityId(".".join(pair)))
scope_entries = st.lists(names, min_size=1, max_size=3).map("/".join)


def _spec(capability_id: CapabilityId, risk: RiskLevel, scoped: bool, entry: str) -> CapabilitySpec:
    return CapabilitySpec(
        id=capability_id,
        created_at=NOW,
        description="generated",
        risk=risk,
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        scope=(entry,) if scoped else (),
        scoped_arguments=("path",) if scoped else (),
        requires_authorization=False,
    )


valid_specs = st.builds(
    _spec,
    capability_ids,
    st.sampled_from(ADMITTED),
    st.booleans(),
    scope_entries,
)


def catalogues() -> st.SearchStrategy[list[CapabilitySpec]]:
    return st.lists(valid_specs, max_size=8, unique_by=lambda s: s.id)


@given(catalogues())
@settings(max_examples=200, deadline=None)
def test_a_valid_catalogue_reads_back_exactly(specs: list[CapabilitySpec]) -> None:
    registry = CapabilityRegistry(specs)
    assert registry.specs() == tuple(specs)
    for spec in specs:
        assert registry.get(spec.id) == spec


@given(catalogues(), st.sampled_from(REFUSED), st.data())
@settings(max_examples=200, deadline=None)
def test_one_refused_risk_anywhere_means_no_registry(
    specs: list[CapabilitySpec], risk: RiskLevel, data: st.DataObject
) -> None:
    position = data.draw(st.integers(min_value=0, max_value=len(specs)))
    intruder = _spec(CapabilityId("intruder.capability"), risk, False, "x")
    with_intruder = [*specs[:position], intruder, *specs[position:]]
    with pytest.raises(RiskNotAllowedError) as info:
        CapabilityRegistry(with_intruder)
    assert info.value.capability_id == intruder.id
    assert info.value.risk is risk
