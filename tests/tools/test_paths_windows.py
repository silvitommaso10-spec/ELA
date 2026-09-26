"""The grammar of form G against a real NTFS (M13.3, ADR 0048): what the rules refuse on every
system is what Windows really reads otherwise.

Declared with its ``skipif`` (ADR 0031 §6) and **in the Windows job's list** (form J): on a Mac
these facts cannot be built — ``is_junction`` answers no there, and ``:`` is a character of a name.
Each test first shows Windows doing the thing, then the classification refusing it.
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

import pytest

from ela.tools import PATH_INVALID, PATH_SYMLINK, classify, resolve_workspace

pytestmark = pytest.mark.skipif(platform.system() != "Windows", reason="NTFS is Windows's")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return resolve_workspace(workspace)


def test_a_junction_that_points_inside_is_a_link(root: Path) -> None:
    (root / "real").mkdir()
    (root / "real" / "a.md").write_text("x", encoding="utf-8")
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(root / "alias"), str(root / "real")],
        check=True,
        capture_output=True,
    )
    assert (root / "alias").is_junction() and not (root / "alias").is_symlink()

    problem = classify(root, "alias/a.md")

    assert problem is not None and problem.code == PATH_SYMLINK


def test_a_colon_names_a_stream_of_another_file(root: Path) -> None:
    (root / "a.md").write_text("visible", encoding="utf-8")
    (root / "a.md:x").write_text("hidden", encoding="utf-8")
    assert os.listdir(root) == ["a.md"]
    assert (root / "a.md").read_text(encoding="utf-8") == "visible"

    problem = classify(root, "a.md:x")

    assert problem is not None and problem.code == PATH_INVALID


def test_a_trailing_dot_is_stripped_into_another_name(root: Path) -> None:
    (root / "b.md.").write_text("x", encoding="utf-8")
    assert os.listdir(root) == ["b.md"]

    problem = classify(root, "b.md.")

    assert problem is not None and problem.code == PATH_INVALID
