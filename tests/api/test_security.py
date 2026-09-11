"""The token in front of everything (spec §58; ADR 0023 §7).

The property under test is not "the token works": it is that **no route can be reached without
it**, including one added tomorrow by somebody who forgets — which is why the check is a
middleware and why this module enumerates the application's own routes instead of listing them.
"""

from __future__ import annotations

import re
import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from ela.api.security import (
    CODE_ROUTES,
    NODE_ROUTES,
    Identity,
    Kind,
    authorized,
)
from ela.devices import (
    LOCAL_USER,
)
from ela.domain import (
    Actor,
    ActorKind,
    DeviceId,
)
from tests.api.routers import api_routers, routes_of
from tests.api.support import served_paths
from tests.composition.support import TOKEN

OTHER = "y" * 40


def test_the_application_serves_the_twenty_five_routes_of_the_adrs_and_its_schema(
    app: FastAPI,
) -> None:
    """Twelve routes (ADR 0023 §6), the two of ADR 0024 §5, the one of ADR 0025 §4, the one of
    ADR 0028 §8, the one of ADR 0032 §13, the three of ADR 0034 §9 and the five of ADR 0037 §4,
    plus ``/openapi.json``,
    which the loop below proves is behind the token like everything else — the HTML pages are
    off, a browser cannot send a header."""
    paths = served_paths(app)

    assert ("GET", "/openapi.json") in paths
    assert ("GET", "/tasks/{task_id}/results") in paths
    assert len(paths) == 26
    assert not {path for _, path in paths} & {"/docs", "/redoc"}


def test_the_application_mounts_every_router_of_its_package_and_nothing_else(
    app: FastAPI,
) -> None:
    """``create_app`` declares its routers in a tuple, as production code should: a module must
    not be mounted because a file appeared. This is the census the tuple is held to — a router
    module the app forgets to mount fails here, and so does a route served from nowhere."""
    served = set(served_paths(app)) - {("GET", "/openapi.json")}

    assert served == routes_of(api_routers().values())


async def test_no_route_answers_without_the_token(app: FastAPI, anonymous: AsyncClient) -> None:
    """A route added without a thought is still protected: the guard is not per route."""
    for method, path in served_paths(app):
        response = await anonymous.request(method, path.replace("{task_id}", str(TOKEN)))

        assert response.status_code == 401, f"{method} {path}"
        assert response.json()["error"]["code"] == "unauthorized"


async def test_the_refusal_says_how_to_authenticate(anonymous: AsyncClient) -> None:
    response = await anonymous.get("/health")

    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_a_path_that_does_not_exist_answers_401_too(anonymous: AsyncClient) -> None:
    """Not 404: whoever has no token does not learn which routes ELA has."""
    assert (await anonymous.get("/what-is-here")).status_code == 401


@pytest.mark.parametrize(
    "header",
    [
        f"Bearer {OTHER}",
        f"Basic {TOKEN}",
        TOKEN,
        "Bearer",
        "Bearer ",
        f"bearer {TOKEN[:-1]}",
    ],
)
async def test_anything_but_the_token_is_refused(anonymous: AsyncClient, header: str) -> None:
    response = await anonymous.get("/health", headers={"Authorization": header})

    assert response.status_code == 401


async def test_the_scheme_is_case_insensitive_and_the_token_is_not(
    anonymous: AsyncClient,
) -> None:
    assert (
        await anonymous.get("/health", headers={"Authorization": f"bearer {TOKEN}"})
    ).status_code == 200
    assert (
        await anonymous.get("/health", headers={"Authorization": f"Bearer {TOKEN.upper()}"})
    ).status_code == 401


async def test_with_the_token_the_door_opens(client: AsyncClient) -> None:
    assert (await client.get("/health")).status_code == 200


def test_a_token_typed_with_an_accent_is_refused_and_does_not_raise() -> None:
    """``compare_digest`` refuses non-ASCII strings: comparing bytes is what makes a wrong
    token an answer instead of a traceback."""
    assert not authorized("Bearer pàssword", TOKEN)
    assert not authorized(None, TOKEN)
    assert authorized(f"Bearer  {TOKEN} ", TOKEN)


