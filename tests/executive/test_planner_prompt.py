"""What leaves for the call that writes a plan, and nothing else (M14.2, ADR 0058; decision F).

Out go the goal of the task, the Planner's instructions and the catalogue **derived from the
registries** — never a list written by hand: a capability added to the registries is in the prompt
and in the schema. Not the declared scopes (sites, folders, programs: the user's, decision 11), not
the devices (decision E), not the context (rule 39, contract 15). And ``parameters`` carries the
Planner's ``max_output_tokens`` (decision 14), whose worst case ADR 0058 writes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ela.domain import CapabilityId
from ela.executive import planner as planner_module
from ela.executive.planner import (
    PLANNING_OUTPUT_TOKENS,
    PLANNING_TASK_TYPE,
    answer_schema,
    catalogue,
    instructions,
    planning_arguments,
)
from ela.permissions import CapabilityRegistry, catalogue_v01
from ela.permissions.capabilities import browser_read, fs_read, terminal_run
from ela.testing.fakes import (
    FakeClock,
    FakeIdGenerator,
    FakeTool,
    FakeToolRegistry,
    FakeVerifier,
    FakeVerifierRegistry,
)
from tests.executive.planning import GOAL, Planned
from tests.permissions.support import ECHO

TASK_TYPES = ("analysis", "planning", "routine")


@pytest.fixture
def world(tmp_path: Path) -> Planned:
    return Planned(tmp_path / "workspace")


def entries_of(world: Planned) -> Any:
    return catalogue(capabilities=world.registry, tools=world.tools, verifiers=world.verifiers)


async def test_the_arguments_are_these_five_and_nothing_else(world: Planned) -> None:
    task = await world.task()
    entries = entries_of(world)

    arguments = planning_arguments(task, entries, task_types=TASK_TYPES)

    assert set(arguments) == {"input", "instructions", "purpose", "task_type", "parameters"}
    assert arguments["input"] == task.goal == GOAL
    assert arguments["task_type"] == PLANNING_TASK_TYPE == "planning"
    assert arguments["parameters"] == {"max_output_tokens": PLANNING_OUTPUT_TOKENS}
    assert PLANNING_OUTPUT_TOKENS == 16384
    assert arguments["instructions"] == instructions(entries, task_types=TASK_TYPES)


async def test_the_purpose_names_the_task_and_carries_no_content(world: Planned) -> None:
    """``purpose`` travels into the audit (ADR 0021): the id of the task, not its goal."""
    task = await world.task("un obiettivo personale")

    arguments = planning_arguments(task, entries_of(world), task_types=TASK_TYPES)

    assert arguments["purpose"] == f"the plan of task {task.id}"
    assert "personale" not in str(arguments["purpose"])


def test_the_catalogue_is_what_has_a_tool_and_a_verifier(world: Planned) -> None:
    """What the executor would run: v0.1's three, each with its verifier's whole vocabulary."""
    entries = entries_of(world)

    assert [entry.spec.id for entry in entries] == [
        "core.echo",
        "workspace.write_note",
        "model.complete",
    ]
    assert entries[2].conditions == ("model.answered", "model.routed_as_asked")


def test_a_capability_added_to_the_registries_is_in_the_prompt_and_in_the_schema() -> None:
    """Derived, never written by hand (decision F): the test adds one and sees it."""
    added = ECHO.model_copy(update={"id": CapabilityId("demo.added"), "description": "Added."})
    clock, ids = FakeClock(), FakeIdGenerator()
    entries = catalogue(
        capabilities=CapabilityRegistry((*catalogue_v01().specs(), added)),
        tools=FakeToolRegistry([FakeTool(added.id, clock, ids)]),
        verifiers=FakeVerifierRegistry([FakeVerifier(added.id, conditions=("demo.held",))]),
    )

    assert [entry.spec.id for entry in entries] == ["demo.added"]
    assert "demo.added" in instructions(entries, task_types=TASK_TYPES)
    assert "demo.held" in instructions(entries, task_types=TASK_TYPES)
    step = answer_schema(entries)["properties"]["plan"]["properties"]["steps"]["items"]
    assert step["properties"]["capability"]["enum"] == ["demo.added"]


def test_a_capability_without_a_tool_or_a_verifier_is_not_offered() -> None:
    clock, ids = FakeClock(), FakeIdGenerator()
    entries = catalogue(
        capabilities=CapabilityRegistry((ECHO,)),
        tools=FakeToolRegistry([FakeTool(ECHO.id, clock, ids)]),
        verifiers=FakeVerifierRegistry([]),
    )

    assert entries == ()


def test_the_declared_scopes_never_leave() -> None:
    """Sites, folders and programs are the user's (decision 11): not in the prompt."""
    sentinels = ("secret-site.example", "secret/folder", "bin/secret-program")
    specs = (browser_read([sentinels[0]]), fs_read(sentinels[1]), terminal_run([sentinels[2]]))
    clock, ids = FakeClock(), FakeIdGenerator()
    entries = catalogue(
        capabilities=CapabilityRegistry(specs),
        tools=FakeToolRegistry([FakeTool(spec.id, clock, ids) for spec in specs]),
        verifiers=FakeVerifierRegistry([FakeVerifier(spec.id) for spec in specs]),
    )

    said = instructions(entries, task_types=TASK_TYPES)

    assert [entry.spec.id for entry in entries] == [spec.id for spec in specs]
    for sentinel in sentinels:
        assert sentinel not in said
    assert sentinels[0] not in json.dumps(answer_schema(entries))


