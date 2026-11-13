"""The routes of the policies on the ``HIGH`` (M13.14, ADR 0068): the births of ``fs.write``,
``browser.act`` and ``browser.act_as_you``, place by place; the refusals; the uses; the preview;
what a policy did, read from the audit; and a policy whose uses are spent — an ELA as ``build``
makes it, with the root of ``tests/composition/support.py`` and the browser of ``ela.testing``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from typing import Any, Final
from uuid import UUID

import pytest

from ela.api.policies import (
    ENDED_DAYS,
    ON_THE_CORE,
    RECENT_MAX,
    PolicyWouldNotStartError,
    ended_of,
    preview_of,
)
from ela.api.schemas import PolicyIn
from ela.api.security import Identity, Kind
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
from ela.permissions import PolicyRequest, authorization_from_policy, production_catalogue
from ela.testing.fakes import FakeAccountBrowser
from ela.tools.fs import ELA_S_OWN, NOT_A_FOLDER
from tests.api.guided import Guided, Script, guided

CORE: Final = Identity(Kind.CORE)
FS_WRITE: Final = CapabilityId("fs.write")
ONE: Final = "ELA/prova/uno"
TWO: Final = "ELA/prova/due"


def root_of(g: Guided) -> Path:
    """The root ``build`` resolved: the folder of ``tests/composition/support.py``."""
    return Path(g.ela.settings.filesystem.root).resolve()


def folders(g: Guided, *names: str) -> None:
    for name in names:
        (root_of(g) / name).mkdir(parents=True, exist_ok=True)


def write_policy(*scope: str, uses: int | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"capability": "fs.write", "scope": list(scope), "days": 1}
    if uses is not None:
        body["uses"] = uses
    return body


async def born(g: Guided, body: dict[str, Any]) -> dict[str, Any]:
    """The preview, then the creation with what the preview named — ``None`` for no model."""
    preview = await g.client.post("/policies/preview", json=body)
    assert preview.status_code == 200, preview.text
    made = await g.client.post("/policies", json={**body, "model": preview.json()["model"]})
    assert made.status_code == 201, made.text
    result: dict[str, Any] = made.json()
    return result


def write_plan(path: str, *, overwrite: bool = False) -> dict[str, Any]:
    """The plan of ``docs/examples/fs-write.json``, on ``path``."""
    return {
        "goal": "scrivere un file",
        "steps": [
            {
                "id": "d1b7c4a2-9e35-4f18-8c60-000000000014",
                "goal": "lasciare un file nella cartella",
                "required_capabilities": ["fs.write"],
                "arguments": {
                    "path": path,
                    "body": "# M13.14\n",
                    "overwrite": overwrite,
                    "purpose": "la prova delle policy",
                },
                "risk": "HIGH",
                "expected_result": "il file è sul disco",
                "success_conditions": ["fs.file_exists", "fs.content_matches"],
                "requires_authorization": True,
            }
        ],
    }


async def written(g: Guided, path: str) -> tuple[str, dict[str, Any]]:
    """A task with one ``fs.write`` step on ``path``, run once: its id and what the run said."""
    task = str((await g.client.post("/tasks", json={"text": "scrivi"})).json()["id"])
    planned = await g.client.post(f"/tasks/{task}/plan", json=write_plan(path))
    assert planned.status_code == 200, planned.text
    ran = await g.client.post(f"/tasks/{task}/run")
    assert ran.status_code == 200, ran.text
    body: dict[str, Any] = ran.json()
    return task, body


async def why(g: Guided, task: str) -> list[str]:
    (found,) = [one for one in (await g.client.get("/approvals")).json() if one["task_id"] == task]
    lines: list[str] = found["why"]
    return lines


# ----------------------------------------------------------------------------------------
# The births
# ----------------------------------------------------------------------------------------


async def test_a_policy_of_fs_write_is_born_with_each_folder_resolved_beside_its_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Answer 20 of the review: what is approved names what counts — each folder as the Core's
    disk names it, whole. No model is called, and the confirmation carries the preview's ``None``
    (defect 16: it was a ``422``)."""
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        folders(g, ONE, TWO)
        preview = (await g.client.post("/policies/preview", json=write_policy(ONE, TWO))).json()
        policy = await born(g, write_policy(ONE, TWO))
        (event,) = [
            one
            for one in await g.ela.audit.read()
            if one.event_type is AuditEventType.AUTHORIZATION_GRANTED
        ]
        root = root_of(g)

    words = production_catalogue().get(FS_WRITE).policy_words
    assert words is not None
    assert preview["risk"] == "HIGH"
    assert preview["does"] == words.does and preview["goes"] == words.goes
    assert preview["scope"] == [ONE, TWO]
    assert preview["resolved"] == [str(root / ONE), str(root / TWO)]
    assert all(Path(place).is_absolute() for place in preview["resolved"])
    assert preview["uses"] == "no limit of uses"
    assert preview["on_the_core"] == ON_THE_CORE
    assert preview["model"] is None and preview["limits"] == {}
    assert any("a step that runs on a node asks" in line for line in preview["never"])
    assert preview["never"][-1] == (
        "what has left is not taken back: a revocation stops only what comes after"
    )
    assert "fs.write" not in preview["never"][0], "a HIGH with terms does not ask at every use"
    assert "terminal.run" in preview["never"][0]
    assert policy["risk"] == "HIGH" and policy["does"] == words.does
    assert policy["max_uses"] is None and policy["remaining"] is None
    assert policy["recent"] == [] and policy["state"] == "LIVE"
    assert event.payload["uses"] is None
    terms = event.payload["terms"]
    assert isinstance(terms, Mapping) and terms["on_the_core"] is True