DECLARATION = {"name": "pc", "os": "WINDOWS", "available_tools": ["core-echo"]}
PLACEHOLDER = "11111111-1111-4111-8111-111111111111"


def concrete(path: str) -> str:
    """A served path with every parameter filled in, so the request reaches its route."""
    return re.sub(r"\{[^}]+\}", PLACEHOLDER, path)


async def a_node(client: AsyncClient) -> dict[str, str]:
    """A node enrolled through the routes, as the header it speaks with."""
    code = (await client.post("/nodes/enrollments", json={"privacy": "TRUSTED"})).json()["code"]
    born = (
        await client.post(
            "/nodes/enroll", json=DECLARATION, headers={"Authorization": f"Bearer {code}"}
        )
    ).json()
    return {"Authorization": f"Bearer {born['device_id']}.{born['secret']}"}


async def test_a_node_reaches_its_two_routes_and_gets_the_same_401_everywhere_else(
    app: FastAPI, client: AsyncClient, anonymous: AsyncClient
) -> None:
    """Criterion 5 (D10, ADR 0037 §4), derived from the application and not listed: a route added
    tomorrow without a thought answers a node exactly as a request with nothing does."""
    node = await a_node(client)
    nothing = (await anonymous.get("/health")).json()

    for method, path in served_paths(app):
        if (method, path) in NODE_ROUTES:
            continue
        response = await client.request(method, concrete(path), headers=node)
        assert response.status_code == 401, f"{method} {path}"
        assert response.json() == nothing, f"{method} {path}"
    assert (await client.post("/nodes/heartbeat", json={}, headers=node)).status_code == 200
    announced = await client.put("/nodes/me", json=DECLARATION, headers={**node, "If-Match": "1"})
    assert announced.status_code == 200


async def test_the_core_is_not_a_node(client: AsyncClient, anonymous: AsyncClient) -> None:
    """The Core's token on a route that speaks as a node is refused like nothing at all."""
    nothing = (await anonymous.get("/health")).json()

    for method, path in sorted(NODE_ROUTES | CODE_ROUTES):
        response = await client.request(method, path, json=DECLARATION)
        assert response.status_code == 401, f"{method} {path}"
        assert response.json() == nothing


async def test_a_code_opens_only_its_route_and_stays_spendable(client: AsyncClient) -> None:
    """Criterion 4: presented anywhere else it is refused, and it is not spent by being refused."""
    code = (await client.post("/nodes/enrollments", json={"privacy": "TRUSTED"})).json()["code"]
    bearer = {"Authorization": f"Bearer {code}"}

    assert (await client.get("/devices", headers=bearer)).status_code == 401
    assert (await client.post("/nodes/heartbeat", json={}, headers=bearer)).status_code == 401
    assert (await client.post("/nodes/enroll", json=DECLARATION, headers=bearer)).status_code == 201


def test_a_node_signs_as_itself_and_the_core_is_not_a_node() -> None:
    """The actor a route reads: the user at this machine for the Core, the node for a node."""
    node = Identity(Kind.NODE, device_id=DeviceId(uuid.UUID(PLACEHOLDER)))

    assert node.actor == Actor(kind=ActorKind.DEVICE, id=PLACEHOLDER)
    assert Identity(Kind.CORE).actor == LOCAL_USER
    with pytest.raises(ValueError, match="not a node"):
        _ = Identity(Kind.CORE).node


async def test_a_node_shaped_credential_with_no_id_in_it_is_anonymous(
    client: AsyncClient, anonymous: AsyncClient
) -> None:
    """``<x>.<y>`` whose first half is no UUID names no node: counted, and not written."""
    response = await anonymous.post(
        "/nodes/heartbeat", json={}, headers={"Authorization": "Bearer not-a-uuid.secret"}
    )

    assert response.status_code == 401
    assert (await client.get("/diagnostics")).json()["refused"] == {"unknown_credential": 1}
