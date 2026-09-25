"""The rules M13.3 writes down, each with the case that makes it fail (ADR 0048).

* **The lock of a task is taken with nothing in between** (T-R1; C10 and R1 of
  ``docs/milestones/M13.3.md``). Two halves: in every function of ``ela.api``, between a check
  ``x in running`` and the ``running.add(x)`` that follows, no ``await``; and every call that
  reaches the executor on a step — the runner's ``run``, the executor's ``begin`` and ``deliver`` —
  comes after a ``running.add`` in the route that makes it, or through a helper of the module whose
  every caller does. One exception, by design: the delivery of an id the Core never minted has no
  task to lock (``api/nodes.py``, ADR 0038 §12).

Each reads the source with ``ast`` and is run against a fabricated module that breaks it: a rule
that only ever passes proves nothing (CLAUDE.md, «Qualità»).
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "ela"
API = PACKAGE / "api"
LOCK = "running"
REACHES_THE_EXECUTOR = frozenset(
    {("runner", "run"), ("executor", "begin"), ("executor", "deliver")}
)
"""``….runner.run(…)``, ``….executor.begin(…)``, ``….executor.deliver(…)``."""
NO_TASK_TO_LOCK = ("deliver_work", "held is None")
"""The route and the test of the branch that delivers an id the Core never minted (ADR 0038 §12)."""


def functions(module: ast.Module) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for node in module.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield node


# ----------------------------------------------------------------------------------------
# Half one: nothing between the check and the insert
# ----------------------------------------------------------------------------------------


def _checks_the_lock(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Compare)
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.In)
        and isinstance(node.comparators[0], ast.Name)
        and node.comparators[0].id == LOCK
    )


def _takes_the_lock(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == LOCK
    )


def awaits_inside_the_lock(source: str) -> list[str]:
    """``function:line`` of every ``await`` between a check of the lock and the insert after it."""
    found: list[str] = []
    for function in functions(ast.parse(source)):
        nodes = list(ast.walk(function))
        checks = sorted(node.lineno for node in nodes if _checks_the_lock(node))
        takes = sorted(node.lineno for node in nodes if _takes_the_lock(node))
        awaits = sorted({node.lineno for node in nodes if isinstance(node, ast.Await)})
        for check in checks:
            after = [take for take in takes if take > check]
            if not after:
                continue
            found.extend(f"{function.name}:{line}" for line in awaits if check < line < after[0])
    return found


# ----------------------------------------------------------------------------------------
# Half two: what reaches the executor on a step does so inside the lock
# ----------------------------------------------------------------------------------------


def _reaches_directly(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Attribute)
        and (node.func.value.attr, node.func.attr) in REACHES_THE_EXECUTOR
    )


def _called_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _no_task_to_lock(function: ast.AST, call: ast.Call) -> bool:
    """Whether ``call`` sits in the declared branch that has no task to lock."""
    name, test = NO_TASK_TO_LOCK
    if not isinstance(function, ast.AsyncFunctionDef | ast.FunctionDef) or function.name != name:
        return False
    return any(
        isinstance(node, ast.If)
        and ast.unparse(node.test) == test
        and any(inner is call for inner in ast.walk(node))
        for node in ast.walk(function)
    )


def unlocked_reaches(source: str) -> list[str]:
    """``function:line`` of every call that reaches the executor on a step outside the lock.

    A helper that takes the lock itself before it reaches (``_taken``) is locked where it stands;
    one that does not (``_delivered``) passes the question to every place that calls it, and the
    places that nobody in the module calls — the routes — are where the answer is read.
    """
    module = ast.parse(source)
    defined = {function.name: function for function in functions(module)}
    needs_lock: set[str] = set()

    def unlocked(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[int]:
        takes = [node.lineno for node in ast.walk(function) if _takes_the_lock(node)]
        return [
            node.lineno
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and (_reaches_directly(node) or _called_name(node) in needs_lock)
            and not _no_task_to_lock(function, node)
            and not any(take < node.lineno for take in takes)
        ]

    grew = True
    while grew:
        grew = False
        for name, function in defined.items():
            if name not in needs_lock and unlocked(function):
                needs_lock.add(name)
                grew = True
    called_here = {
        called
        for function in defined.values()
        for node in ast.walk(function)
        if (called := _called_name(node)) is not None
    }
    return [
        f"{name}:{line}"
        for name, function in defined.items()
        if name not in called_here
        for line in sorted(unlocked(function))
    ]


def api_modules() -> list[Path]:
    return sorted(API.glob("*.py"))


def test_the_lock_of_a_task_is_taken_with_no_await_between_the_check_and_the_insert() -> None:
    found = {
        path.name: awaits
        for path in api_modules()
        if (awaits := awaits_inside_the_lock(path.read_text(encoding="utf-8")))
    }
    assert found == {}, found


def test_what_reaches_the_executor_on_a_step_does_so_inside_the_lock() -> None:
    found = {
        path.name: calls
        for path in api_modules()
        if (calls := unlocked_reaches(path.read_text(encoding="utf-8")))
    }
    assert found == {}, found


def test_an_await_between_the_check_and_the_insert_is_reported() -> None:
    source = """
