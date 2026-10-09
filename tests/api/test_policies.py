"""The routes of the policies of §59 (M13.12, ADR 0062; decisions 6, 7, 9): an ELA as ``build``
makes it, with the guided session the test scripts — the whole road, nothing paid.

A policy is born only from the route of its creation (rule 66); the preview is the same road
without a write; «partirebbe» asks the tool the prospect that precedes a question; a session the
policy covers starts without one; the revocation is written once, and a session it covered asks
again.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from ela.domain import AuditEventType
from ela.permissions import POLICY_PROSPECT
from ela.providers.anthropic.models import HAIKU_5_5
from tests.api.guided import (
    MAX_COST,
    Guided,
    Script,
    call,
    guided,
    planned,
    question,
    run,
)

POLICY: dict[str, Any] = {
    "capability": "browser.guided",
    "scope": ["www.youtube.com", "httpbin.org"],
    "limits": {"max_cost_usd": MAX_COST, "looks": "10", "seconds": "600"},
    "days": 1,
}
"""A policy that covers the sessions of ``tests/api/guided.py``: 0,60 $, eight looks, ten
minutes."""


async def created(g: Guided, body: dict[str, Any] | None = None) -> dict[str, Any]:
    preview = await g.client.post("/policies/preview", json=POLICY if body is None else body)
    assert preview.status_code == 200, preview.text
    shown = preview.json()
    made = await g.client.post(
        "/policies", json={**(POLICY if body is None else body), "model": shown["model"]}
    )
    assert made.status_code == 201, made.text
    result: dict[str, Any] = made.json()
    return result


async def test_the_preview_names_what_is_approved_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        before = await g.ela.audit.read()
        response = await g.client.post("/policies/preview", json=POLICY)
        after = await g.ela.audit.read()
        stored = await g.ela.authorizations.for_capability("browser.guided")  # type: ignore[arg-type]
        now = g.ela.clock.now()

    assert response.status_code == 200, response.text
    shown = response.json()
    assert shown["capability"] == "browser.guided"
    assert shown["scope"] == ["www.youtube.com", "httpbin.org"]
    assert shown["limits"] == {"max_cost_usd": MAX_COST, "looks": "10", "seconds": "600"}
    assert shown["days"] == 1
    assert datetime.fromisoformat(shown["expires_at"]) > now
    assert shown["model"] == HAIKU_5_5
    assert "anthropic" in shown["sends"]
    assert shown["one_call"] == "0.516384 USD"
    assert "reservation" in shown["cost"] and "0.516384 USD" in shown["cost"]
    assert shown["never"][0].startswith("every call of a capability that asks at every use")
    assert "browser.act" in shown["never"][0]
    assert any("task_type" in line for line in shown["never"])
    assert stored == ()
    assert len(after) == len(before), "the preview writes nothing"


async def test_the_creation_saves_the_policy_and_writes_who_created_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        policy = await created(g)
        listed = (await g.client.get("/policies")).json()
        events = [
            one
            for one in await g.ela.audit.read()
            if one.event_type is AuditEventType.AUTHORIZATION_GRANTED
        ]

    assert policy["capability"] == "browser.guided"
    assert policy["short"] == policy["id"][:8]
    assert policy["state"] == "LIVE"
    assert policy["uses"] == 0
    assert policy["model"] == HAIKU_5_5
    assert policy["created_by"]["name"] == "the command line on the Core"
    assert [one["id"] for one in listed["policies"]] == [policy["id"]]
    (admitting,) = listed["admitting"]
    assert admitting["capability"] == "browser.guided"
    assert [limit["name"] for limit in admitting["limits"]] == ["max_cost_usd", "looks", "seconds"]
    assert admitting["uncovered"] == ["task_type"]
    (event,) = events
    assert event.actor.kind.value == "USER"
    assert event.payload["origin"] == "policy"
    assert event.payload["scope"] == ["www.youtube.com", "httpbin.org"]
    assert event.payload["limits"] == {"max_cost_usd": MAX_COST, "looks": "10", "seconds": "600"}
    assert event.task_id is None and event.step_id is None
    assert POLICY_PROSPECT not in str(event.payload), "the sentence of the prospect is never saved"


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ({**POLICY, "capability": "browser.act"}, "no policy reaches a HIGH"),
        ({**POLICY, "capability": "fs.write", "scope": ["ELA"]}, "no policy reaches a HIGH"),
        ({**POLICY, "scope": ["www.google.com"]}, "SCOPE"),
        ({**POLICY, "days": 91}, "DAYS"),
        ({**POLICY, "limits": {"max_cost_usd": "1"}}, "LIMITS"),
    ],
    ids=["browser.act", "fs.write", "a-site-outside", "ninety-one-days", "missing-limits"],
)
async def test_a_refused_creation_is_a_422_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: dict[str, Any], fragment: str
) -> None:
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        preview = await g.client.post("/policies/preview", json=body)
        made = await g.client.post("/policies", json={**body, "model": HAIKU_5_5})
        listed = (await g.client.get("/policies", params={"all": "true"})).json()

    for response in (preview, made):
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "policy.refused"
        assert fragment in response.json()["error"]["message"]
    assert listed["policies"] == []


async def test_a_cost_below_one_call_would_not_start_and_the_tool_s_code_says_why(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Decision 7: «partirebbe», for a policy too — a defence that seems active is refused."""
    body = {**POLICY, "limits": {**POLICY["limits"], "max_cost_usd": "0.05"}}
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        preview = await g.client.post("/policies/preview", json=body)
        made = await g.client.post("/policies", json={**body, "model": HAIKU_5_5})

    for response in (preview, made):
        assert response.status_code == 422, response.text
        error = response.json()["error"]
        assert error["code"] == "policy.would_not_start"
        assert error["message"].startswith("guided.cap_below_one_call:")