async def test_a_policy_with_uses_is_born_with_them_and_the_preview_says_how_many(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        folders(g, ONE)
        preview = (await g.client.post("/policies/preview", json=write_policy(ONE, uses=3))).json()
        policy = await born(g, write_policy(ONE, uses=3))
        (stored,) = await g.ela.authorizations.for_capability(FS_WRITE)
        (event,) = [
            one
            for one in await g.ela.audit.read()
            if one.event_type is AuditEventType.AUTHORIZATION_GRANTED
        ]

    assert preview["uses"] == "at most 3 uses"
    assert policy["max_uses"] == 3 and policy["remaining"] == 3 and policy["uses"] == 0
    assert stored.max_uses == 3
    assert event.payload["uses"] == 3


@pytest.mark.parametrize("capability", ["browser.act", "browser.act_as_you"])
async def test_a_policy_of_a_gesture_is_born_on_a_declared_site(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capability: str
) -> None:
    body = {"capability": capability, "scope": ["httpbin.org"], "days": 1}
    async with guided(monkeypatch, tmp_path, Script([]), accounts=FakeAccountBrowser()) as g:
        preview = (await g.client.post("/policies/preview", json=body)).json()
        policy = await born(g, body)

    words = production_catalogue().get(CapabilityId(capability)).policy_words
    assert words is not None
    assert preview["risk"] == "HIGH" and preview["does"] == words.does
    assert preview["resolved"] == [None], "ELA resolves no name"
    assert preview["on_the_core"] == ""
    assert not any("node" in line for line in preview["never"])
    assert policy["capability"] == capability and policy["scope"] == ["httpbin.org"]


async def test_a_gesture_with_no_browser_would_not_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Proposal 7: «partirebbe» per place — the browser is asked whether it is there."""
    body = {"capability": "browser.act", "scope": ["httpbin.org"], "days": 1}
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        g.browser.installed_answer = False
        preview = await g.client.post("/policies/preview", json=body)
        listed = (await g.client.get("/policies", params={"all": "true"})).json()["policies"]

    assert preview.status_code == 422, preview.text
    error = preview.json()["error"]
    assert error["code"] == "policy.would_not_start"
    assert error["message"].startswith("browser.not_installed: ")
    assert listed == []


# ----------------------------------------------------------------------------------------
# What does not get born
# ----------------------------------------------------------------------------------------


def _a_link(root: Path) -> None:
    (root / "ELA" / "fuori").mkdir(parents=True, exist_ok=True)
    (root / ONE).mkdir(parents=True, exist_ok=True)
    os.symlink(root / "ELA" / "fuori", root / ONE / "link")


def _a_file(root: Path) -> None:
    (root / ONE).parent.mkdir(parents=True, exist_ok=True)
    (root / ONE).write_text("x", encoding="utf-8")


def _nothing(root: Path) -> None:
    return None


@pytest.mark.parametrize(
    ("place", "built", "code"),
    [
        (f"{ONE}/link", _a_link, "path.symlink"),
        (ONE, _a_file, NOT_A_FOLDER),
        (ONE, _nothing, "path.missing"),
    ],
    ids=["a-link-inside-the-folder", "a-file", "a-folder-that-is-not-there"],
)
async def test_a_place_the_tool_refuses_gives_birth_to_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, place: str, built: Any, code: str
) -> None:
    """Criterion 16 and answer 25: the folder must be there, be a folder, and not a link; the
    tool's code is the first word of the refusal, and nothing is written."""
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        built(root_of(g))
        before = await g.ela.audit.read()
        preview = await g.client.post("/policies/preview", json=write_policy(place))
        made = await g.client.post("/policies", json={**write_policy(place), "model": None})
        with pytest.raises(PolicyWouldNotStartError) as caught:
            await preview_of(PolicyIn.model_validate(write_policy(place)), g.ela, CORE)
        after = await g.ela.audit.read()
        stored = await g.ela.authorizations.for_capability(FS_WRITE)

    assert caught.value.code == code
    for response in (preview, made):
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "policy.would_not_start"
        assert response.json()["error"]["message"].startswith(f"{code}: ")
    assert stored == () and len(after) == len(before)


async def test_a_folder_that_is_a_protected_place_gives_birth_to_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Criterion 16: with the list injected into the tool — a valid root never holds one, the
    start-up refuses it — a folder of the scope that is one of ELA's own places is refused."""
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        folders(g, ONE)
        tool = g.ela.tools.get(FS_WRITE)
        monkeypatch.setattr(tool, "_protected", {"ELA's home": root_of(g) / ONE})
        preview = await g.client.post("/policies/preview", json=write_policy(ONE))
        stored = await g.ela.authorizations.for_capability(FS_WRITE)

    assert preview.status_code == 422, preview.text
    error = preview.json()["error"]
    assert error["code"] == "policy.would_not_start"
    assert error["message"].startswith(f"{ELA_S_OWN}: ") and "ELA's home" in error["message"]
    assert stored == ()


@pytest.mark.parametrize(
    "site",
    ["www.google.com", "127.0.0.1", "localhost", "127.0.0.1:8351", "ela.localhost"],
    ids=["not-declared", "loopback", "localhost", "ela-s-port", "a-localhost-name"],
)
async def test_a_site_not_declared_and_ela_s_own_address_give_birth_to_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, site: str
) -> None:
    """Criterion 17: the scope of the capability is the declared sites, and the address of ELA
    itself is none of them."""
    body = {"capability": "browser.act_as_you", "scope": [site], "days": 1}
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        preview = await g.client.post("/policies/preview", json=body)
        made = await g.client.post("/policies", json={**body, "model": None})
        stored = await g.ela.authorizations.for_capability(CapabilityId("browser.act_as_you"))

    for response in (preview, made):
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "policy.refused"
        assert "the scope of a policy of browser.act_as_you" in response.json()["error"]["message"]
    assert stored == ()