async def run_task(task_id, ela, running):
    if task_id in running:
        raise Busy(task_id)
    await ela.devices.heartbeat(LOCAL)
    running.add(task_id)
    return await ela.runner.run(task_id)
"""
    assert awaits_inside_the_lock(source) == ["run_task:5"]


def test_a_lock_taken_at_once_is_not_reported() -> None:
    source = """
async def run_task(task_id, ela, running):
    if task_id in running:
        raise Busy(task_id)
    running.add(task_id)
    try:
        return await ela.runner.run(task_id)
    finally:
        running.discard(task_id)
"""
    assert awaits_inside_the_lock(source) == []
    assert unlocked_reaches(source) == []


def test_a_route_that_reaches_the_executor_without_the_lock_is_reported() -> None:
    source = """
async def take(ela, offer, node):
    return await ela.executor.begin(offer, node)

async def route(ela, offer, node, running):
    claimed = await take(ela, offer, node)
    running.add(offer.task_id)
    return claimed

async def other(ela, task_id):
    return await ela.runner.run(task_id)
"""
    assert unlocked_reaches(source) == ["route:6", "other:11"]


def test_the_delivery_of_an_id_nobody_minted_is_the_one_exception() -> None:
    source = """
async def deliver_work(body, ela, running):
    held = await known(ela, body)
    if held is None:
        return await ela.executor.deliver(body)
    running.add(held.task_id)
    return await ela.executor.deliver(body)
"""
    assert unlocked_reaches(source) == []
    assert unlocked_reaches(source.replace("deliver_work", "deliver_elsewhere")) == [
        "deliver_elsewhere:5"
    ]


# ----------------------------------------------------------------------------------------
# Rule: the heartbeat of ``local`` has one writer (form H; ADR 0044 §8)
# ----------------------------------------------------------------------------------------

HEARTBEAT_WRITER = PACKAGE / "devices" / "beat.py"
"""The Core's heartbeat of ``local``: before every placement, and on a period."""


def beats_local(source: str) -> list[int]:
    """The lines that write a heartbeat for ``LOCAL_DEVICE_ID`` — a device's, never a task's.

    ``devices.heartbeat(LOCAL_DEVICE_ID, …)`` is a sign of life of this machine; the task engine's
    ``heartbeat(task_id)`` is a sign of life of a task, and another thing entirely.
    """
    found: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "heartbeat"
        ):
            continue
        named = [*node.args[:1], *(k.value for k in node.keywords if k.arg == "device_id")]
        if any(isinstance(arg, ast.Name) and arg.id == "LOCAL_DEVICE_ID" for arg in named):
            found.append(node.lineno)
    return found


def test_only_the_cores_heartbeat_writes_the_heartbeat_of_local() -> None:
    found = {
        str(path.relative_to(PACKAGE)): lines
        for path in sorted(PACKAGE.rglob("*.py"))
        if path != HEARTBEAT_WRITER and (lines := beats_local(path.read_text(encoding="utf-8")))
    }
    assert found == {}, found
    assert beats_local(HEARTBEAT_WRITER.read_text(encoding="utf-8")), "the writer writes nothing"


def test_a_route_that_beats_for_local_is_reported() -> None:
    source = """
async def run_task(task_id, ela):
    await ela.devices.heartbeat(LOCAL_DEVICE_ID, power_source=await ela.power())
    await ela.devices.heartbeat(device_id=LOCAL_DEVICE_ID)
    await ela.engine.heartbeat(task_id)
"""
    assert beats_local(source) == [3, 4]
