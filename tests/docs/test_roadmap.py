"""``docs/ROADMAP.md`` is the one place the order of the milestones lives (2026-11-13).

The order itself is a decision of Tommaso's, and no line of the repository holds it. What is held
here is that the roadmap cannot say something the milestone documents deny. The world is closed
four ways (the first three are decision 5 of ``docs-roadmap``):

- every milestone document that is still a ``Proposta`` is an entry of the roadmap **exactly
  once** — in a stage (*tappa*) or outside the queue — and no entry is written twice;
- **the state written beside an entry is the state of its document**, read with the one
  definition ``docs/STATO.md`` and the changelog read it with (``scripts/generate_stato.py``), and
  so is the title;
- **every milestone id the roadmap names has a document or is reserved, never both**, and every
  reserved number sits in a stage;
- **every document still a** ``Proposta`` **has an «Ordine» entry, and that entry points here**
  (decision 6 of ``m9.5-la-pulizia-della-suite``, 2026-11-14): the entry is read whole, with its
  continuation lines, so that a sentence of order left in a document always says where the order
  really lives.

**Why the world starts from the proposals, and not from every document.** The milestones done
before 2026-11-13 are in no stage — the first stage holds M13.14, the last one done, and nothing
before it — so «every milestone with a document» is read as every one still to do when the roadmap
was born, plus every one registered after. An entry already done that somebody deletes from its
stage is therefore not seen here, and the roadmap says so itself, in «Che cosa il test non tiene».

Each check is a function of a text and of the documents, so that its negative case runs on a
roadmap built here rather than on the one of the day.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Final

import pytest

ROOT = Path(__file__).resolve().parents[2]
ROADMAP = ROOT / "docs" / "ROADMAP.md"
SPEC = ROOT / "docs" / "spec" / "ELA_spec.md"
SCRIPT = ROOT / "scripts" / "generate_stato.py"

RESERVED: Final = "riservata"
"""The word beside a number that has no document: lowercase, as no state of a document is."""
STAGES: Final = "## Le tappe"
OUTSIDE: Final = "## Fuori dalla fila"
RESERVATIONS: Final = "## Riservate"
PARTS_WITH_ENTRIES: Final = (STAGES, OUTSIDE)

MILESTONE_ID = re.compile(r"\bM\d+\.\d+[a-z]?\b")
ENTRY_START: Final = "- `M"
ENTRY = re.compile(r"^- `(M\d+\.\d+[a-z]?)` — (\S+) — (.+)$")
STAGE = re.compile(r"^### Tappa (\d+) — .+$")
ROW = re.compile(r"^\| `(M\d+\.\d+[a-z]?)` \| (.+?) \| .+? \| (.+?) \|$")
SECTION = re.compile(r"§(\d+)")
ORDER: Final = "- **Ordine:**"
"""The head entry of a milestone document that says where it sits."""
CONTINUATION: Final = "  "
"""A line of the same entry: the head's bullets wrap with two spaces."""
TO_THE_ROADMAP: Final = "](../ROADMAP.md)"
"""The link a milestone document writes to the roadmap, from ``docs/milestones/``."""
SPEC_HEADING = re.compile(r"^## (\d+)\. ", re.MULTILINE)


@dataclass(frozen=True)
class Entry:
    """One line of a stage, or of the queue's outside: the id, the word beside it, the title."""

    identifier: str
    state: str
    title: str
    stage: int | None
    """The number of the stage it sits in; ``None`` outside the queue."""


@dataclass(frozen=True)
class Reservation:
    """One row of «Riservate»: a number with no document yet."""

    identifier: str
    title: str
    sections: tuple[int, ...]


@dataclass(frozen=True)
class Document:
    """What the roadmap repeats of a milestone document: its state and its title."""

    state: str
    title: str


# ----------------------------------------------------------------------------------------
# Reading the roadmap
# ----------------------------------------------------------------------------------------


