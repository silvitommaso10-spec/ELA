"""The Planner (spec §13): from the goal of a task, one call of the model, a plan — or a reason.

M14.2, ADR 0058. **There is no second door** (decision A): the Planner never calls a provider.
For the task to plan — the **parent** — it creates a task of its own, the **planning task**, the
child of the parent (the first producer of ``parent_id``), with a plan of **one**
``model.complete`` step that the Planner writes itself, and lets the runner walk it like any other.
So the call goes the road of every call: the Guardian decides on the catalogue's spec and asks, the
cap of ADR 0057 denies before the question what a yes could not let out and reserves the rest in
the ``STARTED``, the yes mints a grant of one use, ``ModelCompleteTool`` calls, the verifier
verifies, the audit records. No new transition in ADR 0004, no new source of ``deny_by_cap``.

What the model wrote is **data that comes from outside** (decision B). It is read strictly —
one JSON object and nothing else, an unknown key a refused plan with the key named (decision D) —
and validated **before the door** with the functions the Guardian, the registry, the verifier and
the router already use: :func:`~ela.executive.readiness.readiness`, the executor's own
preconditions; :func:`~ela.permissions.validate_arguments`, the Guardian's; the router's check of
a ``task_type``; :meth:`~ela.tasks.graph.TaskGraph.from_plan`. ``risk`` and
``requires_authorization`` are written from the catalogue, never by the model (decision C); no
field says where a step runs, and the closed vocabulary of the traits is empty (decision E). A
plan that passes enters by the door of a plan written by hand — ``engine.plan``, then ``queue`` —
and **the Planner does not start it** (decision H). One that does not ends the parent ``FAILED``,
with a reason that names the step by position and the constraint, never a value (ADR 0055).

**One call, no loop** (decision G): one planning task per parent, and every end of it either plans
the parent or closes it; re-planning is a new task, a new gesture, a new call.

**What leaves** (decision F): the goal of the parent, the Planner's instructions, and the catalogue
derived from the registries — never the declared scopes (decision 11), the devices or the context
(rule 39, contract 15).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Final, NamedTuple
from uuid import UUID, uuid5

from ela.domain import (
    Approval,
    ApprovalStatus,
    CapabilityId,
    CapabilitySpec,
    ErrorMetadata,
    ExecutionStatus,
    JsonValue,
    PlanAuthor,
    PlanAuthorKind,
    PlanId,
    StepId,
    Task,
    TaskId,
    TaskPlan,
    TaskState,
    TaskStep,
    is_text,
)
from ela.executive.errors import RunnerError
from ela.executive.readiness import Unready, readiness
from ela.executive.runner import TaskRunner
from ela.permissions import InvalidArgumentsError, validate_arguments
from ela.permissions.capabilities import MODEL_COMPLETE, SCHEMA_VALIDATOR
from ela.ports import (
    ROUTING_UNKNOWN_TASK_TYPE,
    ApprovalStore,
    CapabilityRegistryPort,
    ExecutionResultStore,
    ModelRouterPort,
    NotFoundError,
    RoutingError,
    TaskRepository,
    ToolRegistryPort,
    VerifierRegistryPort,
)
from ela.tasks.engine import TERMINAL_STATES, TaskEngine, child_id
from ela.tasks.errors import GraphError
from ela.tasks.graph import TaskGraph

__all__ = [
    "PLANNER_CALL_FAILED",
    "PLANNER_CODES",
    "PLANNER_INVALID_ARGUMENTS",
    "PLANNER_MALFORMED",
    "PLANNER_NOT_A_GRAPH",
    "PLANNER_NOT_JSON",
    "PLANNER_NO_PLAN",
    "PLANNER_TRUNCATED",
    "PLANNER_UNANSWERED",
    "PLANNER_UNVERIFIABLE",
    "PLANNING",
    "PLANNING_OUTPUT_TOKENS",
    "PLANNING_TASK_TYPE",
    "Draft",
    "Entry",
    "NoPlan",
    "Planner",
    "Planning",
    "PlanningError",
    "PlanningOutcome",
    "Refused",
    "answer_schema",
    "catalogue",
    "drafted_plan",
    "instructions",
    "is_planning_task",
    "planning_arguments",
    "planning_id",
    "read_answer",
]

PLANNING: Final = "planning"
"""The key of the planning task among the children of its parent (``child_id``)."""

PLANNING_TASK_TYPE: Final = "planning"
"""The ``task_type`` of the call: the route of §25 for «pianificazione complessa» (Opus 5.5)."""

PLANNING_OUTPUT_TOKENS: Final = 16384
"""``max_output_tokens`` of the call (decision 14 of the review). Opus 5.5 always thinks, and the
thinking is inside ``max_tokens``: with the default of 4096 a plan cut short is a call paid for and
a step of the proof to redo. With ADR 0057's table the worst case of a planning is **4.262144 USD**
(``tests/executive/test_planner_worst_case.py`` works it out with ``WorstCase``, not by hand)."""

PLANNER_TRUNCATED: Final = "planner.truncated"
"""The answer stopped at ``max_tokens``: an answer that did not end is not read."""
PLANNER_NOT_JSON: Final = "planner.not_json"
"""The answer is not one JSON object and nothing else — a sentence, a code fence, an array."""
PLANNER_MALFORMED: Final = "planner.malformed"
"""The answer does not have the shape of a plan: an unknown key, a missing one, a wrong type."""
PLANNER_UNVERIFIABLE: Final = "planner.unverifiable"
"""A step the executor would refuse: its capability, its tool, its verifier, its conditions."""
PLANNER_INVALID_ARGUMENTS: Final = "planner.invalid_arguments"
"""A step whose arguments do not satisfy its capability's input schema, or name no route."""
PLANNER_NOT_A_GRAPH: Final = "planner.not_a_graph"
"""Steps named alike, a step after one that is not in the plan, a circle."""
PLANNER_NO_PLAN: Final = "planner.no_plan"
"""The model answered that the catalogue cannot do it: an answer, not an error of the model."""
PLANNER_CALL_FAILED: Final = "planner.call_failed"
"""The planning task failed: the call, its verification, its route."""
PLANNER_UNANSWERED: Final = "planner.unanswered"
"""The question of the planning task expired with no answer."""

