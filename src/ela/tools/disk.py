"""**One guard for every wait on the disk under the root** (M13.17, ADR 0074; decision 12 of its
starting block, answers 34 and 40, decisions 52 and 53 of the review of its SPEC).

Until M13.17 a look at a file, a read and a write ran **inside the coroutine**: a disk that does
not answer — a window of macOS asking for a permission, a file the system keeps elsewhere and
fetches when it is read, a disk that has gone to sleep — would have held the whole Core still, its
routes, its console and its «stop» included. With the root up to the user's home those waits are
no longer hypothetical.

**What the guard does.** :meth:`Disk.run` hands a synchronous piece of work — a look, a read, a
write — to **a ``daemon`` thread of its own**, and waits for it at most :data:`DISK_LIMIT_SECONDS`;
past it the wait is **abandoned**, and the caller gets :class:`DiskSilent`, which every tool turns
into :data:`NO_ANSWER`. Not ``asyncio.to_thread``: a thread of the default executor holds the end
of ``asyncio.run`` until its call returns — measured, E3 of the SPEC: 5,0 s against 1,1 s — and an
abandoned wait would keep ELA from ending. A ``daemon`` thread does not.

**What is left of an abandoned wait** (E3, and the SPEC's C5): the thread, still inside its call,
which ends when the disk answers; its outcome is dropped. **A write abandoned while it was
looking never writes** (decision 52): the work reads the mark of the abandonment, :class:`Gone`,
before every step with an effect, and :meth:`Gone.begin` refuses that step once the wait is
abandoned. Only a write abandoned *inside* a step with an effect may still land, and the sentence
says so.

**How many at once** (answer 40): at most :data:`ABANDONED_MOST` abandoned waits are left
standing; past them every new piece of work is refused at once, without a thread, with the number
of waits that are still standing — :attr:`Disk.waiting`, which ``ela diagnostics`` shows. A
resource ceiling, not a measure.

**A refusal is not retried** (decision 53): :data:`NO_ANSWER` is not ``retryable`` — a second try
is another wait. A «stop» during a wait is heard by the tool at its own point, after the wait:
in the worst case the stop waits the limit, never more.

:func:`within_the_limit` is the same guard for a synchronous caller — the start-up, which looks at
every folder the scope opens before ELA serves (decisions 6 and 51).
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from typing import Final

__all__ = [
    "ABANDONED_MOST",
    "DISK_LIMIT_SECONDS",
    "LOOKING",
    "NO_ANSWER",
    "Abandoned",
    "Disk",
    "DiskSilent",
    "Gone",
    "within_the_limit",
]

DISK_LIMIT_SECONDS: Final = 10.0
"""How long ELA waits for the disk to answer one look, read or write (M13.17, E1 of its SPEC): the
longest healthy case measured on this Mac was 6,6 ms — a write of 32 MiB —, and the rule written
before the numbers wanted it under a tenth of the limit. Past it the wait is abandoned."""

ABANDONED_MOST: Final = 4
"""How many abandoned waits ELA leaves standing at once (answer 40): a ceiling on threads that
wait for a disk that does not answer, not a measure."""

NO_ANSWER: Final = "fs.no_answer"
"""The disk did not answer within :data:`DISK_LIMIT_SECONDS`, or too many waits are standing. Not
retryable: a second try is another wait (decision 53)."""

LOOKING: Final = "looking"
"""The step of a piece of work that has no effect: a look, or a read."""

MAKING_THE_FOLDER: Final = "making the folder"
WRITING: Final = "writing"


class Abandoned(Exception):
    """Raised inside the work by :meth:`Gone.begin`: the wait was abandoned before a step with an
    effect, and the step is not taken. Nobody is listening for the outcome any more."""


class DiskSilent(Exception):
    """The wait on the disk was abandoned, or not begun because too many are standing: what a tool
    turns into :data:`NO_ANSWER`, with this message."""


class Gone:
    """The mark of a wait, which the work reads before every step that has an effect.

    :meth:`begin` names the step the work is about to take and **refuses it once the wait is
    abandoned**; the abandonment reads the step the work had reached, under the same lock, so a
    step is either refused or named in the sentence — never both, never neither."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._abandoned = False
        self._step = LOOKING

    def begin(self, step: str) -> None:
        """Before a step with an effect: :class:`Abandoned` if the wait was given up."""
        with self._lock:
            if self._abandoned:
                raise Abandoned(step)
            self._step = step

    def _abandon(self) -> str:
        with self._lock:
            self._abandoned = True
            return self._step

    @property
    def abandoned(self) -> bool:
        with self._lock:
            return self._abandoned


class _Wait:
    """One piece of work in its thread: whether it has ended, and whether it was abandoned."""

    def __init__(self) -> None:
        self.ended = False
        self.abandoned = False