@pytest.mark.parametrize("uses", [True, "3", 1.5], ids=["a-boolean", "a-text", "a-fraction"])
async def test_uses_that_are_not_a_whole_number_are_refused_on_the_wire(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, uses: Any
) -> None:
    """A ``true`` is a word and not a count: the wire takes a whole number and nothing else."""
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        folders(g, ONE)
        preview = await g.client.post("/policies/preview", json={**write_policy(ONE), "uses": uses})
        made = await g.client.post(
            "/policies", json={**write_policy(ONE), "uses": uses, "model": None}
        )
        stored = await g.ela.authorizations.for_capability(FS_WRITE)

    for response in (preview, made):
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "invalid"
    assert stored == ()


async def test_a_policy_of_browser_guided_with_uses_has_them(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Answer 23: the field is one, and a ``MEDIUM`` policy has it too."""
    from tests.api.test_policies import POLICY

    async with guided(monkeypatch, tmp_path, Script([])) as g:
        policy = await born(g, {**POLICY, "uses": 2})

    assert policy["max_uses"] == 2 and policy["remaining"] == 2 and policy["risk"] == "MEDIUM"


# ----------------------------------------------------------------------------------------
# Under the policy: what it covers, and what it does not
# ----------------------------------------------------------------------------------------


async def test_a_write_in_its_folder_runs_without_a_question_and_one_outside_asks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Criterion 11, the route's side: inside the folder of the policy, on the Core, no question,
    the file written, one use, the action in the policy's view; outside, the question and why."""
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        folders(g, ONE, TWO)
        policy = await born(g, write_policy(ONE))
        inside, ran = await written(g, f"{ONE}/a.md")
        outside, asked = await written(g, f"{TWO}/b.md")
        lines = await why(g, outside)
        (listed,) = (await g.client.get("/policies")).json()["policies"]
        root = root_of(g)
        decided = [
            one
            for one in await g.ela.audit.read(task_id=TaskId(UUID(inside)))
            if one.event_type is AuditEventType.PERMISSION_DECIDED
        ]

    assert ran["outcome"] == "completed", ran
    assert (root / ONE / "a.md").read_text(encoding="utf-8") == "# M13.14\n"
    assert asked["outcome"] == "waiting_approval", asked
    assert not (root / TWO / "b.md").exists()
    assert lines == [f"a value of path is not among those of policy {policy['short']}"]
    assert listed["uses"] == 1
    (action,) = listed["recent"]
    assert action["task"] == inside[:8] and action["status"] == "SUCCEEDED"
    assert action["capability"] == "fs.write" and action["targets"] == [f"{ONE}/a.md"]
    (decision,) = decided
    assert decision.payload["rule"] == "APPROVAL_UNLESS_POLICY"
    assert f"covered by policy {policy['id']}" in decision.summary


async def test_a_write_through_a_link_in_its_folder_fails_and_spends_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Answer 24: not a question — the step fails with the tool's code, no use spent, nothing
    written, even through a link that stays inside the folder."""
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        folders(g, ONE, f"{ONE}/dentro")
        os.symlink(root_of(g) / ONE / "dentro", root_of(g) / ONE / "link")
        await born(g, write_policy(ONE))
        _, ran = await written(g, f"{ONE}/link/x.md")
        (listed,) = (await g.client.get("/policies")).json()["policies"]
        approvals = (await g.client.get("/approvals")).json()
        root = root_of(g)

    assert ran["outcome"] == "failed", ran
    assert "path.symlink" in ran["reason"]
    assert listed["uses"] == 0 and listed["recent"] == []
    assert approvals == []
    assert not (root / ONE / "dentro" / "x.md").exists()


# ----------------------------------------------------------------------------------------
# What a policy did: the audit, and nothing kept
# ----------------------------------------------------------------------------------------


async def test_the_last_actions_are_the_last_five_tool_executed_and_no_other_event(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Answer 29: five ``TOOL_EXECUTED`` with the policy's id, the most recent first — events of
    other kinds with the same id, and the actions of another policy, are not among them."""
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        folders(g, ONE, TWO)
        policy = await born(g, write_policy(ONE))
        other = await born(g, write_policy(TWO))
        now = g.ela.clock.now()

        async def event(kind: AuditEventType, authorization: str, n: int) -> None:
            await g.ela.audit.append(
                AuditEvent(
                    id=AuditEventId(g.ela.ids.new_uuid()),
                    created_at=now + timedelta(seconds=n),
                    event_type=kind,
                    actor=Actor(kind=ActorKind.SYSTEM, id="test"),
                    summary=f"event {n}",
                    capability_id=FS_WRITE,
                    authorization_id=AuthorizationId(authorization),  # type: ignore[arg-type]
                    payload={"status": "SUCCEEDED", "targets": [f"{ONE}/{n}.md"]},
                )
            )

        for n in range(7):
            await event(AuditEventType.TOOL_EXECUTED, policy["id"], n)
            await event(AuditEventType.EXECUTION_VERIFIED, policy["id"], 100 + n)
        await event(AuditEventType.TOOL_EXECUTED, other["id"], 200)
        await event(AuditEventType.PERMISSION_DECIDED, policy["id"], 300)
        listed = {one["id"]: one for one in (await g.client.get("/policies")).json()["policies"]}

    recent = listed[policy["id"]]["recent"]
    assert RECENT_MAX == 5 and len(recent) == RECENT_MAX
    assert [one["targets"] for one in recent] == [[f"{ONE}/{n}.md"] for n in (6, 5, 4, 3, 2)]
    assert [one["targets"] for one in listed[other["id"]]["recent"]] == [[f"{ONE}/200.md"]]


# ----------------------------------------------------------------------------------------
# A policy whose uses are spent
# ----------------------------------------------------------------------------------------


async def test_a_policy_whose_uses_are_spent_is_exhausted_and_its_revocation_is_a_409(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Answer 30: ``EXHAUSTED``, not ``LIVE``; it stands among the ended ones; revoking it is the
    ``409`` of a policy that is not live, with its reason, and nothing is written. A write after
    it asks, and the line says why."""
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        folders(g, ONE)
        policy = await born(g, write_policy(ONE, uses=1))
        _, first = await written(g, f"{ONE}/a.md")
        second, asked = await written(g, f"{ONE}/b.md")
        lines = await why(g, second)
        live = (await g.client.get("/policies")).json()["policies"]
        (ended,) = (await g.client.get("/policies", params={"all": "true"})).json()["policies"]
        before = await g.ela.audit.read()
        revoked = await g.client.post(f"/policies/{policy['id']}/revoke")
        after = await g.ela.audit.read()
        (stored,) = await g.ela.authorizations.for_capability(FS_WRITE)

    assert first["outcome"] == "completed", first
    assert asked["outcome"] == "waiting_approval", asked
    assert lines == [f"policy {policy['short']} was used 1 of its 1 times"]
    assert live == []
    assert ended["state"] == "EXHAUSTED" and ended["remaining"] == 0 and ended["uses"] == 1
    assert revoked.status_code == 409, revoked.text
    assert revoked.json()["error"]["code"] == "policy.not_live"
    assert revoked.json()["error"]["message"] == (
        f"policy {policy['short']} was used 1 of its 1 times: there is nothing to revoke"
    )
    assert len(after) == len(before) and stored.revoked_at is None


async def test_an_expired_policy_still_refuses_its_revocation_with_its_own_sentence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        folders(g, ONE)
        grant = authorization_from_policy(
            PolicyRequest(capability_id=FS_WRITE, scope=(ONE,), limits={}, days=1),
            catalogue=g.ela.capabilities,
            granted_by="core",
            now=g.ela.clock.now() - timedelta(days=2),
            authorization_id=AuthorizationId(g.ela.ids.new_uuid()),  # type: ignore[arg-type]
        )
        await g.ela.authorizations.grant(grant)
        revoked = await g.client.post(f"/policies/{grant.id}/revoke")
        (ended,) = (await g.client.get("/policies", params={"all": "true"})).json()["policies"]

    assert grant.expires_at is not None
    assert revoked.status_code == 409, revoked.text
    assert revoked.json()["error"]["message"] == (
        f"policy {str(grant.id)[:8]} expired at {grant.expires_at.isoformat()}: "
        "there is nothing to revoke"
    )
    assert ended["state"] == "EXPIRED"


async def test_the_ended_ones_are_the_ones_not_live_of_the_last_thirty_days(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Answer 30, the route's side of the console's «Finite di recente»: revoked, spent, expired
    less than :data:`ENDED_DAYS` ago — and neither a live one nor one ended before."""
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        folders(g, ONE)
        live = await born(g, write_policy(ONE))
        spent = await born(g, write_policy(ONE, uses=1))
        await g.ela.authorizations.consume(
            AuthorizationId(UUID(spent["id"])), now=g.ela.clock.now()
        )
        revoked = await born(g, write_policy(ONE))
        await g.client.post(f"/policies/{revoked['id']}/revoke")
        ended_by_days = {}
        for days_ago in (ENDED_DAYS - 1, ENDED_DAYS + 2):
            grant = authorization_from_policy(
                PolicyRequest(capability_id=FS_WRITE, scope=(ONE,), limits={}, days=1),
                catalogue=g.ela.capabilities,
                granted_by="core",
                now=g.ela.clock.now() - timedelta(days=days_ago),
                authorization_id=AuthorizationId(g.ela.ids.new_uuid()),  # type: ignore[arg-type]
            )
            await g.ela.authorizations.grant(grant)
            ended_by_days[days_ago] = str(grant.id)
        ended = {str(one.id): one.state for one in await ended_of(g.ela)}

    assert ended == {
        spent["id"]: "EXHAUSTED",
        revoked["id"]: "REVOKED",
        ended_by_days[ENDED_DAYS - 1]: "EXPIRED",
    }
    assert live["id"] not in ended


async def test_an_action_says_its_targets_as_the_executor_wrote_them_or_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A ``null`` target stays ``null``, and an event that carries no list of targets has none:
    the view reads the audit, it never invents."""
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        folders(g, ONE)
        policy = await born(g, write_policy(ONE))
        for n, payload in enumerate(
            ({"status": "FAILED"}, {"status": "SUCCEEDED", "targets": [None, f"{ONE}/a.md"]})
        ):
            await g.ela.audit.append(
                AuditEvent(
                    id=AuditEventId(g.ela.ids.new_uuid()),
                    created_at=g.ela.clock.now() + timedelta(seconds=n),
                    event_type=AuditEventType.TOOL_EXECUTED,
                    actor=Actor(kind=ActorKind.SYSTEM, id="test"),
                    summary="execute",
                    authorization_id=AuthorizationId(UUID(policy["id"])),
                    payload=payload,
                )
            )
        (listed,) = (await g.client.get("/policies")).json()["policies"]

    assert [(one["status"], one["targets"], one["task"]) for one in listed["recent"]] == [
        ("SUCCEEDED", [None, f"{ONE}/a.md"], None),
        ("FAILED", [], None),
    ]