async def test_a_confirmation_that_names_another_model_than_the_prospect_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        made = await g.client.post("/policies", json={**POLICY, "model": "claude-sonnet-5-5"})

    assert made.status_code == 409, made.text
    assert made.json()["error"]["code"] == "policy.preview_changed"


async def test_a_session_the_policy_covers_starts_without_a_question_and_spends_one_use(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with guided(monkeypatch, tmp_path, Script([call()])) as g:
        policy = await created(g)
        task = await planned(g)
        ran = await run(g, task)
        detail = (await g.client.get(f"/tasks/{task}")).json()
        listed = (await g.client.get("/policies")).json()
        approvals = (await g.client.get("/approvals")).json()

    assert ran["outcome"] == "completed", ran
    assert approvals == []
    assert detail["steps"][0]["policy"] == policy["id"]
    assert listed["policies"][0]["uses"] == 1


async def test_a_session_beyond_a_limit_asks_and_the_question_says_why(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        policy = await created(g)
        task = await planned(g, looks=11)
        first = await run(g, task)
        asked = await question(g, task)

    assert first["outcome"] == "waiting_approval"
    assert asked["why"] == [f"looks 11 is above the 10 of policy {policy['short']}"]


async def test_the_revocation_is_written_once_and_the_session_asks_again(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        policy = await created(g)
        revoked = await g.client.post(f"/policies/{policy['id']}/revoke")
        again = await g.client.post(f"/policies/{policy['id']}/revoke")
        task = await planned(g)
        await run(g, task)
        asked = await question(g, task)
        live = (await g.client.get("/policies")).json()["policies"]
        everything = (await g.client.get("/policies", params={"all": "true"})).json()["policies"]
        events = [
            one
            for one in await g.ela.audit.read()
            if one.event_type is AuditEventType.AUTHORIZATION_REVOKED
        ]

    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["policy"]["state"] == "REVOKED"
    assert "goes on until it ends" in revoked.json()["running"]
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "policy.not_live"
    assert "revoked" in asked["why"][0]
    assert live == []
    assert [one["state"] for one in everything] == ["REVOKED"]
    (event,) = events
    assert event.payload["origin"] == "policy"
    assert str(event.authorization_id) == policy["id"]


async def test_a_grant_born_from_a_yes_is_not_a_policy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with guided(monkeypatch, tmp_path, Script([call()])) as g:
        task = await planned(g)
        await run(g, task)
        asked = await question(g, task)
        await g.client.post(f"/tasks/{task}/approve", json={"approval_id": asked["id"]})
        await run(g, task)
        grants = await g.ela.authorizations.for_capability("browser.guided")  # type: ignore[arg-type]
        response = await g.client.post(f"/policies/{grants[0].id}/revoke")
        listed = (await g.client.get("/policies", params={"all": "true"})).json()["policies"]
        detail = (await g.client.get(f"/tasks/{task}")).json()

    assert response.status_code == 404
    assert listed == []
    assert detail["steps"][0]["policy"] is None