PLANNER_CODES: Final = frozenset(
    {
        PLANNER_TRUNCATED,
        PLANNER_NOT_JSON,
        PLANNER_MALFORMED,
        PLANNER_UNVERIFIABLE,
        PLANNER_INVALID_ARGUMENTS,
        PLANNER_NOT_A_GRAPH,
        PLANNER_NO_PLAN,
        PLANNER_CALL_FAILED,
        PLANNER_UNANSWERED,
    }
)
"""Every code a parent can fail with because of its planning, and nothing else."""

PLANNED_REASON: Final = "planned by ELA's Planner"
"""The reason of the ``queue`` of a parent the model planned: the counterpart of the route's."""

NAMED_MAX: Final = 40
"""How much of a key the model wrote a reason quotes: the key, cut — never a value (§57)."""

NAME_PATTERN: Final = r"^[a-z][a-z0-9_-]{0,31}$"
"""The local name of a step, which ``after`` cites: the Planner mints the ids."""

_NAMESPACE: Final = UUID("2b6c8f0e-4d1a-4e7b-9c3f-7a5d1e8b0c42")
"""Of the ids the Planner mints for the plans it writes: derived, so a second ``settle`` of the
same answer writes the same plan — the engine's no-op — and never a second one."""

INSTRUCTIONS: Final = """\
You are the Planner of ELA, a personal assistant. You turn the goal of one task into a plan of \
steps. ELA's executor runs the steps one by one, each through exactly one capability of the \
catalogue below, and ELA's Guardian decides on every step when it runs: you write the plan, you do \
not act.

Rules:
1. Answer with one JSON object and nothing else: no text before or after it, no code fence.
2. The object has exactly one key: "plan" or "no_plan". It follows the answer schema below.
3. Write "no_plan", with a short reason, when the goal asks for an effect in the world that no \
capability of the catalogue produces. Never write a plan that talks about the goal instead of \
doing it — a note, a spoken sentence or a question to a model about an effect the plan cannot \
produce does not produce it.
4. Each step uses exactly one capability of the catalogue, and its "arguments" follow the input \
schema of that capability.
5. Each step names at least one success condition, from the conditions of its capability.
6. The arguments are written now: a step cannot use what another step produced.
7. Use the places the goal names — a site, a folder, a path, a program — as the goal writes them. \
Do not invent places.
8. A step never says on which machine it runs: ELA chooses the machine.
9. "name" is a short name of yours for the step; "after" lists the names of the steps that must \
finish before it.
"""
"""What the model is told, beside the catalogue and the schema (decisions F and 16)."""


class PlanningError(RunnerError):
    """The Planner cannot plan this task (a ``409``, like the runner's own refusals)."""


