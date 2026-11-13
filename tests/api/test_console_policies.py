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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

import pytest
from httpx import AsyncClient

from ela.api import console
from ela.api.companion import when
from ela.api.console import NO_POLICIES, _bounds
from ela.api.schemas import LimitOut, PolicyIn, PreviewOut
from ela.domain import (
    Actor,
    ActorKind,
    AuditEvent,
    AuditEventId,
    AuditEventType,
    AuthorizationId,
    CapabilityId,
    TaskId,
)
from ela.permissions import (
    COST_PATTERN,
    PolicyRequest,
    authorization_from_policy,
    production_catalogue,
)
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
    """Decision 25: an integer with its range — the catalogue refuses one without it —, and an
    amount of money with its form."""
    looks = LimitOut(name="looks", type="integer", minimum=1, maximum=30)
    cost = LimitOut(name="max_cost_usd", type="string", pattern=COST_PATTERN)

    assert _bounds(looks) == "un intero da 1 a 30"
    assert _bounds(cost) == "una cifra in dollari, con il punto: 1.10"


async def test_the_list_says_there_is_none_and_the_form_is_derived_from_the_declaration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with guided(monkeypatch, tmp_path, Script([])) as g, a_console(g) as console:
        page = outside_the_block((await console.get("/console/policies")).text)

    assert "Nessuna policy viva" in page
    assert 'value="browser.guided"' in page
    for site in ("www.youtube.com", "example.com", "httpbin.org"):
        assert f'value="{site}"' in page
    assert "un intero da 1 a 30" in page and "un intero da 30 a 1800" in page
    assert 'ela-field__help">un valore<' not in page
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
    assert "terminal.run" in page, "what a policy never covers: a row that asks at every use"
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
    assert "I siti e le cartelle di una policy restano sul Mac" in listed
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


# ----------------------------------------------------------------------------------------
# M13.14 (ADR 0068): the level, what it does, the uses, the last actions, the ended ones
# ----------------------------------------------------------------------------------------

ONE = "ELA/uno"


async def a_write_policy(g: Guided, *, uses: int | None) -> dict[str, Any]:
    """A policy of ``fs.write`` on ``ELA/uno``, created through the route with the Core's token."""
    (Path(g.ela.settings.filesystem.root) / ONE).mkdir(parents=True, exist_ok=True)
    body: dict[str, Any] = {"capability": "fs.write", "scope": [ONE], "days": 1, "uses": uses}
    made = await g.client.post("/policies", json={**body, "model": None})
    assert made.status_code == 201, made.text
    result: dict[str, Any] = made.json()
    return result


async def acted(g: Guided, policy: dict[str, Any], target: str) -> None:
    """One use spent, and the ``TOOL_EXECUTED`` the executor writes with it."""
    authorization = AuthorizationId(UUID(policy["id"]))
    await g.ela.authorizations.consume(authorization, now=g.ela.clock.now())
    await g.ela.audit.append(
        AuditEvent(
            id=AuditEventId(g.ela.ids.new_uuid()),
            created_at=g.ela.clock.now(),
            event_type=AuditEventType.TOOL_EXECUTED,
            actor=Actor(kind=ActorKind.SYSTEM, id="test"),
            summary="execute",
            task_id=TaskId(UUID("3a4d7002-0000-4000-8000-000000000001")),
            capability_id=CapabilityId(policy["capability"]),
            authorization_id=authorization,
            payload={"status": "SUCCEEDED", "targets": [target]},
        )
    )


MARKED = PreviewOut(
    capability=CapabilityId("marked.capability"),
    description="DESCRIPTION-1",
    risk="RISK-2",
    does="DOES-3",
    goes="GOES-4",
    scope=("ELA/uno", "ELA/due"),
    resolved=("/root/ELA/uno", None),
    limits={"LIMIT-5": "VALUE-5"},
    days=6,
    expires_at=datetime(2026, 11, 13, 9, 30, tzinfo=UTC),
    uses="USES-8",
    on_the_core="CORE-9",
    model="MODEL-10",
    sends="SENDS-11",
    one_call="ONE-CALL-12",
    cost="COST-13",
    never=("NEVER-14", "NEVER-15"),
)
"""A preview with a mark in every field: what the page must show, field by field."""


