"""The ELA application: the routes, the token, and the one shape every failure takes.

``create_app`` takes an :class:`~ela.composition.Ela` that somebody else built — this package
never composes anything (architecture rule 27) — and serves it.

The **schema** is served, at ``/openapi.json``, and the token guards it like every other path:
the objection to publishing it was that an unauthenticated schema tells whoever scans the port
what the API looks like, and behind the middleware there is no such reader. What a caller finds
there is not decoration — it is where ``POST /tasks/{task_id}/plan`` says that its own shape is
temporary and unversioned (review of M8.1). The **HTML pages** stay off: a browser cannot send
an ``Authorization`` header, so ``/docs`` behind a token would answer 401 and nothing else.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from importlib.metadata import version

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ela.api import (
    approvals,
    audit,
    context,
    devices,
    perception,
    results,
    system,
    tasks,
    voice,
)
from ela.api.errors import DatabaseUnavailableError, TaskAlreadyRunningError
from ela.api.problems import problem
from ela.api.security import token_middleware
from ela.audit.chain import AuditChainError
from ela.composition import Ela
from ela.executive import ExecutorError, RunnerError
from ela.ports import AlreadyExistsError, ApprovalNotAnswerableError, NotFoundError
from ela.tasks.engine import RecoverySummary
from ela.tasks.errors import GraphError, TaskError

__all__ = ["FAILURES", "Failure", "create_app", "lifespan"]


@dataclass(frozen=True, slots=True)
class Failure:
    """One exception, the status it becomes and the code the caller branches on."""

    exception: type[Exception]
    status: int
    code: str


FAILURES: tuple[Failure, ...] = (
    Failure(NotFoundError, 404, "not_found"),
    Failure(AlreadyExistsError, 409, "already_exists"),
    Failure(ApprovalNotAnswerableError, 409, "not_answerable"),
    Failure(AuditChainError, 409, "tampered"),
    Failure(GraphError, 422, "invalid"),
    Failure(TaskError, 409, "conflict"),
    Failure(ExecutorError, 409, "conflict"),
    Failure(RunnerError, 409, "conflict"),
    Failure(TaskAlreadyRunningError, 409, "already_running"),
    Failure(DatabaseUnavailableError, 503, "database_unavailable"),
    Failure(RequestValidationError, 422, "invalid"),
    Failure(ValueError, 422, "invalid"),
)
"""The table of ADR 0023 §10, read from the most specific entry to the least.

Which handler runs is decided by walking the exception's own ancestry, so the most derived class
in this table wins whatever order it is written in: a ``NotFoundError`` is not a conflict, and a
pydantic ``ValidationError`` — a ``ValueError`` — is a malformed request rather than a bug. The
order is for whoever reads the table.

``GraphError`` is listed above its own base ``TaskError`` for a reason that is not tidiness: a
``TaskError`` says the task is not in a state where this can happen (409), while a ``GraphError``
says the plan that arrived cannot be a graph at all (422) — the caller has to change *what* they
sent, not *when*. The base stays in the table because ``IllegalTransitionError`` lives in
``ela.tasks.state_machine``, which this package may not import (contract 7) and does not need to.
"""


def _message(failed: Exception) -> str:
    """What to tell the caller, without echoing back what they sent (§57).

    A pydantic failure carries the input it refused; only the location and the reason are
    quoted, so an error page never becomes a copy of the user's content.
    """
    errors = getattr(failed, "errors", None)
    if callable(errors):
        return "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in errors()
        )
    return str(failed)


def _handler(failure: Failure) -> Callable[[Request, Exception], Awaitable[Response]]:
    async def handle(request: Request, failed: Exception) -> Response:
        return JSONResponse(
            status_code=failure.status, content=problem(failure.code, _message(failed))
        )

    return handle


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """What a start-up does: close what a crash left open, and look at the machine once.

    ``recover()`` runs once, here, and not periodically: calling it on a schedule is the Proactive
    Core's (§34). It **writes** — an EXECUTING task silent for longer than
    ``ELA_TASK_ORPHAN_AFTER_SECONDS`` is failed as an orphan — so starting ELA is not a read-only
    operation, and the default of fifteen minutes is chosen for that reason (ADR 0023 §3).

    The first perception tick follows the same precedent, for the same reason: once, so that
    ``/diagnostics`` has something true to say about this machine from the first request, and not
    on a schedule, because watching continuously is a separate decision with its own knob
    (``ELA_PERCEPTION_LOOP_INTERVAL_SECONDS``, off by default — M10.1, ADR 0028 §7).

    The loop, when it is on, is a task this context manager owns: started after the first tick and
    cancelled before the process leaves, so ELA never outlives its own observer.

    The sweep of the voice's scratch directory is here for the same reason as the purge below it,
    and it normally finds nothing at all: a spoken sentence's audio has no name from one syscall
    after it exists (ADR 0034 §7).

    The purge of expired screen captures is here for a third reason of its own (M10.2,
    ADR 0029 §1): it is the **only** moment ELA is certain to reach. A capture also purges before
    it writes, but a retention that only ran when somebody took a screenshot would keep the last
    one for as long as ELA is left alone — and a photograph of somebody's screen outliving its
    five minutes because nothing happened is exactly the accumulation §57 forbids.
    """
    ela: Ela = app.state.ela
    app.state.recovery = await ela.engine.recover()
    ela.captures.purge(ela.clock.now())
    # And the voice's floor, for the same reason and a smaller one: what it collects is the crash
    # that landed between making the audio's file and unlinking it — one syscall wide, and exactly
    # the kind of rare leftover that would otherwise sit on a disk for a year (ADR 0034 §7).
    app.state.swept = ela.sweep_speech()
    await ela.perception.tick()
    watching = asyncio.create_task(ela.perception.run())
    try:
        yield
    finally:
        watching.cancel()
        with suppress(asyncio.CancelledError):
            await watching


def create_app(ela: Ela) -> FastAPI:
    """The application serving ``ela``: token first, then the routers.

    The tuple below is a declaration, and stays one: a module is mounted because somebody wrote it
    here, not because a file appeared in the package. It carried a count in this docstring once —
    "the fifteen routes" — and the count outlived the truth by five; the census now lives in
    ``tests/api/test_security.py``, which holds this tuple to every router of ``ela.api``.
    """
    app = FastAPI(
        title="ELA",
        version=version("ela"),
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.state.ela = ela
    app.state.running = set()
    app.state.recovery = RecoverySummary((), (), ())
    app.middleware("http")(token_middleware(ela.settings.api.token))
    for failure in FAILURES:
        app.add_exception_handler(failure.exception, _handler(failure))
    for router in (
        system.router,
        tasks.router,
        approvals.router,
        audit.router,
        devices.router,
        context.router,
        perception.router,
        results.router,
        voice.router,
    ):
        app.include_router(router)
    return app
