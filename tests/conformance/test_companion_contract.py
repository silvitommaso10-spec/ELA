"""The nine stories of the companion, with one driver: a browser (M12.5 dec. A; ADR 0043).

M12.3 and M12.4 measured themselves against the thirteen stories of the work protocol. **M12.5
cannot**, and that is a finding and not a shortcut: an identity that takes no work leaves twelve of
those thirteen with nothing to play — «non chiedere mai» proves the expiry of an *offer* nobody
makes it, «consegna due volte» presupposes work it never took — and a kit with thirteen entries in
``UNSUPPORTED`` would be a driver that recites nothing. So the contract of the companion is written
here, once, with the one bearer a browser has: a cookie, and forms.

The world is the one of ``conftest.py``: the real application, a real migrated database, HTTP over
the ASGI transport. The driver is a client with **no header at all** — what a browser is.

**What this suite cannot prove** (the form of ADR 0038 §18, and it is the honest half of M12.5):

* **A browser is not here.** ``httpx`` holds a cookie because it was told to; Safari and Chrome
  decide for themselves, and what they decide was measured by hand on the iPhone (P1–P4) and is
  written in the milestone, not here.
* **No network, no tailnet, no Tailscale.** The address a notification opens is composed from what
  the server bound, and here nothing is bound.
* **No notification.** The bell is a fake in this suite; what ntfy.sh does with a message is P4.
* **No Universal Clipboard, no Siri, no Shortcut.** How the code crosses to the phone is P3.

Green here means: the Core and a browser say the same thing about the contract. Green **on the
iPhone** is the hand test.
"""

from __future__ import annotations

from typing import Any, Final
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from ela.api.security import COMPANION_COOKIE, COMPANION_ROUTES
from ela.domain import ActorKind, AuditEventType, DeviceRole, RiskLevel, TaskState
from ela.testing.fakes import FakeBell
from tests.api.support import echo_plan, note_plan
from tests.conformance.driver import Conformance

E = AuditEventType
DECLARED: Final = {"name": "iPhone", "os": "IOS"}


class Browser:
    """The one driver of the companion: a cookie, forms, and no header ever.

    It drives; it decides nothing — the tasks, the codes and the revocations are the user's, and
    they live on :class:`~tests.conformance.driver.Conformance`, exactly as for a node.
    """

    def __init__(self, world: Conformance) -> None:
        self._world = world
        self.client = AsyncClient(transport=ASGITransport(app=world.app), base_url=world.base_url)
        self.headers = {"Origin": world.base_url}

    async def enrol(self, code: str, **declared: str) -> Any:
        """Paste the code into the form of the enrolment page, as the user does on the phone."""
        return await self.client.post(
            "/companion/enroll", data={"code": code, **DECLARED, **declared}, headers=self.headers
        )

    async def open(self, path: str = "/companion/") -> Any:
        return await self.client.get(path)

    async def answer(self, approval_id: str, said: str = "yes") -> Any:
        return await self.client.post(
            "/companion/answer", data={"id": approval_id, "answer": said}, headers=self.headers
        )

    async def stop(self, task_id: str) -> Any:
        return await self.client.post(
            "/companion/cancel", data={"id": task_id}, headers=self.headers
        )

    async def aclose(self) -> None:
        await self.client.aclose()


@pytest.fixture
async def phone(world: Conformance) -> Any:
    """A browser that has enrolled: the credential is in its cookie jar and nowhere else."""
    browser = Browser(world)
    answered = await browser.enrol(await world.issue(role="COMPANION"))
    assert answered.status_code == 303, answered.text
    yield browser
    await browser.aclose()


async def companion_id(world: Conformance) -> str:
    rows = (await world.client.get("/devices")).json()
    return str(next(one for one in rows if one["role"] == DeviceRole.COMPANION.value)["id"])


# ----------------------------------------------------------------------------------------
# C1 — enrol as a companion
# ----------------------------------------------------------------------------------------


async def test_c1_a_companion_code_is_spent_by_the_form_and_the_row_says_what_it_is(
    world: Conformance,
) -> None:
    """The secret comes back once, in a ``Set-Cookie``, and never in a body; the row is born
    ``COMPANION``, ``IOS``, with no capability and no tool — it declares that it can do nothing,
    and that is true."""
    browser = Browser(world)
    try:
        answered = await browser.enrol(await world.issue(role="COMPANION"))

        assert answered.status_code == 303
        assert COMPANION_COOKIE in answered.headers["set-cookie"]
        assert "secret" not in answered.text
        rows = (await world.client.get("/devices")).json()
        row = next(one for one in rows if one["role"] == DeviceRole.COMPANION.value)
        assert (row["os"], row["available_tools"], row["capabilities"]) == ("IOS", [], [])
        assert any(
            one["event_type"] == E.DEVICE_ENROLLED.value and "role COMPANION" in one["summary"]
            for one in (await world.client.get("/audit")).json()
        )
    finally:
        await browser.aclose()


