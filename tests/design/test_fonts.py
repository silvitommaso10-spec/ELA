"""The family is the system stack, and nothing else is there (M17.1, criteri 16 e 17).

«Stile Apple» means San Francisco on the Mac and on the iPhone, and the system stack is the
only lawful way to have it: San Francisco cannot be redistributed. On Windows the stack is
Segoe UI, its native counterpart (the user's decision of 2026-09-19; ADR 0042).

So the cycle of the font is closed, and two statements are true at zero files: no candidate is
left in the source, and no font file is in the folder. Two candidates were tried in the working
tree — Inter and IBM Plex Sans — and **no ``.woff2`` ever entered a commit**: a binary in a
commit stays in the history for ever.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.design.tree import DESIGN_SYSTEM, tokens

FONT_FILES = {".woff2", ".woff", ".ttf", ".otf", ".eot"}
LEFT_BY_THE_TRIAL = ("candidates", "fonts")


def left_by_the_trial(source: dict[str, Any]) -> list[str]:
    return [
        f"typography.{name} is still in the source"
        for name in LEFT_BY_THE_TRIAL
        if name in source["typography"]
    ]


def font_files(folder: Path) -> list[str]:
    return sorted(
        path.relative_to(folder).as_posix()
        for path in folder.rglob("*")
        if path.is_file() and path.suffix.lower() in FONT_FILES
    )


def test_no_candidate_is_left_in_the_source_and_the_family_is_the_system_stack() -> None:
    source = tokens()
    assert left_by_the_trial(source) == []
    family = source["typography"]["family"]["sans"]["$value"]
    assert family.split(",")[0].strip() == "system-ui"
    assert '"' not in family.replace('"Segoe UI"', ""), "a named family would need its file"


def test_no_font_file_is_in_the_folder() -> None:
    assert list(DESIGN_SYSTEM.iterdir()), "the folder must exist, or this test is vacuous"
    assert font_files(DESIGN_SYSTEM) == []


def test_a_candidate_left_behind_and_a_font_file_are_found(tmp_path: Path) -> None:
    source = tokens()
    source["typography"]["candidates"] = [{"id": "inter", "family": "Inter"}]
    source["typography"]["fonts"] = [{"family": "Inter", "file": "fonts/inter/Inter.woff2"}]
    assert left_by_the_trial(source) == [
        "typography.candidates is still in the source",
        "typography.fonts is still in the source",
    ]

    (tmp_path / "fonts" / "inter").mkdir(parents=True)
    (tmp_path / "fonts" / "inter" / "Inter-Regular.WOFF2").write_bytes(b"wOF2")
    (tmp_path / "fonts" / "inter" / "OFL.txt").write_text("licence", encoding="utf-8")
    assert font_files(tmp_path) == ["fonts/inter/Inter-Regular.WOFF2"]
