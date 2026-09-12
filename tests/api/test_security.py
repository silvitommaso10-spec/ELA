"""The token in front of everything (spec §58; ADR 0023 §7).

The property under test is not "the token works": it is that **no route can be reached without
it**, including one added tomorrow by somebody who forgets — which is why the check is a
middleware and why this module enumerates the application's own routes instead of listing them.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import (
    Awaitable,
    Callable,
)
from datetime import (
    UTC,
    datetime,
)
from typing import (
    Any,
)

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from ela.api.security import (
    CODE_ROUTES,
    NODE_ROUTES,
    Anonymous,
    Identity,
    Kind,
    authorized,
)
from ela.devices import (
    LOCAL_USER,
    NodeEnrollment,
)
from ela.domain import (
    Actor,
    ActorKind,
    DeviceId,
)
from ela.ports import (
    EnrollmentExpiredError,
)
from tests.api.routers import api_routers, routes_of
from tests.api.support import served_paths
from tests.composition.support import TOKEN

OTHER = "y" * 40


def test_the_application_serves_the_twenty_nine_routes_of_the_adrs_and_its_schema(
    app: FastAPI,
) -> None:
    """Twelve routes (ADR 0023 §6), the two of ADR 0024 §5, the one of ADR 0025 §4, the one of
    ADR 0028 §8, the one of ADR 0032 §13, the three of ADR 0034 §9, the five of ADR 0037 §4,
    the three of ADR 0038 §11 and the one of ADR 0039 §2,
    plus ``/openapi.json``,
    which the loop below proves is behind the token like everything else — the HTML pages are
    off, a browser cannot send a header."""
    paths = served_paths(app)

    assert ("GET", "/openapi.json") in paths
    assert ("GET", "/tasks/{task_id}/results") in paths
    assert len(paths) == 30
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


async def test_a_node_reaches_its_five_routes_and_gets_the_same_401_everywhere_else(
    app: FastAPI, client: AsyncClient, anonymous: AsyncClient
) -> None:
    """Criterion 5 of M12.1 and criterion 23 of M12.2 (D10, I8; ADR 0037 §4, ADR 0038 §11), derived
    from the application and not listed: a route added tomorrow without a thought answers a node
    exactly as a request with nothing does — and the three of the work answer it, which is what
    extending ``NODE_ROUTES`` is for. Without the extension every node would read ``401`` there.

    ``GET /nodes/me`` is the sixth (M12.3 dec. L), and it is exercised here for the same reason the
    work routes are: it is the first thing a node that restarted calls, so a node reading ``401``
    there could never announce again."""
    node = await a_node(client)
    nothing = (await anonymous.get("/health")).json()

    for method, path in served_paths(app):
        if (method, path) in NODE_ROUTES:
            continue
        response = await client.request(method, concrete(path), headers=node)
        assert response.status_code == 401, f"{method} {path}"
        assert response.json() == nothing, f"{method} {path}"
    assert (await client.post("/nodes/heartbeat", json={}, headers=node)).status_code == 200
    # What a node that came back asks first: its row, and the revision to announce against.
    mine = await client.get("/nodes/me", headers=node)
    assert mine.status_code == 200
    assert mine.headers["ETag"] == '"1"'
    announced = await client.put(
        "/nodes/me", json=DECLARATION, headers={**node, "If-Match": mine.headers["ETag"]}
    )
    assert announced.status_code == 200
    # The work routes: nothing is waiting for this node, so what they answer is not 401.
    assert (await client.post("/nodes/work", headers=node)).status_code == 204
    for path in ("/nodes/work/result", "/nodes/work/renew"):
        asked = await client.post(path, json={"assignment_id": str(uuid.uuid4())}, headers=node)
        assert asked.status_code in {404, 422}, path


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


# ----------------------------------------------------------------------------------------
# Every anonymous reason has a request that produces it (ADR 0037 §13)
# ----------------------------------------------------------------------------------------

Producer = Callable[[AsyncClient, AsyncClient, pytest.MonkeyPatch], Awaitable[object]]


async def _nothing_presented(client: AsyncClient, anonymous: AsyncClient, _: Any) -> object:
    return await anonymous.get("/health")


async def _a_credential_nobody_knows(client: AsyncClient, anonymous: AsyncClient, _: Any) -> object:
    return await anonymous.get("/health", headers={"Authorization": f"Bearer {OTHER}"})


async def _a_node_nobody_enrolled(client: AsyncClient, anonymous: AsyncClient, _: Any) -> object:
    bearer = {"Authorization": f"Bearer {uuid.uuid4()}.anything"}
    return await anonymous.post("/nodes/heartbeat", json={}, headers=bearer)


async def _a_code_nobody_issued(client: AsyncClient, anonymous: AsyncClient, _: Any) -> object:
    bearer = {"Authorization": "Bearer not-a-code"}
    return await anonymous.post("/nodes/enroll", json=DECLARATION, headers=bearer)


async def _a_code_past_its_expiry(
    client: AsyncClient, anonymous: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> object:
    """The expiry is moved in time below the route; here the store answers as it would then."""

    async def expired(self: NodeEnrollment, code: str, **declared: Any) -> Any:
        raise EnrollmentExpiredError(datetime.now(UTC))

    monkeypatch.setattr(NodeEnrollment, "enroll", expired)
    return await _a_code_nobody_issued(client, anonymous, monkeypatch)


async def _the_core_on_a_node_route(client: AsyncClient, anonymous: AsyncClient, _: Any) -> object:
    return await client.post("/nodes/heartbeat", json={})


PRODUCED_BY: dict[Anonymous, Producer] = {
    Anonymous.MISSING: _nothing_presented,
    Anonymous.UNKNOWN_CREDENTIAL: _a_credential_nobody_knows,
    Anonymous.UNKNOWN_NODE: _a_node_nobody_enrolled,
    Anonymous.UNKNOWN_CODE: _a_code_nobody_issued,
    Anonymous.EXPIRED_CODE: _a_code_past_its_expiry,
    Anonymous.CORE_ON_A_NODE_ROUTE: _the_core_on_a_node_route,
}
"""One request per reason — the user's condition on the six (2026-09-11): a reason no request can
produce does not enter."""


def test_every_anonymous_reason_has_a_request_that_produces_it() -> None:
    assert set(PRODUCED_BY) == set(Anonymous)


@pytest.mark.parametrize("reason", list(Anonymous), ids=[reason.value for reason in Anonymous])
async def test_each_anonymous_reason_is_counted_by_its_request_and_by_nothing_else(
    reason: Anonymous,
    client: AsyncClient,
    anonymous: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = await PRODUCED_BY[reason](client, anonymous, monkeypatch)

    assert getattr(response, "status_code", None) == 401
    assert (await client.get("/diagnostics")).json()["refused"] == {reason.value: 1}
