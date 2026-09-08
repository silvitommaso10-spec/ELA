"""The list of what v0.1 simplifies lives in ``docs/milestones/M9.4.md`` (decisione 7a).

One list, and everything else points at it: a second file would be a second thing to keep in step
by hand, which is the failure mode this whole phase exists to remove. So the checks here are about
the list not falling behind the things it collects — the declared constraints of the ADRs, the
crash windows nobody repaired, the entries M9.2 still owes — and about each subsection counting
what it says it counts.

What this does **not** check is that each entry is *true*: that is M9.2's voce B1, and it is in
the list itself, which is the honest place for it.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MILESTONE = ROOT / "docs" / "milestones" / "M9.4.md"
CONTINUATIONS = (
    ROOT / "docs" / "milestones" / "M10.1.md",
    ROOT / "docs" / "milestones" / "M10.2.md",
    ROOT / "docs" / "milestones" / "M10.3.md",
)
ADRS = ROOT / "docs" / "adr"
ARCHITECTURE = ROOT / "docs" / "ARCHITECTURE.md"
CHANGELOG = ROOT / "docs" / "CHANGELOG.md"

HEADING = "### L'elenco di ciò che in v0.1 è semplificato"
NEXT = "## Cosa NON entra"
CONTINUED = "## L'elenco di ciò che è semplificato — la continuazione di M9.4"
AFTER_CONTINUED = "## Domande aperte"
DECLARED = "### Vincoli dichiarati"
BULLET = re.compile(r"^- \*\*(.+?)\*\*")
SUBSECTION = re.compile(r"^#### .*?— (?:otto ADR, )?(\d+|una|due|tre|otto|nove) voc[ei]$")
WINDOW = re.compile(r"\*\*Finestra (\d+[a-c]?):")
WORDS = {"una": 1, "due": 2, "tre": 3, "otto": 8, "nove": 9}


def section() -> str:
    text = MILESTONE.read_text(encoding="utf-8")
    return text[text.index(HEADING) : text.index(NEXT)]


def continuation() -> str:
    """The same list, continued by every milestone after v0.1 (M10.1, M10.2, …).

    ``M9.4.md`` is a document of v0.1 and its counts are v0.1's: it is continued, never rewritten
    — the shape ADR 0025 and ADR 0028 already use to extend the tables of ADR 0023 and ADR 0024.
    A milestone that declares constraints adds a section of its own here rather than editing the
    previous one, so the continuations are read as a **list** and not as one file: the day M10.3
    declares something, the failure is "add your section", not "somebody rewrote M10.1".

    What must stay true is that no ADR declares a constraint that appears in none of them.
    """
    found = []
    for path in CONTINUATIONS:
        text = path.read_text(encoding="utf-8")
        start = text.index(CONTINUED)
        found.append(text[start : text.index(AFTER_CONTINUED, start)])
    return "".join(found)


def subsections() -> list[tuple[int, list[str]]]:
    """Each ``####`` subsection: how many entries it claims, and the entries it has."""
    found: list[tuple[int, list[str]]] = []
    for block in section().split("\n#### ")[1:]:
        heading = "#### " + block.splitlines()[0]
        claimed = SUBSECTION.match(heading)
        assert claimed is not None, f"a subsection must say how many entries it has: {heading}"
        number = claimed.group(1)
        entries = [m.group(1) for line in block.splitlines() if (m := BULLET.match(line))]
        found.append((WORDS.get(number, 0) or int(number), entries))
    assert found, "the list must have subsections"
    return found


def declared_constraints() -> dict[str, str]:
    """Every bullet of every "Vincoli dichiarati" section of every ADR -> the ADR number."""
    found: dict[str, str] = {}
    for path in sorted(ADRS.glob("0*.md")):
        text = path.read_text(encoding="utf-8")
        if DECLARED not in text:
            continue
        block = re.split(r"\n#+ ", text.split(DECLARED, 1)[1])[0]
        for line in block.splitlines():
            if (bullet := BULLET.match(line)) is not None:
                found[bullet.group(1)] = path.stem[:4]
    assert found, "some ADR must declare constraints, or this test is vacuous"
    return found


def test_every_subsection_counts_what_it_says_it_counts() -> None:
    for claimed, entries in subsections():
        assert claimed == len(entries), (claimed, entries)


def test_the_whole_list_is_the_sum_of_its_parts() -> None:
    total = sum(claimed for claimed, _ in subsections())
    assert total == 66
    assert "Sessantasei voci" in section()


def test_every_constraint_an_adr_declares_is_in_the_list() -> None:
    """The closed world that matters: ADR 0028 could not be born already outside the list.

    Decisione 10a — the sections are found on the filesystem, not read off a list of seven ADRs,
    which is what the proposal said before ADR 0027 was written and made it eight. ADR 0028 made
    it nine, ADR 0029 ten and ADR 0030 eleven, each landing in a continuation rather than in
    v0.1's own counts.
    """
    text = section() + continuation()
    missing = {
        title: number
        for title, number in declared_constraints().items()
        if f"- **{title}** (ADR {number})" not in text
    }
    assert not missing, missing
    assert len(declared_constraints()) == 70


def test_the_list_names_the_eleven_adrs_that_declare_constraints() -> None:
    assert set(declared_constraints().values()) == {f"00{n}" for n in range(20, 31)}


def test_every_crash_window_nobody_repaired_is_named_or_declared_harmless() -> None:
    """Derived from ADR 0015 §8, not transcribed: the two harmless rows are named as such."""
    from tests.docs.test_adr_recovery import ADR_PATH, documented_windows, repaired_windows

    text = ADR_PATH.read_text(encoding="utf-8")
    unrepaired = set(documented_windows(text)) - repaired_windows(text)
    named = set(WINDOW.findall(section()))
    harmless = {"0", "2"}

    assert named | harmless == unrepaired, (named, unrepaired)
    assert not (named & harmless)
    assert "la 0 non scrive nulla e la 2 non lascia nessun buco" in section()


def test_every_entry_m92_still_owes_is_in_the_list() -> None:
    owed = {"A3", "A4", "B1", "B2", "B3", "C2", "C6", "E1", "G4"}
    text = section()
    assert all(f"**{entry} —" in text for entry in owed), owed


def test_the_two_documents_of_the_release_point_at_the_one_list() -> None:
    """Decisione 7a: one list, and the others send the reader to it."""
    for document in (ARCHITECTURE, CHANGELOG):
        text = document.read_text(encoding="utf-8")
        assert "M9.4.md" in text, document.name
        assert "semplifica" in text, document.name
