"""ADR 0045 and the running code describe the same filesystem, the same rows and the same totals.

This is also where the **pin on today's totals** lives (M13.1 dec. K): an ADR is immutable, so
each older one keeps saying the number it saw, and the ADR that changed a number carries the
assertion about the tree as it is now — the shape ``_rules_up_to`` already gives the architecture
rules.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ela.domain import RiskLevel
from ela.permissions import MAX_RISK, RISK_POLICY, Rule, production_catalogue
from ela.testing.fakes import FakeModelRouter
from ela.tools import (
    FS_READ,
    FS_WRITE,
    CaptureSettings,
    CaptureStore,
    production_verifiers,
)

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0045-filesystem-and-high.md"
VERIFIER_ROW = re.compile(
    r"^\| `(fs\.\w+)` \| `(\w+)` \| `([\w-]+)` \| (.+?) \| (.+?) \|$",
)


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def catalogue_today() -> tuple[str, ...]:
    return tuple(spec.id for spec in production_catalogue().specs())


def verifiers_today(tmp_path: Path):  # type: ignore[no-untyped-def]
    captures = CaptureStore(CaptureSettings(capture_dir=tmp_path / "captures"))
    return production_verifiers(
        root=tmp_path, router=FakeModelRouter(), captures=captures, fs_root=tmp_path / "files"
    )


# ----------------------------------------------------------------------------------------
# The totals of today, pinned here because this ADR is the one that changed them
# ----------------------------------------------------------------------------------------


def test_the_capabilities_of_today_are_ten_and_this_adr_says_so() -> None:
    assert len(catalogue_today()) == 10
    assert "restano dieci" in adr_text()


def test_four_travel_and_six_do_not(tmp_path: Path) -> None:
    """ADR 0038 §14 said four and four, of the eight it saw. Two more stay, and it is six."""
    declared = {v.capability_id: v.reads_the_machine for v in verifiers_today(tmp_path).verifiers()}

    assert sorted(declared.values()) == [False] * 4 + [True] * 6
    assert declared[FS_READ] is True
    assert declared[FS_WRITE] is True
    assert "quattro viaggiano, sei no" in adr_text()


# ----------------------------------------------------------------------------------------
# The rows this ADR writes
# ----------------------------------------------------------------------------------------


def test_the_revised_policy_row_is_the_running_one() -> None:
    assert RISK_POLICY[RiskLevel.HIGH] is Rule.APPROVAL_EVERY_USE
    assert RISK_POLICY[RiskLevel.CRITICAL] is Rule.DENY
    assert MAX_RISK is RiskLevel.HIGH
    assert "`MAX_RISK` passa da `MEDIUM` a `HIGH`" in adr_text()


def test_the_verifier_rows_match_the_verifiers(tmp_path: Path) -> None:
    coded = {v.capability_id: v for v in verifiers_today(tmp_path).verifiers()}
    documented = {
        match.group(1): (match.group(2), match.group(3))
        for line in adr_text().splitlines()
        if (match := VERIFIER_ROW.match(line))
    }

    assert set(documented) == {FS_READ, FS_WRITE}
    for capability, (class_name, name) in documented.items():
        assert type(coded[capability]).__name__ == class_name, capability
        assert coded[capability].name == name, capability


@pytest.mark.parametrize("capability", [FS_READ, FS_WRITE])
def test_the_catalogue_rows_match_the_catalogue(capability: str) -> None:
    """The risk and the scoped argument, which are what the two rows of §4 promise."""
    spec = production_catalogue().get(capability)  # type: ignore[arg-type]

    assert spec.scoped_arguments == ("path",)
    assert spec.risk is (RiskLevel.HIGH if capability == FS_WRITE else RiskLevel.MEDIUM)
    assert spec.requires_authorization


def test_the_adr_names_what_it_supersedes() -> None:
    """A renamed code and a revised row are not silent: both are named here (dec. B, O)."""
    text = adr_text()

    assert "path.outside_workspace" in text and "path.outside_root" in text
    assert "superat" in text
    assert "Policy rivista:" in text


def test_the_adr_says_where_the_bytes_of_a_read_go() -> None:
    """dec. P: the one capability that takes the user's files and puts them in a result."""
    text = adr_text()

    assert "il risultato porta il contenuto" in text
    assert "mai i byte" in text
