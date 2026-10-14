"""The room of the pages a task keeps between two of its steps (M13.10, ADR 0065 §3).

Until M13.10 a step of the browser had a browser of its own, closed with the step (ADR 0052 §3, ADR
0063 §4). Since then, **inside a task**, the page one step leaves can be the page the next step
works on: the step continues (the argument ``continues``) instead of opening one. Between two tasks
nothing passes, as before — the profile's folder alone, for the browser with the accounts.

The room is the one place that holds such a page, and the one that closes it:

* **one page per task**, the key is the task: two tasks never have the same page;
* it keeps a page only when **the step right after** the one that leaves it continues — read from
  the plan, which the step does not write —, and hands it to that step, on the same browser;
* it closes it when the task ends (the engine's stop of the task, which it raises for every end,
  heard here without anybody calling), when the same task opens another page, and when what the
  task waits for is over: the question of the next step until it is answered, then the grant of
  the yes until the step runs (decision 26 of the review of its SPEC). The clock is the one of the
  vault's keeper: a wait a minute at a time that asks the clock, never the time of the loop, which
  stands still while the machine sleeps;
* at ELA's stop the browsers close every page themselves (ADR 0038 §11): the room forgets.

It is built before the tools and receives nothing after: the one late binding of the graph stays
the room of the guided sessions' (ADR 0060 §4). Not a capability: every step is judged by its own.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from ela.domain import ApprovalStatus, CapabilityId, StepId, TaskId, TaskStep
from ela.ports import (
    CONTINUES,
    ApprovalStore,
    AuthorizationStore,
    Browser,
    Clock,
    TaskRepository,
    WaitingPage,
)

__all__ = ["WATCH_SECONDS", "PageRoom"]

WATCH_SECONDS: Final = 60
"""How often the room looks at the clock, and at what the task waits for, while a page waits: the
form of the vault's keeper. A question composed while the page waits is seen within a minute, and
a question lives a day."""

Wait = Callable[[float], Awaitable[None]]


@dataclass
class _Kept:
    """One page a task keeps: on which browser, for which step, and the room's watch over it."""

    task: TaskId
    step: StepId
    """The step that will continue on it: the one right after the step that left it."""
    capability: CapabilityId | None
    page: str
    browser: Browser
    profile: bool
    watching: asyncio.Task[None] | None = field(default=None)


class _Now:
    """What the task waits for is over: the page is closed."""


NOW: Final = _Now()


