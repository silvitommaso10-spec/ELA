"""The stories of the Command Center, with one driver: a browser (M17.2; ADR 0044).

ADR 0043 §9 gave the companion a contract of its own instead of the nodes' thirteen stories,
because an identity that takes no work has nothing to play in twelve of them. The console is the
same species of identity and gets the same treatment — and here the point is not to repeat the
phone's suite but to walk the four things that are **this** surface's: the third role, the ceiling
derived from the socket, the conduct of a "yes" that must be the phone's own, and the refusal of a
credential carried onto the other surface's ground.

The world is ``conftest.py``'s: the real application, a real migrated database, HTTP over the ASGI
transport. The driver is a client with **no header at all** — what a browser is — and the two ends
of its socket are chosen per story, because that is what dec. J reads.

**What this suite cannot prove** (the form of ADR 0038 §18):

* **A browser is not here.** ``httpx`` holds a cookie because it was told to; Chrome and Safari
  decide for themselves, and what they decide was measured by hand on this Mac (C1) and is written
  in the milestone, not here.
* **A network is not here.** The addresses are the ASGI scope's, set by the test; that a packet
  from the tailnet really arrives with the tailnet address at both ends is P0, measured, and not
  something this suite can say.
* **Nothing is forwarded here.** The one risk dec. J carries — something inbound proxying through
  the loopback — is invisible to any test, and what watches it is the sentence the page prints.

Green here means: the Core and a browser say the same thing about the contract. Green **at the
Mac**, at the two addresses, is the hand test.
"""

from __future__ import annotations

from typing import Any, Final

import pytest
from httpx import ASGITransport, AsyncClient

from ela.api.console import FROM_AWAY, FROM_THIS_MACHINE
from ela.api.security import CONSOLE_COOKIE, SEPARATOR
from ela.domain import ActorKind, AuditEventType, DeviceRole, TaskState
from tests.api.support import echo_plan, note_plan
from tests.conformance.driver import Conformance

E = AuditEventType
DECLARED: Final = {"name": "MacBook", "os": "MACOS"}
LOOPBACK: Final = "http://127.0.0.1"
TAILNET: Final = "http://100.76.92.39"
"""The two addresses of P0: the same Mac, and the two ends of the socket that tell them apart."""
AWAY: Final = ("100.70.98.26", 54536)


class Browser:
    """The one driver of the console: a cookie, forms, and no header ever.

    ``at`` is the address this browser has open, and ``peer`` who dialled: together they are what
    the middleware reads to decide the ceiling (dec. J). Everything else — the tasks, the codes,
    the revocations — is the user's and lives on :class:`~tests.conformance.driver.Conformance`.
    """

    def __init__(
        self, world: Conformance, at: str = LOOPBACK, peer: tuple[str, int] = ("127.0.0.1", 123)
    ) -> None:
        self._world = world
        self.at = at
        self.client = AsyncClient(transport=ASGITransport(app=world.app, client=peer), base_url=at)
        self.headers = {"Origin": at}

    async def enrol(self, code: str, **declared: str) -> Any:
        return await self.client.post(
            "/console/enroll", data={"code": code, **DECLARED, **declared}, headers=self.headers
        )

    async def open(self, path: str = "/console/") -> Any:
        return await self.client.get(path)

    async def answer(self, approval_id: str, said: str = "yes") -> Any:
        return await self.client.post(
            "/console/answer", data={"id": approval_id, "answer": said}, headers=self.headers
        )

    async def stop(self, task_id: str) -> Any:
        return await self.client.post("/console/cancel", data={"id": task_id}, headers=self.headers)

    def carrying(self, cookie: str, at: str = TAILNET, peer: tuple[str, int] = AWAY) -> Browser:
        """The same credential, another address: the console the user opened from elsewhere."""
        other = Browser(self._world, at=at, peer=peer)
        other.client.cookies.set(CONSOLE_COOKIE, cookie)
        return other

    @property
    def cookie(self) -> str:
        value = self.client.cookies.get(CONSOLE_COOKIE)
        assert value is not None
        return value

    async def aclose(self) -> None:
        await self.client.aclose()


@pytest.fixture
async def console(world: Conformance) -> Any:
    """A browser that has enrolled as a console, at the address a person types on the Mac."""
    browser = Browser(world)
    answered = await browser.enrol(await world.issue(role="CONSOLE"))
    assert answered.status_code == 303, answered.text
    yield browser
    await browser.aclose()


async def console_id(world: Conformance) -> str:
    rows = (await world.client.get("/devices")).json()
    return str(next(one for one in rows if one["role"] == DeviceRole.CONSOLE.value)["id"])


# ----------------------------------------------------------------------------------------
# K1 — enrol as a console
# ----------------------------------------------------------------------------------------


async def test_k1_a_console_code_is_spent_by_the_form_and_the_row_says_what_it_is(
    world: Conformance,
) -> None:
    """The secret comes back once, in a ``Set-Cookie``, and never in a body; the row is born
    ``CONSOLE``, with no capability and no tool — it declares that it can do nothing, and that is
    true: a console takes no work."""
    browser = Browser(world)
    try:
        answered = await browser.enrol(await world.issue(role="CONSOLE"))

        assert answered.status_code == 303
        assert CONSOLE_COOKIE in answered.headers["set-cookie"]
        assert "secret" not in answered.text
        rows = (await world.client.get("/devices")).json()
        row = next(one for one in rows if one["role"] == DeviceRole.CONSOLE.value)
        assert (row["available_tools"], row["capabilities"], row["available"]) == ([], [], False)
        assert any(
            one["event_type"] == E.DEVICE_ENROLLED.value and "role CONSOLE" in one["summary"]
            for one in (await world.client.get("/audit")).json()
        )
    finally:
        await browser.aclose()


