"""ADR 0053 and the CI say the same thing: the runner is still the moving label, the debt is owed.

The defence §2 asked for, in the form of ADR 0035 §7: ``.github/workflows/ci.yml`` still runs
``make check`` on ``ubuntu-latest`` and still uses the actions the runner warned about on
2026-09-30. The day M6.3c pins the runner and updates the actions, the test below fails, the
payment is written in its ADR, and this test is turned round.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0053-ci-runner.md"
CI = ROOT / ".github" / "workflows" / "ci.yml"

OWED = (
    "os: [ubuntu-latest, macos-latest]",
    "actions/checkout@v4",
    "actions/cache/restore@v4",
    "astral-sh/setup-uv@v6",
)
"""What the debt is, as the file spells it: the moving label, and the actions on Node.js 20."""


def paid(workflow: str) -> list[str]:
    """The parts of the debt the workflow no longer carries."""
    return [line for line in OWED if line not in workflow]


def test_the_ci_still_runs_on_the_moving_label_with_the_node_20_actions() -> None:
    assert paid(CI.read_text(encoding="utf-8")) == [], (
        "ADR 0053 §2 is being paid: write «Il debito di ADR 0053 §2, saldato» in the ADR of M6.3c, "
        "and turn this test round"
    )


def test_a_pinned_runner_and_updated_actions_are_seen_as_paid() -> None:
    """The negative case: a workflow that paid the debt is not the debt."""
    workflow = CI.read_text(encoding="utf-8").replace("ubuntu-latest", "ubuntu-24.04")
    workflow = workflow.replace("actions/checkout@v4", "actions/checkout@v5")

    assert paid(workflow) == [OWED[0], OWED[1]]


def test_the_adr_charges_the_debt_to_m6_3c_with_its_deadline() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")

    assert "### 2. Un debito datato: il runner della CI, da fissare entro il 2026-10-19" in text
    assert "**Debito a carico di M6.3c**, dichiarato il **2026-09-30**" in text