def shown_by_the_page() -> dict[str, tuple[str, ...]]:
    return {
        "capability": ("marked.capability",),
        "description": ("DESCRIPTION-1",),
        "risk": ("RISK-2",),
        "does": ("DOES-3",),
        "goes": ("GOES-4",),
        "scope": ("ELA/uno", "ELA/due"),
        "resolved": ("ELA/uno = /root/ELA/uno",),
        "limits": ("LIMIT-5=VALUE-5",),
        "days": ("fra 6 giorni",),
        "expires_at": (when(MARKED.expires_at),),
        "uses": ("USES-8",),
        "on_the_core": ("CORE-9",),
        "model": ("MODEL-10",),
        "sends": ("SENDS-11",),
        "one_call": ("ONE-CALL-12",),
        "cost": ("COST-13",),
        "never": ("NEVER-14", "NEVER-15"),
    }


async def test_the_preview_shows_every_field_of_the_route_s_answer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Proposal 13 and answer 20, at closed world: a field the route adds to its preview and the
    console does not show fails here (ADR 0045 §11) — the console under ``LOCAL_ONLY`` creates."""

    async def marked(body: PolicyIn, ela: Any, identity: Any) -> PreviewOut:
        return MARKED

    monkeypatch.setattr(console, "preview_of", marked)
    async with guided(monkeypatch, tmp_path, Script([])) as g, a_console(g) as browser:
        answer = await posted(browser, "/console/policies/preview", FIELDS)  # type: ignore[arg-type]

    assert answer.status_code == 200, answer.text
    page = " ".join(outside_the_block(answer.text).split())
    marks = shown_by_the_page()
    assert set(marks) == set(PreviewOut.model_fields)
    for field, wanted in marks.items():
        for mark in wanted:
            assert mark in page, (field, mark)


async def test_a_policy_says_its_level_what_it_does_its_uses_and_its_last_actions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Criterion 19: «Livello», «Che cosa fa senza chiederti», «Usi» — with what is left, or
    without a limit —, «Ultime azioni»; and the empty list says MEDIUM or HIGH."""
    async with guided(monkeypatch, tmp_path, Script([])) as g, a_console(g) as browser:
        empty = outside_the_block((await browser.get("/console/policies")).text)
        write = await a_write_policy(g, uses=10)
        for n in range(3):
            await acted(g, write, f"ELA/uno/{n}.md")
        guided_policy = await posted(browser, "/console/policies", [*FIELDS, ("model", HAIKU_5_5)])
        page = " ".join(outside_the_block((await browser.get("/console/policies")).text).split())

    words = production_catalogue().get(CapabilityId("fs.write")).policy_words
    assert words is not None
    assert NO_POLICIES in empty and "MEDIUM o HIGH" in NO_POLICIES
    assert guided_policy.status_code == 303
    for text in ("Livello", "HIGH", "MEDIUM", "Che cosa fa senza chiederti", words.does):
        assert text in page, text
    assert "3 di 10, ne restano 7" in page
    assert "0, senza limite di usi" in page
    assert "Ultime azioni" in page and "task 3a4d7002" in page and "ELA/uno/2.md" in page
    assert page.index("ELA/uno/2.md") < page.index("ELA/uno/0.md"), "the most recent first"
    assert "Nessuna policy finita negli ultimi trenta giorni." in page


