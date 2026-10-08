"""The room of the guided sessions of the browser (M14.3, ADR 0060): one door for every gesture.

A guided session is a session of Claude Code that ELA launches for one step of ``browser.guided``.
Its model looks at a page and asks for the next gesture; **every gesture is a child task** of the
session's task — created with a derived id, planned with the session as its author and the
session's sites as the narrowing of its scope (``TaskStep.within``), queued, walked by the runner
under the lock of ``run`` — so the Guardian, the grant, the tool, the verifier and the audit are
the ones of every task. There is no second door: the model proposes, the Guardian decides.

The room also holds what the gateway reads: each session's budget (``SessionBudget``), which
weighs every call against the reservation before it leaves, and the token the session presents.
Both live in memory: the reservation is already in the month's ledger, and a crash leaves the
``STARTED`` record open at its worst case (ADR 0057 §4).

The context of ELA never enters a session: this module does not import ``ela.context`` (contract
15, as for the Planner).
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
from collections.abc import AsyncIterator, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Final
from uuid import UUID, uuid5

from pydantic import ValidationError

from ela.domain import (
    Admission,
    CapabilityId,
    ErrorMetadata,
    ExecutionStatus,
    JsonMapping,
    PlanAuthor,
    PlanAuthorKind,
    PlanId,
    StepId,
    Task,
    TaskId,
    TaskPlan,
    TaskState,
    TaskStep,
)
from ela.executive.planner import planning_id
from ela.executive.runner import TaskRunner
from ela.executive.spending import BudgetRefusal, SessionBudget, SpendingGate
from ela.executive.stops import StopOfTask
from ela.permissions.capabilities import BROWSER_ACT, BROWSER_READ
from ela.ports import (
    GUIDED_FOLDER_CHANGED,
    GUIDED_SESSION_GONE,
    GUIDED_UNRESERVED,
    CapabilityRegistryPort,
    ExecutionResultStore,
    Forwarded,
    Gesture,
    ModelGateway,
    NotFoundError,
    OpenedSession,
    SessionTally,
    TaskRepository,
    VerifierRegistryPort,
)
from ela.tasks.engine import TERMINAL_STATES, TaskEngine, child_id

__all__ = [
    "GESTURE_KEY",
    "SESSIONS_PATH",
    "START_WAIT_SECONDS",
    "SessionRoom",
    "gesture_key",
]

SESSIONS_PATH: Final = "/sessions"
"""Where the gateway of a session listens, on ELA's own port: ``/sessions/<step>/v1/messages``."""

GESTURE_KEY: Final = "gesture"
"""The key of a gesture's child task: ``gesture-<n>/<step of the session>``, so asking again for the
same gesture finds the same child (M14.2's form)."""

START_WAIT_SECONDS: Final = 30.0
"""How long the first call of a session waits for the check of the tools of its start (decision
22): the start and the first call travel on two channels, and the call is admitted only after the
check. A start that never arrives is a session halted, not a call let out."""

_NAMESPACE: Final = UUID("1d9a5d6c-8f3b-4e47-9a0f-6c2d4b8e7a15")
"""The namespace of the ids of a gesture's plan and step, derived from the child's id."""

_GESTURES: Final = frozenset({BROWSER_READ, BROWSER_ACT})


def gesture_key(number: int, session: StepId) -> str:
    """The key of the ``number``-th gesture of ``session``."""
    return f"{GESTURE_KEY}-{number}/{session}"


@dataclass(slots=True)
class _Live:
    """One open session: its task, its budget, its token, its sites and its gestures."""

    task_id: TaskId
    budget: SessionBudget
    token: str
    sites: tuple[str, ...]
    halted: asyncio.Future[ErrorMetadata]
    checked: asyncio.Event = field(default_factory=asyncio.Event)
    closed: asyncio.Event = field(default_factory=asyncio.Event)
    looks: int = 0
    refused: int = 0
    acts: int = 0


