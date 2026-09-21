"""The pages of the Command Center (M17.2; ADR 0044): who gets in, what they see, from where.

What is proved here is not "the page renders". It is the three places where a page could quietly
become something the user did not agree to: the **role** of the identity that carries the cookie,
the **ceiling derived from the socket** (dec. J), and the **conduct of a "yes"**, which must be
the phone's own and not a second copy of it.

The browser itself is not here (ADR 0038 §18): a cookie in ``httpx`` is not Chrome, and the hand
test at the Mac is what says the rest. What ``httpx`` *does* give is the one thing dec. J needs —
the two ends of the socket, ``client`` and ``server`` in the ASGI scope — so the promotion and
its refusals are exercised here, address by address.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from html import escape
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ela.api import pages
from ela.api.console import (
    FROM_AWAY,
    FROM_THIS_MACHINE,
    NO_DEVICES,
    NO_PLAN,
    NO_RESULTS,
    NO_TASKS,
    NO_TOOLS,
    NOTHING_RUNS,
    NOTHING_WAITS,
    RESULTS_ARE_ELSEWHERE,
    STAYS_ON_THE_MAC,
    _content,
    _now,
    _pairs,
)
from ela.api.console import HERE as HERE_CONSOLE
from ela.api.pages import CONTENT_SECURITY_POLICY, STYLESHEETS
from ela.api.schemas import ApprovalOut, StepOut, TaskDetail
from ela.api.security import (
    COMPANION_COOKIE,
    CONSOLE_COOKIE,
    CONSOLE_HOME,
    CONSOLE_ROUTES,
    SEPARATOR,
    Identity,
    Kind,
)
from ela.devices import NodeEnrollment
from ela.domain import (
    Approval,
    ApprovalId,
    ApprovalStatus,
    AuditEventType,
    DeviceId,
    DeviceRole,
    PrivacyLevel,
    RiskLevel,
    StepId,
    StepState,
    TaskId,
    TaskState,
)
from ela.ports import EnrollmentExpiredError
from ela.tools import OVERWRITES, READS
from tests.api.support import BASE, echo_plan, note_plan, queued

LOOPBACK = "http://127.0.0.1"
"""What the Mac's browser opens when the person is at the Mac: both ends of the socket loopback."""
TAILNET = "http://100.76.92.39"
"""The address of this Mac on the tailnet, as P0 measured it: neither end is loopback."""
PHONE_PEER = ("100.70.98.26", 54536)
"""The iPhone, as P0 measured it arriving: its own address, not ``127.0.0.1``."""
FORGED_PEER = ("127.0.0.1", 1)
"""A peer that claims to be local on a connection that came in on the tailnet (dec. 9)."""
DECLARED = {"name": "MacBook", "os": "MACOS"}


def origin(base: str) -> dict[str, str]:
    """What a browser sends on a ``POST``, and what every page of ELA answers to (dec. C.1)."""
    return {"Origin": base}


async def code_for(client: AsyncClient, role: str = "CONSOLE") -> str:
    """A one-shot code minted by the Core, for the role the user chose."""
    minted = await client.post("/nodes/enrollments", json={"privacy": "TRUSTED", "role": role})
    assert minted.status_code == 201, minted.text
    code: str = minted.json()["code"]
    return code


def opened(app: FastAPI, base: str, peer: tuple[str, int] = ("127.0.0.1", 123)) -> AsyncClient:
    """A browser at an address: ``base`` is what the socket was accepted on, ``peer`` who dialled.

    This is the whole of dec. J's world in a test — ``server`` and ``client`` of the ASGI scope
    are the ``getsockname()`` and the ``getpeername()`` a real request would carry.
    """
    return AsyncClient(transport=ASGITransport(app=app, client=peer), base_url=base)