async def test_c1_a_code_of_another_role_or_another_route_is_refused_and_not_spent(
    world: Conformance,
) -> None:
    """Dec. C.5: the role is a condition of the statement that spends the code."""
    browser = Browser(world)
    try:
        code = await world.issue(role="COMPANION")
        elsewhere = await world.client.post(
            "/nodes/enroll", json=DECLARED, headers={"Authorization": f"Bearer {code}"}
        )
        assert elsewhere.status_code == 422

        assert (await browser.enrol(code)).status_code == 303, "the code is still spendable"
    finally:
        await browser.aclose()


# ----------------------------------------------------------------------------------------
# C2 — one request is enough
# ----------------------------------------------------------------------------------------


async def test_c2_every_page_answers_one_request_with_nothing_to_reread(phone: Browser) -> None:
    """No ``If-Match``, no ``ETag`` to read back, no long poll: the only wait in the companion is
    the run of dec. H. Derived from the routes, not listed — a page added to
    ``COMPANION_ROUTES`` is walked here the day it is written."""
    for method, path in sorted(COMPANION_ROUTES):
        if method != "GET":
            continue
        # The pages that take an id are asked with one that names nothing: what is being proved is
        # that one request is enough and that no page hands back an entity tag to read again —
        # not that an invented id exists, which is a ``404`` and says so.
        answered = await phone.client.get(f"{path}?id={uuid4()}")

        assert answered.status_code in {200, 404}, path
        assert "ETag" not in answered.headers, path


# ----------------------------------------------------------------------------------------
# C3 — nothing ever arrives at a companion
# ----------------------------------------------------------------------------------------


async def test_c3_a_task_walks_with_a_companion_in_the_registry_and_nothing_is_placed_on_it(
    world: Conformance, phone: Browser
) -> None:
    """Dec. A and B: the companion is among the candidates and is refused ``UNAVAILABLE``, for a
    step **with no required capability** too — the case where ``MISSING_TOOL`` cannot fire, and
    the one that would have let the runner open a task in its name."""
    task_id = await world.task(echo_plan(), privacy="TRUSTED")

    walked = await world.walk(task_id)

    assert walked.status == 200, walked.body
    assert walked.body["task"]["state"] == TaskState.COMPLETED.value
    written = (await world.client.get("/audit")).json()
    placed = [one for one in written if one["event_type"] == E.DEVICE_SELECTED.value]
    assert placed, "or this story would be vacuous"
    phone_id = await companion_id(world)
    assert all(one["device_id"] != phone_id for one in placed)
    candidates = [
        candidate
        for one in placed
        for candidate in one["payload"]["candidates"]
        if candidate["device_id"] == phone_id
    ]
    assert candidates, "the companion is judged like every other row (D19), not filtered out"
    assert all("UNAVAILABLE" in candidate["refusals"] for candidate in candidates), candidates


# ----------------------------------------------------------------------------------------
# C4 — answer, and sign who chose
# ----------------------------------------------------------------------------------------


async def test_c4_the_yes_and_the_grant_carry_the_id_of_the_iphone(
    world: Conformance, phone: Browser
) -> None:
    """The user's fixed point 2: every "yes" leaves the iPhone's identity in ``responded_by``."""
    task_id = await world.task(note_plan(), privacy="TRUSTED")
    await world.walk(task_id)
    waiting = (await world.client.get("/approvals")).json()
    assert waiting

    answered = await phone.answer(waiting[0]["id"])

    assert answered.status_code == 303
    phone_id = await companion_id(world)
    written = (await world.client.get("/audit")).json()
    resolved = next(one for one in written if one["event_type"] == E.APPROVAL_RESOLVED.value)
    assert resolved["actor"]["id"] == phone_id
    granted = next(one for one in written if one["event_type"] == E.AUTHORIZATION_GRANTED.value)
    assert granted["actor"]["id"] == phone_id
    assert (await world.client.get(f"/tasks/{task_id}")).json()["state"] == "COMPLETED"


# ----------------------------------------------------------------------------------------
# C5 — see only what the ceiling admits
# ----------------------------------------------------------------------------------------


async def test_c5_a_local_only_task_shows_no_content_and_cannot_be_answered_from_here(
    world: Conformance, phone: Browser
) -> None:
    """Dec. F2-a: the ceiling of the companion decides what it sees, and one does not approve what
    one cannot see (§30)."""
    task_id = await world.task(note_plan(), privacy="LOCAL_ONLY")
    await world.walk(task_id)
    waiting = (await world.client.get("/approvals")).json()
    assert waiting

    page = await phone.open(f"/companion/approval?id={waiting[0]['id']}")
    assert page.status_code == 200
    assert "briefing.md" not in page.text
    assert "resta sul Mac" in page.text

    refused = await phone.answer(waiting[0]["id"])
    assert refused.status_code == 409
    assert (await world.client.get("/approvals")).json(), "the question still waits"


