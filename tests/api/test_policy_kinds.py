"""Who reaches the policies of §59, for every identity ELA knows (M13.12, ADR 0062; decision 9).

No route declares which kinds it admits — the middleware decides, by the ground a request stands
on (``security.py``) —, so «CORE and CONSOLE» is read on two grounds: the token on the JSON routes
of ``/policies``, a console's cookie on the pages of ``/console/policies``, which call those routes'
functions (rule 55). **The table is a closed world on** :class:`~ela.api.security.Kind`: an identity
added tomorrow has to say which side it stands on, or this fails.
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import urlencode

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ela.api.security import SESSION_KEY_HEADER, Kind
from ela.domain import AuditEvent, AuditEventType
from ela.permissions import BROWSER_GUIDED
from ela.providers.anthropic.models import HAIKU_5_5
from tests.api.guided import Guided, Script, guided
from tests.api.support import BASE
from tests.api.test_console import LOOPBACK, code_for, opened
from tests.api.test_console_policies import FIELDS
from tests.api.test_guided_room import a_session
from tests.api.test_policies import POLICY, created
from tests.api.test_security import a_node

POLICIES: Final = ("/policies", "/policies/preview")
PAGES: Final = ("/console/policies",)

REACHES: Final[dict[Kind, str]] = {
    Kind.CORE: "the routes of /policies, with the Core's token",
    Kind.CONSOLE: "the pages of /console/policies, with its cookie",
    Kind.COMPANION: "nothing: creating and revoking from the phone are out (decision 12)",
    Kind.NODE: "nothing: a node takes work, it does not decide what ELA may do",
    Kind.CODE: "nothing: a code is spent on its one route",
    Kind.SESSION: "nothing: a session calls its gateway, and no capability creates a policy",
}


def test_every_identity_says_which_side_it_stands_on() -> None:
    assert set(REACHES) == set(Kind)


async def test_the_core_reaches_the_routes_and_not_the_pages(
    app: FastAPI, client: AsyncClient
) -> None:
    assert (await client.get("/policies")).status_code == 200
    page = await client.get("/console/policies")
    assert page.status_code == 401


async def test_a_console_reaches_the_pages_and_not_the_routes(
    app: FastAPI, client: AsyncClient
) -> None:
    async with opened(app, LOOPBACK) as browser:
        answered = await browser.post(
            "/console/enroll",
            data={"code": await code_for(client), "name": "MacBook", "os": "MACOS"},
            headers={"Origin": LOOPBACK},
        )
        assert answered.status_code == 303
        assert (await browser.get("/console/policies")).status_code == 200
        assert (await browser.get("/policies")).status_code == 401


async def test_a_phone_reaches_neither(app: FastAPI, client: AsyncClient) -> None:
    async with opened(app, "http://ela.tailnet") as browser:
        answered = await browser.post(
            "/companion/enroll",
            data={"code": await code_for(client, "COMPANION"), "name": "iPhone", "os": "IOS"},
            headers={"Origin": "http://ela.tailnet"},
        )
        assert answered.status_code == 303
        assert (await browser.get("/policies")).status_code == 401
        assert (await browser.get("/companion/policies")).status_code == 404
        assert (await browser.get("/console/policies")).status_code == 401


async def test_a_node_a_code_and_a_session_reach_nothing(
    client: AsyncClient, anonymous: AsyncClient
) -> None:
    node = await a_node(client)
    code = (await client.post("/nodes/enrollments", json={"privacy": "TRUSTED"})).json()["code"]
    for headers in (
        node,
        {"Authorization": f"Bearer {code}"},
        {SESSION_KEY_HEADER: "z" * 43},
    ):
        for path in POLICIES:
            response = await anonymous.get(path, headers=headers)
            assert response.status_code in {401, 405}, (headers, path)
        assert (await anonymous.post("/policies", json={}, headers=headers)).status_code == 401


# ----------------------------------------------------------------------------------------
# Every identity, every path, every method (M13.14, proposal 12 of the SPEC; criterion 3)
# ----------------------------------------------------------------------------------------

METHODS: Final = ("GET", "POST", "PUT", "PATCH", "DELETE")
REVOKE: Final = "/policies/{id}/revoke"
PATHS: Final = (
    "/policies",
    "/policies/preview",
    REVOKE,
    "/console/policies",
    "/console/policies/preview",
    "/console/policies/revoke",
)
"""The six paths of the policies: the JSON routes and the pages that call their functions. The
revocation's carries the id of a policy that exists, so a cell that reached it would revoke it."""