class PlanningOutcome(StrEnum):
    """Where the planning of a task stands, as the route answers it."""

    WAITING_APPROVAL = "waiting_approval"
    """The planning task asks for the user's yes to its call."""
    PLANNING = "planning"
    """The planning task is on its way — queued after the yes, or running."""
    PLANNED = "planned"
    """The parent has its plan, written by the model, and is ``QUEUED``: the run is the user's."""
    DENIED = "denied"
    """The call was denied — by the user's no or by the month's cap —, and so is the parent."""
    FAILED = "failed"
    """No plan: refused, answered «no plan», or the call failed or went unanswered."""
    CANCELLED = "cancelled"
    """Somebody stopped the planning."""
    EXPIRED = "expired"
    """The parent's deadline passed."""


_ENDS: Final[Mapping[TaskState, PlanningOutcome]] = {
    TaskState.DENIED: PlanningOutcome.DENIED,
    TaskState.FAILED: PlanningOutcome.FAILED,
    TaskState.CANCELLED: PlanningOutcome.CANCELLED,
    TaskState.EXPIRED: PlanningOutcome.EXPIRED,
}


class Planning(NamedTuple):
    """The planning of one task, as it stands: what the route answers and the CLI prints.

    ``no_plan`` is the model's reason for «no plan», read from the planning task's result — the
    private store — and never from the audit, which does not have it (ADR 0021 §7). ``problems``
    are the constraints a refused plan broke, each a sentence without a value.
    """

    task: Task
    planning_task: Task | None
    outcome: PlanningOutcome
    reason: str | None = None
    approval: Approval | None = None
    no_plan: str | None = None
    problems: tuple[str, ...] = ()


class Entry(NamedTuple):
    """A capability as the model reads it: the catalogue's spec, and its verifier's conditions."""

    spec: CapabilitySpec
    conditions: tuple[str, ...]


class Draft(NamedTuple):
    """One step as the model wrote it, after the schema and before the checks."""

    name: str
    goal: str
    capability: str
    arguments: Mapping[str, Any]
    after: tuple[str, ...]
    expected_result: str
    success_conditions: tuple[str, ...]


@dataclass(frozen=True)
class NoPlan:
    """The model answered that the catalogue cannot do it, and why.

    A dataclass and not a tuple, like :class:`Refused`: what :func:`read_answer` returns is told
    apart from the tuple of drafts by its type.
    """

    reason: str


@dataclass(frozen=True)
class Refused:
    """A plan refused before the door: the first constraint that fell, and all those found."""

    code: str
    message: str
    problems: tuple[str, ...] = ()


def planning_id(parent_id: TaskId) -> TaskId:
    """The id of the planning task of ``parent_id``: one per parent, the same at every retry."""
    return child_id(parent_id, PLANNING)


def is_planning_task(task: Task) -> bool:
    """Whether ``task`` is the planning task of its parent: by its id, never by a label."""
    return task.parent_id is not None and task.id == planning_id(task.parent_id)


# ----------------------------------------------------------------------------------------
# What leaves: the catalogue, the schema, the instructions, the arguments (decision F)
# ----------------------------------------------------------------------------------------


def catalogue(
    *,
    capabilities: CapabilityRegistryPort,
    tools: ToolRegistryPort,
    verifiers: VerifierRegistryPort,
) -> tuple[Entry, ...]:
    """The capabilities the executor would run — a tool and a verifier each —, in the registry's
    order, with the whole vocabulary of their verifier. Derived, never a list written by hand."""
    entries: list[Entry] = []
    for spec in capabilities.specs():
        try:
            tools.get(spec.id)
            verifier = verifiers.get(spec.id)
        except NotFoundError:
            continue
        entries.append(Entry(spec, tuple(sorted(verifier.conditions))))
    return tuple(entries)


