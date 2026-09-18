"""Every text file is checked out with LF, whatever the machine's ``core.autocrlf`` (M12.4).

A clone on the PC with Git for Windows' default converted **598 files out of 629** to CRLF (P0,
2026-09-15). ``.gitattributes`` is the protection, and this is its guard in the derived form: the
question goes to git, which is the one that knows which attributes a file carries. A test looking
for a line inside ``.gitattributes`` would be a list checking itself.

The ``attr/`` column of ``git ls-files --eol`` does not depend on the platform, so the guard says
the same on every runner. The ``w/`` column does — it is what this machine checked out — and is not
read: the CI job on Windows keeps the runner's ``core.autocrlf`` on purpose (M12.4 dec. H), and a
Mac clone made with ``autocrlf=true`` would show CRLF there while the attributes are right.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROTECTED = "attr/text=auto eol=lf"
BINARY = "i/-text"


def unprotected(listing: str) -> list[str]:
    """The paths of a ``git ls-files --eol -z`` listing that are not binary and lack ``PROTECTED``.

    Each entry is ``i/<index> w/<worktree> attr/<attributes>``, a tab, the path. The attributes may
    hold a space (``text=auto eol=lf``), so the path is cut at the tab first. A binary is judged by
    the index, which is what git stored, and is left alone: ``text=auto`` never converts it.
    """
    found: list[str] = []
    for entry in filter(None, listing.split("\0")):
        described, path = entry.split("\t", 1)
        index, _worktree, attributes = described.split(maxsplit=2)
        if index != BINARY and attributes.strip() != PROTECTED:
            found.append(path)
    return found


def _listing() -> tuple[str, str | None]:
    listed = subprocess.run(["git", "ls-files", "--eol", "-z"], cwd=ROOT, capture_output=True)
    if listed.returncode != 0:
        return "", "not a git repository: nobody to ask which attributes a file carries"
    return listed.stdout.decode("utf-8"), None


LISTING, NO_REPOSITORY = _listing()


@pytest.mark.skipif(NO_REPOSITORY is not None, reason=NO_REPOSITORY or "")
def test_every_text_file_carries_lf_whatever_the_machine_that_clones_it() -> None:
    """Git's answer for the tree, and not a sample of it. Seeing nothing is not a pass."""
    assert LISTING, "git listed no files"

    found = unprotected(LISTING)

    assert not found, f"{len(found)} text files without {PROTECTED!r}, e.g. {found[:5]}"


def test_a_text_file_without_the_attributes_is_named() -> None:
    """The negative case: what the tree before ``.gitattributes`` looked like, one line of it."""
    listing = "i/lf    w/crlf  attr/                 \tsrc/ela/node/state.py\0"

    assert unprotected(listing) == ["src/ela/node/state.py"]


def test_a_binary_is_not_asked_for_them() -> None:
    """``docs/spec/ELA.pdf`` is stored as binary; its attributes are not what protects it."""
    listing = (
        "i/-text w/-text attr/                 \tdocs/spec/ELA.pdf\0"
        "i/none  w/none  attr/text=auto eol=lf \tsrc/ela/__init__.py\0"
    )

    assert unprotected(listing) == []
