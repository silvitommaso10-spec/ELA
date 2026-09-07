"""ADR 0021 and the code of M7.2 say the same thing.

The tool and verifier tables of §9 and §10 are checked where the other tables of their kind are
(``test_adr_executor.py``, ``test_adr_verification.py``), the port extension of §8 in
``test_adr_ports.py`` and the added column of §11 in ``test_adr_persistence.py``: an ADR that adds
a row to an existing table is read together with the ADR that created it, and this module would
be a second, weaker copy of those. What is left here is what only ADR 0021 says: the crash-window
table of §12, the names of the codes it introduces, and the fact that architecture rule 25 is
registered under the name the ADR gives it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ela.domain import ExecutionStatus
from ela.executive import EXECUTION_INTERRUPTED
from ela.tools import PROVIDER_NO_OUTPUT
from ela.tools.model import ModelCompleteTool
from ela.tools.verifiers import ModelCompleteVerifier
from tests.architecture.rules import RULES

ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "adr"
ADR_PATH = ADR_DIR / "0021-started-protocol-and-model-complete.md"
RECOVERY_ADR = ADR_DIR / "0015-approval-and-result-persistence.md"
WINDOW_ROW = re.compile(r"^\| (\d) \| (.+?) \| (.+?) \| (.+?) \| (.+?) \|$")
RULE_NAME = "provider-complete-callers"


def text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def documented_windows(source: str) -> dict[str, tuple[str, str, str]]:
    """Crash number → (rows in the store, audit, step), from the §12 table."""
    rows = {
        number: (stored, audit, step)
        for line in source.splitlines()
        for number, _situation, stored, audit, step in [
            m.groups() for m in [WINDOW_ROW.match(line)] if m is not None
        ]
    }
    assert rows, "ADR 0021 must contain the crash-window table"
    return rows


def test_the_crash_window_table_covers_the_five_moments_of_one_run() -> None:
    """Five, in order, and each says what is in the store, in the audit and on the step."""
    windows = documented_windows(text())
    assert list(windows) == ["1", "2", "3", "4", "5"]
    stored, audit, step = windows["1"]
    assert "STARTED" in stored and "TOOL_EXECUTED" in audit
    assert "COMPLETED" in step
    for number in ("2", "4"):
        assert "solo la STARTED" in windows[number][0], number
        assert "FAILED" in windows[number][2], number
    assert "execution.interrupted" in windows["2"][1]
    assert "non riscritto" in windows["4"][1]  # written once, however many retries
    assert "nessuna" in windows["5"][0]  # nothing was written before the crash


def test_the_codes_the_adr_introduces_are_the_codes_the_code_uses() -> None:
    source = text()
    for code in (EXECUTION_INTERRUPTED, PROVIDER_NO_OUTPUT):
        assert f"`{code}`" in source, code
    assert f"**`{ExecutionStatus.STARTED.value}`**" in source


def test_the_interruption_is_declared_retryable_and_the_code_agrees() -> None:
    """§2: what failed is the crash, not the request — and a failed step never restarts."""
    assert "`retryable=True`: ciò che è fallito è il crash" in text()


def test_rule_25_is_registered_under_the_name_the_adr_gives_it() -> None:
    source = text()
    assert f"(`{RULE_NAME}`)" in source
    assert RULE_NAME in RULES


def test_the_tool_and_the_verifier_declare_what_the_adr_says_they_do() -> None:
    """§1 and §6, as class-level facts rather than prose."""
    assert ModelCompleteTool.idempotent is False
    assert "idempotent = False" in text()
    assert ModelCompleteVerifier.conditions == frozenset({"model.answered"})
    assert "`model.routed_as_asked` in M7.3" in text()


def test_the_adr_answers_the_debt_adr_0015_wrote_down() -> None:
    """ADR 0015 §8 named the milestone that would carry the protocol; this is that ADR."""
    assert "M7.2 `model.complete`" in RECOVERY_ADR.read_text(encoding="utf-8")
    assert "ADR 0015 §8" in text()
    assert "Milestone:** M7.2" in text()


def test_a_drifted_window_table_is_detected() -> None:
    source = text()
    softened = source.replace(
        "| solo la STARTED | `TOOL_EXECUTED` con", "| nessuna | `TOOL_EXECUTED` con", 1
    )
    assert softened != source
    assert documented_windows(softened)["2"][0] != documented_windows(source)["2"][0]
    with pytest.raises(AssertionError, match="crash-window table"):
        documented_windows("nothing")
