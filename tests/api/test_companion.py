"""The pages of the iPhone (M12.5; ADR 0043): who gets in, what they see, and what a "yes" does.

What is proved here is not "the page renders": it is the four rules of dec. C.3, the ceiling of
dec. F.2, and the order of dec. H1 — the three places where a page of ELA could quietly become
something the user did not agree to. The browser itself is not here (ADR 0038 §18): a cookie in
``httpx`` is not Safari, and the hand test on the iPhone is what says the rest.
"""

from __future__ import annotations

import html
import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ela.api.companion import (
    IDLE,
    SHOWN,
    WAITING_APPROVAL,
    WORKING,
    _pairs,
    may_see,
    presence,
    terms,
)
from ela.api.pages import CONTENT_SECURITY_POLICY, STYLESHEETS
from ela.api.schemas import ApprovalOut
from ela.api.security import COMPANION_COOKIE, COMPANION_HOME, COMPANION_ROUTES, Identity, Kind
from ela.composition import Ela
from ela.devices import NodeEnrollment
from ela.domain import (
    Approval,
    ApprovalId,
    ApprovalStatus,
    AuditEventType,
    DeviceRole,
    PrivacyLevel,
    StepId,
    TaskId,
    TaskState,
)
from ela.permissions import SINGLE_USE
from ela.ports import EnrollmentExpiredError
from tests.api.support import BASE, echo_plan, note_plan, queued

ORIGIN = {"Origin": BASE}
"""What a browser sends on a ``POST``, and what every page of ELA answers to (dec. C.1)."""
DECLARED = {"name": "iPhone", "os": "IOS"}
OTHER_ORIGIN = {"Origin": "http://altrove"}


async def code_for(client: AsyncClient, role: str = "COMPANION") -> str:
    """A one-shot code minted by the Core, for the role the user chose (dec. C.5)."""
    minted = await client.post("/nodes/enrollments", json={"privacy": "TRUSTED", "role": role})
    assert minted.status_code == 201, minted.text
    code: str = minted.json()["code"]
    return code