KIND_OF: Final[dict[str, Kind | None]] = {
    "core": Kind.CORE,
    "console": Kind.CONSOLE,
    "companion": Kind.COMPANION,
    "node": Kind.NODE,
    "code": Kind.CODE,
    "session in x-api-key": Kind.SESSION,
    "session as bearer": Kind.SESSION,
    "nobody": None,
}
"""Who knocks: every identity ELA knows, and the anonymous caller. A session knocks with the header
of its own gateway and with the one of the routes, with a token opened by the room — a real one,
read on its own path (:func:`test_the_session_s_token_is_read_on_its_own_path`)."""

REFUSED: Final = (401, 401, 401, 401, 401)
"""Refused by the middleware, before any route, whatever the method."""

ANSWERS: Final[dict[tuple[str, str], tuple[int, int, int, int, int]]] = {
    **{(caller, path): REFUSED for caller in KIND_OF for path in PATHS},
    ("core", "/policies"): (200, 201, 405, 405, 405),
    ("core", "/policies/preview"): (405, 200, 405, 405, 405),
    ("core", REVOKE): (405, 200, 405, 405, 405),
    ("console", "/console/policies"): (200, 303, 404, 404, 404),
    ("console", "/console/policies/preview"): (404, 200, 404, 404, 404),
    ("console", "/console/policies/revoke"): (404, 303, 404, 404, 404),
}
"""What every cell answers: per caller and path, ``GET``, ``POST``, ``PUT``, ``PATCH``,
``DELETE``. Every caller is refused on every path with a ``401``, except two: **the Core on the
JSON routes**, where a method no route serves is a ``405``; **a console on its pages**, where a
method no page serves is the ``404`` of a route a console may not use (``route_not_allowed``,
which also writes ``DEVICE_REJECTED``). Every form carries the ``Origin`` of the address it was
sent to, so a ``401`` is the identity and never the origin check."""

RIGHT: Final = frozenset(
    {
        ("core", "/policies", "GET"),
        ("core", "/policies", "POST"),
        ("core", "/policies/preview", "POST"),
        ("core", REVOKE, "POST"),
        ("console", "/console/policies", "GET"),
        ("console", "/console/policies", "POST"),
        ("console", "/console/policies/preview", "POST"),
        ("console", "/console/policies/revoke", "POST"),
    }
)
"""The cells that are the right ones: the positive control. Every other cell writes nothing."""

WRITES: Final = [
    ("core", "/policies", "POST"),
    ("core", REVOKE, "POST"),
    ("console", "/console/policies", "POST"),
    ("console", "/console/policies/revoke", "POST"),
]
"""The right cells that write — a birth or a revocation —, in the order they run: last."""


@dataclass(frozen=True)
class Caller:
    client: AsyncClient
    headers: dict[str, str]


def test_every_identity_knocks_on_the_table() -> None:
    """The closed world of the table: every member of :class:`Kind`, and the anonymous caller."""
    assert {kind for kind in KIND_OF.values() if kind is not None} == set(Kind)
    assert set(ANSWERS) == {(caller, path) for caller in KIND_OF for path in PATHS}


async def _callers(g: Guided, stack: AsyncExitStack) -> dict[str, Caller]:
    nobody = await stack.enter_async_context(
        AsyncClient(transport=ASGITransport(app=g.app), base_url=BASE)
    )
    here = await stack.enter_async_context(opened(g.app, LOOPBACK))
    console = await stack.enter_async_context(opened(g.app, LOOPBACK))
    enrolled = await console.post(
        "/console/enroll",
        data={"code": await code_for(g.client), "name": "MacBook", "os": "MACOS"},
        headers={"Origin": LOOPBACK},
    )
    assert enrolled.status_code == 303, enrolled.text
    phone = await stack.enter_async_context(opened(g.app, "http://ela.tailnet"))
    enrolled = await phone.post(
        "/companion/enroll",
        data={"code": await code_for(g.client, "COMPANION"), "name": "iPhone", "os": "IOS"},
        headers={"Origin": "http://ela.tailnet"},
    )
    assert enrolled.status_code == 303, enrolled.text
    code = (await g.client.post("/nodes/enrollments", json={"privacy": "TRUSTED"})).json()["code"]
    _, _, session = await a_session(g)
    return {
        "core": Caller(g.client, {}),
        "console": Caller(console, {}),
        "companion": Caller(phone, {}),
        "node": Caller(nobody, await a_node(g.client)),
        "code": Caller(nobody, {"Authorization": f"Bearer {code}"}),
        "session in x-api-key": Caller(here, {SESSION_KEY_HEADER: session.token}),
        "session as bearer": Caller(here, {"Authorization": f"Bearer {session.token}"}),
        "nobody": Caller(nobody, {}),
    }


