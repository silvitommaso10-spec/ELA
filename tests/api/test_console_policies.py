"""The fifth view of the Command Center: ``/console/policies`` (M13.12, ADR 0062; decisions 9,
18 and 23).

The list, the form derived from the catalogue and the declaration, the preview with «Crea», the
creation, the revocation — forms ``POST`` with the origin check of the forms of a yes, and no
JavaScript. A policy has no task, so no level: its sites are ``LOCAL_ONLY`` content (decision 18),
and a console under a narrower ceiling neither shows them nor creates — it revokes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pytest
from httpx import AsyncClient

from ela.api.console import _bounds
from ela.permissions import COST_PATTERN
from ela.providers.anthropic.models import HAIKU_5_5
from tests.api.guided import MAX_COST, Guided, Script, guided
from tests.api.support import outside_the_block
from tests.api.test_console import LOOPBACK, PHONE_PEER, TAILNET, code_for, opened

FIELDS: list[tuple[str, str]] = [
    ("capability", "browser.guided"),
    ("scope", "www.youtube.com"),
    ("scope", "httpbin.org"),
    ("limit-max_cost_usd", MAX_COST),
    ("limit-looks", "10"),
    ("limit-seconds", "600"),
    ("days", "1"),
]


@asynccontextmanager
async def a_console(g: Guided, *, away: bool = False) -> AsyncIterator[AsyncClient]:
    """A browser enrolled as a console: on the Mac, or on the tailnet with the level ``TRUSTED``."""
    base, peer = (TAILNET, PHONE_PEER) if away else (LOOPBACK, ("127.0.0.1", 123))
    async with opened(g.app, base, peer) as browser:
        answered = await browser.post(
            "/console/enroll",
            data={"code": await code_for(g.client), "name": "MacBook", "os": "MACOS"},
            headers={"Origin": base},
        )
        assert answered.status_code == 303, answered.text
        browser.headers["Origin"] = base
        yield browser


async def posted(console: AsyncClient, path: str, fields: list[tuple[str, str]]) -> Any:
    """A form as a browser sends it, with a key repeated for every site ticked."""
    return await console.post(
        path,
        content=urlencode(fields),
        headers={"content-type": "application/x-www-form-urlencoded"},
    )


def test_the_form_says_the_bounds_of_every_limit_the_catalogue_admits() -> None:
    """An integer with its range, a cost with its pattern, and a limit whose schema says neither —
    which the catalogue admits for an integer — as what it is."""
    assert _bounds(1, 30, None) == "un intero da 1 a 30"
    assert _bounds(None, None, COST_PATTERN) == "una cifra in dollari, con il punto: 1.10"
    assert _bounds(None, None, None) == "un valore"


async def test_the_list_says_there_is_none_and_the_form_is_derived_from_the_declaration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with guided(monkeypatch, tmp_path, Script([])) as g, a_console(g) as console:
        page = outside_the_block((await console.get("/console/policies")).text)

    assert "Nessuna policy viva" in page
    assert 'value="browser.guided"' in page
    for site in ("www.youtube.com", "example.com", "httpbin.org"):
        assert f'value="{site}"' in page
    for name in ("max_cost_usd", "looks", "seconds"):
        assert f'name="limit-{name}"' in page
    assert 'name="days"' in page and 'min="1"' in page and 'max="90"' in page
    assert 'name="days" value=' not in page, "the days have no default (decision 3d)"
    assert "<script" not in page


async def test_the_preview_names_what_is_approved_and_offers_crea(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with guided(monkeypatch, tmp_path, Script([])) as g, a_console(g) as console:
        page = outside_the_block(
            (await posted(console, "/console/policies/preview", FIELDS)).text  # type: ignore[arg-type]
        )
        stored = await g.ela.authorizations.for_capability("browser.guided")  # type: ignore[arg-type]

    assert "www.youtube.com" in page and "httpbin.org" in page
    assert HAIKU_5_5 in page
    assert "0.516384 USD" in page
    assert "browser.act" in page
    assert 'action="/console/policies"' in page and "Crea" in page
    assert stored == (), "a preview writes nothing"


async def test_the_creation_and_the_revocation_from_the_console(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with guided(monkeypatch, tmp_path, Script([])) as g, a_console(g) as console:
        made = await posted(console, "/console/policies", [*FIELDS, ("model", HAIKU_5_5)])
        listed = outside_the_block((await console.get("/console/policies")).text)
        (policy,) = (await g.client.get("/policies")).json()["policies"]
        gone = await console.post("/console/policies/revoke", data={"id": policy["id"]})
        after = outside_the_block((await console.get("/console/policies")).text)
        everything = (await g.client.get("/policies", params={"all": "true"})).json()["policies"]

    assert made.status_code == 303 and made.headers["location"] == "/console/policies"
    assert policy["short"] in listed and "www.youtube.com" in listed
    assert 'action="/console/policies/revoke"' in listed
    assert policy["created_by"]["role"] == "CONSOLE"
    assert gone.status_code == 303
    assert "Nessuna policy viva" in after
    assert [one["state"] for one in everything] == ["REVOKED"]


async def test_a_post_without_the_origin_of_ela_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with guided(monkeypatch, tmp_path, Script([])) as g, a_console(g) as console:
        del console.headers["Origin"]
        refused = await posted(console, "/console/policies", [*FIELDS, ("model", HAIKU_5_5)])
        stored = await g.ela.authorizations.for_capability("browser.guided")  # type: ignore[arg-type]

    assert refused.status_code == 403
    assert stored == ()


async def test_under_a_narrower_ceiling_the_sites_stay_on_the_mac_and_nothing_is_created(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Decision 18: the sites of a policy are ``LOCAL_ONLY``; the revocation stays possible."""
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        made = await g.client.post("/policies/preview", json=_body())
        await g.client.post("/policies", json={**_body(), "model": made.json()["model"]})
        async with a_console(g, away=True) as console:
            listed = outside_the_block((await console.get("/console/policies")).text)
            preview = await posted(console, "/console/policies/preview", FIELDS)
            create = await posted(console, "/console/policies", [*FIELDS, ("model", HAIKU_5_5)])
            (policy,) = (await g.client.get("/policies")).json()["policies"]
            gone = await console.post("/console/policies/revoke", data={"id": policy["id"]})

    assert "www.youtube.com" not in listed
    assert "I siti di una policy restano sul Mac" in listed
    assert 'name="limit-' not in listed, "no form under the ceiling"
    assert preview.status_code == 409
    assert create.status_code == 409
    assert gone.status_code == 303


def _body() -> dict[str, Any]:
    return {
        "capability": "browser.guided",
        "scope": ["www.youtube.com"],
        "limits": {"max_cost_usd": MAX_COST, "looks": "10", "seconds": "600"},
        "days": 1,
    }
