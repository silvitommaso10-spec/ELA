"""ADR 0026 and the code say the same thing about the placement, the token and the two new rules.

The tables of §9 are the load-bearing part — the signature that replaces ADR 0018 §4's, the
method, the error, the two rules — and each is read from the ADR and compared with what the code
has. The declared limits are checked too: a constraint nobody reads is the failure mode M9.2
exists to fix, and this ADR's own list is at least held to naming the things it defers.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from ela.devices import (
    UNGUARDED_RISK,
    DeviceOrchestrator,
    NotPlacedError,
    PlacementDecision,
    ensure_placed,
)
from ela.executive import Executor
from ela.permissions import MAX_RISK
from tests.architecture.rules import RULES
from tests.architecture.violations import PACKAGE_ROOT

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0026-placement-as-data.md"
REFUSAL_ROW = re.compile(r"^\| (\d) \| ([^|]+?) \| ([^|]+?) \|$")
"""§3: the three refusals of ``ensure_placed``, numbered."""
RULE_ROW = re.compile(r"^\| (\d+) `([a-z-]+)` \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \|$")
"""§9: the two rules this ADR introduces, by number and by their key in ``RULES``."""
ERROR_ROW = re.compile(r"^\| `(\w+)` \| `(\w+(?:\.\w+)+)` \| ([^|]+?) \|$")
"""§9: three cells, and the middle one is a dotted module — no other table here has that."""
METHOD_ROW = re.compile(r"^\| `(\w+)` \| `(\w+)` \| ([^|]+?) \| (sì|no) \|$")
"""§9: four cells, the last one the audit answer. Distinct from every other row shape."""


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def rows(pattern: re.Pattern[str], text: str) -> list[tuple[str, ...]]:
    return [m.groups() for line in text.splitlines() if (m := pattern.match(line))]


# --------------------------------------------------------------------------------------
# §9: the tables
# --------------------------------------------------------------------------------------


def test_the_signature_row_is_the_one_the_executor_has() -> None:
    """``Firma aggiornata:`` repeats the row of ADR 0018 §4 because an ADR is immutable."""
    assert "`Firma aggiornata:`" in adr_text()
    parameters = inspect.signature(Executor.execute).parameters

    assert list(parameters) == ["self", "task_id", "step_id", "placement"]
    assert parameters["placement"].annotation == "PlacementDecision"
    assert "`execute(task_id, step_id, *, placement: PlacementDecision)`" in adr_text()


def test_the_method_row_is_the_one_the_orchestrator_has() -> None:
    ((owner, name, _, writes_audit),) = rows(METHOD_ROW, adr_text())

    assert (owner, name) == (DeviceOrchestrator.__name__, "confirm")
    assert callable(DeviceOrchestrator.confirm)
    assert writes_audit == "no"
    assert "_audit" not in inspect.getsource(DeviceOrchestrator.confirm)


def test_the_error_row_is_the_error_the_code_raises() -> None:
    ((name, module, _),) = rows(ERROR_ROW, adr_text())

    assert name == NotPlacedError.__name__
    assert module == NotPlacedError.__module__
    assert not issubclass(NotPlacedError, ValueError)  # §3: it is not a malformed value


def test_the_two_rules_are_registered_under_the_names_the_adr_gives_them() -> None:
    documented = rows(RULE_ROW, adr_text())

    assert [number for number, *_ in documented] == ["30", "31"]
    for _, name, *_ in documented:
        assert any(name in inspect.getsource(check) for check in RULES.values()), name


@pytest.mark.parametrize("key", ["placement-builders", "constant-time-token"])
def test_each_new_rule_has_an_entry_in_rules_that_holds(key: str) -> None:
    assert key in RULES
    assert RULES[key](PACKAGE_ROOT) == []


def test_the_conseguenze_count_the_rules_the_code_has() -> None:
    """ADR 0026 said thirty-one, and thirty-one is still checkable — by number, not by total.

    An immutable document cannot keep counting a growing collection: M10.1 added three rules, and
    a literal ``len(RULES) == 31`` would have made this test fail for a document that never became
    wrong. What ADR 0026 actually claimed is *"the architecture rules go from twenty-nine to
    **thirty-one**"*, and that claim is about the rules numbered up to 31 — which every rule
    declares in its own docstring, so the count is derived from the code rather than restated.

    The count of *today* is pinned by the newest ADR that changed it (``test_adr_perception.py``).
    The thirteen import-linter contracts stay a plain equality: nothing since has added one, and
    the day something does, its ADR will say so.
    """
    conseguenze = adr_text().split("## Conseguenze", 1)[1]

    assert "**trentuno**" in conseguenze
    assert len(_rules_up_to(31)) == 31
    assert "**tredici**" in conseguenze


def _rules_up_to(highest: int) -> list[str]:
    """The rules whose declared number is at most ``highest``, read from their docstrings."""
    numbered = []
    for key, check in RULES.items():
        found = re.search(r"Rule (\d+)", inspect.getdoc(check) or "")
        assert found is not None, f"{key} does not say which rule number it is"
        if int(found.group(1)) <= highest:
            numbered.append(key)
    return numbered


# --------------------------------------------------------------------------------------
# §2–§4: what the decision carries, and who checks it
# --------------------------------------------------------------------------------------


def test_the_decision_carries_the_question_the_adr_says_it_carries() -> None:
    """§2: a bare id says "here" without saying "for what"; these are the fields that fix that."""
    assert set(PlacementDecision._fields) == {
        "created_at",
        "task_id",
        "step_id",
        "requirements",
        "device",
        "scores",
        "reason",
    }
    for field in ("created_at", "task_id", "step_id", "requirements"):
        assert f"    {field}:" in adr_text(), field


def test_the_three_refusals_of_ensure_placed_are_the_three_the_adr_lists() -> None:
    """§3: the table has three numbered rows, and the function has three ``raise``."""
    documented = [line for line in adr_text().splitlines() if REFUSAL_ROW.match(line)]
    source = inspect.getsource(ensure_placed)

    assert [REFUSAL_ROW.match(line).group(1) for line in documented] == ["1", "2", "3"]  # type: ignore[union-attr]
    assert source.count("raise NotPlacedError") == 3


def test_who_chooses_writes_and_who_only_looks_does_not() -> None:
    """§4 and §10: the criterion, not the case — ``chi sceglie scrive, non chi tocca``.

    Both halves are asserted, because half of it is not a criterion: ``place`` decides and writes,
    ``confirm`` answers "does it still hold?" and does not. The day ``confirm`` can replace the
    node it will be choosing, and §10 already says what it must do then.
    """
    assert "_audit" not in inspect.getsource(DeviceOrchestrator.confirm)
    assert "_audit" in inspect.getsource(DeviceOrchestrator.place)
    assert "non scrive un evento di audit" in adr_text().lower()
    assert "chi sceglie scrive, non chi tocca" in adr_text().lower()


# --------------------------------------------------------------------------------------
# The declared limits
# --------------------------------------------------------------------------------------


def test_the_vacuous_filter_is_declared_and_still_vacuous() -> None:
    """§7: the DEGRADED filter cannot fire while the catalogue stops below ``UNGUARDED_RISK``."""
    assert UNGUARDED_RISK > MAX_RISK
    assert "il filtro `degraded` è vacuo" in adr_text().lower()


def test_the_declared_constraints_name_what_they_defer() -> None:
    constraints = adr_text().split("Vincoli dichiarati", 1)[1]

    for deferred in ("Fase 12", "in-process", "tamper-evidence", "authorization_uses", "M9.2"):
        assert deferred in constraints, deferred


def test_the_review_addition_keeps_the_decision_and_adds_only_its_reason() -> None:
    """§10 is an addition, not a rewrite: §4 still says what it said (as ADR 0006 §12–§13 do)."""
    text = adr_text()

    assert "## 10. Aggiunta in review" in text
    assert text.index("## 4. La ripresa") < text.index("## 10. Aggiunta in review")
    assert "La decisione del §4 non cambia" in text


def test_a_drifted_table_is_detected() -> None:
    """The tests above are worth their runtime only if a wrong row would fail them.

    Three drifts, one per table, each checked against the same expression the real test uses.
    """
    text = adr_text()

    renamed_error = text.replace("| `NotPlacedError` |", "| `NotPlacedYetError` |")
    ((name, _, _),) = rows(ERROR_ROW, renamed_error)
    assert name != NotPlacedError.__name__

    audited_confirm = text.replace(
        "| `DeviceOrchestrator` | `confirm` | giudica il nodo di uno step già avviato, "
        "invece di sceglierne uno | no |",
        "| `DeviceOrchestrator` | `confirm` | giudica il nodo di uno step già avviato, "
        "invece di sceglierne uno | sì |",
    )
    ((*_, writes_audit),) = rows(METHOD_ROW, audited_confirm)
    assert writes_audit == "sì"  # and the real test asserts "no"

    dropped_rule = "\n".join(line for line in text.splitlines() if not line.startswith("| 31 `"))
    assert [number for number, *_ in rows(RULE_ROW, dropped_rule)] == ["30"]
