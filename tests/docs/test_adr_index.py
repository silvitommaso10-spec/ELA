"""The index of ``docs/adr/README.md`` and the files in ``docs/adr/`` are the same list.

A hand-written list that does not know it has gone stale is exactly the shape M9.3 exists to
remove, and this one had gone stale in silence: the index stopped at ADR 0027 while three
documents — 0028, 0029 and 0030 — had been merged, and nothing in the suite could notice. An index
nobody verifies is a table of contents that describes a repository which no longer exists.

Closed in **both** directions and on the state too: a document with no row fails, a row with no
document fails, a row that links to somebody else's file fails, and a row that still says
``Accettata`` about a document that has been superseded fails. The comparison itself is a pure
function of two arguments — the documents and the rows — so every one of those failures is
exercised here instead of being waited for (ADR 0031 §3).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

ADRS = Path(__file__).resolve().parents[2] / "docs" / "adr"
INDEX = ADRS / "README.md"
ROW = re.compile(r"^\| \[(\d{4})\]\((\d{4}-[a-z0-9-]+\.md)\) \| (.+?) \| (.+?) \|$")
STATE = re.compile(r"^- \*\*Stato:\*\*\s*(.+)$", re.MULTILINE)
TEMPLATE_STATE = re.compile(r"^- \*\*Stato:\*\* (.+)$", re.MULTILINE)
WORD = re.compile(r"[A-Za-zÀ-ÿ]+")


@dataclass(frozen=True)
class Row:
    """One line of the index: the number it shows, the file it links to, the state it claims."""

    number: str
    filename: str
    title: str
    state: str


# ----------------------------------------------------------------------------------------
# The two lists, read from the tree
# ----------------------------------------------------------------------------------------


def documents() -> dict[str, str]:
    """Every ADR file, mapped to the first word of the ``Stato`` line it declares."""
    found = {
        path.name: WORD.search(state.group(1)).group(0)  # type: ignore[union-attr]
        for path in sorted(ADRS.glob("[0-9][0-9][0-9][0-9]-*.md"))
        if (state := STATE.search(path.read_text(encoding="utf-8"))) is not None
    }
    assert found, "no ADR declares a state: this test would be vacuous"
    return found


def rows() -> list[Row]:
    found = [
        Row(*match.groups())
        for line in INDEX.read_text(encoding="utf-8").splitlines()
        if (match := ROW.match(line))
    ]
    assert found, "the index has no rows: the regex or the table changed shape"
    return found


def offered_states() -> set[str]:
    """The words the template in the index itself offers, first word of each alternative."""
    template = TEMPLATE_STATE.search(INDEX.read_text(encoding="utf-8"))
    assert template is not None, "the index must keep the template that names the states"
    return {
        match.group(0)
        for alternative in template.group(1).split("|")
        if (match := WORD.search(alternative)) is not None
    }


# ----------------------------------------------------------------------------------------
# The comparison, pure, so that every way of being wrong can be shown
# ----------------------------------------------------------------------------------------


def faults(known: Mapping[str, str], listed: Sequence[Row]) -> list[str]:
    """Everything that does not line up between the documents and the index rows."""
    by_file = {row.filename: row for row in listed}
    found = [f"{name}: no row in the index" for name in known if name not in by_file]
    found += [
        f"{row.filename}: a row for a document that does not exist"
        for row in listed
        if row.filename not in known
    ]
    found += [
        f"{row.number}: the row links to {row.filename}"
        for row in listed
        if not row.filename.startswith(row.number)
    ]
    found += [
        f"{row.number}: listed twice"
        for row in listed
        if [other.number for other in listed].count(row.number) > 1
    ]
    found += [
        f"{row.filename}: the index says {row.state}, the document says {known[row.filename]}"
        for row in listed
        if row.filename in known and row.state != known[row.filename]
    ]
    numbers = [row.number for row in listed]
    if numbers != sorted(numbers):
        found.append("the rows are not in ascending order")
    return sorted(found)


# ----------------------------------------------------------------------------------------
# The tree as it is
# ----------------------------------------------------------------------------------------


def test_the_index_lists_every_adr_and_only_those() -> None:
    assert faults(documents(), rows()) == []


def test_every_state_is_one_of_the_words_the_template_offers() -> None:
    """The fifth word somebody invents is caught here rather than tolerated (test_changelog)."""
    offered = offered_states()

    assert offered == {"Proposta", "Accettata", "Deprecata", "Sostituita"}
    assert {state for state in documents().values() if state not in offered} == set()


def test_every_row_says_something_about_its_document() -> None:
    """A title column is a summary, never the document's own heading — but never empty either."""
    assert all(row.title.strip() for row in rows())


# ----------------------------------------------------------------------------------------
# The negative cases: one per way of being wrong
# ----------------------------------------------------------------------------------------

KNOWN = {"0001-first.md": "Accettata", "0002-second.md": "Accettata"}
LISTED = [
    Row("0001", "0001-first.md", "Il primo", "Accettata"),
    Row("0002", "0002-second.md", "Il secondo", "Accettata"),
]


def test_the_agreeing_pair_reports_nothing() -> None:
    """Without this the negative cases below could all pass because the function always speaks."""
    assert faults(KNOWN, LISTED) == []


def test_a_document_with_no_row_is_reported() -> None:
    """The failure this file was written for: three ADRs merged, the index still at 0027."""
    assert faults({**KNOWN, "0003-third.md": "Accettata"}, LISTED) == [
        "0003-third.md: no row in the index"
    ]


def test_a_row_with_no_document_is_reported() -> None:
    ghost = [*LISTED, Row("0003", "0003-third.md", "Il terzo", "Accettata")]

    assert faults(KNOWN, ghost) == ["0003-third.md: a row for a document that does not exist"]


def test_a_row_that_links_to_somebody_elses_file_is_reported() -> None:
    wrong = [Row("0001", "0002-second.md", "Il primo", "Accettata"), LISTED[1]]

    assert faults(KNOWN, wrong) == [
        "0001-first.md: no row in the index",
        "0001: the row links to 0002-second.md",
    ]


def test_a_row_that_kept_a_state_the_document_changed_is_reported() -> None:
    """An ADR superseded by a later one, and an index that still calls it the current answer."""
    superseded = {**KNOWN, "0001-first.md": "Sostituita"}

    assert faults(superseded, LISTED) == [
        "0001-first.md: the index says Accettata, the document says Sostituita"
    ]


def test_rows_out_of_order_are_reported() -> None:
    assert faults(KNOWN, list(reversed(LISTED))) == ["the rows are not in ascending order"]


@pytest.mark.parametrize(
    ("line", "is_a_row"),
    [
        ("| [0031](0031-runner-parity.md) | Titolo | Accettata |", True),
        ("| 0031 | Titolo | Accettata |", False),  # a number that links nowhere
        ("| [0031](0031-runner-parity.md) | Titolo |", False),  # no state column
        ("| [0031](../elsewhere.md) | Titolo | Accettata |", False),  # a link out of the folder
        ("|----|--------|-------|", False),  # the separator of the table itself
    ],
)
def test_only_a_real_row_is_counted_as_one(line: str, is_a_row: bool) -> None:
    """The positive case first: a regex matching nothing would make every check above vacuous."""
    assert bool(ROW.match(line)) is is_a_row
