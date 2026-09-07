"""``docs/GETTING_STARTED.md`` and the code say the same thing (M8.3, ADR 0025 §8).

Two drifts, both found by the user's first hand-run of the guide and neither by a review:

* a **placeholder** written as ``<id>`` and explained nowhere, so it was pasted with the angle
  brackets on. The guide now declares the convention once, in a table; this module keeps that
  table and the guide's code blocks the same set, so a new placeholder cannot arrive unexplained.
* a **risk level** printed in prose — "scrivere è MEDIUM (§29)" — three sections above a sample
  of the audit trail that printed ``LOW``. Wherever the guide names a capability and a risk on
  the same line, this module reads the catalogue and compares.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ela.domain import RiskLevel
from ela.permissions import catalogue_v01

GUIDE = Path(__file__).resolve().parents[2] / "docs" / "GETTING_STARTED.md"
BLOCK = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
PLACEHOLDER = re.compile(r"<[^<>\s][^<>]*>")
LEGEND_ROW = re.compile(r"^\| `(<[^`]+>)` \| ([^|]+) \| ([^|]+) \|$")
RISKS = "|".join(level.value for level in RiskLevel)


def guide() -> str:
    return GUIDE.read_text(encoding="utf-8")


def declared() -> dict[str, str]:
    """placeholder → what the legend says goes there."""
    rows = {
        match.group(1): match.group(2).strip()
        for line in guide().splitlines()
        if (match := LEGEND_ROW.match(line)) is not None
    }
    assert rows, "the guide must open with the table of its placeholders"
    return rows


def used(text: str) -> set[str]:
    """Every ``<…>`` inside a fenced code block: what a reader actually types."""
    return {found for block in BLOCK.findall(text) for found in PLACEHOLDER.findall(block)}


# ----------------------------------------------------------------------------------------
# The placeholders
# ----------------------------------------------------------------------------------------


def test_every_placeholder_a_reader_would_type_is_explained() -> None:
    assert used(guide()) <= set(declared())


def test_the_legend_explains_nothing_the_guide_stopped_using() -> None:
    """A legend that outlives its placeholder teaches a convention nobody meets."""
    assert set(declared()) <= used(guide())


def test_the_convention_says_the_brackets_are_not_pasted() -> None:
    """The whole debt in one sentence: the user pasted them because nothing said not to."""
    text = guide()
    opening = text.split("## 0.", 1)[0]

    assert "segnaposto" in opening
    assert "non si incollano" in opening


def test_the_first_placeholder_is_also_shown_substituted() -> None:
    """Read once, seen once: the first command with a ``<id>`` is repeated with the real id
    printed two lines above it."""
    text = guide()
    created = re.search(r"^id +([0-9a-f-]{36})$", text, re.MULTILINE)
    assert created is not None

    first = next(block for block in BLOCK.findall(text) if "<id>" in block)
    after = text.index(first) + len(first)
    assert created.group(1) in text[after : after + 400]


def test_a_placeholder_nobody_explained_is_reported() -> None:
    """Negative case: this test is the guard, so it must fail when the guard is needed."""
    invented = guide().replace("uv run ela task run <id>", "uv run ela task run <task-id>", 1)

    assert invented != guide()
    assert not used(invented) <= set(declared())


def test_a_legend_row_that_names_nothing_is_reported() -> None:
    """The other direction: a row for a placeholder the guide does not use."""
    stale = declared() | {"<node-id>": "un nodo"}

    assert not set(stale) <= used(guide())


# ----------------------------------------------------------------------------------------
# The risk levels the guide prints
# ----------------------------------------------------------------------------------------


def test_no_risk_level_in_the_guide_contradicts_the_catalogue() -> None:
    """The debt of the first hand-run: the guide said MEDIUM where §29 says LOW.

    Every line that names a capability **and** a risk is read, prose and sample output alike:
    the guide contradicted itself across two pages, so half a check would have missed it.
    """
    catalogue = {spec.id: spec.risk.value for spec in catalogue_v01().specs()}
    checked = 0

    for line in guide().splitlines():
        for capability, risk in catalogue.items():
            if capability not in line:
                continue
            found = re.findall(rf"\b({RISKS})\b", line)
            if not found:
                continue
            checked += 1
            assert set(found) == {risk}, f"{capability} is {risk} (§29), not {found}: {line}"

    assert checked >= 3, "the guide must still show the risk of a capability somewhere"


def test_a_wrong_risk_in_the_guide_would_be_reported() -> None:
    """Negative case, on the exact sentence that was wrong until M8.3."""
    catalogue = {spec.id: spec.risk.value for spec in catalogue_v01().specs()}
    line = "il secondo scrive un file, e scrivere è MEDIUM (§29)"
    drifted = f"`workspace.write_note` {line}"

    found = re.findall(rf"\b({RISKS})\b", drifted)

    assert found == ["MEDIUM"]
    assert set(found) != {catalogue["workspace.write_note"]}


# ----------------------------------------------------------------------------------------
# The examples the guide points at
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("example", ["first-task.json", "ask-model.json"])
def test_the_guide_points_at_both_examples(example: str) -> None:
    assert example in guide()


def test_the_command_that_reads_an_output_is_in_the_guide() -> None:
    """``ela task results``: without it the model example completes and shows nothing."""
    assert "ela task results" in guide()
