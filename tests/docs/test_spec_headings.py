"""Integrity check of docs/spec/ELA_spec.md, the converted project specification."""

import re
from pathlib import Path

SPEC_PATH = Path(__file__).resolve().parents[2] / "docs" / "spec" / "ELA_spec.md"
SECTION_COUNT = 70
HEADING = re.compile(r"^## (\d+)\. (.*)$")
# Italian function words: a title ending with one of these was cut mid-sentence by the PDF.
DANGLING_WORDS = {
    "a",
    "ad",
    "al",
    "alla",
    "alle",
    "ai",
    "agli",
    "che",
    "come",
    "con",
    "da",
    "dal",
    "dalla",
    "degli",
    "dei",
    "del",
    "della",
    "delle",
    "di",
    "e",
    "ed",
    "il",
    "in",
    "la",
    "le",
    "lo",
    "nel",
    "nella",
    "non",
    "o",
    "per",
    "su",
    "sul",
    "sulla",
    "un",
    "una",
    "gli",
    "i",
}
# Titles the PDF wrapped onto two lines: they must have been re-joined.
REJOINED_TITLES = {
    8: "ELA non deve essere sempre rumorosa",
    36: "Livello di autonomia del miglioramento",
    58: "Sicurezza come parte dell'architettura",
    65: "ELA non deve diventare incontrollabile",
}


def test_spec_has_70_numbered_sections_with_complete_titles() -> None:
    lines = SPEC_PATH.read_text(encoding="utf-8").splitlines()
    headings = [m for line in lines if (m := HEADING.match(line))]
    numbers = [int(m.group(1)) for m in headings]
    titles = {int(m.group(1)): m.group(2).strip() for m in headings}

    assert numbers == list(range(1, SECTION_COUNT + 1)), "sections must be numbered 1..70 in order"
    for number, title in titles.items():
        assert title, f"section {number} has an empty title"
        assert not title.endswith("-"), f"section {number} title ends mid-word: {title!r}"
        last_word = title.split()[-1].lower().strip("'")
        assert last_word not in DANGLING_WORDS, f"section {number} title is cut: {title!r}"
    for number, expected in REJOINED_TITLES.items():
        assert titles[number] == expected