def part(text: str, heading: str) -> str:
    """The body of the ``## `` part opened by ``heading``, up to the next one; empty if absent."""
    if f"\n{heading}\n" not in f"\n{text}":
        return ""
    body = f"\n{text}".split(f"\n{heading}\n", 1)[1]
    return body.split("\n## ", 1)[0]


def entries(text: str) -> list[Entry]:
    """Every well-formed entry of the stages and of the outside, with the stage it sits in."""
    found: list[Entry] = []
    for heading in PARTS_WITH_ENTRIES:
        stage: int | None = None
        for line in part(text, heading).splitlines():
            if (opened := STAGE.match(line)) is not None:
                stage = int(opened.group(1))
            elif (entry := ENTRY.match(line)) is not None:
                identifier, state, title = entry.groups()
                found.append(Entry(identifier, state, title, stage if heading == STAGES else None))
    return found


def malformed(text: str) -> list[str]:
    """The lines shaped like an entry that the reading above would not count.

    An entry the grammar does not match, or one written outside the two parts that hold entries,
    would leave the closed world without a sound: it is read neither as present nor as absent.
    """
    inside = {line for heading in PARTS_WITH_ENTRIES for line in part(text, heading).splitlines()}
    return [
        line
        for line in text.splitlines()
        if line.startswith(ENTRY_START) and (ENTRY.match(line) is None or line not in inside)
    ]


def stages(text: str) -> list[int]:
    """The numbers of the stages, in the order they are written."""
    return [
        int(opened.group(1))
        for line in part(text, STAGES).splitlines()
        if (opened := STAGE.match(line)) is not None
    ]


def reservations(text: str) -> list[Reservation]:
    """The rows of «Riservate», in the order they are written."""
    return [
        Reservation(
            identifier=row.group(1),
            title=row.group(2),
            sections=tuple(int(number) for number in SECTION.findall(row.group(3))),
        )
        for line in part(text, RESERVATIONS).splitlines()
        if (row := ROW.match(line)) is not None
    ]


def mentioned(text: str) -> set[str]:
    """Every milestone id the roadmap names, anywhere: an entry, a row, or a sentence."""
    return set(MILESTONE_ID.findall(text))


# ----------------------------------------------------------------------------------------
# The checks
# ----------------------------------------------------------------------------------------


def missing(found: Iterable[Entry], documents: Mapping[str, Document], proposed: str) -> set[str]:
    """The proposals with a document that are not an entry anywhere."""
    listed = {entry.identifier for entry in found}
    return {name for name, document in documents.items() if document.state == proposed} - listed


def repeated(found: Iterable[Entry], rows: Iterable[Reservation]) -> set[str]:
    """The ids written as two entries, or as two rows of «Riservate»."""
    entry_counts = Counter(entry.identifier for entry in found)
    row_counts = Counter(row.identifier for row in rows)
    return {name for counts in (entry_counts, row_counts) for name, n in counts.items() if n > 1}


def wrong_beside(
    found: Iterable[Entry], documents: Mapping[str, Document], rows: Iterable[Reservation]
) -> dict[str, tuple[tuple[str, str], tuple[str, str]]]:
    """``id -> (written, expected)`` for every entry whose state or title is not its source's.

    The source of a documented id is its document; of a reserved one, its row and the word
    :data:`RESERVED`. An id that is neither has no expected value: :func:`unaccounted` reports it.
    """
    reserved = {row.identifier: row for row in rows}
    wrong: dict[str, tuple[tuple[str, str], tuple[str, str]]] = {}
    for entry in found:
        if entry.identifier in documents:
            document = documents[entry.identifier]
            expected = (document.state, document.title)
        elif entry.identifier in reserved:
            expected = (RESERVED, reserved[entry.identifier].title)
        else:
            continue
        if (entry.state, entry.title) != expected:
            wrong[entry.identifier] = ((entry.state, entry.title), expected)
    return wrong


