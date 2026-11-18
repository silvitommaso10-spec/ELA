"""Every step of a hand proof that waits for a failure names its reason (M13.15, ADR 0071; decision
22, answer 46 of the review of its SPEC).

The fourth point of M13.15: the step 4 of section 33 waited for «outcome failed», and the failure
that came was another than the one it was written for — `browser.download_not_started`, not the
time of the tool —: an ``atteso`` that says only «failed» cannot tell the two apart. **The rule**,
derived from the guide and not from a list: an ``atteso`` block that waits for ``outcome failed``
names, in the same block, the code of the reason — ``browser.file_changed``, ``vault.locked``.

**The two steps of before** stay as they were proven, in a closed list, each with its dated
annotation: the step 7 of section 30 (its next block names the code) and the step 4 of section 33.
The exemption is shown necessary — without one of them the rule speaks —, and a step that one day
names its reason makes the list false.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "GETTING_STARTED.md"
SECTION = re.compile(r"^## (\d+)\. ", re.M)
BLOCK = re.compile(r"<!-- prova: (\d+)\.atteso -->\n```\n(.*?)```", re.S)
FAILED = re.compile(r"^outcome\s+failed\s*$", re.M)
CODE = re.compile(r"\b[a-z]+(?:_[a-z]+)*\.[a-z]+(?:_[a-z]+)*\b")
OF_BEFORE: frozenset[tuple[str, str]] = frozenset({("30", "7"), ("33", "4")})
"""The steps of before, proven as they are: their annotation is dated 2026-11-17."""


def sections(text: str) -> dict[str, str]:
    """Each numbered section of the guide, by its number."""
    starts = [(match.group(1), match.start()) for match in SECTION.finditer(text)]
    ends = [start for _, start in starts[1:]] + [len(text)]
    return {number: text[start:end] for (number, start), end in zip(starts, ends, strict=True)}


def unnamed(text: str) -> set[tuple[str, str]]:
    """The steps whose block waits for «outcome failed» and names no code of a reason in it."""
    found = set()
    for number, body in sections(text).items():
        for step, block in BLOCK.findall(body):
            if FAILED.search(block) and not CODE.search(block):
                found.add((number, step))
    return found


def problems(text: str, of_before: frozenset[tuple[str, str]]) -> list[str]:
    found = unnamed(text)
    said = [f"§{n} step {s} waits for a failure and names no reason" for n, s in found - of_before]
    said += [f"§{n} step {s} names its reason now: out of the list" for n, s in of_before - found]
    return said


def test_every_step_that_waits_for_a_failure_names_its_reason() -> None:
    assert problems(GUIDE.read_text(encoding="utf-8"), OF_BEFORE) == []


def test_each_step_of_before_carries_its_dated_annotation() -> None:
    by_number = sections(GUIDE.read_text(encoding="utf-8"))

    for number, step in OF_BEFORE:
        body = by_number[number]
        heading = re.search(rf"^### {step}\. ", body, re.M)
        assert heading is not None, (number, step)
        rest = body[heading.end() :]
        own = re.split(r"^### ", rest, maxsplit=1, flags=re.M)[0]
        assert "***Annotato il 2026-11-17" in own, (number, step)


def test_without_one_of_them_the_rule_speaks() -> None:
    text = GUIDE.read_text(encoding="utf-8")

    for left_out in OF_BEFORE:
        assert problems(text, OF_BEFORE - {left_out}) != [], left_out


def test_a_step_of_before_that_names_its_reason_makes_the_list_false() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    by_number = sections(text)
    body = by_number["33"]
    named = body.replace("```\noutcome failed\n```", "```\noutcome failed\nbrowser.timeout\n```", 1)
    assert named != body

    said = problems(text.replace(body, named, 1), OF_BEFORE)

    assert said == ["§33 step 4 names its reason now: out of the list"]
