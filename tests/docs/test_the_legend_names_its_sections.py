"""The legend of ``docs/GETTING_STARTED.md`` names the sections that use a placeholder and the
scripts that write it, **derived from the guide, not written beside it** (decision 60 of M13.15).

The rows of ``<id della policy 2>`` and ``<id della policy 5>`` said «la sezione 32» and
``scripts/prova_m13_14.py`` while section 34 used them too: a list written by hand had become
false, and :mod:`tests.docs.test_getting_started` could not see it — it asks only that a row
exists for every placeholder.

**The rule, as decision 60 writes it, read to the letter.** A row that names a section — «sezione
N», «sezioni N e M», «§N» — names **every** section whose code blocks use its placeholder; and a
row that names a script of ``scripts/`` names **the script of each of those sections** that has
one. The script of a section is the one whose ``HEADING`` is that section's heading, read from
``scripts/prova_*.py``, never from a list here. A row that names no section is a placeholder of
the whole guide, and the rule does not reach it. Naming a section more is not a fault: a row may
also say where a value is read.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.docs.test_getting_started import BLOCK, LEGEND_ROW, PLACEHOLDER, guide

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
HEADING = re.compile(r'^HEADING\b[^=\n]*= "## (\d+)\. "', re.MULTILINE)
SECTION = re.compile(r"^## (\d+)\. ", re.MULTILINE)
NAMED = re.compile(r"(?:\bsezion[ei]|§)\s*(\d+(?:(?:,\s*|\s+e\s+)\d+)*)")
SCRIPT = re.compile(r"scripts/prova_\w+\.py")


def sections(text: str) -> dict[str, str]:
    """Section number → its text, up to the next ``## N.``."""
    parts = SECTION.split(text)
    return {parts[index]: parts[index + 1] for index in range(1, len(parts), 2)}


def using(text: str) -> dict[str, set[str]]:
    """Placeholder → the sections whose fenced blocks use it: what a reader types, and where."""
    found: dict[str, set[str]] = {}
    for number, body in sections(text).items():
        for block in BLOCK.findall(body):
            for placeholder in PLACEHOLDER.findall(block):
                found.setdefault(placeholder, set()).add(number)
    return found


def rows(text: str) -> dict[str, str]:
    """Placeholder → the two cells of its legend row that say what it is and where it comes from."""
    return {
        match.group(1): f"{match.group(2)} {match.group(3)}"
        for line in text.splitlines()
        if (match := LEGEND_ROW.match(line)) is not None
    }


def named_sections(cells: str) -> set[str]:
    return {number for found in NAMED.findall(cells) for number in re.findall(r"\d+", found)}


def script_of_section() -> dict[str, str]:
    """Section number → the proof script that walks it, from each script's own ``HEADING``."""
    found: dict[str, str] = {}
    for path in sorted(SCRIPTS.glob("prova_*.py")):
        for number in HEADING.findall(path.read_text(encoding="utf-8")):
            found[number] = f"scripts/{path.name}"
    return found


def unnamed(text: str) -> list[str]:
    """Every row that names a section but not all of those that use its placeholder, or names a
    script but not the one of each of those sections — one line per fault, with the section."""
    use, scripts, faults = using(text), script_of_section(), []
    for placeholder, cells in rows(text).items():
        named = named_sections(cells)
        if not named:
            continue
        for number in sorted(use.get(placeholder, set()), key=int):
            if number not in named:
                faults.append(
                    f"{placeholder}: section {number} uses it, and its row does not name it"
                )
            script = scripts.get(number)
            if SCRIPT.search(cells) and script is not None and script not in cells:
                faults.append(f"{placeholder}: section {number} is walked by {script}, not named")
    return faults


def test_a_row_that_names_a_section_names_every_section_that_uses_it_and_its_script() -> None:
    assert unnamed(guide()) == []


def test_the_rule_reaches_the_rows_of_the_proofs() -> None:
    """The rows decision 60 was written for are among the ones the rule reads, and the script of
    this milestone's section is found from its own heading."""
    reached = {placeholder for placeholder, cells in rows(guide()).items() if named_sections(cells)}

    assert {"<id della policy 2>", "<id della policy 5>", "<id del figlio>"} <= reached
    assert script_of_section()["34"] == "scripts/prova_m13_15.py"


def test_a_section_that_uses_a_placeholder_its_row_does_not_name_is_found() -> None:
    """The negative case of decision 60: section 33 types the policy of step 7 of section 32,
    whose row names section 32 only."""
    text = guide()
    line_end = text.index("\n", text.index("\n## 33. ") + 1)
    added = "\n\n```\nuv run ela policy show <id della policy 7>\n```\n"
    drifted = text[:line_end] + added + text[line_end:]
    fault = "<id della policy 7>: section 33 uses it, and its row does not name it"

    assert fault not in unnamed(text)
    assert fault in unnamed(drifted)


def test_a_row_that_leaves_out_the_script_of_a_section_is_found() -> None:
    """The other half: the row of ``<id del passo 3>`` still names section 25, and no longer the
    script that walks it."""
    text = guide()
    row = next(line for line in text.splitlines() if line.startswith("| `<id del passo 3>`"))
    drifted = text.replace(row, row.replace("scripts/prova_m13_1e.py", "scripts/prova_m6_3c.py"))

    fault = "<id del passo 3>: section 25 is walked by scripts/prova_m13_1e.py, not named"

    assert drifted != text
    assert fault not in unnamed(text)
    assert fault in unnamed(drifted)