class PageRoom:
    """Implements :class:`~ela.ports.TaskPages`.

    ``ends`` is the engine's stop of a task (``TaskEngine.stop_signal``), raised when the task
    reaches a final state; ``stopping`` is ELA's. ``wait`` is how a minute is waited for — a
    sleep, and an event in a test.
    """

    def __init__(
        self,
        *,
        repository: TaskRepository,
        approvals: ApprovalStore,
        authorizations: AuthorizationStore,
        ends: Callable[[TaskId], asyncio.Event],
        stopping: asyncio.Event,
        clock: Clock,
        wait: Wait = asyncio.sleep,
    ) -> None:
        self._repository = repository
        self._approvals = approvals
        self._authorizations = authorizations
        self._ends = ends
        self._stopping = stopping
        self._clock = clock
        self._wait = wait
        self._kept: dict[TaskId, _Kept] = {}

    async def leave(
        self, task: TaskId, step: StepId, page: str, browser: Browser, *, profile: bool
    ) -> bool:
        following = await self._following(task, step)
        if following is None or following.arguments.get(CONTINUES) is not True:
            return False
        await self.release(task)
        await browser.hold(page)
        kept = _Kept(
            task=task,
            step=following.id,
            capability=following.required_capabilities[0]
            if following.required_capabilities
            else None,
            page=page,
            browser=browser,
            profile=profile,
        )
        self._kept[task] = kept
        kept.watching = asyncio.create_task(self._watch(kept))
        return True

    async def take(self, task: TaskId, browser: Browser) -> str | None:
        kept = self._unkept(task)
        if kept is None:
            return None
        if kept.browser is not browser:
            await kept.browser.close(kept.page)
            return None
        return kept.page

    async def where(self, task: TaskId, browser: Browser) -> str | None:
        kept = self._kept.get(task)
        if kept is None or kept.browser is not browser:
            return None
        return await browser.where(kept.page)

    async def release(self, task: TaskId) -> None:
        kept = self._unkept(task)
        if kept is not None:
            await kept.browser.close(kept.page)

    async def waiting(self) -> tuple[WaitingPage, ...]:
        said: list[WaitingPage] = []
        for kept in list(self._kept.values()):
            until = await self._until(kept)
            said.append(
                WaitingPage(
                    task=kept.task,
                    profile=kept.profile,
                    until=self._clock.now() if isinstance(until, _Now) else until,
                )
            )
        return tuple(said)

    async def stopped(self) -> None:
        """ELA's close: every watch ends, and the room forgets — the browsers close their pages
        at the stop, which is raised before this is asked."""
        watching = [kept.watching for kept in self._kept.values() if kept.watching is not None]
        self._kept.clear()
        for one in watching:
            one.cancel()
        for one in watching:
            with contextlib.suppress(asyncio.CancelledError):
                await one

    async def _following(self, task: TaskId, step: StepId) -> TaskStep | None:
        plan = await self._repository.plan(task)
        steps = list(plan.steps)
        for index, one in enumerate(steps):
            if one.id == step:
                return steps[index + 1] if index + 1 < len(steps) else None
        return None

    def _unkept(self, task: TaskId) -> _Kept | None:
        """The page of ``task``, no longer kept: whoever has it now closes it, or uses it."""
        kept = self._kept.pop(task, None)
        if kept is not None and kept.watching is not None:
            kept.watching.cancel()
        return kept

    async def _until(self, kept: _Kept) -> datetime | _Now | None:
        """The end of what the task waits for, read now: the question of the step that continues
        until it is answered, then the grant of the yes; :data:`NOW` once it is over — a no, a
        question that expired, a grant revoked or gone —; ``None`` while nothing that ends is
        awaited: no question asked yet, or a step that asks none."""
        asked = [
            one for one in await self._approvals.for_task(kept.task) if one.step_id == kept.step
        ]
        if not asked:
            return None
        last = max(asked, key=lambda one: one.created_at)
        if last.status is ApprovalStatus.PENDING:
            return last.expires_at
        if last.status is not ApprovalStatus.GRANTED or kept.capability is None:
            return NOW
        grants = [
            one
            for one in await self._authorizations.for_capability(kept.capability)
            if one.step_id == kept.step and one.revoked_at is None
        ]
        if not grants:
            return NOW
        if any(one.expires_at is None for one in grants):
            return None
        return max(one.expires_at for one in grants if one.expires_at is not None)

    async def _watch(self, kept: _Kept) -> None:
        """The room's own watch over one page: it closes it when the task ends, or when what the
        task waits for is over. It looks a minute at a time and asks the clock. At ELA's stop it
        ends and closes nothing: the browsers do."""
        ended = self._ends(kept.task)
        while not ended.is_set():
            until = await self._until(kept)
            if isinstance(until, _Now):
                break
            seconds = float(WATCH_SECONDS)
            if until is not None:
                left = (until - self._clock.now()).total_seconds()
                if left <= 0:
                    break
                seconds = min(seconds, left)
            if await self._first(ended, seconds):
                return
        if self._kept.get(kept.task) is kept:
            del self._kept[kept.task]
            await kept.browser.close(kept.page)

    async def _first(self, ended: asyncio.Event, seconds: float) -> bool:
        """Wait for the task's end, ELA's stop or ``seconds``, whichever comes first: ``True`` if
        it was ELA's stop."""
        waits = {
            asyncio.ensure_future(ended.wait()),
            asyncio.ensure_future(self._stopping.wait()),
            asyncio.ensure_future(self._wait(seconds)),
        }
        try:
            await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for one in waits:
                one.cancel()
        return self._stopping.is_set()
