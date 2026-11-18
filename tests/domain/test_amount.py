"""The singular is decided in one place (M13.15, ADR 0071; decision 21, answer 42)."""

from __future__ import annotations

import pytest

from ela.api.companion import counted
from ela.domain import amount, noun


@pytest.mark.parametrize(
    ("how_many", "said"), [(0, "0 uses"), (1, "1 use"), (2, "2 uses"), (10, "10 uses")]
)
def test_one_is_singular_and_every_other_number_plural(how_many: int, said: str) -> None:
    assert amount(how_many, "use", "uses") == said
    assert noun(how_many, "use", "uses") == said.split(" ", 1)[1]


def test_the_companion_asks_the_same_decision() -> None:
    assert counted(1, "un uso", "usi") == "un uso"
    assert counted(2, "un uso", "usi") == "2 usi"
    assert counted(0, "un uso", "usi") == ""