def unaccounted(
    names: Iterable[str], documents: Mapping[str, Document], rows: Iterable[Reservation]
) -> set[str]:
    """The ids the roadmap names that have neither a document nor a row of «Riservate»."""
    return set(names) - set(documents) - {row.identifier for row in rows}


def both(documents: Mapping[str, Document], rows: Iterable[Reservation]) -> set[str]:
    """The reserved numbers that already have a document: a number never sits in the two places."""
    return {row.identifier for row in rows} & set(documents)


def unplaced(found: Iterable[Entry], rows: Iterable[Reservation]) -> set[str]:
    """The reserved numbers that are not an entry of a stage."""
    in_a_stage = {entry.identifier for entry in found if entry.stage is not None}
    return {row.identifier for row in rows} - in_a_stage


def order_entry(text: str) -> str | None:
    """The «Ordine» entry of a milestone document, whole: its line and its continuation lines.

    ``None`` when the document has none. Only the first is read: the head has one.
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(ORDER):
            kept = [line]
            for following in lines[index + 1 :]:
                if not following.startswith(CONTINUATION):
                    break
                kept.append(following)
            return "\n".join(kept)
    return None


def not_pointing_here(texts: Mapping[str, str]) -> set[str]:
    """The documents (``id -> text``) with no «Ordine» entry, or one that does not link here."""
    return {
        name
        for name, text in texts.items()
        if (entry := order_entry(text)) is None or TO_THE_ROADMAP not in entry
    }


def numbered_without_gaps(numbers: list[int]) -> bool:
    """Stages are numbered 1, 2, 3… in the order they are written, and no number is skipped."""
    return bool(numbers) and numbers == list(range(1, len(numbers) + 1))


def unknown_sections(rows: Iterable[Reservation], spec: str) -> dict[str, tuple[int, ...]]:
    """``id -> sections`` for every row citing a section the spec does not have, or none at all."""
    headings = {int(number) for number in SPEC_HEADING.findall(spec)}
    return {
        row.identifier: row.sections
        for row in rows
        if not row.sections or not set(row.sections) <= headings
    }


# ----------------------------------------------------------------------------------------
# The roadmap of the day
# ----------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    """The generator of STATO: a state is read here with the definition STATO reads it with."""
    spec = importlib.util.spec_from_file_location("generate_stato_roadmap", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before it runs: its dataclasses resolve their annotations through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def documents(generator: ModuleType) -> dict[str, Document]:
    return {m.identifier: Document(m.state, m.title) for m in generator.milestones(ROOT)}


def roadmap() -> str:
    return ROADMAP.read_text(encoding="utf-8")


def test_the_roadmap_has_its_parts_and_they_are_not_empty() -> None:
    """The checks below are vacuous on a roadmap with no entries or no reservations."""
    text = roadmap()

    assert entries(text) and reservations(text) and stages(text)
    assert all(part(text, heading) for heading in (*PARTS_WITH_ENTRIES, RESERVATIONS))


def test_every_line_shaped_like_an_entry_is_read_as_one() -> None:
    assert malformed(roadmap()) == []


def test_every_proposal_is_an_entry_exactly_once(
    generator: ModuleType, documents: dict[str, Document]
) -> None:
    text = roadmap()
    found = entries(text)

    assert missing(found, documents, generator.PROPOSED) == set()
    assert repeated(found, reservations(text)) == set()


def test_beside_every_entry_are_the_state_and_the_title_of_its_source(
    documents: dict[str, Document],
) -> None:
    text = roadmap()

    assert wrong_beside(entries(text), documents, reservations(text)) == {}


def test_every_id_has_a_document_or_is_reserved_never_both(documents: dict[str, Document]) -> None:
    text = roadmap()
    rows = reservations(text)

    assert unaccounted(mentioned(text), documents, rows) == set()
    assert both(documents, rows) == set()
    assert unplaced(entries(text), rows) == set()


def test_every_proposal_s_order_entry_points_to_the_roadmap(
    generator: ModuleType, documents: dict[str, Document]
) -> None:
    proposals = {
        name: (ROOT / "docs" / "milestones" / f"{name}.md").read_text(encoding="utf-8")
        for name, document in documents.items()
        if document.state == generator.PROPOSED
    }

    assert proposals
    assert not_pointing_here(proposals) == set()


def test_the_stages_are_numbered_from_one_without_gaps() -> None:
    assert numbered_without_gaps(stages(roadmap()))


def test_every_reserved_number_cites_sections_the_spec_has() -> None:
    assert unknown_sections(reservations(roadmap()), SPEC.read_text(encoding="utf-8")) == {}


# ----------------------------------------------------------------------------------------
# The negative cases, on a roadmap built here
# ----------------------------------------------------------------------------------------

BUILT: Final = """# La roadmap

