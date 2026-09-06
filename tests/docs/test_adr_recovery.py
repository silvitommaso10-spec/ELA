"""The crash-window table of ADR 0015 §8 and the recovery tests describe the same repairs.

Every row the ADR marks **Riparato.** is a window ``tests/executive/test_executor_recovery.py``
crashes at and retries — one ``test_window_<n>_…`` per window, listed in its ``REPAIRED`` — and
every window that module repairs is a row the ADR marks so. A row that cites another milestone
cannot claim a repair; a row demoted, or a test removed, is noticed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.executive import test_executor_recovery as recovery

ADR_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "adr" / "0015-approval-and-result-persistence.md"
)
WINDOW_ROW = re.compile(r"^\| (\d+[a-c]?) \| (.+?) \| (.+?) \| (.+?) \| (.+) \|$")
REPAIRED_MARK = "**Riparato.**"
MILESTONE = re.compile(r"M\d+\.\d+")


def documented_windows(text: str) -> dict[str, str]:
    """Window id -> the "Retry" cell of the crash-window table."""
    rows = {
        window: retry
        for line in text.splitlines()
        for window, _, _, _, retry in [
            m.groups() for m in [WINDOW_ROW.match(line)] if m is not None
        ]
    }
    assert rows, "ADR 0015 must contain the crash-window table"
    return rows


def repaired_windows(text: str) -> frozenset[str]:
    return frozenset(w for w, retry in documented_windows(text).items() if REPAIRED_MARK in retry)


def windows_under_test() -> frozenset[str]:
    names = [n for n in dir(recovery) if n.startswith("test_window_")]
    return frozenset(n.removeprefix("test_window_").split("_")[0] for n in names)


def test_every_repaired_row_has_a_retry_test_and_vice_versa() -> None:
    repaired = repaired_windows(ADR_PATH.read_text(encoding="utf-8"))
    assert repaired == recovery.REPAIRED
    assert windows_under_test() >= recovery.REPAIRED


def test_the_declared_windows_have_a_test_of_their_own_too() -> None:
    """A window that is not repaired still has a test that pins what the retry does."""
    declared = {"5c", "7a", "9"}
    assert declared <= windows_under_test()
    assert not (declared & recovery.REPAIRED)


def test_a_repaired_row_never_defers_to_another_milestone() -> None:
    for window, retry in documented_windows(ADR_PATH.read_text(encoding="utf-8")).items():
        if REPAIRED_MARK in retry:
            assert MILESTONE.search(retry) is None, window


def test_the_table_lists_every_window_of_the_earlier_adrs() -> None:
    windows = set(documented_windows(ADR_PATH.read_text(encoding="utf-8")))
    numbered = {str(n) for n in range(11)} - {"7"}  # 7 became 7a and 7b
    assert windows >= numbered | {"5b", "5c", "7a", "7b", "8a", "8b", "8c", "9a"}


def test_a_demoted_row_or_a_removed_test_is_detected() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")
    demoted = text.replace(
        "→ scritto ora con `recovered`, poi si prosegue (§5). Il tool non gira. **Riparato.** |",
        "→ scritto ora con `recovered`, poi si prosegue (§5). Il tool non gira. |",
        1,
    )
    assert demoted != text
    assert repaired_windows(demoted) != recovery.REPAIRED
    deferred = text.replace(
        "`fail_step` + `fail` con l'`error` dell'evento. **Riparato.** |",
        "`fail_step` + `fail` con l'`error` dell'evento → M6.2. **Riparato.** |",
        1,
    )
    assert deferred != text
    with pytest.raises(AssertionError):
        for window, retry in documented_windows(deferred).items():
            if REPAIRED_MARK in retry:
                assert MILESTONE.search(retry) is None, window
    assert "5" in windows_under_test() and "zz" not in windows_under_test()


def test_a_missing_table_is_detected() -> None:
    with pytest.raises(AssertionError, match="crash-window table"):
        documented_windows("nothing")
