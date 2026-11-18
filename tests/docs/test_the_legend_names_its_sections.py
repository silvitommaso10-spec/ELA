"""The legend of ``docs/GETTING_STARTED.md`` names the script of every proof that types a
placeholder, **derived from the guide and the scripts, not written beside them** (decisions 60 and
63 of M13.15).

The rows of ``<id della policy 2>`` and ``<id della policy 5>`` named ``scripts/prova_m13_14.py``
while section 34, whose script is ``scripts/prova_m13_15.py``, typed them too: a list written by
hand had become false, and :mod:`tests.docs.test_getting_started` could not see it — it asks only
that a row exists for every placeholder.

**The rule, decision 63** — narrower than decision 60, which would have reached the rows of the
placeholders of the whole guide, that say to no section they belong and must not: **a row that
names at least one proof script** (``scripts/prova_*.py``) **names the script of every proof
section that uses its placeholder** in a fenced block. A proof section is one with the markers
``<!-- prova: N.tipo -->``; its script is the one whose ``HEADING`` is that section's heading, read
from ``scripts/prova_*.py``, never from a list here. A row that names no script is not touched.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.composition.support import (
    _only_the_declared_environment,  # noqa: F401 — it reads the scripts of the proofs
)
from tests.docs.test_getting_started import BLOCK, LEGEND_ROW, PLACEHOLDER, guide

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
HEADING = re.compile(r'^HEADING\b[^=\n]*= "## (\d+)\. "', re.MULTILINE)
SECTION = re.compile(r"^## (\d+)\. ", re.MULTILINE)
MARKER = re.compile(r"<!-- prova: \d+\.\w+ -->")
SCRIPT = re.compile(r"scripts/prova_\w+\.py")


def sections(text: str) -> dict[str, str]:
    """Section number → its text, up to the next ``## N.``."""
    parts = SECTION.split(text)
    return {parts[index]: parts[index + 1] for index in range(1, len(parts), 2)}


def proof_sections(text: str) -> set[str]:
    """The sections a script walks: those with the markers of a proof."""
    return {number for number, body in sections(text).items() if MARKER.search(body)}


def using(text: str) -> dict[str, set[str]]:
    """Placeholder → the proof sections whose fenced blocks use it."""
    proofs, found = proof_sections(text), {}
    for number, body in sections(text).items():
        if number not in proofs:
            continue
        for block in BLOCK.findall(body):
            for placeholder in PLACEHOLDER.findall(block):
                found.setdefault(placeholder, set()).add(number)
    return found


def rows(text: str) -> dict[str, str]:
    """Placeholder → the two cells of its row that say what it is and where it comes from."""
    return {
        match.group(1): f"{match.group(2)} {match.group(3)}"
        for line in text.splitlines()
        if (match := LEGEND_ROW.match(line)) is not None
    }


def script_of_section() -> dict[str, str]:
    """Section number → the proof script that walks it, from each script's own ``HEADING``."""
    found: dict[str, str] = {}
    for path in sorted(SCRIPTS.glob("prova_*.py")):
        for number in HEADING.findall(path.read_text(encoding="utf-8")):
            found[number] = f"scripts/{path.name}"
    return found


def unnamed(text: str) -> list[str]:
    """Every row that names a proof script but not the script of each proof section using its
    placeholder — one line per fault, with the section and the script."""
    use, scripts, faults = using(text), script_of_section(), []
    for placeholder, cells in rows(text).items():
        if SCRIPT.search(cells) is None:
            continue
        for number in sorted(use.get(placeholder, set()), key=int):
            script = scripts.get(number)
            if script is not None and script not in cells:
                faults.append(f"{placeholder}: section {number} is walked by {script}, not named")
    return faults


def test_a_row_that_names_a_proof_script_names_the_script_of_every_proof_using_it() -> None:
    assert unnamed(guide()) == []


def test_every_proof_section_has_its_script_from_its_heading() -> None:
    """Decision 63: a proof section whose script did not declare it readably would stay out of
    the rule, with its reason written beside it. Today there is none: every one is found."""
    assert proof_sections(guide()) <= set(script_of_section())
    assert script_of_section()["34"] == "scripts/prova_m13_15.py"


def test_a_row_that_names_no_script_is_not_touched() -> None:
    """The placeholders of the whole guide say to no section they belong: ``<approval-id>`` is
    typed in many proofs, its row names no script, and that is no fault."""
    text = guide()

    assert "34" in using(text)["<approval-id>"]
    assert SCRIPT.search(rows(text)["<approval-id>"]) is None
    assert not any(fault.startswith("<approval-id>") for fault in unnamed(text))


def test_a_proof_that_types_a_placeholder_whose_row_does_not_name_its_script_is_found() -> None:
    """The negative case of decision 60, kept by 63: section 33 types the policy of step 7 of
    section 32, whose row names ``scripts/prova_m13_14.py`` only."""
    text = guide()
    line_end = text.index("\n", text.index("\n## 33. ") + 1)
    added = "\n\n```\nuv run ela policy show <id della policy 7>\n```\n"
    drifted = text[:line_end] + added + text[line_end:]
    fault = "<id della policy 7>: section 33 is walked by scripts/prova_m9_5.py, not named"

    assert fault not in unnamed(text)
    assert fault in unnamed(drifted)


def test_a_row_that_leaves_out_the_script_of_a_proof_is_found() -> None:
    """The row of ``<id del passo 3>`` no longer names the script of section 25."""
    text = guide()
    row = next(line for line in text.splitlines() if line.startswith("| `<id del passo 3>`"))
    drifted = text.replace(row, row.replace("scripts/prova_m13_1e.py", "scripts/prova_m6_3c.py"))
    fault = "<id del passo 3>: section 25 is walked by scripts/prova_m13_1e.py, not named"

    assert drifted != text
    assert fault not in unnamed(text)
    assert fault in unnamed(drifted)