## Le tappe

### Tappa 1 — Una

- `M1.1` — Proposta — Il primo
- `M1.1` — Proposta — Il primo
- `M1.3` — Proposta — Il terzo
- `M1.4` — riservata — Un titolo diverso

### Tappa 3 — Un buco prima

- `M1.5` — Implementata — Il quinto
- `M1.6` Proposta Il sesto
- In una frase, `M42.1`, che nessuno ha scritto.

## Fuori dalla fila

- `M1.7` — riservata — Fuori

## Riservate

| Numero | Titolo | Che cosa porta | Spec |
|---|---|---|---|
| `M1.4` | Il quarto | Una riga. | §1, §99 |
| `M1.5` | Il quinto | Ha già un documento. | §1 |
| `M1.7` | Fuori | Fuori dalla fila. | §1 |
| `M1.8` | Nessuna tappa | Non è una voce. | nessuna |
- `M1.9` — Proposta — Una voce nella parte sbagliata
"""

BUILT_DOCUMENTS: Final = {
    "M1.1": Document("Proposta", "Il primo"),
    "M1.2": Document("Proposta", "Il secondo"),
    "M1.3": Document("Implementata", "Il terzo"),
    "M1.5": Document("Implementata", "Il quinto"),
    "M1.6": Document("Proposta", "Il sesto"),
    "M1.9": Document("Proposta", "Una voce nella parte sbagliata"),
    "M0.1": Document("Implementata", "Fatta prima della roadmap"),
}

SPEC_BUILT: Final = "# Spec\n\n## 1. Una\n\n## 2. Due\n"


def test_a_proposal_left_out_and_an_entry_written_twice_are_seen() -> None:
    """M1.2 is nowhere, M1.6 and M1.9 are not read as entries; a done one left out is not asked."""
    found = entries(BUILT)

    assert missing(found, BUILT_DOCUMENTS, "Proposta") == {"M1.2", "M1.6", "M1.9"}
    assert repeated(found, reservations(BUILT)) == {"M1.1"}
    assert "M0.1" not in missing(found, BUILT_DOCUMENTS, "Proposta")


def test_a_row_written_twice_is_seen() -> None:
    rows = [Reservation("M2.1", "Uno", (1,)), Reservation("M2.1", "Uno", (1,))]

    assert repeated([], rows) == {"M2.1"}


def test_an_entry_that_is_not_read_is_seen() -> None:
    """Without the grammar, M1.6 and M1.9 would be neither present nor missing."""
    assert malformed(BUILT) == [
        "- `M1.6` Proposta Il sesto",
        "- `M1.9` — Proposta — Una voce nella parte sbagliata",
    ]


def test_a_state_or_a_title_that_is_not_its_source_s_is_seen() -> None:
    """M1.3 says Proposta and its document Implementata; M1.4 is reserved under another title."""
    wrong = wrong_beside(entries(BUILT), BUILT_DOCUMENTS, reservations(BUILT))

    assert wrong == {
        "M1.3": (("Proposta", "Il terzo"), ("Implementata", "Il terzo")),
        "M1.4": (("riservata", "Un titolo diverso"), ("riservata", "Il quarto")),
    }


def test_a_reserved_number_written_with_a_state_is_seen() -> None:
    rows = [Reservation("M2.1", "Uno", (1,))]
    found = [Entry("M2.1", "Proposta", "Uno", 1)]

    assert wrong_beside(found, {}, rows) == {"M2.1": (("Proposta", "Uno"), ("riservata", "Uno"))}


def test_an_id_without_a_source_one_with_two_and_a_reservation_off_the_stages_are_seen() -> None:
    """M42.1 is only a sentence; M1.5 is reserved and documented; M1.7 is outside, M1.8 nowhere."""
    rows = reservations(BUILT)

    assert unaccounted(mentioned(BUILT), BUILT_DOCUMENTS, rows) == {"M42.1"}
    assert both(BUILT_DOCUMENTS, rows) == {"M1.5"}
    assert unplaced(entries(BUILT), rows) == {"M1.7", "M1.8"}


def test_a_stage_skipped_or_a_count_that_does_not_start_at_one_is_seen() -> None:
    assert stages(BUILT) == [1, 3]
    assert not numbered_without_gaps([1, 3])
    assert not numbered_without_gaps([2, 3])
    assert not numbered_without_gaps([2, 1])
    assert not numbered_without_gaps([])
    assert numbered_without_gaps([1, 2, 3])


def test_a_section_the_spec_does_not_have_or_no_section_at_all_is_seen() -> None:
    assert unknown_sections(reservations(BUILT), SPEC_BUILT) == {"M1.4": (1, 99), "M1.8": ()}


ORDER_BUILT: Final = {
    "M1.1": (
        "# M1.1 — Il primo\n\n- **Stato:** **Proposta**.\n"
        "- **Ordine:** **dopo M1.0**, come diceva la fila.\n"
        "  ***Dal 2026-11-13 l'ordine vive in [`docs/ROADMAP.md`](../ROADMAP.md)***.\n"
        "\n## Obiettivo\n"
    ),
    "M1.2": "# M1.2 — Il secondo\n\n- **Stato:** **Proposta**.\n\n## Obiettivo\n",
    "M1.3": (
        "# M1.3 — Il terzo\n\n- **Stato:** **Proposta**.\n"
        "- **Ordine:** **non deciso.**\n  Lo decide Tommaso.\n\n## Obiettivo\n"
    ),
    "M1.4": (
        "# M1.4 — Il quarto\n\n- **Stato:** **Proposta**.\n"
        "- **Ordine:** **non deciso.**\n- **ADR:** nessuno.\n\n"
        "Altrove nel testo, [`docs/ROADMAP.md`](../ROADMAP.md), che non è la riga «Ordine».\n"
    ),
    "M1.5": (
        "# M1.5 — Il quinto\n\n- **Stato:** **Proposta**.\n"
        "- **Ordine:** l'ordine vive in [`docs/ROADMAP.md`](../ROADMAP.md).\n"
    ),
    "M1.6": (
        "# M1.6 — Il sesto\n\n- **Stato:** **Proposta**.\n\n"
        "La riga **Ordine:** non c'è; [`docs/ROADMAP.md`](../ROADMAP.md) sì.\n"
    ),
}


def test_an_order_entry_missing_or_not_pointing_to_the_roadmap_is_seen() -> None:
    """M1.2 has none; M1.3 has no link; M1.4 links in another paragraph; M1.6 only in prose.

    M1.1 links on a continuation line and M1.5 on the first: both are read as pointing here.
    """
    assert not_pointing_here(ORDER_BUILT) == {"M1.2", "M1.3", "M1.4", "M1.6"}
    assert order_entry(ORDER_BUILT["M1.4"]) == "- **Ordine:** **non deciso.**"