def test_the_task_types_are_the_routing_table_s(world: Planned) -> None:
    said = instructions(entries_of(world), task_types=TASK_TYPES)

    for task_type in TASK_TYPES:
        assert task_type in said


def test_the_instructions_say_when_there_is_no_plan(world: Planned) -> None:
    """Decision 16: no_plan for an effect in the world that no capability produces, and never a
    plan that talks about the goal instead of doing it."""
    said = instructions(entries_of(world), task_types=TASK_TYPES)

    assert "no_plan" in said
    assert "an effect in the world that no capability of the catalogue produces" in said
    assert "talks about the goal instead of doing it" in said


def test_the_schema_has_no_field_that_chooses_where_or_what_the_catalogue_decides(
    world: Planned,
) -> None:
    """Decisions C and E: the model does not write risk, authorization, traits or a machine."""
    schema = answer_schema(entries_of(world))
    step = schema["properties"]["plan"]["properties"]["steps"]["items"]

    assert set(step["properties"]) == {
        "name",
        "goal",
        "capability",
        "arguments",
        "after",
        "expected_result",
        "success_conditions",
    }
    assert set(schema["properties"]) == {"plan", "no_plan"}
    assert set(schema["properties"]["plan"]["properties"]) == {"steps"}


def test_every_object_of_the_schema_is_closed_but_the_arguments(world: Planned) -> None:
    """Decision D: closed everywhere the Planner decides the shape; the arguments are closed by
    the input schema of their capability."""
    schema = answer_schema(entries_of(world))
    step = schema["properties"]["plan"]["properties"]["steps"]["items"]

    assert schema["additionalProperties"] is False
    assert schema["properties"]["plan"]["additionalProperties"] is False
    assert schema["properties"]["no_plan"]["additionalProperties"] is False
    assert step["additionalProperties"] is False
    assert "additionalProperties" not in step["properties"]["arguments"]


async def test_no_device_and_no_context_reach_the_planner(world: Planned) -> None:
    """Decision E and rule 39: the Planner holds no device registry and no context."""
    held = vars(world.planner).values()

    names = {type(value).__name__ for value in held}
    assert not {name for name in names if "Device" in name or "Context" in name}
    source = Path(planner_module.__file__).read_text(encoding="utf-8")
    assert "ContextSnapshot" not in source
    assert "DeviceRegistry" not in source