async def test_under_a_narrower_ceiling_the_targets_of_the_actions_stay_on_the_mac(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        write = await a_write_policy(g, uses=None)
        await acted(g, write, "ELA/uno/segreto.md")
        async with a_console(g, away=True) as browser:
            page = outside_the_block((await browser.get("/console/policies")).text)

    assert "segreto.md" not in page and "ELA/uno" not in page
    assert "i bersagli restano sul Mac" in page and "resta sul Mac" in page
    assert "task 3a4d7002" in page, "when and which task are not the user's content"


async def test_a_policy_that_ended_is_among_the_ended_ones_and_offers_no_revocation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Answer 30: a policy whose uses are spent is not live; the console says it ended its uses,
    beside the revoked and the expired ones of the last thirty days, with no «Revoca»."""
    async with guided(monkeypatch, tmp_path, Script([])) as g, a_console(g) as browser:
        spent = await a_write_policy(g, uses=1)
        await acted(g, spent, "ELA/uno/a.md")
        revoked = await a_write_policy(g, uses=None)
        await g.client.post(f"/policies/{revoked['id']}/revoke")
        for days_ago, name in ((2, "recent"), (40, "old")):
            grant = authorization_from_policy(
                PolicyRequest(
                    capability_id=CapabilityId("fs.write"), scope=(ONE,), limits={}, days=1
                ),
                catalogue=g.ela.capabilities,
                granted_by=name,
                now=g.ela.clock.now() - timedelta(days=days_ago),
                authorization_id=AuthorizationId(g.ela.ids.new_uuid()),  # type: ignore[arg-type]
            )
            await g.ela.authorizations.grant(grant)
            if name == "old":
                old = str(grant.id)[:8]
            else:
                expired = str(grant.id)[:8]
        page = outside_the_block((await browser.get("/console/policies")).text)

    live, ended = page.split("Finite di recente", 1)
    assert "Nessuna policy viva" in live
    assert 'action="/console/policies/revoke"' not in page
    assert spent["short"] in ended and "ha finito gli usi" in ended
    assert revoked["short"] in ended and "revocata" in ended
    assert expired in ended and "scaduta" in ended
    assert old not in page, "ended more than thirty days ago"


@pytest.mark.parametrize(
    ("uses", "max_uses"), [("", None), ("3", 3)], ids=["empty-is-no-limit", "a-number"]
)
async def test_the_form_takes_the_uses_and_a_place_of_its_own(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, uses: str, max_uses: int | None
) -> None:
    """The field «Usi», empty for no limit; and «Un'altra voce», a folder under the declared one;
    the console's empty «model» is the preview's ``None``."""
    fields = [("capability", "fs.write"), ("scope", ONE), ("days", "1"), ("uses", uses)]
    async with guided(monkeypatch, tmp_path, Script([])) as g, a_console(g) as browser:
        (Path(g.ela.settings.filesystem.root) / ONE).mkdir(parents=True)
        form = outside_the_block((await browser.get("/console/policies")).text)
        preview = outside_the_block(
            (await posted(browser, "/console/policies/preview", fields)).text
        )
        made = await posted(browser, "/console/policies", [*fields, ("model", "")])
        (policy,) = (await g.client.get("/policies")).json()["policies"]

    assert 'name="uses" type="number" min="1">' in form, "no value: the uses are yours"
    assert 'id="policy-place-fs.write" name="scope">' in form
    assert f'name="uses" value="{uses}"' in preview if uses else 'name="uses"' not in preview
    assert made.status_code == 303, made.text
    assert policy["capability"] == "fs.write" and policy["scope"] == [ONE]
    assert policy["max_uses"] == max_uses


@pytest.mark.parametrize("uses", ["tre", "-1", "0"], ids=["a-word", "negative", "zero"])
async def test_uses_that_are_not_a_whole_number_from_one_create_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, uses: str
) -> None:
    fields = [("capability", "fs.write"), ("scope", ONE), ("days", "1"), ("uses", uses)]
    async with guided(monkeypatch, tmp_path, Script([])) as g, a_console(g) as browser:
        (Path(g.ela.settings.filesystem.root) / ONE).mkdir(parents=True)
        made = await posted(browser, "/console/policies", [*fields, ("model", "")])
        stored = await g.ela.authorizations.for_capability(CapabilityId("fs.write"))

    assert made.status_code == 422, made.text
    assert stored == ()