async def test_k2_a_code_of_another_role_is_refused_here_and_stays_spendable(
    world: Conformance,
) -> None:
    """The symmetry of ADR 0043 §3, for the third role: the refusal touches no row."""
    browser = Browser(world)
    try:
        code = await world.issue(role="COMPANION")

        refused = await browser.enrol(code)

        assert refused.status_code == 422
        spent = await world.client.post(
            "/companion/enroll", data={"code": code, "name": "iPhone", "os": "IOS"}
        )
        assert spent.status_code in {303, 403}, "the code was not consumed by the refusal"
    finally:
        await browser.aclose()


# ----------------------------------------------------------------------------------------
# K3 — the ceiling is of the request, not of the row
# ----------------------------------------------------------------------------------------


async def test_k3_the_same_console_sees_the_goal_from_here_and_the_id_from_away(
    world: Conformance, console: Browser
) -> None:
    """Dec. J, end to end: one cookie, one page, two addresses — and the page says which ceiling
    is in force each time, which is the only way the difference is visible to a person."""
    task = await world.task(echo_plan())
    goal = (await world.client.get(f"/tasks/{task}")).json()["goal"]

    here = await console.open(f"/console/task?id={task}")

    assert goal in here.text
    assert FROM_THIS_MACHINE in here.text

    away = console.carrying(console.cookie)
    try:
        there = await away.open(f"/console/task?id={task}")
    finally:
        await away.aclose()

    assert goal not in there.text
    assert task in there.text


async def test_k4_the_registry_keeps_the_level_the_user_imposed(
    world: Conformance, console: Browser
) -> None:
    """A promotion that wrote itself down would be a ceiling that changed without a decision."""
    await console.open()

    rows = (await world.client.get("/devices")).json()
    row = next(one for one in rows if one["role"] == DeviceRole.CONSOLE.value)

    assert row["privacy"] == "TRUSTED"


# ----------------------------------------------------------------------------------------
# K5 — a "yes" answers and runs, through the conduct both surfaces share
# ----------------------------------------------------------------------------------------


async def test_k5_a_yes_answers_and_resumes_the_task(world: Conformance, console: Browser) -> None:
    """The two things the user does at the Mac, in one request (M12.5 dec. H1) — and the actor is
    the **user**, with the id of the browser the act came from (ADR 0037 §15)."""
    task = await world.task(note_plan())
    await world.client.post(f"/tasks/{task}/run")
    identifier = (await world.client.get("/approvals")).json()[0]["id"]

    answered = await console.answer(identifier)

    assert answered.status_code in {200, 303}
    assert (await world.client.get(f"/tasks/{task}")).json()["state"] == TaskState.COMPLETED.value
    resolved = [
        one
        for one in (await world.client.get(f"/audit?task_id={task}")).json()
        if one["event_type"] == E.APPROVAL_RESOLVED.value
    ]
    assert resolved and resolved[0]["actor"]["kind"] == ActorKind.USER.value
    assert resolved[0]["actor"]["id"] == await console_id(world)


async def test_k6_stopping_a_task_is_signed_by_the_console(
    world: Conformance, console: Browser
) -> None:
    """A route that only takes away, and the audit says **where** the act came from."""
    task = await world.task(note_plan())

    await console.stop(task)

    assert (await world.client.get(f"/tasks/{task}")).json()["state"] == TaskState.CANCELLED.value
    cancelled = next(
        one
        for one in (await world.client.get(f"/audit?task_id={task}")).json()
        if one["event_type"] == E.TASK_CANCELLED.value
    )
    assert cancelled["actor"] == {"kind": ActorKind.USER.value, "id": await console_id(world)}


# ----------------------------------------------------------------------------------------
# K7 — a credential is worth its own ground, and a revocation closes the door
# ----------------------------------------------------------------------------------------


async def test_k7_the_credential_of_a_console_opens_nothing_on_the_phones_ground(
    world: Conformance, console: Browser
) -> None:
    """The two cookies have two names and two paths, so a browser never sends one to the other's
    ground (C1). What is exercised here is the credential somebody **copies**."""
    phone = Browser(world)
    try:
        phone.client.cookies.set("ela_companion", console.cookie)
        answered = await phone.open("/companion/")
    finally:
        await phone.aclose()

    assert answered.status_code == 401
    assert "<form" in answered.text


async def test_k8_the_secret_of_a_console_is_refused_in_a_header(
    world: Conformance, console: Browser
) -> None:
    """The bearer is part of the role: a browser's credential in a header opens nothing."""
    identity, _, secret = console.cookie.partition(SEPARATOR)
    machine = world.node_client()
    try:
        answered = await machine.get(
            "/nodes/me", headers={"Authorization": f"Bearer {identity}{SEPARATOR}{secret}"}
        )
    finally:
        await machine.aclose()

    assert answered.status_code == 401


async def test_k9_a_revoked_console_is_asked_to_enrol_again(
    world: Conformance, console: Browser
) -> None:
    """The revocation is the remedy for a cookie in the wrong hands, and it acts at once."""
    assert (await console.open()).status_code == 200

    revoked = await world.client.post(f"/nodes/{await console_id(world)}/revoke")

    assert revoked.status_code == 200
    again = await console.open()
    assert again.status_code == 401
    assert "<form" in again.text


def test_k10_the_two_sentences_of_the_ceiling_differ() -> None:
    """The page speaks in both directions, and a page that said the same thing from both sides
    would say nothing at all (dec. 17 of the review)."""
    assert FROM_THIS_MACHINE != FROM_AWAY