async def _knock(caller: Caller, method: str, path: str, policies: tuple[str, str]) -> int:
    """One request, with the body the right identity would send on that path: so a cell that
    reached the route would have created, previewed or revoked. The route's revocation and the
    page's each have a live policy of their own."""
    route_s, page_s = policies
    model = HAIKU_5_5
    target = path.replace("{id}", route_s)
    if path.startswith("/console/"):
        fields = {
            "/console/policies": [*FIELDS, ("model", model)],
            "/console/policies/preview": FIELDS,
            "/console/policies/revoke": [("id", page_s)],
        }[path]
        response = await caller.client.request(
            method,
            target,
            content=urlencode(fields) if method != "GET" else None,
            headers={
                "Origin": str(caller.client.base_url).rstrip("/"),
                **caller.headers,
                "content-type": "application/x-www-form-urlencoded",
            },
        )
    else:
        body = {"/policies": {**POLICY, "model": model}, "/policies/preview": POLICY}.get(path)
        response = await caller.client.request(
            method, target, json=body if method != "GET" else None, headers=caller.headers
        )
    return response.status_code


async def _written(g: Guided) -> tuple[tuple[object, ...], tuple[AuditEvent, ...]]:
    """What a cell could have written: the policies with their uses, and the whole audit."""
    stored = await g.ela.authorizations.for_capability(BROWSER_GUIDED)
    uses = [await g.ela.authorizations.uses(grant.id) for grant in stored]
    return tuple(zip(stored, uses, strict=True)), await g.ela.audit.read()


async def test_every_identity_on_every_path_in_every_method(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Criterion 3 (c), the second missing piece: who reaches the creation, the preview and the
    revocation, **for every identity, in every method, with a real session token**. Every cell
    answers what :data:`ANSWERS` says. Every cell that is not one of :data:`RIGHT` leaves the
    store of the policies as it was, and adds to the audit at most the refusal of a known device
    (``DEVICE_REJECTED``: the console and the node are named when they knock where they may not) —
    and the right ones, run last with the same requests, are the ones that write."""
    async with guided(monkeypatch, tmp_path, Script([])) as g, AsyncExitStack() as stack:
        policies = ((await created(g))["id"], (await created(g))["id"])
        callers = await _callers(g, stack)
        cells = [(c, p, m) for c in KIND_OF for p in PATHS for m in METHODS]
        measured: dict[tuple[str, str], list[int]] = {}
        wrote: list[tuple[str, str, str]] = []
        refusals: set[AuditEventType] = set()
        births: set[AuditEventType] = set()
        for caller, path, method in sorted(cells, key=lambda cell: cell in RIGHT):
            before = await _written(g)
            status = await _knock(callers[caller], method, path, policies)
            measured.setdefault((caller, path), [0] * len(METHODS))[METHODS.index(method)] = status
            after = await _written(g)
            if after[0] != before[0]:
                wrote.append((caller, path, method))
            added = {event.event_type for event in after[1][len(before[1]) :]}
            (births if (caller, path, method) in RIGHT else refusals).update(added)

    assert {key: tuple(codes) for key, codes in measured.items()} == ANSWERS
    assert wrote == WRITES
    assert refusals == {AuditEventType.DEVICE_REJECTED}
    assert births == {AuditEventType.AUTHORIZATION_GRANTED, AuditEventType.AUTHORIZATION_REVOKED}


async def test_the_session_s_token_is_read_on_its_own_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The token of the table is a real one: on its own gateway, from this machine, while the
    session is open, it is **read and accepted** — so its ``401`` on the paths of the policies is
    the identity standing on the wrong ground, never «no credential»."""
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        _, step, session = await a_session(g)
        before = dict(g.app.state.refused)
        async with opened(g.app, LOOPBACK) as here:
            own = await here.post(
                f"/sessions/{step}/v1/messages",
                content=b"{}",
                headers={SESSION_KEY_HEADER: session.token},
            )
        after = dict(g.app.state.refused)

    assert own.status_code != 401, own.text
    assert after == before