@pytest.fixture
async def browser(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """A browser with no header and no cookie, at the address a person types on the Mac."""
    async with opened(app, LOOPBACK) as client:
        yield client


@pytest.fixture
async def console(browser: AsyncClient, client: AsyncClient) -> AsyncClient:
    """A browser that enrolled as a console: from here on it carries the cookie."""
    answered = await browser.post(
        "/console/enroll",
        data={"code": await code_for(client), **DECLARED},
        headers=origin(LOOPBACK),
    )
    assert answered.status_code == 303, answered.text
    return browser


def credential(console: AsyncClient) -> str:
    """The cookie the console holds, as a browser would hand it back."""
    value = console.cookies.get(CONSOLE_COOKIE)
    assert value is not None
    return value


# ----------------------------------------------------------------------------------------
# The third role: a code is worth one route, and a refused code is not spent
# ----------------------------------------------------------------------------------------


async def test_the_browser_enrols_and_leaves_with_a_cookie_of_its_own(
    browser: AsyncClient, client: AsyncClient
) -> None:
    """Measured in C1: the ``Path`` without the trailing slash, ``Lax``, ``HttpOnly``, 400 days,
    and no ``Secure`` — and a name that is **not** the companion's."""
    answered = await browser.post(
        "/console/enroll",
        data={"code": await code_for(client), **DECLARED},
        headers=origin(LOOPBACK),
    )

    assert answered.status_code == 303
    assert answered.headers["Location"] == "/console/"
    cookie = answered.headers["set-cookie"]
    assert cookie.startswith(f"{CONSOLE_COOKIE}=")
    assert COMPANION_COOKIE not in cookie
    assert "SameSite=Lax" in cookie and "Strict" not in cookie
    assert "HttpOnly" in cookie and "Secure" not in cookie
    assert f"Path={CONSOLE_HOME};" in cookie and "Max-Age=34560000" in cookie
    assert "Path=/console/" not in cookie, "a cookie at /console/ never reaches /console"


async def test_a_console_code_on_the_nodes_route_is_refused_and_stays_spendable(
    browser: AsyncClient, client: AsyncClient
) -> None:
    """The symmetry of ADR 0043 §3, and it costs nothing: the role is a condition of the
    ``UPDATE`` that spends the code, so a code presented on another route touches no row."""
    code = await code_for(client)

    refused = await client.post(
        "/nodes/enroll",
        json={"name": "x", "os": "MACOS"},
        headers={"Authorization": f"Bearer {code}"},
    )

    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "invalid"
    spent = await browser.post(
        "/console/enroll", data={"code": code, **DECLARED}, headers=origin(LOOPBACK)
    )
    assert spent.status_code == 303, "the refusal must not have consumed it"


@pytest.mark.parametrize("role", ["WORKER", "COMPANION"])
async def test_another_roles_code_on_the_console_route_is_refused_and_stays_spendable(
    role: str, browser: AsyncClient, client: AsyncClient
) -> None:
    """And the page says which command mints the right one, so nobody goes looking."""
    code = await code_for(client, role)

    refused = await browser.post(
        "/console/enroll", data={"code": code, **DECLARED}, headers=origin(LOOPBACK)
    )

    assert refused.status_code == 422
    assert "--role console" in refused.text
    assert (await client.get("/devices")).json() == [
        one for one in (await client.get("/devices")).json()
    ], "no row was born"


async def test_a_console_may_declare_any_system_including_the_phones(
    browser: AsyncClient, client: AsyncClient
) -> None:
    """Dec. 14 of the review: the declared system governs nothing in a console and the cookie
    works in any browser, so refusing ``IOS`` would not keep a phone out — it would only keep it
    from saying so, and leave a row that reads ``MACOS`` where a phone is."""
    answered = await browser.post(
        "/console/enroll",
        data={"code": await code_for(client), "name": "un telefono", "os": "IOS"},
        headers=origin(LOOPBACK),
    )

    assert answered.status_code == 303
    rows = (await client.get("/devices")).json()
    console = next(one for one in rows if one["role"] == DeviceRole.CONSOLE.value)
    assert console["os"] == "IOS", "the registry says what is there"


async def test_the_row_of_a_console_says_what_it_is_and_is_never_available(
    console: AsyncClient, client: AsyncClient
) -> None:
    """Dec. D: availability is derived from the role, at the positive — only a ``WORKER`` can be
    available — so a console that just opened a page is still ``available: false``."""
    await console.get("/console/")
    rows = (await client.get("/devices")).json()
    row = next(one for one in rows if one["role"] == DeviceRole.CONSOLE.value)

    assert row["available"] is False
    assert row["last_seen_at"] is not None, "the contact is a fact; availability is another"


# ----------------------------------------------------------------------------------------
# Two grounds, and a credential on the other one
# ----------------------------------------------------------------------------------------


async def test_the_cookie_opens_the_console_routes_and_nothing_else(
    console: AsyncClient, app: FastAPI
) -> None:
    """A credential that works on a path that does not exist gets a ``404`` and keeps its cookie:
    whoever presents one already knows they have it, so there is nothing to hide."""
    for method, path in sorted(CONSOLE_ROUTES):
        answered = await console.request(method, path, headers=origin(LOOPBACK))
        assert answered.status_code in {200, 303, 404, 422}, f"{method} {path}"
        assert answered.status_code != 401, f"{method} {path}"

    nowhere = await console.get("/console/non-esiste")
    assert nowhere.status_code == 404
    assert "set-cookie" not in nowhere.headers
    assert "non esiste" in nowhere.text


async def test_a_credential_copied_into_the_other_surfaces_cookie_opens_nothing(
    console: AsyncClient, app: FastAPI, client: AsyncClient
) -> None:
    """Two cookies with two names and two ``Path``s: a browser never sends one to the other's
    ground (measured in C1). What the code defends is the credential somebody **copies**, and the
    role checked there is the role of *this* surface."""
    async with opened(app, LOOPBACK) as phone:
        phone.cookies.set(COMPANION_COOKIE, credential(console))
        answered = await phone.get("/companion/")

    assert answered.status_code == 401
    assert "<form" in answered.text
    assert f"{COMPANION_COOKIE}=;" in answered.headers["set-cookie"], "and it is cleared"
    rejected = (await client.get("/audit")).json()
    assert any(one["event_type"] == AuditEventType.DEVICE_REJECTED.value for one in rejected)


async def test_the_secret_of_a_console_in_a_header_is_refused(
    console: AsyncClient, client: AsyncClient, app: FastAPI
) -> None:
    """The bearer is part of the role: a browser's credential in a header is refused wherever it
    is presented, because what is wrong is not *where* it is calling but *how*."""
    rows = (await client.get("/devices")).json()
    row = next(one for one in rows if one["role"] == DeviceRole.CONSOLE.value)
    secret = credential(console).split(SEPARATOR, 1)[1]

    async with opened(app, BASE) as machine:
        answered = await machine.get(
            "/health", headers={"Authorization": f"Bearer {row['id']}{SEPARATOR}{secret}"}
        )

    assert answered.status_code == 401
    assert answered.json()["error"]["code"] == "unauthorized"


async def test_the_core_on_a_page_of_the_console_is_refused_and_counted_once(
    client: AsyncClient,
) -> None:
    """Dec. K.3: one entry for one fact — the Core's token on a page — whichever prefix it is."""
    assert (await client.get("/console/")).status_code == 401
    assert (await client.get("/companion/")).status_code == 401

    assert (await client.get("/diagnostics")).json()["refused"] == {"core_on_a_page": 2}


async def test_without_a_cookie_every_path_answers_the_same_page_and_clears_nothing(
    browser: AsyncClient,
) -> None:
    """Rule 3 of dec. C.3: knocking teaches only that the prefix asks for a code — and a browser
    that presented nothing keeps whatever it holds, because it may be holding a good one."""
    for path in ("/console/", "/console/devices", "/console/qualunque-cosa"):
        answered = await browser.get(path)

        assert answered.status_code == 401
        assert "<form" in answered.text and "code" in answered.text
        assert "set-cookie" not in answered.headers


async def test_the_address_a_person_types_reaches_the_home(console: AsyncClient) -> None:
    """``/console`` without the slash is ground of the console, and the **router** redirects."""
    answered = await console.get(CONSOLE_HOME)

    assert answered.status_code == 307
    assert answered.headers["location"].endswith("/console/")


async def test_a_form_that_did_not_come_from_ela_is_refused(
    console: AsyncClient, app: FastAPI
) -> None:
    """``SameSite=Lax`` keeps the cookie off a ``POST`` born elsewhere; this is the other half,
    and it does not depend on the browser's default."""
    answered = await console.post(
        "/console/cancel", data={"id": str(uuid.uuid4())}, headers={"Origin": "http://altrove"}
    )

    assert answered.status_code == 403
    assert "non arriva da una pagina di ELA" in answered.text


# ----------------------------------------------------------------------------------------
# The four views
# ----------------------------------------------------------------------------------------


async def test_the_home_shows_the_three_states_in_their_order(
    console: AsyncClient, client: AsyncClient
) -> None:
    """The projection of §6 of the design, derived at every read and stored nowhere: a question
    that waits comes first, then work, then rest."""
    assert "IDLE" in (await console.get("/console/")).text

    task = await queued(client, note_plan())
    await client.post(f"/tasks/{task}/run")
    waiting = await console.get("/console/")

    assert "WAITING APPROVAL" in waiting.text


async def test_the_home_says_what_ela_is_doing_and_links_to_the_task(
    console: AsyncClient, client: AsyncClient
) -> None:
    """§8 of the design: the answer without opening a task manager — and the way to the summary."""
    task = await queued(client, echo_plan())
    home = await console.get("/console/")

    assert f"/console/task?id={task}" in home.text
    assert "Non sta facendo niente" in home.text, "nothing is executing right now"


async def test_the_approval_center_lists_what_waits_and_shows_one_question(
    console: AsyncClient, client: AsyncClient
) -> None:
    """§14 and §29 of the design: the capability, the risk with its meter, the terms of a "yes".

    And three things §14 asks for that are **not** there, each for a reason ADR 0043 wrote: the
    device, because the placement is not decided when the question is born; the consequences and
    the reversibility, because the catalogue does not state them.
    """
    task = await queued(client, note_plan())
    await client.post(f"/tasks/{task}/run")
    identifier = (await client.get("/approvals")).json()[0]["id"]

    listed = await console.get("/console/approvals")
    assert f"/console/approval?id={identifier}" in listed.text

    one = await console.get(f"/console/approval?id={identifier}")
    assert one.status_code == 200
    assert "workspace.write_note" in one.text
    assert 'data-ela-risk="LOW"' in one.text and "ela-meter" in one.text
    assert "un uso" in one.text, "the terms of the grant"
    assert "Dispositivo" not in one.text


async def test_a_yes_answers_and_runs_through_the_conduct_both_surfaces_share(
    console: AsyncClient, client: AsyncClient
) -> None:
    """Dec. K.1: the same function as the phone's, not a copy of it — and after it the task has
    moved past the question instead of sitting in the queue waiting for somebody at the Mac."""
    task = await queued(client, note_plan())
    await client.post(f"/tasks/{task}/run")
    identifier = (await client.get("/approvals")).json()[0]["id"]

    answered = await console.post(
        "/console/answer",
        data={"id": identifier, "answer": "yes"},
        headers=origin(LOOPBACK),
        follow_redirects=False,
    )

    assert answered.status_code == 303
    assert answered.headers["location"] == f"/console/task?id={task}"
    assert (await client.get(f"/tasks/{task}")).json()["state"] == TaskState.COMPLETED.value


async def test_a_no_denies_and_runs_nothing(console: AsyncClient, client: AsyncClient) -> None:
    task = await queued(client, note_plan())
    await client.post(f"/tasks/{task}/run")
    identifier = (await client.get("/approvals")).json()[0]["id"]

    await console.post(
        "/console/answer", data={"id": identifier, "answer": "no"}, headers=origin(LOOPBACK)
    )

    assert (await client.get(f"/tasks/{task}")).json()["state"] == TaskState.DENIED.value


async def test_a_question_that_cannot_be_answered_any_more_is_a_page_not_found(
    console: AsyncClient, client: AsyncClient
) -> None:
    """Two outcomes and they are different, exactly as they are for the phone: already answered
    or expired is not among the pending ones and is a ``404``; the ceiling is a ``409``."""
    task = await queued(client, note_plan())
    await client.post(f"/tasks/{task}/run")
    identifier = (await client.get("/approvals")).json()[0]["id"]
    await console.post(
        "/console/answer", data={"id": identifier, "answer": "no"}, headers=origin(LOOPBACK)
    )

    again = await console.get(f"/console/approval?id={identifier}")

    assert again.status_code == 404
    assert "<html" in again.text, "a page, not JSON: this is a browser"


async def test_the_device_center_keeps_availability_and_last_contact_apart(
    console: AsyncClient, client: AsyncClient
) -> None:
    """§11 and §12 of the design, as far as a route can say them: two facts, two rows."""
    answered = await console.get("/console/devices")

    assert answered.status_code == 200
    assert "Disponibile" in answered.text and "Ultimo contatto" in answered.text
    assert "CONSOLE" in answered.text and "WORKER" in answered.text
    assert "due fatti, e due colonne" in answered.text


async def test_the_task_page_is_a_summary_and_says_where_the_content_is(
    console: AsyncClient, client: AsyncClient
) -> None:
    """§10 of the design, and dec. K.2: the summary names that a result exists and where it is
    read, instead of ending at «completato» as if the task had produced nothing."""
    task = await queued(client, echo_plan())
    await client.post(f"/tasks/{task}/run")

    page = await console.get(f"/console/task?id={task}")

    assert page.status_code == 200
    assert "ela-steps" in page.text and "ela-step--done" in page.text
    assert escape(RESULTS_ARE_ELSEWHERE) in page.text
    assert "ciao" not in page.text, "the output of a tool is not on this page"


async def test_a_task_that_produced_nothing_says_so(
    console: AsyncClient, client: AsyncClient
) -> None:
    task = await queued(client, echo_plan())

    assert NO_RESULTS in (await console.get(f"/console/task?id={task}")).text


async def test_stopping_a_task_takes_two_pages_and_is_signed_by_the_console(
    console: AsyncClient, client: AsyncClient
) -> None:
    """Without JavaScript a confirmation is a page; and the actor is the **user**, with the id of
    the browser the act came from (ADR 0037 §15)."""
    task = await queued(client, note_plan())
    confirm = await console.get(f"/console/cancel?id={task}")

    assert "non si può annullare" in confirm.text

    await console.post("/console/cancel", data={"id": task}, headers=origin(LOOPBACK))

    assert (await client.get(f"/tasks/{task}")).json()["state"] == TaskState.CANCELLED.value
    events = (await client.get(f"/audit?task_id={task}")).json()
    cancelled = next(
        one for one in events if one["event_type"] == AuditEventType.TASK_CANCELLED.value
    )
    assert cancelled["actor"]["kind"] == "USER"
    assert "fermato dal Command Center" in cancelled["summary"]


async def test_stopping_a_task_that_is_over_is_a_page_not_found(
    console: AsyncClient, client: AsyncClient
) -> None:
    task = await queued(client, echo_plan())
    await client.post(f"/tasks/{task}/run")

    assert (await console.get(f"/console/cancel?id={task}")).status_code == 404


async def test_every_page_carries_the_policy_and_is_never_cached(console: AsyncClient) -> None:
    """The second defence of «niente JavaScript», and the one that outlives a template."""
    for path in ("/console/", "/console/approvals", "/console/devices"):
        answered = await console.get(path)

        assert answered.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
        assert answered.headers["cache-control"] == "no-store"
        for sheet in STYLESHEETS:
            assert f"/console/{sheet}" in answered.text


async def test_a_value_of_the_user_is_escaped_and_not_run(
    console: AsyncClient, client: AsyncClient
) -> None:
    """The escape is by construction; the policy is the second half. A goal with a tag in it comes
    back as text."""
    task = await queued(client, echo_plan(), text="<script>alert(1)</script>")

    page = await console.get(f"/console/task?id={task}")

    assert "<script>alert(1)</script>" not in page.text
    assert "&lt;script&gt;" in page.text


async def test_the_two_sheets_are_served_under_this_surfaces_prefix(console: AsyncClient) -> None:
    for sheet in STYLESHEETS:
        answered = await console.get(f"/console/{sheet}")

        assert answered.status_code == 200
        assert "--ela-" in answered.text


# ----------------------------------------------------------------------------------------
# Dec. J — the ceiling derived from the pair of addresses
# ----------------------------------------------------------------------------------------


GOAL = "il segreto di Tommaso"


async def a_local_task(client: AsyncClient) -> str:
    """A task at the default level: ``LOCAL_ONLY``, which is what nearly every task is."""
    return await queued(client, echo_plan(), text=GOAL)


async def test_on_loopback_the_console_sees_the_goal_of_a_local_task(
    console: AsyncClient, client: AsyncClient
) -> None:
    """Dec. J: both ends of the socket are loopback, so the content is not leaving the machine
    it lives on — and the page says *why* it is visible."""
    task = await a_local_task(client)

    page = await console.get(f"/console/task?id={task}")

    assert GOAL in page.text
    assert FROM_THIS_MACHINE in page.text


async def test_from_the_tailnet_the_same_console_sees_the_id_and_says_so(
    console: AsyncClient, client: AsyncClient, app: FastAPI
) -> None:
    """The same cookie, the same page, another address: the price of dec. J, declared and shown.

    This is also the eye-level check of the risk nothing else can see: if this page ever said the
    other sentence, something would be forwarding through the loopback.
    """
    task = await a_local_task(client)

    async with opened(app, TAILNET, peer=PHONE_PEER) as away:
        away.cookies.set(CONSOLE_COOKIE, credential(console))
        page = await away.get(f"/console/task?id={task}")

    assert page.status_code == 200
    assert GOAL not in page.text
    assert task in page.text
    assert escape(FROM_AWAY) in page.text and STAYS_ON_THE_MAC in page.text


async def test_a_peer_that_claims_to_be_local_on_a_tailnet_socket_is_not_promoted(
    console: AsyncClient, client: AsyncClient, app: FastAPI
) -> None:
    """Dec. 9 of the review: the condition is the **pair**. P0 measured that a connection coming
    in on the tailnet interface carries that address at both ends, so a forged source leaves the
    sockname where it was — and the sockname is written by the operating system, not by the
    caller."""
    task = await a_local_task(client)

    async with opened(app, TAILNET, peer=FORGED_PEER) as forged:
        forged.cookies.set(CONSOLE_COOKIE, credential(console))
        page = await forged.get(f"/console/task?id={task}")

    assert GOAL not in page.text
    assert escape(FROM_AWAY) in page.text


async def test_a_companion_on_loopback_is_not_promoted(client: AsyncClient, app: FastAPI) -> None:
    """The promotion is bound to the role, and that is the whole safety of it: a promotion that
    applied to whoever arrives from there would be a door, not a derivation."""
    task = await a_local_task(client)
    minted = await client.post(
        "/nodes/enrollments", json={"privacy": "TRUSTED", "role": "COMPANION"}
    )

    async with opened(app, LOOPBACK) as phone:
        await phone.post(
            "/companion/enroll",
            data={"code": minted.json()["code"], "name": "iPhone", "os": "IOS"},
            headers=origin(LOOPBACK),
        )
        page = await phone.get("/companion/")

    assert GOAL not in page.text, "a companion on loopback sees what it always saw"
    assert task in page.text


async def test_a_worker_on_loopback_is_not_promoted(client: AsyncClient) -> None:
    """A node's credential is refused on a page whatever address it dials from: there is no
    promotion to reach, because there is no page to reach."""
    code = await code_for(client, "WORKER")
    born = await client.post(
        "/nodes/enroll",
        json={"name": "un nodo", "os": "MACOS"},
        headers={"Authorization": f"Bearer {code}"},
    )
    assert born.status_code == 201, born.text
    node = born.json()

    answered = await client.get(
        "/console/",
        headers={"Authorization": f"Bearer {node['device_id']}{SEPARATOR}{node['secret']}"},
    )

    assert answered.status_code == 401


async def test_the_promotion_is_of_the_request_and_the_registry_keeps_what_the_user_imposed(
    console: AsyncClient, client: AsyncClient
) -> None:
    """Dec. 16 of the review: the level dec. J derives lives for one request. The row still says
    what the user imposed at enrolment, and the audit of that request writes no ``LOCAL_ONLY``
    anywhere — a ceiling that wrote itself down would be a ceiling that changed without anybody
    deciding it."""
    task = await queued(client, note_plan())
    await console.get(f"/console/task?id={task}")
    await console.post("/console/cancel", data={"id": task}, headers=origin(LOOPBACK))

    rows = (await client.get("/devices")).json()
    row = next(one for one in rows if one["role"] == DeviceRole.CONSOLE.value)
    assert row["privacy"] == PrivacyLevel.TRUSTED.value

    signed = [one for one in (await client.get("/audit")).json() if one["actor"]["id"] == row["id"]]
    assert signed, "the console signed something, or this check is vacuous"
    assert not [one for one in signed if PrivacyLevel.LOCAL_ONLY.value in str(one)]


async def test_an_enrolment_code_never_carries_local_only(client: AsyncClient) -> None:
    """Dec. 2 of the review: the validator is not touched and takes no exemption. The answer to
    «where is this browser» is the socket's, not a level engraved in a row."""
    refused = await client.post(
        "/nodes/enrollments", json={"privacy": "LOCAL_ONLY", "role": "CONSOLE"}
    )

    assert refused.status_code == 422


def test_the_two_sentences_of_the_ceiling_are_different(console: Any) -> None:
    """A page that said the same thing from both sides would say nothing at all."""
    assert FROM_THIS_MACHINE != FROM_AWAY


# ----------------------------------------------------------------------------------------
# What a page composes, without an application: the branches a rendering has
# ----------------------------------------------------------------------------------------


def an_approval(**changed: Any) -> ApprovalOut:
    """A question as the route returns it, with the parts dec. F added defaulted away."""
    bare = ApprovalOut.of(
        Approval(
            id=ApprovalId(uuid.uuid4()),
            created_at=datetime.now(UTC),
            task_id=TaskId(uuid.uuid4()),
            step_id=StepId(uuid.uuid4()),
            capability_id="workspace.write_note",
            prompt="una domanda",
            status=ApprovalStatus.PENDING,
        )
    )
    return bare.model_copy(update=changed)


def a_step(state: StepState, goal: str = "uno step") -> StepOut:
    return StepOut(
        id=uuid.uuid4(),
        goal=goal,
        state=state,
        required_capabilities=("core.echo",),
        arguments={},
        preferred_device_traits=(),
        dependencies=(),
        risk=RiskLevel.SAFE,
        expected_result="qualcosa",
        success_conditions=(),
        requires_authorization=False,
    )


def a_detail(*steps: StepOut, state: TaskState = TaskState.EXECUTING) -> TaskDetail:
    return TaskDetail(
        id=uuid.uuid4(),
        created_at=datetime.now(UTC),
        goal="preparare il briefing di domani",
        state=state,
        intent_id=None,
        plan_id=uuid.uuid4(),
        parent_id=None,
        deadline=None,
        max_privacy=PrivacyLevel.LOCAL_ONLY,
        steps=steps,
    )


SEEN = Identity(Kind.CONSOLE, device_id=DeviceId(uuid.uuid4()), privacy=PrivacyLevel.LOCAL_ONLY)
"""A console reading from this machine: the ceiling lets the content through (dec. J)."""
AWAY = Identity(Kind.CONSOLE, device_id=DeviceId(uuid.uuid4()), privacy=PrivacyLevel.TRUSTED)
"""The same console, read from the tailnet: what it may see is what the phone may see."""


def test_now_says_what_is_running_and_marks_the_step_that_is() -> None:
    """§8 of the design: the plan with the one step in progress marked, and the ones that are
    done behind it — three templates, because a raw attribute in a slot would be escaped."""
    said = _now(
        a_detail(
            a_step(StepState.COMPLETED, "letto il calendario"),
            a_step(StepState.RUNNING, "analizzo i documenti"),
            a_step(StepState.PENDING, "preparo il briefing"),
            a_step(StepState.FAILED, "quello che non è andato"),
        ),
        SEEN,
    )

    assert "ela-step--done" in said and "letto il calendario" in said
    assert 'ela-step--now" aria-current="step"' in said
    assert "preparo il briefing · PENDING" in said
    assert "quello che non è andato · FAILED" in said


def test_now_says_so_when_nothing_is_running() -> None:
    assert NOTHING_RUNS in _now(None, SEEN)


def test_a_step_of_a_task_the_ceiling_hides_is_named_by_its_capability() -> None:
    """The goal of a step is the user's content; the capability it asks for is the catalogue's."""
    said = _now(a_detail(a_step(StepState.RUNNING, "il segreto")), AWAY)

    assert "il segreto" not in said
    assert "core.echo" in said


def test_a_question_asked_before_the_parts_existed_shows_what_it_has() -> None:
    """The bag of dec. F has defaults, and a page that refused to open would lose a question."""
    pairs = _pairs(an_approval(), seen=True)

    assert "Rischio" in pairs
    assert "Dove può andare" not in pairs and "Durata" not in pairs and "Scade" not in pairs


def test_a_question_shows_the_targets_only_when_the_ceiling_lets_it() -> None:
    """A target is the user's content — a path, an address — and it goes where the goal goes."""
    question = an_approval(targets=("workspace/notes/briefing.md",))

    assert "Su" in _pairs(question, seen=True)
    assert "Su" not in _pairs(question, seen=False)
    assert _content(question, seen=False) == ""


def test_a_question_shows_the_terms_and_the_expiry_when_it_has_them() -> None:
    question = an_approval(
        grant_uses=1,
        grant_seconds=1800,
        expires_at=datetime.now(UTC),
        max_privacy=PrivacyLevel.TRUSTED,
    )

    pairs = _pairs(question, seen=True)

    assert "un uso, entro 30 minuti" in pairs
    assert "Scade" in pairs and "Dove può andare" in pairs


# ----------------------------------------------------------------------------------------
# The refusals of the enrolment, each with its own sentence
# ----------------------------------------------------------------------------------------


async def test_a_code_nobody_issued_is_told_so(browser: AsyncClient, client: AsyncClient) -> None:
    """Four refusals and four sentences: the user has to know whether to mint another one."""
    answered = await browser.post(
        "/console/enroll", data={"code": "x" * 43, **DECLARED}, headers=origin(LOOPBACK)
    )

    assert answered.status_code == 401
    assert "non esiste" in answered.text
    assert (await client.get("/diagnostics")).json()["refused"] == {"unknown_code": 1}


async def test_a_code_already_spent_is_told_so(browser: AsyncClient, client: AsyncClient) -> None:
    code = await code_for(client)
    assert (
        await browser.post(
            "/console/enroll", data={"code": code, **DECLARED}, headers=origin(LOOPBACK)
        )
    ).status_code == 303

    again = await browser.post(
        "/console/enroll", data={"code": code, **DECLARED}, headers=origin(LOOPBACK)
    )

    assert again.status_code == 401
    assert "già" in again.text


async def test_a_code_past_its_expiry_is_told_so(
    browser: AsyncClient, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The expiry is moved below the route, as the phone's suite does: what is proved is the
    answer, not the arithmetic of the clock."""

    async def expired(self: NodeEnrollment, code: str, **declared: Any) -> Any:
        raise EnrollmentExpiredError(datetime.now(UTC))

    monkeypatch.setattr(NodeEnrollment, "enroll", expired)

    answered = await browser.post(
        "/console/enroll", data={"code": "x" * 43, **DECLARED}, headers=origin(LOOPBACK)
    )

    assert answered.status_code == 401
    assert "scaduto" in answered.text
    assert (await client.get("/diagnostics")).json()["refused"] == {"expired_code": 1}


async def test_a_declaration_that_is_not_a_system_is_refused(browser: AsyncClient) -> None:
    """No system is refused (dec. 14), but a word that is no system at all is not a system."""
    answered = await browser.post(
        "/console/enroll",
        data={"code": "x" * 43, "name": "MacBook", "os": "UN-COSO"},
        headers=origin(LOOPBACK),
    )

    assert answered.status_code == 422
    assert "dai un nome" in answered.text


async def test_a_revoked_node_says_so_in_the_device_center(
    console: AsyncClient, client: AsyncClient
) -> None:
    """Revoked is not «not available»: two facts, two names (ADR 0037 §12)."""
    code = await code_for(client, "WORKER")
    born = await client.post(
        "/nodes/enroll",
        json={"name": "un nodo", "os": "MACOS"},
        headers={"Authorization": f"Bearer {code}"},
    )
    await client.post(f"/nodes/{born.json()['device_id']}/revoke")

    page = await console.get("/console/devices")

    assert "Revocato" in page.text


async def test_answering_a_question_the_ceiling_hides_is_refused(
    console: AsyncClient, client: AsyncClient, app: FastAPI
) -> None:
    """One does not approve what one cannot see (§30): from the tailnet, a question about a task
    that stays on the Mac has no buttons — and a form built by hand is refused all the same."""
    task = await queued(client, note_plan())
    await client.post(f"/tasks/{task}/run")
    identifier = (await client.get("/approvals")).json()[0]["id"]

    async with opened(app, TAILNET, peer=PHONE_PEER) as away:
        away.cookies.set(CONSOLE_COOKIE, credential(console))
        shown = await away.get(f"/console/approval?id={identifier}")
        answered = await away.post(
            "/console/answer",
            data={"id": identifier, "answer": "yes"},
            headers=origin(TAILNET),
        )

    assert STAYS_ON_THE_MAC in shown.text and "answer" not in shown.text
    assert answered.status_code == 409
    assert (await client.get(f"/tasks/{task}")).json()["state"] == TaskState.WAITING_APPROVAL.value


# ----------------------------------------------------------------------------------------
# Ogni caso vuoto si nomina (dec. 21 della review, dalla prova a mano del 2026-09-20)
# ----------------------------------------------------------------------------------------


def test_a_task_with_no_plan_says_so_instead_of_showing_an_empty_list() -> None:
    """The defect the hand test found: an empty ``<ol>`` reads as «1.» and nothing, which says
    «there is nothing to say» in the one way indistinguishable from a bug (dec. K.2)."""
    said = _now(a_detail(), SEEN)

    assert NO_PLAN in said
    assert "ela-steps" not in said


async def test_the_page_of_a_task_with_no_plan_says_so(
    console: AsyncClient, client: AsyncClient
) -> None:
    created = await client.post("/tasks", json={"text": "una cosa da fare"})

    page = await console.get(f"/console/task?id={created.json()['id']}")

    assert NO_PLAN in page.text
    assert NO_RESULTS in page.text


async def test_the_approval_center_with_nothing_waiting_says_so(console: AsyncClient) -> None:
    answered = await console.get("/console/approvals")

    assert escape(NOTHING_WAITS) in answered.text


async def test_the_home_with_no_live_task_says_so(console: AsyncClient) -> None:
    home = await console.get("/console/")

    assert NO_TASKS in home.text
    assert NOTHING_RUNS in home.text
    assert escape(NOTHING_WAITS) in home.text


async def test_a_node_with_no_tool_says_so(console: AsyncClient) -> None:
    """``local`` declares the tools of this process; a node that declares none reads «nessuno»
    and not an empty cell, which would look like a value nobody wrote."""
    page = await console.get("/console/devices")

    assert "Tool" in page.text
    assert NO_TOOLS in page.text or "core.echo" in page.text


def test_a_registry_with_no_identity_says_so() -> None:
    """Never true in production — ``local`` is written at start-up — and the view must not lie
    about it anyway: what a page shows is what the route answered, empty included."""
    assert NO_DEVICES in pages.fragment(HERE_CONSOLE, "empty", text=NO_DEVICES)


# ----------------------------------------------------------------------------------------
# Una vista si raggiunge (dec. 22 della review)
# ----------------------------------------------------------------------------------------


def test_what_is_running_links_to_its_summary() -> None:
    """A view reachable only by typing its address is a view that is not there."""
    detail = a_detail(a_step(StepState.RUNNING))

    assert f'href="/console/task?id={detail.id}"' in _now(detail, SEEN)


async def test_a_question_links_to_the_summary_of_its_task(
    console: AsyncClient, client: AsyncClient
) -> None:
    """From the question to what it is part of: the other way into the execution summary."""
    task = await queued(client, note_plan())
    await client.post(f"/tasks/{task}/run")
    identifier = (await client.get("/approvals")).json()[0]["id"]

    page = await console.get(f"/console/approval?id={identifier}")

    assert f'href="/console/task?id={task}"' in page.text


def test_a_question_about_a_file_names_the_resolved_target_and_renders_its_sentence() -> None:
    """M13.1 dec. G: two facts of the machine, and the sentence comes from the capability.

    The page renders ``does`` as it stands. It owns no phrase of its own — that is blocker 2 of
    the proof by hand, where a read was told it «overwrites a file that is already there».
    """
    writing = an_approval(target="/Users/tommaso/Documenti/ELA/nota.md", does=OVERWRITES)
    reading = an_approval(target="/Users/tommaso/Documenti/ELA/nota.md", does=READS)

    written = _pairs(writing, seen=True)
    read = _pairs(reading, seen=True)

    assert "/Users/tommaso/Documenti/ELA/nota.md" in written
    assert "sovrascrive" in written or "overwrites" in written
    assert "overwrite" not in read.lower(), "a read is not told it overwrites anything"


def test_a_question_about_no_file_says_nothing_about_one() -> None:
    """Eight capabilities of ten touch no file, and their question must not invent one."""
    pairs = _pairs(an_approval(), seen=True)

    assert "Il file" not in pairs and "Che cosa fa" not in pairs


def test_the_two_facts_of_a_file_go_where_the_goal_goes() -> None:
    """A resolved path is the user's own filesystem: the ceiling keeps it on the Mac (§57)."""
    question = an_approval(target="/Users/tommaso/Documenti/ELA/nota.md", does=OVERWRITES)

    assert "Il file" not in _pairs(question, seen=False)
    assert "Che cosa fa" not in _pairs(question, seen=False)
