"""The font files are the ones declared, in both directions (M17.1, criterio 17, second half).

True also when there are none: until the user chooses, the family is the system stack, and
``fonts/`` does not exist — an orphan file, or a file declared and missing, is what this sees.
The licence, the provenance and the digest of a family (criterio 16) arrive with the first font;
that ``typography.candidates`` is gone (criterio 17, first half) arrives with the choice.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.design.tree import DESIGN_SYSTEM, tokens

FONTS = "fonts"
BESIDE = {"OFL.txt", "PROVENANCE.md"}
"""What lives beside the font files of a family, and is not itself a font."""


def font_files(folder: Path) -> set[str]:
    return {
        path.relative_to(folder).as_posix()
        for path in (folder / FONTS).rglob("*")
        if path.is_file() and path.name not in BESIDE
    }


def declared_files(source: dict[str, Any]) -> set[str]:
    return {font["file"] for font in source["typography"].get("fonts", [])}


def faults(source: dict[str, Any], folder: Path) -> list[str]:
    there, declared = font_files(folder), declared_files(source)
    found = [f"{name}: in {FONTS}/ and declared by no font" for name in sorted(there - declared)]
    found += [f"{name}: declared and not there" for name in sorted(declared - there)]
    return found


def test_the_font_files_are_exactly_the_declared_ones() -> None:
    assert faults(tokens(), DESIGN_SYSTEM) == []


def test_an_orphan_and_a_missing_file_are_found(tmp_path: Path) -> None:
    family = tmp_path / FONTS / "inter"
    family.mkdir(parents=True)
    (family / "Inter.woff2").write_bytes(b"wOF2")
    (family / "OFL.txt").write_text("SIL OPEN FONT LICENSE Version 1.1", encoding="utf-8")

    source = tokens()
    assert faults(source, tmp_path) == [
        "fonts/inter/Inter.woff2: in fonts/ and declared by no font"
    ]

    entry = {
        "family": "Inter",
        "file": "fonts/inter/Inter.woff2",
        "weight": "100 900",
        "style": "normal",
    }
    source["typography"]["fonts"] = [entry]
    assert faults(source, tmp_path) == []

    source["typography"]["fonts"].append({**entry, "file": "fonts/inter/Inter-Italic.woff2"})
    assert faults(source, tmp_path) == ["fonts/inter/Inter-Italic.woff2: declared and not there"]
