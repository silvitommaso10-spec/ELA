"""The contract a node implements, and the world it talks to (M12.2, dec. P; ADR 0038 §18).

**This file is the artefact M12.3–M12.5 inherit.** They write a :class:`NodeDriver` for their
platform — the macOS node, the Windows Power Node, the iPhone companion — and recite the stories of
``test_node_contract.py`` unchanged. A driver that needed the stories bent to fit it would have
turned the contract into a description of whatever was built, which is the one thing a conformance
suite must not become.

Three decisions are worth saying out loud, because every driver inherits them:

* **The acts are the protocol, and the answers are data.** Every method returns an
  :class:`Answered` — the status, the body, the ``ETag`` where there is one — instead of raising on
  a refusal or hiding it. A story asserts ``410`` because that is what the node is *told*, and a
  driver that translated statuses into exceptions would make the stories unable to say what they are
  about.
* **A driver drives; it decides nothing.** It enrolls, announces, reports, asks, runs a tool,
  delivers, renews, goes quiet, restarts, and (where the platform allows it) clones itself. Which
  task exists, who approves it and when the clock moves are the *user's* acts and the Core's, and
  they live on :class:`Conformance`.
* **A story a driver cannot recite is declared, never skipped quietly.** :attr:`NodeKit.unsupported`
  maps a story of :data:`STORIES` to the reason — "a Shortcut cannot be cloned into two processes" —
  and the suite turns that into a visible skip (ADR 0031 §6). ``test_unsupported.py`` pins the map
  per driver, so it cannot grow in silence.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ela.composition import Ela
from ela.testing.fakes import FakeClock

STORIES: tuple[str, ...] = (
    "enrolled_and_reports",
    "never_asks",
    "goes_quiet",
    "comes_back_late",
    "comes_back_twice_over",
    "ask_together",
    "delivers_twice",
    "delivers_what_is_not_its_own",
    "revoked_halfway",
    "works_longer_than_the_ttl",
    "the_core_dies_halfway",
    "an_undeclared_task_never_arrives",
    "what_is_verified_only_here_never_arrives",
)
"""The thirteen stories of dec. P, by key, in the order the spec lists them.

Keys and not test names: a story is a *property of the protocol*, and the test that plays it may be
renamed or split without the map of what a driver cannot do changing meaning. Every key here has a
test in ``test_node_contract.py`` and every key a driver declares unsupported is one of these —
both held by ``test_unsupported.py``.
"""


@dataclass(frozen=True, slots=True)
class Answered:
    """What the Core answered one act of a node: the status, the body, the entity tag.

    ``body`` is ``{}`` for an answer with none — a ``204`` from ``POST /nodes/work`` — so a story
    can read it without asking first whether there was one. ``etag`` is the revision of
    ``PUT /nodes/me`` (ADR 0037 §9) and ``None`` everywhere else.
    """

    status: int
    body: Mapping[str, Any]
    etag: str | None = None

    @property
    def code(self) -> str | None:
        """The error code of a refusal, or ``None`` for an answer that is not one."""
        error = self.body.get("error")
        return error.get("code") if isinstance(error, dict) else None


@dataclass
class Conformance:
    """The world the stories happen in: one Core, its clock, and a way to reach it.

    Everything here is the **user's** side or the Core's — creating a task, approving a step,
    issuing an enrollment code, moving time, restarting the process. A driver never touches it:
    what a node may do is exactly :class:`NodeDriver`, which is the point of having two objects.
    """

    app: FastAPI
    ela: Ela
    clock: FakeClock
    client: AsyncClient
    """A client carrying the **Core's** token: the user's acts, and never a node's."""
    base_url: str
    reborn: Callable[[], Awaitable[None]]
    """Start the Core again over the same database, as a process that never saw what happened.

    The Core's act and not a node's, which is why it lives here. It keeps **this** clock — the same
    instance across the two builds — because a restart is not a time machine: what a crash loses is
    memory, not the hour. Nothing of the old process survives it: the lifespan of the new one runs,
    so ``recover()`` gets its say (ADR 0023 §11).
    """

    def node_client(self) -> AsyncClient:
        """A client with no credentials at all, for a node to present its own.

        The transport is ASGI, so a request reaches the application in this process and no socket is
        opened — which is also the first thing the suite cannot prove (see the limits in
        ``test_node_contract.py``).
        """
        return AsyncClient(transport=ASGITransport(app=self.app), base_url=self.base_url)

    async def issue(self, privacy: str = "TRUSTED") -> str:
        """``ela node enroll``: a one-shot code, with the level the user imposes (ADR 0037 §5)."""
        answered = await self.client.post("/nodes/enrollments", json={"privacy": privacy})
        assert answered.status_code == 201, answered.text
        return str(answered.json()["code"])

    async def task(self, plan: Mapping[str, Any], *, privacy: str | None = None) -> str:
        """A task with ``plan`` attached, ready to walk; ``privacy`` is its declared sensitivity."""
        body: dict[str, Any] = {"text": "una cosa da fare"}
        if privacy is not None:
            body["max_privacy"] = privacy
        created = await self.client.post("/tasks", json=body)
        assert created.status_code == 201, created.text
        task_id = str(created.json()["id"])
        planned = await self.client.post(f"/tasks/{task_id}/plan", json=dict(plan))
        assert planned.status_code == 200, planned.text
        return task_id

    async def walk(self, task_id: str) -> Answered:
        """``POST /tasks/{id}/run``: the walk of production, with nothing passed that a user
        could not pass."""
        answered = await self.client.post(f"/tasks/{task_id}/run")
        return Answered(answered.status_code, answered.json())

    async def approve(self, task_id: str) -> Answered:
        """Say yes to the one request of consent this task is waiting on (§30)."""
        pending = (await self.client.get("/approvals")).json()
        waiting = [one for one in pending if one["task_id"] == task_id]
        assert len(waiting) == 1, waiting
        answered = await self.client.post(
            f"/tasks/{task_id}/approve", json={"approval_id": waiting[0]["id"]}
        )
        return Answered(answered.status_code, answered.json())

    async def revoke(self, device_id: str) -> Answered:
        """``ela node revoke``: the row stays, the secret opens nothing, the work is cut (D17)."""
        answered = await self.client.post(f"/nodes/{device_id}/revoke")
        return Answered(answered.status_code, answered.json())