def answer_schema(entries: Sequence[Entry]) -> dict[str, Any]:
    """The JSON Schema of the answer: **one** object, the one the instructions show and the one
    the answer is validated against. That it holds exactly one of ``plan`` and ``no_plan`` the
    instructions say and :func:`read_answer` checks: as a schema it would hide an unknown key
    behind a count. Closed everywhere the Planner decides the shape; the
    ``arguments`` are closed by the input schema of their capability. No ``risk``, no
    ``requires_authorization``, no traits, no machine (decisions C and E)."""
    step = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "pattern": NAME_PATTERN},
            "goal": {"type": "string", "minLength": 1},
            "capability": {"enum": [str(entry.spec.id) for entry in entries]},
            "arguments": {"type": "object"},
            "after": {"type": "array", "items": {"type": "string"}},
            "expected_result": {"type": "string", "minLength": 1},
            "success_conditions": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        },
        "required": [
            "name",
            "goal",
            "capability",
            "arguments",
            "expected_result",
            "success_conditions",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "plan": {
                "type": "object",
                "properties": {"steps": {"type": "array", "items": step, "minItems": 1}},
                "required": ["steps"],
                "additionalProperties": False,
            },
            "no_plan": {
                "type": "object",
                "properties": {"reason": {"type": "string", "minLength": 1}},
                "required": ["reason"],
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }


def _described(entry: Entry, task_types: Sequence[str]) -> dict[str, Any]:
    """One capability for the model: never its ``scope``, which is the user's (decision 11)."""
    spec = entry.spec
    described: dict[str, Any] = {
        "capability": str(spec.id),
        "description": spec.description,
        "risk": spec.risk.value,
        "asks_the_user": spec.requires_authorization,
        "input_schema": spec.model_dump(mode="json")["input_schema"],
        "success_conditions": list(entry.conditions),
    }
    if spec.id == MODEL_COMPLETE:
        described["task_types"] = list(task_types)
    return described


def instructions(entries: Sequence[Entry], *, task_types: Sequence[str]) -> str:
    """The Planner's instructions, then the catalogue and the schema, both derived."""
    listed = json.dumps([_described(entry, task_types) for entry in entries], ensure_ascii=False)
    schema = json.dumps(answer_schema(entries), ensure_ascii=False)
    return (
        f"{INSTRUCTIONS}\nCatalogue (JSON):\n{listed}\n\nAnswer schema (JSON Schema):\n{schema}\n"
    )


def planning_arguments(
    task: Task, entries: Sequence[Entry], *, task_types: Sequence[str]
) -> dict[str, JsonValue]:
    """The arguments of the call, and they are everything that leaves (criterion 8)."""
    return {
        "input": task.goal,
        "instructions": instructions(entries, task_types=task_types),
        "purpose": f"the plan of task {task.id}",
        "task_type": PLANNING_TASK_TYPE,
        "parameters": {"max_output_tokens": PLANNING_OUTPUT_TOKENS},
    }


# ----------------------------------------------------------------------------------------
# Reading the answer: strictly (decision D)
# ----------------------------------------------------------------------------------------


class _Twice(ValueError):
    """A key written twice in one object: the parser would keep the last, silently."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise _Twice(key)
        seen[key] = value
    return seen


def _constant(name: str) -> Any:
    raise ValueError(f"{name} is not JSON")


def _named(key: str) -> str:
    """A key the model wrote, as a reason may quote it: cut, and only the key."""
    cut = key[:NAMED_MAX]
    return cut if cut.isidentifier() else json.dumps(cut, ensure_ascii=True)


def _violations(error: Any) -> list[str]:
    """What one error of the schema says, as paths and constraints — never a value."""
    path = error.json_path
    if error.validator == "additionalProperties":
        known = set(error.schema.get("properties", {}))
        return [
            f"{path}.{_named(str(key))} is not a key of the answer"
            for key in error.instance
            if key not in known
        ]
    if error.validator == "required":
        return [
            f"{path}.{key} is missing" for key in error.validator_value if key not in error.instance
        ]
    said = {
        "enum": "is not a capability of the catalogue",
        "type": f"is not of type {error.validator_value}",
        "minItems": "is empty",
        "minLength": "is empty",
        "pattern": "is not a short name of lowercase letters, digits, - and _",
    }
    return [f"{path} {said.get(error.validator, f'breaks {error.validator}')}"]


def read_answer(
    text: str, finish_reason: str | None, schema: Mapping[str, Any]
) -> tuple[Draft, ...] | NoPlan | Refused:
    """The answer of the model: drafts, a «no plan», or a refusal of what it wrote."""
    if finish_reason == "max_tokens":
        return Refused(
            PLANNER_TRUNCATED,
            f"the answer stopped at max_tokens ({PLANNING_OUTPUT_TOKENS}) before its end",
        )
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except _Twice:
        return Refused(PLANNER_MALFORMED, "the answer writes a key twice in one object")
    except ValueError:
        return Refused(PLANNER_NOT_JSON, "the answer is not one JSON object and nothing else")
    if not isinstance(value, dict) or not is_text(value):
        return Refused(PLANNER_NOT_JSON, "the answer is not one JSON object of text")
    errors = sorted(SCHEMA_VALIDATOR(dict(schema)).iter_errors(value), key=lambda e: e.json_path)
    problems = tuple(said for error in errors for said in _violations(error))
    if len(value) != 1 and not problems:
        problems = ("$ has both plan and no_plan" if value else "$ has neither plan nor no_plan",)
    if problems:
        return Refused(
            PLANNER_MALFORMED,
            f"the answer does not have the shape of a plan: {problems[0]}",
            problems,
        )
    if "no_plan" in value:
        return NoPlan(value["no_plan"]["reason"])
    return tuple(
        Draft(
            name=one["name"],
            goal=one["goal"],
            capability=one["capability"],
            arguments=one["arguments"],
            after=tuple(one.get("after", ())),
            expected_result=one["expected_result"],
            success_conditions=tuple(one["success_conditions"]),
        )
        for one in value["plan"]["steps"]
    )


# ----------------------------------------------------------------------------------------
# Before the door: the functions of who decides (decision B)
# ----------------------------------------------------------------------------------------


def _step_id(plan_id: PlanId, index: int) -> StepId:
    return StepId(uuid5(_NAMESPACE, f"{plan_id}/step/{index}"))


def drafted_plan(
    drafts: Sequence[Draft],
    *,
    task_id: TaskId,
    goal: str,
    plan_id: PlanId,
    created_at: datetime,
    author: PlanAuthor,
    capabilities: CapabilityRegistryPort,
    tools: ToolRegistryPort,
    verifiers: VerifierRegistryPort,
    router: ModelRouterPort,
) -> TaskPlan | Refused:
    """The drafts as a plan of ``task_id``, or the refusal of the first constraint that fell.

    ``goal`` is the plan's, and it is the task's: the model writes no goal of the plan, so no
    sentence of the model enters the payload of ``PLAN_CREATED`` (ADR 0058).

    Per step, in order: the executor's preconditions, then the arguments — the Guardian's
    ``validate_arguments`` on the **registered** spec, and for ``model.complete`` the router's own
    check of the ``task_type`` (ADR 0022 §6). Then the graph: names, ``after``, circles. The step is
    named by its position and its capability — a catalogue id, already validated —, the constraint
    by its words; never a value the model wrote.
    """
    count = len(drafts)
    ids = {draft.name: _step_id(plan_id, index) for index, draft in enumerate(drafts)}
    problems: list[str] = []
    codes: list[str] = []
    steps: list[TaskStep] = []
    for index, draft in enumerate(drafts):
        spec = capabilities.get(CapabilityId(draft.capability))
        where = f"step {index + 1} of {count} ({spec.id})"
        built = TaskStep(
            id=_step_id(plan_id, index),
            created_at=created_at,
            goal=draft.goal,
            required_capabilities=(spec.id,),
            arguments=dict(draft.arguments),
            dependencies=tuple(ids[name] for name in draft.after if name in ids),
            risk=spec.risk,
            expected_result=draft.expected_result,
            success_conditions=draft.success_conditions,
            requires_authorization=spec.requires_authorization,
        )
        steps.append(built)
        ready = readiness(built, capabilities=capabilities, tools=tools, verifiers=verifiers)
        if isinstance(ready, Unready):
            codes.append(PLANNER_UNVERIFIABLE)
            problems.append(f"{where}: {ready.said}")
            continue
        try:
            validate_arguments(spec, built.arguments)
        except InvalidArgumentsError as error:
            paths = ", ".join(sorted({one.partition(": ")[0] for one in error.errors}))
            codes.append(PLANNER_INVALID_ARGUMENTS)
            problems.append(f"{where}: {paths} does not match the input schema of {spec.id}")
            continue
        if spec.id == MODEL_COMPLETE:
            unrouted = _unrouted(router, built.arguments)
            if unrouted is not None:
                codes.append(PLANNER_INVALID_ARGUMENTS)
                problems.append(f"{where}: {unrouted}")
    graph = _graph(drafts, ids)
    if graph is not None:
        codes.append(PLANNER_NOT_A_GRAPH)
        problems.append(graph)
    if problems:
        return Refused(codes[0], problems[0], tuple(problems))
    plan = TaskPlan(
        id=plan_id,
        created_at=created_at,
        task_id=task_id,
        goal=goal,
        steps=tuple(steps),
        author=author,
    )
    try:
        TaskGraph.from_plan(plan)
    except GraphError:
        return Refused(PLANNER_NOT_A_GRAPH, "the steps wait for one another in a circle")
    return plan


def _unrouted(router: ModelRouterPort, arguments: Mapping[str, Any]) -> str | None:
    """The router's own word on a ``task_type`` it does not know; nothing on anything else — a
    route with no usable provider is the run's to refuse, with the cap's reason (ADR 0057 §2)."""
    task_type, hint = arguments.get("task_type"), arguments.get("model_hint")
    try:
        router.route(
            task_type if isinstance(task_type, str) else None,
            hint if isinstance(hint, str) else None,
        )
    except RoutingError as error:
        if error.code == ROUTING_UNKNOWN_TASK_TYPE:
            return "$.task_type names no route of the routing table"
    return None


def _graph(drafts: Sequence[Draft], ids: Mapping[str, StepId]) -> str | None:
    """Names alike, or a step after one that is not in the plan: the first, by position."""
    count = len(drafts)
    if len(ids) != count:
        return "two steps have the same name"
    for index, draft in enumerate(drafts):
        if any(name not in ids for name in draft.after):
            return f"step {index + 1} of {count} waits for a step that is not in the plan"
    return None


# ----------------------------------------------------------------------------------------
# The Planner: the planning task, and how its end settles the parent
# ----------------------------------------------------------------------------------------


class Planner:
    """Plans a task with one call of the model through a planning task (M14.2, ADR 0058).

    Holds the engine, the runner and the stores to drive the planning task, the three registries
    and the router to validate what comes back, and ``task_types`` — the routing table's
    vocabulary, data the composition root supplies. **No device registry, no context, no
    provider** (decisions A, E, F).
    """

    def __init__(
        self,
        *,
        engine: TaskEngine,
        runner: TaskRunner,
        repository: TaskRepository,
        results: ExecutionResultStore,
        approvals: ApprovalStore,
        capabilities: CapabilityRegistryPort,
        tools: ToolRegistryPort,
        verifiers: VerifierRegistryPort,
        router: ModelRouterPort,
        task_types: Sequence[str],
    ) -> None:
        self._engine = engine
        self._runner = runner
        self._repository = repository
        self._results = results
        self._approvals = approvals
        self._capabilities = capabilities
        self._tools = tools
        self._verifiers = verifiers
        self._router = router
        self._task_types = tuple(task_types)

    def _entries(self) -> tuple[Entry, ...]:
        return catalogue(
            capabilities=self._capabilities, tools=self._tools, verifiers=self._verifiers
        )

    # The gesture ---------------------------------------------------------------------------

    async def plan(self, task_id: TaskId) -> Planning:
        """The planning of ``task_id`` as far as it goes — rientrante, like ``run``.

        A ``CREATED`` task starts planning; its planning task is created, planned and queued if it
        is not there, walked by the runner if it is in the queue — up to its question, or, after
        the yes, through the call —; and its end settles the parent. Asked again, it answers where
        the planning stands and calls nobody.

        :raises PlanningError: the task is a planning task, has a plan of another author, or
            ended without planning.
        """
        task = await self._repository.get(task_id)
        if is_planning_task(task):
            raise PlanningError(
                task_id,
                f"task {task_id} is the planning task of {task.parent_id}: it is planned "
                "by the Planner, not asked for a plan",
            )
        if task.plan_id is not None:
            plan = await self._repository.plan(task_id)
            if plan.author.by is not PlanAuthorKind.MODEL:
                raise PlanningError(
                    task_id, f"the task already has a plan, written by {plan.author.by.value}"
                )
            return await self.settle(task_id)
        if task.state is TaskState.CREATED:
            task = await self._engine.start_planning(task_id)
        if task.state is not TaskState.PLANNING:
            if await self._child(task_id) is not None:
                return await self.settle(task_id)
            raise PlanningError(
                task_id, f"a plan is asked of a CREATED or PLANNING task, not {task.state.value}"
            )
        child = await self._planning_task(task)
        if child.state in (TaskState.QUEUED, TaskState.EXECUTING):
            await self._runner.run(child.id)
        return await self.settle(task_id)

    async def _child(self, task_id: TaskId) -> Task | None:
        try:
            return await self._repository.get(planning_id(task_id))
        except NotFoundError:
            return None

    async def _planning_task(self, parent: Task) -> Task:
        """The planning task of ``parent``: created, planned and queued, once each."""
        child = await self._child(parent.id)
        entries = self._entries()
        if child is None:
            child = await self._engine.create_child(
                parent.id, key=PLANNING, goal=f"plan task {parent.id}: {parent.goal}"
            )
        if child.state is TaskState.CREATED:
            child = await self._engine.start_planning(child.id)
        if child.state is TaskState.PLANNING:
            if child.plan_id is None:
                await self._engine.plan(child.id, self._call(parent, child, entries))
            child = await self._engine.queue(child.id, reason=PLANNED_REASON)
        return child

    def _call(self, parent: Task, child: Task, entries: Sequence[Entry]) -> TaskPlan:
        """The plan of one ``model.complete`` step the planning task runs: written by the Planner's
        code (``PLANNER``), and through the same checks as a plan the model writes."""
        spec = self._capabilities.get(MODEL_COMPLETE)
        conditions = tuple(sorted(self._verifiers.get(MODEL_COMPLETE).conditions))
        plan_id = PlanId(uuid5(_NAMESPACE, f"{child.id}/call"))
        step = TaskStep(
            id=_step_id(plan_id, 0),
            created_at=child.created_at,
            goal=(
                f"plan task {parent.id} «{parent.goal}» — out go the goal, the Planner's "
                f"instructions and the catalogue of {len(entries)} capabilities; no scope, no "
                "device, no context"
            ),
            required_capabilities=(spec.id,),
            arguments=planning_arguments(parent, entries, task_types=self._task_types),
            risk=spec.risk,
            expected_result="a plan of the task, or the reason there is none, as one JSON object",
            success_conditions=conditions,
            requires_authorization=spec.requires_authorization,
        )
        ready = readiness(
            step, capabilities=self._capabilities, tools=self._tools, verifiers=self._verifiers
        )
        if isinstance(ready, Unready):
            raise PlanningError(parent.id, f"the planning call cannot be made: it {ready.said}")
        validate_arguments(spec, step.arguments)
        return TaskPlan(
            id=plan_id,
            created_at=child.created_at,
            task_id=child.id,
            goal=child.goal,
            steps=(step,),
            author=PlanAuthor(by=PlanAuthorKind.PLANNER),
        )

    # The end of the planning task, and the parent ------------------------------------------

    async def settle(self, task_id: TaskId) -> Planning:
        """Plan or close the parent from where its planning task ended; nothing if it has not.

        Idempotent: every write it makes is an engine operation that is a no-op the second time,
        and the plan it attaches has an id derived from the answer it comes from.
        """
        task = await self._repository.get(task_id)
        child = await self._child(task_id)
        if (
            task.state is TaskState.PLANNING
            and task.plan_id is None
            and child is not None
            and child.state in TERMINAL_STATES
        ):
            await self._close(task, child)
        return await self.view(task_id)

    async def _close(self, parent: Task, child: Task) -> None:
        closed = await self._engine.ending(child)
        said = child.state.value if closed is None else closed.reason
        if child.state is TaskState.COMPLETED:
            await self._collect(parent, child)
        elif child.state is TaskState.DENIED:
            await self._engine.deny_by_planning(
                parent.id,
                planning_task_id=child.id,
                reason=f"the planning task {child.id} was denied: {said}",
            )
        elif child.state is TaskState.CANCELLED:
            await self._engine.cancel(
                parent.id, reason=f"the planning task {child.id} was cancelled: {said}"
            )
        else:
            code = PLANNER_UNANSWERED if child.state is TaskState.EXPIRED else PLANNER_CALL_FAILED
            ended = "expired" if child.state is TaskState.EXPIRED else "failed"
            await self._engine.fail(
                parent.id,
                ErrorMetadata(
                    code=code,
                    message=f"the planning task {child.id} {ended}: {said}",
                    retryable=False,
                    details={"planning_task_id": str(child.id)},
                ),
            )

    async def _answer(self, child: Task) -> tuple[Any, Any] | None:
        """The outcome of the planning call, and what the model wrote: the private store."""
        plan = await self._repository.plan(child.id)
        rows = await self._results.for_step(child.id, plan.steps[0].id)
        ended = [row for row in rows if row.status is ExecutionStatus.SUCCEEDED]
        if not ended:
            return None
        outcome = ended[-1]
        text = outcome.output.get("output")
        finish = outcome.output.get("finish_reason")
        read = read_answer(
            text if isinstance(text, str) else "",
            finish if isinstance(finish, str) else None,
            answer_schema(self._entries()),
        )
        return outcome, read

    async def _collect(self, parent: Task, child: Task) -> None:
        answered = await self._answer(child)
        details: dict[str, JsonValue] = {"planning_task_id": str(child.id)}
        if answered is None:
            await self._engine.fail(
                parent.id,
                ErrorMetadata(
                    code=PLANNER_CALL_FAILED,
                    message=f"the planning task {child.id} completed with no answer to read",
                    retryable=False,
                    details=details,
                ),
            )
            return
        outcome, read = answered
        details["result_id"] = str(outcome.id)
        if isinstance(read, NoPlan):
            await self._engine.fail(
                parent.id,
                ErrorMetadata(
                    code=PLANNER_NO_PLAN,
                    message=(
                        "the model wrote no plan for this goal; its reason is in the result of "
                        f"task {child.id}"
                    ),
                    retryable=False,
                    details=details,
                ),
            )
            return
        if isinstance(read, tuple):
            read = self._drafted(parent, outcome, read)
        if isinstance(read, Refused):
            await self._engine.fail(
                parent.id,
                ErrorMetadata(
                    code=read.code,
                    message=read.message,
                    retryable=False,
                    details={**details, "problems": list(read.problems)},
                ),
            )
            return
        await self._engine.plan(parent.id, read)
        await self._engine.queue(parent.id, reason=PLANNED_REASON)

    def _drafted(self, parent: Task, outcome: Any, drafts: tuple[Draft, ...]) -> TaskPlan | Refused:
        model = outcome.output.get("model")
        author = PlanAuthor(
            by=PlanAuthorKind.MODEL,
            result_id=outcome.id,
            model=model if isinstance(model, str) and model else "unknown",
        )
        return drafted_plan(
            drafts,
            task_id=parent.id,
            goal=parent.goal,
            plan_id=PlanId(uuid5(_NAMESPACE, f"{outcome.id}/plan")),
            created_at=outcome.created_at,
            author=author,
            capabilities=self._capabilities,
            tools=self._tools,
            verifiers=self._verifiers,
            router=self._router,
        )

    async def view(self, task_id: TaskId) -> Planning:
        """Where the planning of ``task_id`` stands, read and never written."""
        task = await self._repository.get(task_id)
        child = await self._child(task_id)
        if task.plan_id is not None:
            return Planning(task, child, PlanningOutcome.PLANNED)
        if task.state in _ENDS:
            ended = await self._engine.ending(task)
            assert ended is not None  # every state of _ENDS is one of REASONED
            no_plan, problems = await self._words(child)
            return Planning(
                task, child, _ENDS[task.state], ended.reason, no_plan=no_plan, problems=problems
            )
        if child is not None and child.state is TaskState.WAITING_APPROVAL:
            return Planning(
                task, child, PlanningOutcome.WAITING_APPROVAL, approval=await self._asked(child)
            )
        return Planning(task, child, PlanningOutcome.PLANNING)

    async def _words(self, child: Task | None) -> tuple[str | None, tuple[str, ...]]:
        """The model's reason for «no plan», or the problems of a refused plan: from the private
        store, read again — the audit does not have them (ADR 0021 §7)."""
        if child is None or child.state is not TaskState.COMPLETED:
            return None, ()
        answered = await self._answer(child)
        if answered is None:
            return None, ()
        outcome, read = answered
        parent = await self._repository.get(child.parent_id)  # type: ignore[arg-type]
        if isinstance(read, tuple):
            read = self._drafted(parent, outcome, read)
        if isinstance(read, NoPlan):
            return read.reason, ()
        if isinstance(read, Refused):
            return None, read.problems
        return None, ()

    async def _asked(self, child: Task) -> Approval | None:
        """The question the planning task waits on: its last one still pending."""
        pending = [
            one
            for one in await self._approvals.for_task(child.id)
            if one.status is ApprovalStatus.PENDING
        ]
        return pending[-1] if pending else None

    # The stop, and the start-up ------------------------------------------------------------

    async def stop_planning(self, task_id: TaskId, *, reason: str) -> Task | None:
        """When the parent is stopped, its planning task stops too: a yes given later would pay
        for a plan nobody can attach. ``None`` when there is no live planning task."""
        child = await self._child(task_id)
        if child is None or child.state in TERMINAL_STATES:
            return None
        return await self._engine.cancel(
            child.id, reason=f"the task it plans was stopped: {reason}" if reason else ""
        )

    async def settle_all(self) -> tuple[Planning, ...]:
        """At start-up (decision 13): every parent ``PLANNING`` whose planning task has ended, found
        with a read of the repository — a question that expired in ``recover``, a crash between
        the end of the planning task and ``settle``."""
        settled: list[Planning] = []
        for task in await self._repository.tasks(states=frozenset({TaskState.PLANNING})):
            child = await self._child(task.id)
            if task.plan_id is None and child is not None and child.state in TERMINAL_STATES:
                settled.append(await self.settle(task.id))
        return tuple(settled)
