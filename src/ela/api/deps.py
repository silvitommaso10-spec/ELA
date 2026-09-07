"""How a route reaches the ELA that was built for this process (ADR 0023 §1).

``ela.api`` never builds anything: the composition root does, once, and the app carries it. The
dependency reads it off the application state, so a route asks for ``Ela`` and gets the one this
process is serving — in a test, the one the test built.
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from ela.composition import Ela
from ela.domain import TaskId

__all__ = ["ElaDep", "RunningDep", "ela_of", "running_of"]


def ela_of(request: Request) -> Ela:
    return cast(Ela, request.app.state.ela)


def running_of(request: Request) -> set[TaskId]:
    """The tasks a ``run`` is walking right now (ADR 0023 §9).

    A plain set, and it is enough: the event loop is one thread, and the check and the insert
    happen with no ``await`` between them.
    """
    return cast("set[TaskId]", request.app.state.running)


ElaDep = Annotated[Ela, Depends(ela_of)]
RunningDep = Annotated[set[TaskId], Depends(running_of)]
