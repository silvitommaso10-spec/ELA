"""ADR 0018 and the code say the same thing about where a step's arguments live.

The claims worth pinning are few and load-bearing: the field exists on ``TaskStep`` with an empty
default, ``Executor.execute`` no longer takes the arguments and does take a mandatory node, the
plan needs no migration because its steps are one JSON column, and rule 23 is in ``RULES``.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from ela.domain import TaskPlan, TaskStep
from ela.executive import Executor
from tests.architecture.rules import RULES

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0018-step-arguments.md"
RULE_ROW = re.compile(r"^\| (\d+) `([a-z-]+)` \| ([^|]+?) \| ([^|]+?) \|$")
"""§5: the one architecture rule this ADR introduces, by number and by its key in ``RULES``."""


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


# --------------------------------------------------------------------------------------
# §2: the field
# --------------------------------------------------------------------------------------


def test_the_step_carries_its_arguments_and_they_default_to_nothing() -> None:
    field = TaskStep.model_fields["arguments"]
    assert field.annotation == TaskPlan.model_fields["metadata"].annotation
    assert field.default == {}
    assert not field.is_required()
    assert "`TaskStep.arguments: JsonMapping = {}`" in adr_text()


def test_the_arguments_of_a_step_cannot_be_mutated() -> None:
    """A plan editable in place after the Guardian read it is a plan nobody decided about."""
    step = TaskStep.model_validate(
        {
            "id": "00000000-0000-4000-8000-000000000001",
            "created_at": "2026-09-07T10:00:00Z",
            "goal": "g",
            "arguments": {"path": "workspace/notes/a.md"},
            "risk": "LOW",
            "expected_result": "done",
            "requires_authorization": False,
        }
    )
    with pytest.raises(TypeError):
        step.arguments["path"] = "elsewhere"  # type: ignore[index]


def test_the_domain_does_not_validate_the_arguments_against_a_schema() -> None:
    """ADR 0018 §2: validating twice would put the catalogue inside the domain.

    The step takes any JSON mapping, including one no capability would accept; refusing it is
    the Guardian's move, with its ``PERMISSION_DECIDED`` behind it (§27, ADR 0011).
    """
    assert "Nessuna validazione contro `input_schema` nel dominio" in adr_text()
    nonsense = TaskStep.model_validate(
        {
            "id": "00000000-0000-4000-8000-000000000001",
            "created_at": "2026-09-07T10:00:00Z",
            "goal": "g",
            "required_capabilities": ["workspace.write_note"],
            "arguments": {"not_a_property_of_any_schema": 1},
            "risk": "LOW",
            "expected_result": "done",
            "requires_authorization": False,
        }
    )
    assert nonsense.arguments == {"not_a_property_of_any_schema": 1}


def test_a_plan_written_before_m6_3_still_reads() -> None:
    """The claim that lets §2 say "nessuna migrazione": the field is additive inside a JSON
    column, so a row without the key rehydrates on the default."""
    step = TaskStep.model_validate(
        {
            "id": "00000000-0000-4000-8000-000000000001",
            "created_at": "2026-09-07T10:00:00Z",
            "goal": "g",
            "risk": "LOW",
            "expected_result": "done",
            "requires_authorization": False,
        }
    )
    assert step.arguments == {}
    assert "**Nessuna migrazione**" in adr_text()


def test_the_plan_is_still_stored_as_one_json_column() -> None:
    """If this ever stops being true, "nessuna migrazione" stops being true with it."""
    mappers = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "ela"
        / "infrastructure"
        / "persistence"
        / "mappers.py"
    ).read_text(encoding="utf-8")
    assert '"steps": [step.model_dump(mode="json") for step in plan.steps]' in mappers


# --------------------------------------------------------------------------------------
# §4: the signature of the executor
# --------------------------------------------------------------------------------------


def test_execute_takes_no_arguments_and_a_mandatory_node() -> None:
    parameters = inspect.signature(Executor.execute).parameters
    assert "arguments" not in parameters
    assert "approval" not in parameters
    node = parameters["device_id"]
    assert node.kind is inspect.Parameter.KEYWORD_ONLY
    assert node.default is inspect.Parameter.empty
    assert "`execute(task_id, step_id, *, device_id: DeviceId)`" in adr_text()


def test_the_executor_reads_the_arguments_from_the_step() -> None:
    """The property of §1 is structural or it is nothing: the arguments come from the plan the
    retry rereads, not from whoever calls."""
    source = inspect.getsource(Executor.execute)
    assert "arguments = step.arguments" in source


# --------------------------------------------------------------------------------------
# §5: the rule that keeps the arguments out of the audit
# --------------------------------------------------------------------------------------


def test_the_adr_names_the_rule_the_code_registers() -> None:
    (row,) = [m for m in (RULE_ROW.match(line) for line in adr_text().splitlines()) if m]
    assert row.group(1) == "23"
    assert row.group(2) in RULES
    assert row.group(4).strip() == "nessuna"


def test_the_rule_holds_on_the_package_today() -> None:
    package = Path(__file__).resolve().parents[2] / "src" / "ela"
    assert RULES["audit-arguments"](package) == []


# --------------------------------------------------------------------------------------
# §6: the limit, and the condition attached to lifting it
# --------------------------------------------------------------------------------------


def test_the_adr_binds_a_future_reference_to_be_resolved_before_the_guardian() -> None:
    """Asked for explicitly in the review of the M6.3 spec: the additive road is allowed, and it
    is allowed only in the order that keeps "what is authorised is what is executed" true."""
    text = adr_text()
    assert "**Con una condizione che non è negoziabile: la risoluzione avviene PRIMA del" in text
    assert "sarebbe un bypass" in text