class SessionRoom:
    """The room of the guided sessions (implements :class:`~ela.ports.Gestures`).

    Built with the engine and the catalogue, **before** the runner and the verifiers exist — the
    tools are built before them in the composition (``root.py``), and the tool of
    ``browser.guided`` holds this room —; the two are handed over once, with :meth:`bind`: the one
    late binding of ELA's graph, written.
    """

    def __init__(
        self,
        *,
        engine: TaskEngine,
        repository: TaskRepository,
        results: ExecutionResultStore,
        capabilities: CapabilityRegistryPort,
        spending: SpendingGate,
        gateway: ModelGateway,
        running: set[TaskId],
    ) -> None:
        self._engine = engine
        self._repository = repository
        self._results = results
        self._capabilities = capabilities
        self._spending = spending
        self._gateway = gateway
        self._running = running
        self._runner: TaskRunner | None = None
        self._verifiers: VerifierRegistryPort | None = None
        self._live: dict[StepId, _Live] = {}

    def bind(self, *, runner: TaskRunner, verifiers: VerifierRegistryPort) -> None:
        """Hand the room the runner and the verifiers, once: the composition calls this after
        building them — they are built after the tools, and the tool of ``browser.guided`` holds
        this room (and its verifier too)."""
        if self._runner is not None:
            raise RuntimeError("the room of the sessions is bound already")
        self._runner = runner
        self._verifiers = verifiers

    # The tool's side ------------------------------------------------------------------------

    async def open(
        self, task_id: TaskId, step_id: StepId, *, sites: tuple[str, ...], tools: frozenset[str]
    ) -> OpenedSession | ErrorMetadata:
        # A plan by hand carries the caller's step ids, so one file sent to two tasks gives two
        # sessions one step: the identity of the path, of the folder and of the place here. The
        # second is refused before it touches the first — the code the adapter gives a folder it
        # cannot prepare, which is what ``<sessions>/<step>`` would be (M14.3, the proof's plans).
        if step_id in self._live:
            return ErrorMetadata(
                code=GUIDED_FOLDER_CHANGED,
                message=f"step {step_id} has a session open already, in another task: its folder "
                "and its gateway are that session's",
            )
        reservation = await self._spending.reservation(task_id, step_id)
        if reservation is None:
            return ErrorMetadata(
                code=GUIDED_UNRESERVED,
                message=f"step {step_id} has no reservation of the cap: a session is not launched",
            )
        live = _Live(
            task_id=task_id,
            budget=SessionBudget(reservation, tools),
            token=secrets.token_urlsafe(32),
            sites=sites,
            halted=asyncio.get_running_loop().create_future(),
        )
        self._live[step_id] = live
        return OpenedSession(
            session=step_id,
            token=live.token,
            reservation=reservation,
            path=f"{SESSIONS_PATH}/{step_id}",
        )

    async def start(self, session: StepId, tools: Sequence[str]) -> ErrorMetadata | None:
        live = self._live.get(session)
        if live is None:
            return ErrorMetadata(code=GUIDED_SESSION_GONE, message=f"no open session {session}")
        refused = live.budget.start(tools)
        live.checked.set()
        if refused is None:
            return None
        error = _error(refused)
        await self.halt(session, error)
        return error

    async def gesture(
        self, session: StepId, capability: CapabilityId, arguments: JsonMapping
    ) -> Gesture:
        live = self._live.get(session)
        if live is None or live.closed.is_set():
            return Gesture(f"the session {session} is over", TaskState.CANCELLED, acted=False)
        live.looks += 1
        number = live.looks
        if capability == BROWSER_ACT:
            live.acts += 1
        if capability not in _GESTURES:
            live.refused += 1
            return Gesture(f"gesture {number}: no such gesture", TaskState.DENIED, acted=False)
        # Shielded (M14.3): the interrupt of the session cancels the call of its in-process tool,
        # and a runner cancelled halfway would leave the child's step open and its lock let go.
        # The gesture goes on to the end its own stop gives it; the session stops waiting for it.
        made = asyncio.ensure_future(self._made(live, session, number, capability, arguments))
        child = await asyncio.shield(made)
        if child is None:
            live.refused += 1
            return Gesture(
                f"gesture {number}: its arguments are not a call ELA can plan",
                TaskState.DENIED,
                acted=False,
            )
        if child.state is TaskState.DENIED:
            live.refused += 1
        acted = capability == BROWSER_ACT and child.state is TaskState.COMPLETED
        return Gesture(await self._said(number, child), child.state, acted=acted)

    async def halt(self, session: StepId, error: ErrorMetadata) -> None:
        live = self._live.get(session)
        if live is not None and not live.halted.done():
            live.halted.set_result(error)

    async def halted(self, session: StepId) -> ErrorMetadata:
        live = self._live.get(session)
        if live is None:
            return ErrorMetadata(code=GUIDED_SESSION_GONE, message=f"no open session {session}")
        return await asyncio.shield(live.halted)

    async def close(self, session: StepId, *, reason: str) -> SessionTally:
        live = self._live.pop(session)
        live.closed.set()
        live.checked.set()
        await self._stop_children(live, session, reason)
        budget = live.budget
        budget.close()
        return SessionTally(
            usage=budget.usage(),
            calls=len(budget.settled),
            unknown=budget.unknown,
            input_minus_bytes_max=budget.input_minus_bytes_max,
            looks=live.looks,
            refused=live.refused,
            acts=live.acts,
            per_call=tuple(
                (call.model, call.input_tokens, call.output_tokens, call.request_bytes)
                for call in budget.settled
            ),
        )

    async def is_open(self, session: StepId) -> bool:
        return session in self._live

    async def gesture_ids(self, task_id: TaskId, session: StepId, count: int) -> tuple[TaskId, ...]:
        return tuple(child_id(task_id, gesture_key(n, session)) for n in range(1, count + 1))

    # The gateway's side -----------------------------------------------------------------------

    def token(self, session: StepId) -> str | None:
        """The token of an open session, for the one module that compares it (rule 31)."""
        live = self._live.get(session)
        return None if live is None or live.closed.is_set() else live.token

    async def relay(
        self, session: StepId, body: bytes, beta: str | None
    ) -> Forwarded | ErrorMetadata:
        """One call of the session: weighed by its budget, and forwarded only if admitted. A call
        refused **halts the session**: a session that receives errors retries, and every retry is a
        new call that would be refused again."""
        live = self._live.get(session)
        if live is None or live.closed.is_set():
            return ErrorMetadata(code=GUIDED_SESSION_GONE, message=f"no open session {session}")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(live.checked.wait(), START_WAIT_SECONDS)
        request = await self._gateway.read(body)
        tokens = request.max_tokens
        worst = (
            await self._gateway.worst(live.budget.reservation.model, tokens)
            if tokens is not None and tokens >= 1
            else None
        )
        admitted = live.budget.admit(request, worst)
        if isinstance(admitted, BudgetRefusal):
            error = _error(admitted)
            await self.halt(session, error)
            return error
        forwarded = await self._gateway.forward(admitted, body, beta)
        return Forwarded(
            status=forwarded.status,
            content_type=forwarded.content_type,
            chunks=self._settled(live, admitted, forwarded),
            usage=forwarded.usage,
        )

    @staticmethod
    async def _settled(
        live: _Live, admitted: Admission, forwarded: Forwarded
    ) -> AsyncIterator[bytes]:
        """The body of the call, passed on as it comes; the call is settled when it ends — or when
        whoever reads it stops, an outcome nobody knows, at its worst case."""
        try:
            async for chunk in forwarded.chunks:
                yield chunk
        finally:
            live.budget.settle(admitted, forwarded.usage())

    # The stop's side --------------------------------------------------------------------------

    async def stop_gestures(self, task_id: TaskId, *, reason: str) -> tuple[Task, ...]:
        """The «ferma» of a session's task, carried down to its live gestures (ADR 0054): each child
        still alive is cancelled, and returned so that the route closes what it left open. The
        session itself hears the stop of its own task."""
        stopped: list[Task] = []
        for session, live in list(self._live.items()):
            if live.task_id == task_id:
                stopped.extend(await self._stop_children(live, session, reason))
        return tuple(stopped)

    async def close_orphans(self) -> tuple[Task, ...]:
        """At start-up: the gestures still alive whose session's task has ended — the window of a
        crash, a restart with a question open —, found with a read of the repository and
        cancelled. The caller closes the steps they left open."""
        alive = frozenset(TaskState) - TERMINAL_STATES
        stopped: list[Task] = []
        for task in await self._repository.tasks(states=alive):
            if task.parent_id is None or not await self._is_gesture(task):
                continue
            parent = await self._repository.get(TaskId(task.parent_id))
            if parent.state in TERMINAL_STATES:
                stopped.append(
                    await self._engine.cancel(
                        task.id, reason=f"the guided session of task {parent.id} has ended"
                    )
                )
        return tuple(stopped)

    async def _is_gesture(self, task: Task) -> bool:
        assert task.parent_id is not None
        try:
            plan = await self._repository.plan(task.id)
        except NotFoundError:
            return task.id != planning_id(TaskId(task.parent_id))
        return plan.author.by is PlanAuthorKind.SESSION

    async def _stop_children(self, live: _Live, session: StepId, reason: str) -> list[Task]:
        stopped: list[Task] = []
        for identifier in await self.gesture_ids(live.task_id, session, live.looks):
            try:
                child = await self._repository.get(identifier)
            except NotFoundError:
                continue
            if child.state not in TERMINAL_STATES:
                stopped.append(await self._engine.cancel(identifier, reason=reason))
        return stopped

    # A gesture, as a child task ---------------------------------------------------------------

    async def _made(
        self,
        live: _Live,
        session: StepId,
        number: int,
        capability: CapabilityId,
        arguments: JsonMapping,
    ) -> Task | None:
        """The child of a gesture, created, planned and walked to its end — or ``None``."""
        child = await self._child(live, session, number, capability, arguments)
        return None if child is None else await self._walk(live, child)

    async def _child(
        self,
        live: _Live,
        session: StepId,
        number: int,
        capability: CapabilityId,
        arguments: JsonMapping,
    ) -> Task | None:
        site = arguments.get("site")
        where = site if isinstance(site, str) and site in live.sites else "a site outside it"
        child = await self._engine.create_child(
            live.task_id,
            key=gesture_key(number, session),
            goal=f"gesture {number} of the session of step {session}: {capability} on {where}",
        )
        # A gesture's number is the session's own count, so its child is always new: no retry
        # finds one half made in this room, and a room does not outlive its process.
        child = await self._engine.start_planning(child.id)
        plan = self._plan(live, session, number, child, capability, arguments)
        if plan is None:
            await self._engine.cancel(
                child.id, reason="the arguments of the gesture are not a call ELA can plan"
            )
            return None
        await self._engine.plan(child.id, plan)
        return await self._engine.queue(child.id, reason="planned by the guided session")

    def _plan(
        self,
        live: _Live,
        session: StepId,
        number: int,
        child: Task,
        capability: CapabilityId,
        arguments: JsonMapping,
    ) -> TaskPlan | None:
        assert self._verifiers is not None, "the room of the sessions has no verifiers: bind() it"
        spec = self._capabilities.get(capability)
        conditions = tuple(sorted(self._verifiers.get(capability).conditions))
        plan_id = PlanId(uuid5(_NAMESPACE, f"{child.id}/gesture"))
        try:
            step = TaskStep(
                id=StepId(uuid5(_NAMESPACE, f"{plan_id}/0")),
                created_at=child.created_at,
                goal=f"{capability}, asked by the model of the session of step {session}",
                required_capabilities=(capability,),
                arguments={
                    **arguments,
                    "purpose": f"gesture {number} of the guided session of step {session}",
                },
                risk=spec.risk,
                expected_result=f"what {capability} answers, read back by the session",
                success_conditions=conditions,
                requires_authorization=spec.requires_authorization,
                within=live.sites,
            )
        except ValidationError:
            return None
        return TaskPlan(
            id=plan_id,
            created_at=child.created_at,
            task_id=child.id,
            goal=child.goal,
            steps=(step,),
            author=PlanAuthor(
                by=PlanAuthorKind.SESSION, session=session, model=live.budget.reservation.model
            ),
        )

    async def _walk(self, live: _Live, child: Task) -> Task:
        """Walk the child under the lock of ``run`` and wait for its end: a ``browser.act`` waits
        for the user's yes — given on the console, the phone or with the CLI — and the session
        waits with it. The check and the insert of the lock with nothing in between (rule of
        ``tests/architecture/test_travel_rules.py``)."""
        assert self._runner is not None, "the room of the sessions has no runner: bind() it"
        if child.id not in self._running:
            self._running.add(child.id)
            try:
                await self._runner.run(child.id)
            finally:
                self._running.discard(child.id)
        await self._ended(live, child.id)
        return await self._repository.get(child.id)

    async def _ended(self, live: _Live, task_id: TaskId) -> None:
        if (await self._repository.get(task_id)).state in TERMINAL_STATES:
            return
        ended = asyncio.ensure_future(_awaited(StopOfTask(self._engine.stop_signal(task_id), None)))
        closing = asyncio.ensure_future(live.closed.wait())
        try:
            await asyncio.wait((ended, closing), return_when=asyncio.FIRST_COMPLETED)
        finally:
            for waiting in (ended, closing):
                waiting.cancel()

    async def _said(self, number: int, child: Task) -> str:
        """What the session reads of a gesture: the result of the child, or why it ended."""
        if child.state is not TaskState.COMPLETED:
            ending = await self._engine.ending(child)
            why = child.state.value if ending is None else ending.reason
            return f"gesture {number}: {child.state.value} — {why}"
        plan = await self._repository.plan(child.id)
        rows = await self._results.for_step(child.id, plan.steps[0].id)
        done = [row.output for row in rows if row.status is ExecutionStatus.SUCCEEDED]
        return "\n".join([f"gesture {number}: {child.state.value}", *_lines(done[-1])])


_SHOWN: Final = ("address", "status", "title", "gestures", "text")
"""What of a gesture's result the session reads, in this order: the text last, since it is long."""


def _lines(output: JsonMapping) -> Iterable[str]:
    for key in _SHOWN:
        if key in output:
            yield f"{key}: {output[key]}"


async def _awaited(stop: StopOfTask) -> None:
    """The end of a gesture's task, read through the stop of one call: the engine raises it when
    the task ends, and nobody but the engine raises it (rule 58)."""
    await stop.stopped()


def _error(refused: BudgetRefusal) -> ErrorMetadata:
    return ErrorMetadata(code=refused.code.value, message=refused.reason, retryable=False)
