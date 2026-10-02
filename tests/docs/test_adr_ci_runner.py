"""ADR 0053 and the CI say the same thing: the runner has a written version, the debt is paid.

The defence §2 asked for, in the form of ADR 0035 §7, turned round by M6.3c (ADR 0054 §1): until
2026-09-30 ``.github/workflows/ci.yml`` ran ``make check`` on ``ubuntu-latest`` and used the actions
the runner warned about. Now the Linux runner is a written Ubuntu version and none of those actions
is left; the day one of them comes back — a merge, a revert — the debt is owed again, and the test
below says so.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0053-ci-runner.md"
PAYMENT_PATH = ROOT / "docs" / "adr" / "0054-stopped-midway.md"
CI = ROOT / ".github" / "workflows" / "ci.yml"

OWED = (
    "os: [ubuntu-latest, macos-latest]",
    "actions/checkout@v4",
    "actions/cache/restore@v4",
    "astral-sh/setup-uv@v6",
)
"""What the debt was, as the file spelled it: the moving label, and the actions on Node.js 20."""

WRITTEN_UBUNTU = re.compile(r"os: \[ubuntu-\d{2}\.\d{2}, macos-latest\]")
"""The matrix of ``make check`` with Linux as a version, not a label (ADR 0053 §1)."""


def owed(workflow: str) -> list[str]:
    """The parts of the debt the workflow still carries."""
    return [line for line in OWED if line in workflow]


def test_the_ci_runs_on_a_written_ubuntu_with_no_node_20_action() -> None:
    workflow = CI.read_text(encoding="utf-8")

    assert owed(workflow) == []
    assert WRITTEN_UBUNTU.search(workflow) is not None


def test_bringing_back_one_part_of_the_debt_owes_it_again() -> None:
    """The negative case: the moving label, or one old action, is the debt again."""
    workflow = CI.read_text(encoding="utf-8")
    moving = WRITTEN_UBUNTU.sub(OWED[0], workflow)
    old_checkout = re.sub(r"actions/checkout@v\d+", OWED[1], workflow)

    assert owed(moving) == [OWED[0]]
    assert WRITTEN_UBUNTU.search(moving) is None
    assert owed(old_checkout) == [OWED[1]]


def test_the_adr_charges_the_debt_to_m6_3c_with_its_deadline() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")

    assert "### 2. Un debito datato: il runner della CI, da fissare entro il 2026-10-19" in text
    assert "**Debito a carico di M6.3c**, dichiarato il **2026-09-30**" in text


def test_the_adr_of_m6_3c_writes_the_payment() -> None:
    """The heading ``scripts/generate_stato.py`` reads to call the debt paid."""
    text = PAYMENT_PATH.read_text(encoding="utf-8")

    assert "### 1. Il debito di ADR 0053 §2, saldato" in text
