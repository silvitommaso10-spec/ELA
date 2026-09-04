"""RiskLevel is ordered by risk, not alphabetically (§29)."""

from __future__ import annotations

import json

import pytest

from ela.domain import RiskLevel

SPEC_ORDER = [
    RiskLevel.SAFE,
    RiskLevel.LOW,
    RiskLevel.MEDIUM,
    RiskLevel.HIGH,
    RiskLevel.CRITICAL,
]


def test_values_match_the_spec() -> None:
    assert list(RiskLevel) == SPEC_ORDER


def test_ordering_follows_the_spec() -> None:
    assert RiskLevel.SAFE < RiskLevel.LOW < RiskLevel.MEDIUM < RiskLevel.HIGH < RiskLevel.CRITICAL


def test_sorting_follows_the_spec() -> None:
    assert sorted(reversed(SPEC_ORDER)) == SPEC_ORDER


def test_ordering_is_not_alphabetical() -> None:
    """The trap this test exists for: str would order CRITICAL < HIGH < LOW < MEDIUM < SAFE."""
    alphabetical = sorted(level.value for level in RiskLevel)
    assert [level.value for level in SPEC_ORDER] != alphabetical
    assert RiskLevel.CRITICAL > RiskLevel.HIGH


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (RiskLevel.SAFE, RiskLevel.SAFE, True),
        (RiskLevel.SAFE, RiskLevel.CRITICAL, True),
        (RiskLevel.CRITICAL, RiskLevel.SAFE, False),
    ],
)
def test_le_and_ge(left: RiskLevel, right: RiskLevel, expected: bool) -> None:
    assert (left <= right) is expected
    assert (right >= left) is expected


@pytest.mark.parametrize("other", ["LOW", 2, None])
def test_comparison_with_other_types_is_rejected(other: object) -> None:
    """A silent comparison against a string would be alphabetical, so it must fail loudly."""
    for operator in ("__lt__", "__le__", "__gt__", "__ge__"):
        with pytest.raises(TypeError, match="RiskLevel"):
            getattr(RiskLevel.MEDIUM, operator)(other)


def test_equality_still_works_like_a_string() -> None:
    assert RiskLevel.MEDIUM == "MEDIUM"
    assert RiskLevel.MEDIUM != RiskLevel.HIGH


def test_severity_is_the_position_in_the_spec_order() -> None:
    assert [level.severity for level in SPEC_ORDER] == [0, 1, 2, 3, 4]


def test_serialises_as_a_string() -> None:
    assert json.dumps(RiskLevel.HIGH) == '"HIGH"'