# ----------------------------------------------------------------------------------------
# C6 — be revoked
# ----------------------------------------------------------------------------------------


async def test_c6_a_revoked_companion_is_shut_out_and_the_question_stays_answerable_at_the_mac(
    world: Conformance, phone: Browser
) -> None:
    """The revocation reaches the browser at its next request, the cookie is taken away, and what
    the user could do at the Mac they can still do. A new code enrols the same browser again."""
    task_id = await world.task(note_plan(), privacy="TRUSTED")
    await world.walk(task_id)
    phone_id = await companion_id(world)

    assert (await world.revoke(phone_id)).status == 200

    shut = await phone.open()
    assert shut.status_code == 401
    assert "Max-Age=0" in shut.headers["set-cookie"]
    assert any(
        one["event_type"] == E.DEVICE_REJECTED.value and "revoked" in one["summary"]
        for one in (await world.client.get("/audit")).json()
    )
    assert (await world.approve(task_id)).status == 200, "the Mac answers what the phone cannot"

    again = await phone.enrol(await world.issue(role="COMPANION"))
    assert again.status_code == 303, "a new code enrols the browser again"


# ----------------------------------------------------------------------------------------
# C7 — everyone on their own ground
# ----------------------------------------------------------------------------------------


async def test_c7_a_node_a_companion_in_a_header_and_the_core_are_each_refused_in_their_turn(
    world: Conformance, phone: Browser
) -> None:
    """The three cases of the review: a node's credential on a page, a companion's secret in a
    header, the Core's token on a page. Each gets the JSON ``401``, and where the identity exists
    the audit says ``route_not_allowed``."""
    code = await world.issue()
    born = (
        await world.node_client().post(
            "/nodes/enroll",
            json={"name": "pc", "os": "WINDOWS"},
            headers={"Authorization": f"Bearer {code}"},
        )
    ).json()
    node = {"Authorization": f"Bearer {born['device_id']}.{born['secret']}"}
    phone_id = await companion_id(world)

    with_a_node = await phone.client.get("/companion/", headers=node)
    assert with_a_node.status_code == 401
    assert with_a_node.json()["error"]["code"] == "unauthorized"

    as_a_header = await world.node_client().get(
        "/companion/", headers={"Authorization": f"Bearer {phone_id}.{'x' * 43}"}
    )
    assert as_a_header.status_code == 401

    core = await world.client.get("/companion/")
    assert core.status_code == 401
    assert core.json()["error"]["code"] == "unauthorized"

    written = (await world.client.get("/audit")).json()
    assert any("route_not_allowed" in one["summary"] for one in written)


# ----------------------------------------------------------------------------------------
# C8 — stop
# ----------------------------------------------------------------------------------------


async def test_c8_stopping_is_signed_user_with_the_id_of_the_phone(
    world: Conformance, phone: Browser
) -> None:
    """Dec. I: the actor comes from the identity the middleware resolved, and for a phone that is
    a person — ``USER``, with the phone's id, so the audit says where the act came from."""
    task_id = await world.task(echo_plan(), privacy="TRUSTED")
    phone_id = await companion_id(world)

    answered = await phone.stop(task_id)

    assert answered.status_code == 303
    assert (await world.client.get(f"/tasks/{task_id}")).json()["state"] == "CANCELLED"
    cancelled = next(
        one
        for one in (await world.client.get("/audit")).json()
        if one["event_type"] == E.TASK_CANCELLED.value
    )
    assert cancelled["actor"] == {"kind": ActorKind.USER.value, "id": phone_id}


# ----------------------------------------------------------------------------------------
# C9 — the bell says nothing of yours
# ----------------------------------------------------------------------------------------


async def test_c9_what_the_provider_receives_is_the_text_of_a_voice_and_nothing_else(
    world: Conformance, phone: Browser
) -> None:
    """Dec. E: the port takes a ``RiskLevel``, so a goal and an argument cannot reach a third
    party — and this walks the whole way to check it, with a task whose words are recognisable."""
    recognisable = "scrivi-la-nota-riconoscibile"
    task_id = await world.task(note_plan(), privacy="TRUSTED")
    await world.client.post(f"/tasks/{task_id}/plan", json=note_plan(body=recognisable))

    await world.walk(task_id)

    bell = world.ela.bell
    assert isinstance(bell, FakeBell)  # the world's bell, named at build (conftest)
    assert bell.rung, "the question was asked, so the bell rang"
    assert all(isinstance(voice, RiskLevel) for voice in bell.rung)
    written = " ".join(
        one["summary"] + str(one.get("payload"))
        for one in (await world.client.get("/audit")).json()
        if one["event_type"] == E.BELL_RUNG.value
    )
    assert recognisable not in written
    assert "note" not in written.lower(), "not even the capability's own words travel by accident"
