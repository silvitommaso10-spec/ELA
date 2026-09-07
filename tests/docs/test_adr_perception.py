"""ADR 0028 and the code say the same thing about the perception (M10.1).

The tables of §12 are read from the document and compared with what the code has, and the
decisions that are *properties* — a cause that cannot fire is not shipped, no capability was
added, the audit stays out of it — are asserted rather than believed. A declared constraint
nobody reads is the failure mode M9.2 exists to fix.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from ela.domain import SensorCause, SensorState
from ela.perception import PerceptionCore
from ela.permissions import catalogue_v01
from tests.architecture.rules import RULES
from tests.architecture.violations import PACKAGE_ROOT
from tests.contracts.protocols import port_protocols

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0028-perception-core.md"
RULE_ROW = re.compile(r"^\| (\d+) `([a-z-]+)` \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \|$")
"""§12: the three rules this ADR introduces, by number and by their key in ``RULES``."""


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


# ----------------------------------------------------------------------------------------
# §12: the tables
# ----------------------------------------------------------------------------------------


def test_the_three_rules_are_registered_under_the_names_the_adr_gives_them() -> None:
    documented = [
        match.groups() for line in adr_text().splitlines() if (match := RULE_ROW.match(line))
    ]

    assert [number for number, *_ in documented] == ["32", "33", "34"]
    for _, name, *_ in documented:
        assert name in RULES, name


@pytest.mark.parametrize(
    "key",
    [
        "machine-access-in-one-place",
        "perception-probe-imports-only-stdlib",
        "perception-adapter-decides-nothing",
    ],
)
def test_each_new_rule_holds_on_the_real_tree(key: str) -> None:
    assert RULES[key](PACKAGE_ROOT) == []


def test_the_conseguenze_count_the_rules_and_the_ports_the_code_has() -> None:
    """The current totals, pinned by the ADR that changed them.

    ADR 0026 counted thirty-one and still can, by number (``test_adr_placement.py``); this is the
    document that owns today's total, and the next one to add a rule takes the pin over.
    """
    conseguenze = adr_text().split("## Conseguenze", 1)[1]

    assert "**trentaquattro**" in conseguenze
    assert len(RULES) == 34
    assert "**diciannove**" in conseguenze
    assert len(tuple(port_protocols())) == 19
    assert "**tredici**" in conseguenze


# ----------------------------------------------------------------------------------------
# The decisions that are properties, not prose
# ----------------------------------------------------------------------------------------


def test_the_cause_that_cannot_fire_was_not_shipped() -> None:
    """§4: under §3 no §11 state depends on a permission, so ``DENIED_BY_SYSTEM`` has no case.

    Shipping it would be shipping a value that can never appear, which is what ADR 0026 §7 calls
    worse than an absent defence. The ADR also has to say where it is born, or the decision is a
    deletion instead of a deferral.
    """
    assert "DENIED_BY_SYSTEM" not in {cause.value for cause in SensorCause}
    assert "rendere `ACTIVE`" in adr_text()


def test_the_three_states_are_the_three_of_the_spec() -> None:
    """§3: §11 declares three, and nothing widens them — the cause is the fourth fact, not a
    fourth state."""
    assert [state.value for state in SensorState] == ["OFF", "AVAILABLE", "ACTIVE"]


def test_the_catalogue_did_not_grow() -> None:
    """§9: the Guardian decides when a tool is about to run, and M10.1 runs none.

    The constraint the ADR registers is where the first one is born — with content, not with
    perception — and that sentence has to be in the document for the deferral to mean anything.
    """
    assert len(catalogue_v01().specs()) == 3
    assert "prima lettura di contenuto" in adr_text()


def test_the_criterion_about_the_audit_is_written_down_and_not_only_applied() -> None:
    """§10: the rule that generalises ADR 0026 §10 from choosing to observing.

    The fact — perception writes nothing — lives in a test; the criterion that produces it lives
    only where somebody writes it, and without it the next person has to decide again.
    """
    assert "l'audit registra ciò che ela decide, non ciò che il mondo fa" in adr_text().lower()
    assert "audit" not in "".join(PerceptionCore.__slots__)


def test_the_adapter_imports_primitives_and_no_decision() -> None:
    """§1: what the adapter is allowed to know, read off its imports.

    Rule 34 is the enforcement and has its own negative cases; this says the positive half, which
    a rule cannot: the adapter *does* name ``RawObservation`` and ``ProbeFamily``, so its silence
    about the states is a boundary and not an accident of it importing nothing at all.

    Docstrings are deliberately not searched — they explain the boundary, and a rule that forbade
    naming it in prose would forbid documenting it.
    """
    imported = {name for path in _adapter_sources() for name in _imported_names(path)}

    assert {"RawObservation", "ProbeFamily"} <= imported
    assert not imported & {"SensorState", "SensorCause", "PermissionState"}


def _adapter_sources() -> list[Path]:
    return sorted((PACKAGE_ROOT / "infrastructure" / "perception").rglob("*.py"))


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }


def test_the_helper_carries_none_of_elas_import_graph() -> None:
    """§2: rule 33 in the same form. What must be able to die alone must be alone."""
    source = (PACKAGE_ROOT / "infrastructure" / "perception" / "probe.py").read_text("utf-8")
    modules = {
        node.module or ""
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert "ela" not in {name.partition(".")[0] for name in modules}


# ----------------------------------------------------------------------------------------
# The declared constraints
# ----------------------------------------------------------------------------------------


def test_the_deprecated_api_the_adr_refuses_is_nowhere_in_the_code() -> None:
    """A declared constraint with a name: the webcam's "in use" stays unobservable rather than
    being guessed through ``isInUseByAnotherApplication``, deprecated since 10.14."""
    sources = (PACKAGE_ROOT / "infrastructure" / "perception").rglob("*.py")

    assert not [
        path for path in sources if "isInUseByAnotherApplication" in path.read_text("utf-8")
    ]
    assert "deprecato da 10.14" in adr_text()


def test_the_perception_is_not_the_memory() -> None:
    """The current observation and the previous one, and nothing that accumulates."""
    kept = [name for name in PerceptionCore.__slots__ if "current" in name or "previous" in name]

    assert sorted(kept) == ["_current", "_previous"]
    assert "La percezione non è memoria" in adr_text()