@pytest.fixture
async def browser(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """A browser: no header, and whatever cookies ELA gave it."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as opened:
        yield opened


@pytest.fixture
async def phone(browser: AsyncClient, client: AsyncClient) -> AsyncClient:
    """A browser that enrolled: from here on it carries the cookie, as Safari would."""
    answered = await browser.post(
        "/companion/enroll",
        data={"code": await code_for(client), **DECLARED},
        headers=ORIGIN,
    )
    assert answered.status_code == 303, answered.text
    return browser


# ----------------------------------------------------------------------------------------
# C.5 — a code is worth one route, and a refused code is not spent
# ----------------------------------------------------------------------------------------


async def test_the_browser_enrols_and_leaves_with_a_cookie_that_says_lax(
    browser: AsyncClient, client: AsyncClient
) -> None:
    """Dec. C.1, measured: ``Lax`` and not ``Strict``, ``HttpOnly``, the path of the pages, 400
    days, and no ``Secure`` — which Safari would accept on ``http`` only for the loopback."""
    answered = await browser.post(
        "/companion/enroll", data={"code": await code_for(client), **DECLARED}, headers=ORIGIN
    )

    assert answered.status_code == 303
    assert answered.headers["Location"] == "/companion/"
    cookie = answered.headers["set-cookie"]
    assert cookie.startswith(f"{COMPANION_COOKIE}=")
    assert "SameSite=Lax" in cookie and "Strict" not in cookie
    assert "HttpOnly" in cookie and "Secure" not in cookie
    assert "Path=/companion;" in cookie and "Max-Age=34560000" in cookie
    assert "Path=/companion/" not in cookie, "a cookie at /companion/ never reaches /companion"


async def test_the_row_of_a_companion_says_what_it_is_and_declares_nothing_else(
    phone: AsyncClient, client: AsyncClient
) -> None:
    """Dec. A: the role is the code's, the declared half is a name and ``IOS``, and no tool."""
    rows = (await client.get("/devices")).json()
    companion = next(one for one in rows if one["role"] == DeviceRole.COMPANION.value)

    assert (companion["name"], companion["os"]) == ("iPhone", "IOS")
    assert companion["available_tools"] == [] and companion["capabilities"] == []
    assert companion["available"] is False


@pytest.mark.parametrize(
    ("role", "route", "status"),
    [
        ("WORKER", "/nodes/enroll", 201),
        ("COMPANION", "/nodes/enroll", 422),
        ("COMPANION", "/companion/enroll", 303),
        ("WORKER", "/companion/enroll", 422),
    ],
    ids=["a worker where nodes enrol", "a companion there", "a companion here", "a worker here"],
)
async def test_the_table_of_c5_is_what_the_two_routes_answer(
    role: str, route: str, status: int, browser: AsyncClient, client: AsyncClient
) -> None:
    """One code, one route, and the two refusals are ``422``: whoever holds a code that exists
    already knows they hold it, so what they are told is the thing they can act on."""
    code = await code_for(client, role)

    if route == "/nodes/enroll":
        answered = await client.post(
            route, json={"name": "pc", "os": "WINDOWS"}, headers={"Authorization": f"Bearer {code}"}
        )
    else:
        answered = await browser.post(route, data={"code": code, **DECLARED}, headers=ORIGIN)

    assert answered.status_code == status, answered.text


async def test_a_code_refused_for_its_role_is_not_spent(
    browser: AsyncClient, client: AsyncClient
) -> None:
    """Dec. C.5: the role is a condition of the statement that spends the code, so the user who
    pasted it in the wrong place has lost nothing — the same code still works where it belongs."""
    code = await code_for(client)

    refused = await client.post(
        "/nodes/enroll",
        json={"name": "pc", "os": "WINDOWS"},
        headers={"Authorization": f"Bearer {code}"},
    )
    assert refused.status_code == 422

    answered = await browser.post(
        "/companion/enroll", data={"code": code, **DECLARED}, headers=ORIGIN
    )
    assert answered.status_code == 303


@pytest.mark.parametrize(
    ("fields", "status"),
    [
        ({"code": "x" * 43, "name": "iPhone", "os": "IOS"}, 401),
        ({"name": "iPhone", "os": "IOS"}, 401),
        ({"code": "", "name": "iPhone", "os": "IOS"}, 401),
    ],
    ids=["a code nobody issued", "no code at all", "an empty code"],
)
async def test_an_enrolment_that_fails_is_the_same_page_again(
    fields: dict[str, str], status: int, browser: AsyncClient
) -> None:
    """The form comes back with the sentence that says what to do — and the command that mints
    the right code, so the user never has to go looking for it."""
    answered = await browser.post("/companion/enroll", data=fields, headers=ORIGIN)

    assert answered.status_code == status
    assert "<form" in answered.text
    assert "--role companion" in answered.text
    assert "set-cookie" not in answered.headers


@pytest.mark.parametrize(
    "os", ["WINDOWS", "FROBOZZ", ""], ids=["another system", "no system at all", "nothing"]
)
async def test_an_enrolment_that_is_not_an_iphone_is_refused(
    os: str, browser: AsyncClient, client: AsyncClient
) -> None:
    """Dec. A: a companion declares a name and ``IOS``; anything else is a row that would lie,
    and the declared half is never rewritten — so the lie would outlive the mistake."""
    answered = await browser.post(
        "/companion/enroll",
        data={"code": await code_for(client), "name": "iPhone", "os": os},
        headers=ORIGIN,
    )

    assert answered.status_code == 422
    assert "IOS" in answered.text


async def test_a_code_presented_twice_is_told_so(browser: AsyncClient, client: AsyncClient) -> None:
    """One code, one identity: the second presentation is refused, and the page says which of the
    reasons it is — the user has to know whether to mint another one."""
    code = await code_for(client)
    assert (
        await browser.post("/companion/enroll", data={"code": code, **DECLARED}, headers=ORIGIN)
    ).status_code == 303

    again = await browser.post("/companion/enroll", data={"code": code, **DECLARED}, headers=ORIGIN)

    assert again.status_code == 401
    assert "già" in again.text


async def test_a_code_past_its_expiry_is_told_so(
    browser: AsyncClient, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ten minutes, and the page says so instead of the same sentence for every refusal.

    The expiry is moved below the route, as ``tests/api/test_security.py`` does for the nodes':
    what is being proved is the answer, not the arithmetic of the clock.
    """

    async def expired(self: NodeEnrollment, code: str, **declared: Any) -> Any:
        raise EnrollmentExpiredError(datetime.now(UTC))

    monkeypatch.setattr(NodeEnrollment, "enroll", expired)

    answered = await browser.post(
        "/companion/enroll", data={"code": "x" * 43, **DECLARED}, headers=ORIGIN
    )

    assert answered.status_code == 401
    assert "scaduto" in answered.text
    assert (await client.get("/diagnostics")).json()["refused"] == {"expired_code": 1}


# ----------------------------------------------------------------------------------------
# C.3 — the three cases of rule 3, one test each
# ----------------------------------------------------------------------------------------


async def test_a_request_with_no_cookie_gets_the_form_and_nothing_is_cleared(
    browser: AsyncClient,
) -> None:
    """The second case of rule 3, decided on the measures: P1 showed a browser can hold a good
    cookie back, so clearing on nothing would destroy a credential that works."""
    answered = await browser.get("/companion/")

    assert answered.status_code == 401
    assert "<form" in answered.text
    assert "set-cookie" not in answered.headers


@pytest.mark.parametrize(
    "cookie",
    ["not-a-credential", "not-a-uuid.secret", f"{uuid.uuid4()}.wrong-secret"],
    ids=["a cookie of the wrong shape", "an id that is no id", "an id nobody enrolled"],
)
async def test_a_cookie_that_fails_gets_the_form_and_is_cleared(
    cookie: str, browser: AsyncClient
) -> None:
    """The first case of rule 3: what was presented and is worth nothing is taken away."""
    browser.cookies.set(COMPANION_COOKIE, cookie)

    answered = await browser.get("/companion/")

    assert answered.status_code == 401
    assert f"{COMPANION_COOKIE}=;" in answered.headers["set-cookie"]
    assert "Max-Age=0" in answered.headers["set-cookie"]


async def test_a_cookie_with_the_right_id_and_the_wrong_secret_is_written_as_bad_secret(
    phone: AsyncClient, client: AsyncClient
) -> None:
    """The first case of rule 3 for a credential that **names somebody**: the registry writes a
    ``DEVICE_REJECTED`` — that is what ADR 0037 §13 reserves for a refusal naming a node that
    exists — and the cookie is taken away, because it is worth nothing."""
    device_id, _, _ = phone.cookies[COMPANION_COOKIE].partition(".")
    phone.cookies.set(COMPANION_COOKIE, f"{device_id}.{'w' * 43}")

    answered = await phone.get("/companion/")

    assert answered.status_code == 401
    assert "Max-Age=0" in answered.headers["set-cookie"]
    written = (await client.get("/audit")).json()
    assert any(
        one["event_type"] == AuditEventType.DEVICE_REJECTED.value and "bad_secret" in one["summary"]
        for one in written
    )


async def test_a_revoked_companion_is_told_to_enrol_again_and_the_audit_says_why(
    phone: AsyncClient, client: AsyncClient
) -> None:
    """C6 of the contract: the revocation reaches the browser at its next request."""
    rows = (await client.get("/devices")).json()
    companion = next(one for one in rows if one["role"] == DeviceRole.COMPANION.value)
    assert (await client.post(f"/nodes/{companion['id']}/revoke")).status_code == 200

    answered = await phone.get("/companion/")

    assert answered.status_code == 401
    assert "Max-Age=0" in answered.headers["set-cookie"]
    written = (await client.get("/audit")).json()
    assert any(
        one["event_type"] == AuditEventType.DEVICE_REJECTED.value and "revoked" in one["summary"]
        for one in written
    )


async def test_a_nodes_credential_in_the_cookie_is_not_a_companion(
    browser: AsyncClient, client: AsyncClient
) -> None:
    """The bearer is part of the role (dec. A): a node's secret in a cookie opens no page."""
    code = await code_for(client, "WORKER")
    born = (
        await client.post(
            "/nodes/enroll",
            json={"name": "pc", "os": "WINDOWS"},
            headers={"Authorization": f"Bearer {code}"},
        )
    ).json()
    browser.cookies.set(COMPANION_COOKIE, f"{born['device_id']}.{born['secret']}")

    answered = await browser.get("/companion/")

    assert answered.status_code == 401
    assert "Max-Age=0" in answered.headers["set-cookie"]


async def test_a_good_companion_on_a_path_that_is_not_a_route_gets_the_404_and_keeps_its_cookie(
    phone: AsyncClient, client: AsyncClient
) -> None:
    """The third case of rule 3 (the review of 2026-09-19): whoever presents a credential that
    works already knows they have one — the form would invite them to leave the old identity
    alive in the registry with a secret nobody holds any more."""
    answered = await phone.get("/companion/qualcosa")

    assert answered.status_code == 404
    assert "non esiste" in answered.text
    assert "set-cookie" not in answered.headers
    written = (await client.get("/audit")).json()
    assert any("route_not_allowed" in one["summary"] for one in written)
    assert (await phone.get("/companion/")).status_code == 200


async def test_a_companions_secret_in_a_header_opens_nothing(
    phone: AsyncClient, client: AsyncClient
) -> None:
    """C7: the other half of "the bearer is part of the role", with the **real** credential —
    taken out of the browser's jar, which is the one place it exists — so the refusal happens on
    the role and not on the secret. The ``401`` is the JSON one: a header is what a machine sends.
    """
    header = {"Authorization": f"Bearer {phone.cookies[COMPANION_COOKIE]}"}

    for path in ("/nodes/heartbeat", "/nodes/me", "/companion/"):
        answered = await client.request(
            "POST" if "heartbeat" in path else "GET", path, headers=header, json={}
        )
        assert answered.status_code == 401, path
        assert answered.json()["error"]["code"] == "unauthorized"
    written = (await client.get("/audit")).json()
    assert any("route_not_allowed" in one["summary"] for one in written)


async def test_the_core_is_not_a_browser(client: AsyncClient) -> None:
    """Rule 2: the Core's token on a page is refused with a reason of its own (dec. C.3)."""
    answered = await client.get("/companion/")

    assert answered.status_code == 401
    assert answered.json()["error"]["code"] == "unauthorized"
    assert (await client.get("/diagnostics")).json()["refused"] == {"core_on_a_companion_route": 1}


# ----------------------------------------------------------------------------------------
# C.1 — a form comes from a page of ELA
# ----------------------------------------------------------------------------------------


async def test_a_form_from_another_site_is_refused(phone: AsyncClient) -> None:
    """``Lax`` keeps the cookie off a ``POST`` born elsewhere; this is the half that does not
    depend on the browser's default (dec. C.1), and it is measured — every browser sent it."""
    answered = await phone.post(
        "/companion/answer", data={"id": str(uuid.uuid4()), "answer": "yes"}, headers=OTHER_ORIGIN
    )

    assert answered.status_code == 403
    assert "ELA" in answered.text


async def test_a_form_with_no_origin_is_refused(phone: AsyncClient) -> None:
    """An absent ``Origin`` is a no: the measures saw it present from Safari, from the web app of
    the home screen and from Chrome, so refusing costs nothing and guessing would."""
    answered = await phone.post("/companion/answer", data={"id": str(uuid.uuid4())})

    assert answered.status_code == 403


# ----------------------------------------------------------------------------------------
# D — what a page is: the policy, the escape, the sheets
# ----------------------------------------------------------------------------------------


async def test_every_page_carries_the_policy_that_forbids_a_script(phone: AsyncClient) -> None:
    """Dec. D, the second of the two defences: even the pages served before anybody is known."""
    for answered in (await phone.get("/companion/"), await phone.get("/companion/qualcosa")):
        assert answered.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
        assert "<script" not in answered.text
        assert answered.headers["cache-control"] == "no-store"


async def test_the_pages_of_the_enrolment_carry_it_too(browser: AsyncClient) -> None:
    answered = await browser.get("/companion/")

    assert answered.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert "stylesheet" not in answered.text, "the sheets are behind the middleware (dec. D)"


async def test_what_the_user_wrote_is_escaped_and_never_markup(
    phone: AsyncClient, client: AsyncClient
) -> None:
    """The escape is by construction: a goal with a tag in it is text on the page, and the policy
    would refuse it even if it were not."""
    await queued(client, echo_plan(), text="<script>alert('x')</script>", privacy="TRUSTED")

    answered = await phone.get("/companion/")

    assert "<script>" not in answered.text
    assert "&lt;script&gt;" in answered.text


async def test_the_two_sheets_are_served_and_nothing_else_of_apps(phone: AsyncClient) -> None:
    """Dec. D: ``ela.api`` serves the two derived sheets of the design system, read only, and the
    request chooses **between two files** instead of describing one."""
    for sheet in STYLESHEETS:
        answered = await phone.get(f"/companion/{sheet}")
        assert answered.status_code == 200
        assert answered.headers["content-type"].startswith("text/css")
        assert "--ela-" in answered.text
    assert (await phone.get("/companion/specimen.css")).status_code == 404


# ----------------------------------------------------------------------------------------
# D — the presence is a projection, and B — the last contact
# ----------------------------------------------------------------------------------------


def test_the_presence_is_the_three_states_in_their_order() -> None:
    """Dec. D: a question that waits comes first, then work, then rest."""
    waiting = (object(),)
    executing = (_task(TaskState.EXECUTING),)

    assert presence(waiting, executing) == WAITING_APPROVAL  # type: ignore[arg-type]
    assert presence((), executing) == WORKING
    assert presence((), (_task(TaskState.QUEUED),)) == IDLE
    assert presence((), ()) == IDLE


def _task(state: TaskState) -> Any:
    class _Out:
        def __init__(self) -> None:
            self.state = state

    return _Out()


async def test_a_page_writes_the_last_contact_and_not_the_availability(
    phone: AsyncClient, client: AsyncClient
) -> None:
    """Dec. B2: opening a page is contact, and contact is not a heartbeat — the iPhone reads
    ``available: false`` with an hour of contact nobody can mistake for a claim."""
    await phone.get("/companion/")

    rows = (await client.get("/devices")).json()
    companion = next(one for one in rows if one["role"] == DeviceRole.COMPANION.value)
    assert companion["last_seen_at"] is not None
    assert companion["available"] is False


# ----------------------------------------------------------------------------------------
# F and H — the question, its ceiling, and the "yes" that runs the task
# ----------------------------------------------------------------------------------------


async def waiting_question(client: AsyncClient, *, privacy: str) -> tuple[str, str]:
    """A task whose run stopped on a question, at the level the caller asked for."""
    task_id = await queued(client, note_plan(), privacy=privacy)
    ran = await client.post(f"/tasks/{task_id}/run")
    assert ran.status_code == 200, ran.text
    approval = (await client.get("/approvals")).json()
    assert approval, ran.text
    return task_id, approval[0]["id"]


async def test_the_question_shows_the_parts_of_itself(
    phone: AsyncClient, client: AsyncClient
) -> None:
    """Dec. F: the description of the catalogue, the risk the Guardian used, how far the content
    may go, the goal of the step, the declared arguments and the terms of the grant."""
    _, approval_id = await waiting_question(client, privacy="TRUSTED")

    answered = await phone.get(f"/companion/approval?id={approval_id}")

    assert answered.status_code == 200
    assert "workspace.write_note" in answered.text
    assert "LOW" in answered.text
    assert "TRUSTED" in answered.text
    assert "uso" in answered.text and "ora dal tuo sì" in answered.text
    assert "write" in answered.text, "the goal of the step"


async def test_the_question_of_a_local_only_task_keeps_its_content_on_the_mac(
    phone: AsyncClient, client: AsyncClient
) -> None:
    """Dec. F2-a: the ceiling of the companion decides what it sees, and what it does not see it
    cannot answer — the page shows the facts that are not content, and no buttons."""
    _, approval_id = await waiting_question(client, privacy="LOCAL_ONLY")

    answered = await phone.get(f"/companion/approval?id={approval_id}")

    assert answered.status_code == 200
    assert "resta sul Mac" in answered.text
    assert "<form" not in answered.text
    assert "briefing.md" not in answered.text, "the targets are content"
    assert "workspace.write_note" in answered.text, "the capability is not"


async def test_a_yes_to_a_local_only_task_is_refused_even_by_hand(
    phone: AsyncClient, client: AsyncClient
) -> None:
    """The page hides the buttons and the route refuses the answer: one does not approve what one
    cannot see (§30), and a form typed by hand is answered the same way."""
    _, approval_id = await waiting_question(client, privacy="LOCAL_ONLY")

    answered = await phone.post(
        "/companion/answer", data={"id": approval_id, "answer": "yes"}, headers=ORIGIN
    )

    assert answered.status_code == 409
    assert "not_answerable" in answered.text or "Mac" in answered.text
    assert (await client.get("/approvals")).json(), "the question is still waiting"


async def test_a_yes_answers_and_runs_the_task_in_the_same_request(
    phone: AsyncClient, client: AsyncClient
) -> None:
    """Dec. H1: the two things the user does at the Mac, from the page, in one request — and the
    page it lands on shows the true state of the task it just answered."""
    task_id, approval_id = await waiting_question(client, privacy="TRUSTED")

    answered = await phone.post(
        "/companion/answer", data={"id": approval_id, "answer": "yes"}, headers=ORIGIN
    )

    assert answered.status_code == 303
    assert answered.headers["Location"] == f"/companion/?task={task_id}"
    task = (await client.get(f"/tasks/{task_id}")).json()
    assert task["state"] == TaskState.COMPLETED.value, task
    landed = await phone.get(f"/companion/?task={task_id}")
    assert TaskState.COMPLETED.value in landed.text


async def test_the_yes_is_signed_by_the_iphone(phone: AsyncClient, client: AsyncClient) -> None:
    """C4 of the contract, and the fixed point 2: every "yes" leaves the iPhone's identity in
    ``responded_by`` — the authorisation that follows is granted by it too."""
    _, approval_id = await waiting_question(client, privacy="TRUSTED")
    rows = (await client.get("/devices")).json()
    companion = next(one for one in rows if one["role"] == DeviceRole.COMPANION.value)

    await phone.post("/companion/answer", data={"id": approval_id, "answer": "yes"}, headers=ORIGIN)

    written = (await client.get("/audit")).json()
    resolved = next(
        one for one in written if one["event_type"] == AuditEventType.APPROVAL_RESOLVED.value
    )
    assert resolved["actor"]["id"] == companion["id"]
    granted = next(
        one for one in written if one["event_type"] == AuditEventType.AUTHORIZATION_GRANTED.value
    )
    assert granted["actor"]["id"] == companion["id"]


async def test_a_no_answers_and_runs_nothing(phone: AsyncClient, client: AsyncClient) -> None:
    """A refusal is an answer (§62), and the task is DENIED: nothing was run."""
    task_id, approval_id = await waiting_question(client, privacy="TRUSTED")

    answered = await phone.post(
        "/companion/answer", data={"id": approval_id, "answer": "no"}, headers=ORIGIN
    )

    assert answered.status_code == 303
    task = (await client.get(f"/tasks/{task_id}")).json()
    assert task["state"] == TaskState.DENIED.value


async def test_the_home_page_lists_what_waits_and_says_so_when_nothing_does(
    phone: AsyncClient, client: AsyncClient
) -> None:
    empty = await phone.get("/companion/")
    assert "altro ti aspetta" in empty.text, "and the apostrophe is escaped, like every value"

    _, approval_id = await waiting_question(client, privacy="TRUSTED")

    full = await phone.get("/companion/")
    assert f"/companion/approval?id={approval_id}" in full.text
    assert WAITING_APPROVAL in full.text


async def test_a_question_that_is_not_waiting_is_not_a_page(
    phone: AsyncClient, client: AsyncClient
) -> None:
    """The page reads the route, and the route already leaves out what expired and what belongs
    to a task that moved on: a page must not offer an answer ELA would refuse (§33)."""
    answered = await phone.get(f"/companion/approval?id={uuid.uuid4()}")

    assert answered.status_code == 404


# ----------------------------------------------------------------------------------------
# I — stopping a task takes two pages, because a confirmation without JavaScript is a page
# ----------------------------------------------------------------------------------------


async def test_a_list_that_cuts_says_how_much_it_is_showing(
    phone: AsyncClient, client: AsyncClient
) -> None:
    """A phone is not a dashboard, so the list stops at :data:`SHOWN` — and the title carries the
    cut, because six rows under «I task» with nine alive is a page that lies quietly."""
    for number in range(SHOWN + 2):
        await queued(client, echo_plan(), text=f"task {number}", privacy="TRUSTED")

    answered = await phone.get("/companion/")

    assert f"I task · {SHOWN} di {SHOWN + 2}" in answered.text
    assert answered.text.count('class="ela-row"') == SHOWN


async def test_a_list_that_fits_says_nothing_about_a_cut(
    phone: AsyncClient, client: AsyncClient
) -> None:
    await queued(client, echo_plan(), privacy="TRUSTED")

    answered = await phone.get("/companion/")

    assert "I task</p>" in answered.text or ">I task<" in answered.text
    assert " di " not in answered.text.split("ela-eyebrow")[-1][:60]


async def test_the_home_page_offers_to_stop_a_live_task(
    phone: AsyncClient, client: AsyncClient
) -> None:
    task_id = await queued(client, echo_plan(), privacy="TRUSTED")

    answered = await phone.get("/companion/")

    assert f"/companion/cancel?id={task_id}" in answered.text


async def test_the_confirmation_says_what_stops_and_that_it_cannot_be_undone(
    phone: AsyncClient, client: AsyncClient
) -> None:
    """Dec. I: the second page is the confirmation, and it says the price before the button."""
    task_id = await queued(client, echo_plan(), text="un lavoro", privacy="TRUSTED")

    answered = await phone.get(f"/companion/cancel?id={task_id}")

    assert answered.status_code == 200
    assert "un lavoro" in answered.text
    assert "non si può annullare" in answered.text
    assert f'value="{task_id}"' in answered.text


async def test_stopping_is_signed_user_with_the_id_of_the_iphone(
    phone: AsyncClient, client: AsyncClient
) -> None:
    """C8: the actor is ``USER`` — an iPhone is where the person is — and the id is the phone's,
    so the audit says where the act came from. The negative can fail: a ``DEVICE`` here would be
    ELA saying a machine stopped the user's task."""
    task_id = await queued(client, echo_plan(), privacy="TRUSTED")
    rows = (await client.get("/devices")).json()
    companion = next(one for one in rows if one["role"] == DeviceRole.COMPANION.value)

    answered = await phone.post("/companion/cancel", data={"id": task_id}, headers=ORIGIN)

    assert answered.status_code == 303
    assert answered.headers["Location"] == "/companion/"
    task = (await client.get(f"/tasks/{task_id}")).json()
    assert task["state"] == TaskState.CANCELLED.value
    written = (await client.get("/audit")).json()
    cancelled = next(
        one for one in written if one["event_type"] == AuditEventType.TASK_CANCELLED.value
    )
    assert cancelled["actor"] == {"kind": "USER", "id": companion["id"]}


async def test_a_local_only_task_can_be_stopped_without_being_shown(
    phone: AsyncClient, client: AsyncClient
) -> None:
    """Dec. I: stopping does not ask to see — what is being asked for is less, not more."""
    task_id = await queued(client, echo_plan(), text="quello che resta sul Mac")

    confirmation = await phone.get(f"/companion/cancel?id={task_id}")
    assert confirmation.status_code == 200
    assert "resta sul Mac" not in confirmation.text, "the goal is content"
    assert task_id in confirmation.text

    answered = await phone.post("/companion/cancel", data={"id": task_id}, headers=ORIGIN)
    assert answered.status_code == 303
    assert (await client.get(f"/tasks/{task_id}")).json()["state"] == TaskState.CANCELLED.value


async def test_a_task_that_is_not_live_is_not_offered_to_be_stopped(
    phone: AsyncClient, client: AsyncClient
) -> None:
    """A page must not offer what ELA would refuse (§33): the state machine would say no, and the
    page says nothing at all."""
    task_id = await queued(client, echo_plan(), privacy="TRUSTED")
    await phone.post("/companion/cancel", data={"id": task_id}, headers=ORIGIN)

    assert (await phone.get(f"/companion/cancel?id={task_id}")).status_code == 404
    again = await phone.post("/companion/cancel", data={"id": task_id}, headers=ORIGIN)
    assert again.status_code == 404


def test_a_question_asked_before_m12_5_shows_what_it_has() -> None:
    """The bag of dec. F has defaults, and this is why: a request stored before M12.5 carries
    none of them, and a page that refused to open would be a page that lost a question.

    What it shows then is what it has — the risk, with no level beside it — and never a label
    with nothing after it.
    """
    bare = ApprovalOut.of(
        Approval(
            id=ApprovalId(uuid.uuid4()),
            created_at=datetime.now(UTC),
            task_id=TaskId(uuid.uuid4()),
            step_id=StepId(uuid.uuid4()),
            capability_id="workspace.write_note",
            prompt="una domanda di prima",
            status=ApprovalStatus.PENDING,
        )
    )

    pairs = _pairs(bare, seen=True)

    assert "Rischio" in pairs
    assert "Dove può andare" not in pairs
    assert "Durata" not in pairs
    assert "Scade" not in pairs


@pytest.mark.parametrize(
    ("uses", "seconds", "said"),
    [
        (1, 1800, "un uso, entro 30 minuti dal tuo sì"),
        (1, 3600, "un uso, entro un'ora dal tuo sì"),
        (1, 7200, "un uso, entro 2 ore dal tuo sì"),
        (1, 5400, "un uso, entro un'ora e 30 minuti dal tuo sì"),
        (3, 3600, "3 usi, entro un'ora dal tuo sì"),
        (1, 45, "un uso, entro 45 secondi dal tuo sì"),
    ],
    ids=["half an hour", "an hour", "two hours", "an hour and a half", "three uses", "seconds"],
)
def test_the_terms_of_the_grant_are_derived_from_the_numbers(
    uses: int, seconds: int, said: str
) -> None:
    """``ELA_AUTHORIZATION_TTL_SECONDS`` is the user's setting, so the phrase is derived and not
    written: with the hours divided out, half an hour read «entro 0 ora» and two hours «2 ora».

    The assertion is the sentence and not the presence of the row: this is the page where consent
    is given, and what is approved has to name what it is.
    """
    assert terms(uses, seconds) == said


async def test_the_page_of_a_question_says_the_terms_it_was_asked_with(
    phone: AsyncClient, client: AsyncClient, ela: Ela
) -> None:
    """And the page shows exactly that sentence, for the TTL this ELA is configured with."""
    _, approval_id = await waiting_question(client, privacy="TRUSTED")
    said = terms(SINGLE_USE, int(ela.settings.core.authorization_ttl.total_seconds()))

    answered = await phone.get(f"/companion/approval?id={approval_id}")

    assert html.escape(said) in answered.text


# ----------------------------------------------------------------------------------------
# The address a person types
# ----------------------------------------------------------------------------------------


async def test_the_prefix_without_its_slash_is_the_companions_ground(browser: AsyncClient) -> None:
    """The review of 2026-09-20: ``/companion`` is what a person types, and before this it fell
    outside the prefix — so a browser with no cookie got JSON instead of the form."""
    answered = await browser.get(COMPANION_HOME)

    assert answered.status_code == 401
    assert "<form" in answered.text
    assert "set-cookie" not in answered.headers


async def test_the_address_a_person_types_lands_on_the_page(phone: AsyncClient) -> None:
    """With a credential that works it is let through to the router, which redirects it to the
    page: the redirect is the router's job, and the middleware only decides who may be there."""
    answered = await phone.get(COMPANION_HOME)

    assert answered.status_code in {307, 308}
    assert answered.headers["Location"].endswith("/companion/")
    landed = await phone.get(COMPANION_HOME, follow_redirects=True)
    assert landed.status_code == 200
    assert IDLE in landed.text


async def test_an_address_that_is_really_wrong_still_says_it_does_not_exist(
    phone: AsyncClient,
) -> None:
    """The third case of rule 3 is untouched: what is let through is **that one** address."""
    assert (await phone.get("/companionqualcosa")).status_code == 401
    assert (await phone.get("/companion/qualcosa")).status_code == 404


# ----------------------------------------------------------------------------------------
# The ceiling, as a function
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ceiling", "task", "seen"),
    [
        (PrivacyLevel.TRUSTED, PrivacyLevel.TRUSTED, True),
        (PrivacyLevel.TRUSTED, PrivacyLevel.CLOUD_ALLOWED, True),
        (PrivacyLevel.TRUSTED, PrivacyLevel.LOCAL_ONLY, False),
        (PrivacyLevel.CLOUD_ALLOWED, PrivacyLevel.TRUSTED, False),
        (PrivacyLevel.TRUSTED, None, False),
    ],
    ids=["the same level", "a wider task", "the Mac's own", "a narrower task", "nothing declared"],
)
def test_the_ceiling_is_the_comparison_the_orchestrator_already_makes(
    ceiling: PrivacyLevel, task: PrivacyLevel | None, seen: bool
) -> None:
    identity = Identity(Kind.COMPANION, privacy=ceiling)

    assert may_see(identity, task) is seen


def test_the_pages_a_cookie_may_call_are_the_ones_the_router_serves(app: FastAPI) -> None:
    """The closed list of the middleware against the application: a page added without a row in
    ``COMPANION_ROUTES`` answers ``404`` to the iPhone, which is the safe direction and a
    surprise nobody would explain."""
    served = {
        (method, path)
        for method, path in _served(app)
        if path.startswith("/companion/") and (method, path) != ("POST", "/companion/enroll")
    }

    assert served == COMPANION_ROUTES


def _served(app: FastAPI) -> list[tuple[str, str]]:
    from tests.api.support import served_paths

    return served_paths(app)


def test_no_page_puts_an_id_in_its_path(app: FastAPI) -> None:
    """Dec. D: an id travels in the query or in the body, for the reason of ADR 0038 §11 — a
    template taught to the middleware would be a defence that looks active."""
    for _, path in _served(app):
        if path.startswith("/companion/"):
            assert not re.search(r"\{", path), path
