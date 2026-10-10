"""Who reaches the policies of §59, for every identity ELA knows (M13.12, ADR 0062; decision 9).

No route declares which kinds it admits — the middleware decides, by the ground a request stands
on (``security.py``) —, so «CORE and CONSOLE» is read on two grounds: the token on the JSON routes
of ``/policies``, a console's cookie on the pages of ``/console/policies``, which call those routes'
functions (rule 55). **The table is a closed world on** :class:`~ela.api.security.Kind`: an identity
added tomorrow has to say which side it stands on, or this fails.
"""

from __future__ import annotations

from typing import Final

from fastapi import FastAPI
from httpx import AsyncClient

from ela.api.security import SESSION_KEY_HEADER, Kind
from tests.api.test_console import LOOPBACK, code_for, opened
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
