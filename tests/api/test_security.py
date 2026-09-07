"""The token in front of everything (spec §58; ADR 0023 §7).

The property under test is not "the token works": it is that **no route can be reached without
it**, including one added tomorrow by somebody who forgets — which is why the check is a
middleware and why this module enumerates the application's own routes instead of listing them.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from ela.api.security import authorized
from tests.api.support import served_paths
from tests.composition.support import TOKEN

OTHER = "y" * 40


def test_the_application_serves_the_sixteen_routes_of_the_adrs_and_its_schema(
    app: FastAPI,
) -> None:
    """Twelve routes (ADR 0023 §6), the two of ADR 0024 §5, the one of ADR 0025 §4 and the one of
    ADR 0028 §8, plus ``/openapi.json``, which the loop below proves is behind the token like
    everything else — the HTML pages are off, a browser cannot send a header."""
    paths = served_paths(app)

    assert ("GET", "/openapi.json") in paths
    assert ("GET", "/tasks/{task_id}/results") in paths
    assert len(paths) == 17
    assert not {path for _, path in paths} & {"/docs", "/redoc"}


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