@runtime_checkable
class NodeDriver(Protocol):
    """What a node can do, and nothing else (ADR 0038 §11; M12.1, ADR 0037 §4, §9).

    The nine acts are the protocol a real node speaks. Nothing here decides anything: there is no
    method for "be chosen", because being chosen is the orchestrator's, and none for "create work",
    because work comes from a task the user asked for.
    """

    @property
    def device_id(self) -> str:
        """The id the Core minted at enrollment (D5). A node never chooses its own."""

    @property
    def revision(self) -> int:
        """The revision this node last saw, for the ``If-Match`` of its next announcement."""

    async def enroll(self, code: str, **declared: Any) -> Answered:
        """Spend an enrollment code and come into existence (ADR 0037 §5)."""

    async def announce(self, **declared: Any) -> Answered:
        """Rewrite the declared half at the revision last seen: ``If-Match`` in, ``ETag`` out."""

    async def report(self, **observed: Any) -> Answered:
        """A sign of life, with what the node observes of itself; no event (ADR 0016 §6)."""

    async def ask(self) -> Answered:
        """``POST /nodes/work``: ask, and hold the request until there is work — or ``204``."""

    async def run(self, order: Mapping[str, Any]) -> Mapping[str, Any]:
        """Run the call of ``order`` **on this node** and return the envelope to deliver.

        The one act that is genuinely the platform's: here is where a macOS node speaks through its
        own voice and a Windows node renders with its own GPU. Everything the Core gets back is the
        envelope of ADR 0038 §4 — what the tool said, and nothing the Core already knows.
        """

    async def deliver(
        self, envelope: Mapping[str, Any], *, assignment_id: str | None = None
    ) -> Answered:
        """``POST /nodes/work/result``: bring the envelope back, with the id **in the body**.

        ``assignment_id`` defaults to the work this node holds. A story passes one explicitly to
        deliver on an id that is not its own — which must be answered exactly as an id the Core
        never minted, and is the reason the parameter exists at all.
        """

    async def renew(self, assignment_id: str) -> Answered:
        """``POST /nodes/work/renew``: ask for more time on the work in hand."""

    async def restart(self) -> None:
        """Come back as a new process that kept its identity — and whatever it had in hand.

        What a node keeps is what it wrote down: its id and its secret. Its **revision** is not one
        of those — it is a fact of the Core's row, and a copy of it on a node is a cache nobody
        resynchronises — so a driver that comes back here has to read it again, with
        ``GET /nodes/me`` (M12.3 dec. L). A driver that remembered one instead announces against a
        number nobody promised it and reads ``412`` for ever; story 11 is where that shows.
        """

    def clone(self) -> NodeDriver:
        """A second process with **this** identity, for the story of two clones (ADR 0035 §5).

        A driver whose platform cannot do it declares the story unsupported instead of pretending:
        one Shortcut is not two processes.
        """


class NodeKit(Protocol):
    """How the suite gets a node of one implementation, and what that implementation cannot play."""

    @property
    def name(self) -> str:
        """What the parametrised tests are labelled with."""

    @property
    def unsupported(self) -> Mapping[str, str]:
        """Story key → the reason this implementation cannot recite it. Empty for the fake node."""

    async def node(
        self, world: Conformance, *, privacy: str = "TRUSTED", tools: tuple[str, ...] | None = None
    ) -> NodeDriver:
        """A node of this implementation, enrolled and ready: the Core minted its id and secret."""


def needs(kit: NodeKit, story: str) -> None:
    """Skip visibly when ``kit`` has declared ``story`` unrecitable (ADR 0031 §6).

    A ``skipif`` and not an ``if`` inside the test: a story that did not run has to appear in the
    summary with its reason, or a suite can quietly stop proving the thing it exists for.
    """
    assert story in STORIES, f"{story} is not a story of the contract"
    reason = kit.unsupported.get(story)
    if reason is not None:
        pytest.skip(f"{kit.name} cannot recite {story}: {reason}")