class Disk:
    """The guard: one per process, shared by every tool and verifier that looks under the root, so
    that :data:`ABANDONED_MOST` counts every standing wait of the process."""

    def __init__(self, *, limit: float = DISK_LIMIT_SECONDS, most: int = ABANDONED_MOST) -> None:
        self._limit = limit
        self._most = most
        self._lock = threading.Lock()
        self._waiting = 0

    @property
    def limit(self) -> float:
        return self._limit

    @property
    def waiting(self) -> int:
        """How many abandoned waits are standing now: they end when the disk answers."""
        with self._lock:
            return self._waiting

    async def run[T](self, work: Callable[[Gone], T], what: str) -> T:
        """``work`` in a thread of its own, waited for at most the limit; :class:`DiskSilent` past
        it, or at once when :data:`ABANDONED_MOST` waits are standing. ``what`` names the work in
        the sentence — a path and a verb, never a content (§57)."""
        self._room(what)
        loop = asyncio.get_running_loop()
        answer: asyncio.Future[T] = loop.create_future()
        gone, wait = Gone(), _Wait()

        def body() -> None:
            try:
                value = work(gone)
            except BaseException as error:  # noqa: BLE001 — handed to the waiting coroutine
                outcome: tuple[T | None, BaseException | None] = (None, error)
            else:
                outcome = (value, None)
            with self._lock:
                wait.ended = True
                if wait.abandoned:
                    self._waiting -= 1
                    return
            try:
                loop.call_soon_threadsafe(_settle, answer, outcome)
            except RuntimeError:  # pragma: no cover — the loop has ended: nobody waits
                return

        threading.Thread(target=body, name="ela-disk", daemon=True).start()
        try:
            async with asyncio.timeout(self._limit):
                return await asyncio.shield(answer)
        except asyncio.CancelledError:
            # A wait cancelled by whoever waited for it: given up like one past the limit, unless
            # its work has ended — and the cancellation goes on either way.
            self._abandoned(gone, wait)
            raise
        except TimeoutError:
            step = self._abandoned(gone, wait)
            if step is None:
                # The work ended as the wait was given up: its outcome is on its way.
                return await answer
            raise DiskSilent(self._silent(what, step)) from None

    def _room(self, what: str) -> None:
        with self._lock:
            standing = self._waiting
        if standing >= self._most:
            raise DiskSilent(
                f"{what}: {standing} waits on the disk are still standing, the most ELA leaves "
                "waiting — they end when the disk answers, and nothing new is asked of it until "
                "then"
            )

    def _abandoned(self, gone: Gone, wait: _Wait) -> str | None:
        """Give the wait up, unless the work has ended: the step it had reached, or ``None``."""
        with self._lock:
            if wait.ended:
                return None
            wait.abandoned = True
            self._waiting += 1
        return gone._abandon()  # noqa: SLF001 — the guard and its mark are one mechanism

    def _silent(self, what: str, step: str) -> str:
        said = f"{what}: the disk did not answer within {self._limit:g} s, and ELA stopped waiting"
        if step == WRITING:
            return f"{said}; the write may still happen when the disk answers"
        if step == MAKING_THE_FOLDER:
            return f"{said}; the folder may still be made, and the file will not be written"
        return f"{said}; nothing was written"


def _settle[T](future: asyncio.Future[T], outcome: tuple[T | None, BaseException | None]) -> None:
    """The outcome of a work nobody gave up, handed to the coroutine that waits for it: the one
    place the future is settled, once."""
    value, error = outcome
    if error is not None:
        future.set_exception(error)
    else:
        future.set_result(value)  # type: ignore[arg-type]


def within_the_limit[T](work: Callable[[Gone], T], what: str, *, limit: float) -> T:
    """The guard for a synchronous caller (the start-up): ``work`` in a ``daemon`` thread, joined
    at most ``limit``; :class:`DiskSilent` past it. The start-up is one look per folder, with the
    person who started ELA in front of it, so there is no ceiling of standing waits here."""
    gone = Gone()
    box: list[tuple[T | None, BaseException | None]] = []

    def body() -> None:
        try:
            box.append((work(gone), None))
        except BaseException as error:  # noqa: BLE001 — handed to the caller
            box.append((None, error))

    thread = threading.Thread(target=body, name="ela-disk-start", daemon=True)
    thread.start()
    thread.join(limit)
    if not box:
        gone._abandon()  # noqa: SLF001 — the guard and its mark are one mechanism
        raise DiskSilent(
            f"{what}: the system did not answer within {limit:g} s. If a window asked for a "
            "permission, answer it and start ELA again"
        )
    value, error = box[0]
    if error is not None:
        raise error
    return value  # type: ignore[return-value]
