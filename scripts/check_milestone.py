"""Fail if a milestone in ``docs/milestones/`` lacks a filled "Criteri di accettazione".

Every ``*.md`` file in the milestones directory, except ``TEMPLATE.md``, must contain a
``## Criteri di accettazione`` section with at least one line of real content: blank lines
and template placeholders (``<...>``) do not count.

Usage::

    uv run python scripts/check_milestone.py [docs/milestones]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REQUIRED_SECTION = "Criteri di accettazione"
TEMPLATE_NAME = "TEMPLATE.md"
HEADING = re.compile(r"^##\s+(.+?)\s*$")
PLACEHOLDER = re.compile(r"^[-*\d.\s]*<[^<>]*>[.\s]*$")


def section_body(text: str, title: str) -> list[str] | None:
    """Return the lines of the ``## title`` section, or ``None`` if the section is missing."""
    body: list[str] | None = None
    for line in text.splitlines():
        heading = HEADING.match(line)
        if heading is not None:
            if body is not None:
                break
            if heading.group(1) == title:
                body = []
            continue
        if body is not None:
            body.append(line)
    return body


def is_filled(lines: list[str]) -> bool:
    return any(line.strip() and PLACEHOLDER.match(line) is None for line in lines)


def check_milestones(directory: Path) -> list[str]:
    """Return one problem description per invalid milestone file."""
    problems: list[str] = []
    for path in sorted(directory.glob("*.md")):
        if path.name == TEMPLATE_NAME:
            continue
        body = section_body(path.read_text(encoding="utf-8"), REQUIRED_SECTION)
        if body is None:
            problems.append(f"{path}: missing section '## {REQUIRED_SECTION}'")
        elif not is_filled(body):
            problems.append(f"{path}: section '## {REQUIRED_SECTION}' is not filled in")
    return problems


def main(argv: list[str]) -> int:
    default = Path(__file__).resolve().parents[1] / "docs" / "milestones"
    directory = Path(argv[1]) if len(argv) > 1 else default
    if not directory.is_dir():
        print(f"{directory}: not a directory", file=sys.stderr)
        return 1
    problems = check_milestones(directory)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print(f"milestones OK ({directory})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
