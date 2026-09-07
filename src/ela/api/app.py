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

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from importlib.metadata import version

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ela.api import approvals, audit, system, tasks
from ela.api.errors import DatabaseUnavailableError, TaskAlreadyRunningError
from ela.api.problems import problem
from ela.api.security import token_middleware
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
    """What a start-up does: close what a crash left open (ADR 0008 §6, ADR 0015 §6).

    Once, here, and not periodically: calling ``recover()`` on a schedule is the Proactive Core's
    (§34). It **writes** — an EXECUTING task silent for longer than
    ``ELA_TASK_ORPHAN_AFTER_SECONDS`` is failed as an orphan — so starting ELA is not a read-only
    operation, and the default of fifteen minutes is chosen for that reason (ADR 0023 §3).
    """
    ela: Ela = app.state.ela
    app.state.recovery = await ela.engine.recover()
    yield


def create_app(ela: Ela) -> FastAPI:
    """The application serving ``ela``: token first, then the twelve routes."""
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
    for router in (system.router, tasks.router, approvals.router, audit.router):
        app.include_router(router)
    return app
