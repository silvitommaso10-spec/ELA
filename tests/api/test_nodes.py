"""The five routes of the nodes, through the real application (M12.1; ADR 0037 §4, §5, §9-§13).

Every status here is observed, never declared: each test drives the routes the way the user and a
node would — ``ela node enroll`` is ``POST /nodes/enrollments`` with the Core's token, and a node
is whoever presents the code and then its own secret — and reads what came back and what the
audit kept. The acceptance criteria of M12.1 are named where each is held.
"""

from __future__ import annotations

import uuid
from datetime import (
    UTC,
    datetime,
)
from typing import Any

import pytest
from httpx import AsyncClient, Response

from ela.composition import Ela
from ela.devices import (
    LOCAL_DEVICE_ID,
    LOCAL_USER,
    DeviceRegistry,
    NodeEnrollment,
    fingerprint,
)
from ela.domain import AuditEvent, AuditEventType
from ela.ports import (
    DeviceRevokedError,
    EnrollmentExpiredError,
)
from tests.api.support import echo_plan, queued

DECLARATION: dict[str, Any] = {
    "name": "pc",
    "os": "WINDOWS",
    "available_tools": ["core-echo"],
    "performance": "HIGH",
}
"""What a Windows node declares of itself: the half that is its to write (ADR 0037 §10)."""


async def issue(client: AsyncClient, privacy: str = "TRUSTED") -> str:
    """``ela node enroll --privacy <privacy>``, as the route it calls."""
    response = await client.post("/nodes/enrollments", json={"privacy": privacy})
    assert response.status_code == 201, response.text
    return str(response.json()["code"])


async def enroll(client: AsyncClient, code: str, body: dict[str, Any] | None = None) -> Response:
    """A node presenting its code, with the half it declares."""
    return await client.post(
        "/nodes/enroll",
        json=DECLARATION if body is None else body,
        headers={"Authorization": f"Bearer {code}"},
    )


async def enrolled(
    client: AsyncClient, privacy: str = "TRUSTED", **declared: Any
) -> tuple[str, dict[str, str]]:
    """A node born through the routes: its id, and the header it speaks with."""
    response = await enroll(client, await issue(client, privacy), {**DECLARATION, **declared})
    assert response.status_code == 201, response.text
    born = response.json()
    return str(born["device_id"]), {"Authorization": f"Bearer {born['device_id']}.{born['secret']}"}


async def row(client: AsyncClient, device_id: str) -> dict[str, Any]:
    """The node as ``GET /devices`` shows it."""
    (found,) = [one for one in (await client.get("/devices")).json() if one["id"] == device_id]
    return dict(found)


async def written(ela: Ela, kind: AuditEventType) -> list[AuditEvent]:
    return [event for event in await ela.audit.read() if event.event_type is kind]


# ----------------------------------------------------------------------------------------
# Enrollment (criteria 1, 2, 3)
# ----------------------------------------------------------------------------------------


async def test_a_node_is_born_with_an_id_and_a_privacy_it_did_not_write(
    client: AsyncClient, ela: Ela
) -> None:
    """Criterion 1: the privacy is the code's, the network the registry's, and a node never seen
    is not available; the admission is the user's."""
    response = await enroll(client, await issue(client, "TRUSTED"))

    assert response.status_code == 201
    born = response.json()
    assert set(born) == {"device_id", "secret", "revision"}
    assert born["revision"] == 1
    node = await row(client, born["device_id"])
    assert (node["privacy"], node["network"], node["last_seen_at"], node["available"]) == (
        "TRUSTED",
        "REMOTE",
        None,
        False,
    )
    (event,) = await written(ela, AuditEventType.DEVICE_ENROLLED)
    assert event.actor == LOCAL_USER
    assert str(event.device_id) == born["device_id"]


@pytest.mark.parametrize(
    "extra", [{"id": str(uuid.uuid4())}, {"privacy": "CLOUD_ALLOWED"}], ids=["id", "privacy"]
)
async def test_a_node_that_names_its_own_id_or_privacy_is_refused_and_nothing_is_born(
    client: AsyncClient, extra: dict[str, str]
) -> None:
    """Criterion 1, the negative: with pydantic's default the body would be trimmed and answered
    ``201``. Refused before the code is spent, so the same code still works afterwards."""
    code = await issue(client)
    before = len((await client.get("/devices")).json())

    response = await enroll(client, code, {**DECLARATION, **extra})

    assert response.status_code == 422
    assert len((await client.get("/devices")).json()) == before
    assert (await enroll(client, code)).status_code == 201


async def test_local_only_is_refused_by_the_route_and_no_code_is_issued(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 2 (D18): in the server and not only in the CLI, which is a client."""
    issued: list[object] = []
    original = NodeEnrollment.issue

    async def spy(self: NodeEnrollment, privacy: Any) -> Any:
        issued.append(privacy)
        return await original(self, privacy)

    monkeypatch.setattr(NodeEnrollment, "issue", spy)
    response = await client.post("/nodes/enrollments", json={"privacy": "LOCAL_ONLY"})

    assert response.status_code == 422
    assert "LOCAL_ONLY is this machine's level" in response.json()["error"]["message"]
    assert issued == []


async def test_a_code_opens_the_door_once(client: AsyncClient, anonymous: AsyncClient) -> None:
    """Criterion 3 at the route: presented again, the same ``401`` as an invented code, and no
    second node. The expiry is held below the route, where a clock can be moved
    (``tests/devices/test_enrollment.py``), and the race with two connections below that."""
    code = await issue(client)
    assert (await enroll(client, code)).status_code == 201
    nodes = len((await client.get("/devices")).json())

    again = await enroll(client, code)
    invented = await enroll(client, "not-a-code")

    assert again.status_code == invented.status_code == 401
    assert again.json() == invented.json() == (await anonymous.get("/health")).json()
    assert len((await client.get("/devices")).json()) == nodes


# ----------------------------------------------------------------------------------------
# The secret (criterion 6) and the heartbeat (criterion 7)
# ----------------------------------------------------------------------------------------


async def test_the_secret_is_in_clear_only_in_the_answer_that_hands_it_out(
    client: AsyncClient, ela: Ela
) -> None:
    """Criterion 6. The probe proves what this test exercises and nothing more: an enrollment, a
    heartbeat, an announcement, a refused route, the lists, a revocation, a refused heartbeat —
    and it searches everything they produced, their answers and the audit, for the code, the
    secret and their hashes."""
    code = await issue(client)
    answer = await enroll(client, code)
    born = answer.json()
    secret = born["secret"]
    node = {"Authorization": f"Bearer {born['device_id']}.{secret}"}
    produced = [
        await client.post("/nodes/heartbeat", json={}, headers=node),
        await client.put("/nodes/me", json=DECLARATION, headers={**node, "If-Match": "1"}),
        await client.get("/devices", headers=node),
        await client.get("/devices"),
        await client.get("/diagnostics"),
        await client.post(f"/nodes/{born['device_id']}/revoke"),
        await client.post("/nodes/heartbeat", json={}, headers=node),
    ]

    audit = " ".join(event.model_dump_json() for event in await ela.audit.read())
    for value in (secret, fingerprint(secret), code, fingerprint(code)):
        assert value not in audit
        assert all(value not in response.text for response in produced)
    assert secret in answer.text
    assert await ela.devices.secret_hash(uuid.UUID(born["device_id"])) == fingerprint(secret)  # type: ignore[arg-type]


async def test_a_heartbeat_makes_the_node_available_and_writes_nothing(
    client: AsyncClient, ela: Ela
) -> None:
    """Criterion 7: the rows of the audit counted on that one call (ADR 0016 §6)."""
    device_id, node = await enrolled(client)
    before = len(await ela.audit.read())

    response = await client.post(
        "/nodes/heartbeat", json={"status": "IDLE", "power_source": "AC"}, headers=node
    )

    assert response.status_code == 200
    assert len(await ela.audit.read()) == before
    assert (await row(client, device_id))["available"] is True


# ----------------------------------------------------------------------------------------
# The work a remote node never receives (criteria 8, 9)
# ----------------------------------------------------------------------------------------


async def test_a_remote_node_built_to_win_never_receives_work(
    client: AsyncClient, ela: Ela
) -> None:
    """Criterion 8 (D18, ``PRIVACY``), which M12.2 retires in the commit that brings the
    sensitivity of a task. Two remote nodes — ``TRUSTED`` and ``CLOUD_ALLOWED`` — built by the
    routes to win on today's weights: every tool, ``HIGH``, on ``AC``, available. The run of
    production names ``local``, with both among the candidates and ``PRIVACY`` among their
    refusals."""
    tools = [tool.name for tool in ela.tools.tools()]
    remote = []
    for privacy in ("TRUSTED", "CLOUD_ALLOWED"):
        device_id, node = await enrolled(client, privacy, available_tools=tools)
        await client.post("/nodes/heartbeat", json={"power_source": "AC"}, headers=node)
        assert (await row(client, device_id))["available"] is True
        remote.append(device_id)
    task_id = await queued(client, echo_plan())

    assert (await client.post(f"/tasks/{task_id}/run")).status_code == 200

    (selected,) = await written(ela, AuditEventType.DEVICE_SELECTED)
    assert selected.device_id == LOCAL_DEVICE_ID
    candidates = {candidate["device_id"]: candidate for candidate in selected.payload["candidates"]}
    for device_id in remote:
        assert "PRIVACY" in candidates[device_id]["refusals"]


async def test_a_revoked_node_is_refused_with_its_own_diagnosis(
    client: AsyncClient, ela: Ela
) -> None:
    """Criterion 9 (D13): enrolled, heard from, revoked — the run of production judges it and
    says ``REVOKED``, beside ``PRIVACY``, instead of forgetting it existed."""
    device_id, node = await enrolled(client, available_tools=[t.name for t in ela.tools.tools()])
    await client.post("/nodes/heartbeat", json={}, headers=node)
    await client.post(f"/nodes/{device_id}/revoke")
    task_id = await queued(client, echo_plan())

    await client.post(f"/tasks/{task_id}/run")

    (selected,) = await written(ela, AuditEventType.DEVICE_SELECTED)
    refusals = {c["device_id"]: c["refusals"] for c in selected.payload["candidates"]}[device_id]
    assert "REVOKED" in refusals
    assert "PRIVACY" in refusals


# ----------------------------------------------------------------------------------------
# Revocation (criterion 10), the revision (criterion 11), what a node may write (criterion 13)
# ----------------------------------------------------------------------------------------


async def test_a_revocation_keeps_the_row_and_closes_the_door(
    client: AsyncClient, anonymous: AsyncClient, ela: Ela
) -> None:
    """Criterion 10: the row stays with ``revoked_at``; the secret gets the ``401`` of nothing;
    the audit says ``DEVICE_REVOKED`` and then ``DEVICE_REJECTED`` ``revoked``; a second
    revocation writes nothing; ``local`` is refused."""
    device_id, node = await enrolled(client)
    await client.post("/nodes/heartbeat", json={}, headers=node)

    revoked = await client.post(f"/nodes/{device_id}/revoke")

    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None
    kept = await row(client, device_id)
    assert kept["revoked_at"] == revoked.json()["revoked_at"]
    assert kept["available"] is False
    refused = await client.post("/nodes/heartbeat", json={}, headers=node)
    assert refused.status_code == 401
    assert refused.json() == (await anonymous.get("/health")).json()
    kinds = [event.event_type for event in await ela.audit.read()]
    assert kinds.index(AuditEventType.DEVICE_REVOKED) < kinds.index(AuditEventType.DEVICE_REJECTED)
    (revocation,) = await written(ela, AuditEventType.DEVICE_REVOKED)
    (rejection,) = await written(ela, AuditEventType.DEVICE_REJECTED)
    assert revocation.actor == LOCAL_USER
    assert rejection.payload["reason"] == "revoked"

    count = len(await ela.audit.read())
    assert (await client.post(f"/nodes/{device_id}/revoke")).status_code == 200
    assert len(await ela.audit.read()) == count
    assert (await client.post(f"/nodes/{LOCAL_DEVICE_ID}/revoke")).status_code == 409


async def test_a_stale_revision_is_refused_as_a_conflict_of_identity(
    client: AsyncClient, ela: Ela
) -> None:
    """Criterion 11 at the route; the race itself is held with two real connections below it
    (``tests/infrastructure/persistence/test_device_registry.py``)."""
    device_id, node = await enrolled(client)
    first = await client.put(
        "/nodes/me", json={**DECLARATION, "name": "first"}, headers={**node, "If-Match": '"1"'}
    )
    second = await client.put(
        "/nodes/me", json={**DECLARATION, "name": "second"}, headers={**node, "If-Match": '"1"'}
    )

    assert first.status_code == 200
    assert first.headers["ETag"] == '"2"'
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "identity_conflict"
    assert (await row(client, device_id))["name"] == "first"
    (conflict,) = await written(ela, AuditEventType.DEVICE_IDENTITY_CONFLICT)
    assert str(conflict.device_id) == device_id


@pytest.mark.parametrize(
    "field",
    [{"privacy": "LOCAL_ONLY"}, {"network": "LOCAL"}, {"revoked_at": None}, {"revision": 7}],
    ids=["privacy", "network", "revoked_at", "revision"],
)
async def test_a_node_cannot_write_what_it_does_not_declare(
    client: AsyncClient, field: dict[str, Any]
) -> None:
    """Criterion 13: ``422``, and the row does not move — not even the declared half sent beside."""
    device_id, node = await enrolled(client)
    before = await row(client, device_id)

    response = await client.put(
        "/nodes/me",
        json={**DECLARATION, "name": "renamed", **field},
        headers={**node, "If-Match": "1"},
    )

    assert response.status_code == 422
    assert await row(client, device_id) == before


# ----------------------------------------------------------------------------------------
# What is written and what is counted (criterion 14)
# ----------------------------------------------------------------------------------------


async def test_only_a_refusal_that_names_an_existing_node_is_written(
    client: AsyncClient, anonymous: AsyncClient, ela: Ela
) -> None:
    """Criterion 14, in both directions: nothing presented, an unknown id and an invented code
    leave no row and are counted in ``/diagnostics``; a wrong secret for a known id is written."""
    device_id, _ = await enrolled(client)

    await anonymous.post("/nodes/heartbeat", json={})
    await anonymous.post(
        "/nodes/heartbeat", json={}, headers={"Authorization": f"Bearer {uuid.uuid4()}.nothing"}
    )
    await anonymous.post(
        "/nodes/enroll", json=DECLARATION, headers={"Authorization": "Bearer not-a-code"}
    )
    assert await written(ela, AuditEventType.DEVICE_REJECTED) == []

    await anonymous.post(
        "/nodes/heartbeat", json={}, headers={"Authorization": f"Bearer {device_id}.wrong"}
    )

    (rejected,) = await written(ela, AuditEventType.DEVICE_REJECTED)
    assert dict(rejected.payload) == {"reason": "bad_secret", "named_device_id": device_id}
    refused = (await client.get("/diagnostics")).json()["refused"]
    assert refused == {"missing": 1, "unknown_node": 1, "unknown_code": 1}


# ----------------------------------------------------------------------------------------
# The refusals a race or a broken node reaches
# ----------------------------------------------------------------------------------------


async def test_an_expired_code_gets_the_401_of_an_unknown_one_and_is_counted(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The expiry itself is held below the route, where a clock can be moved; this holds what the
    route does with it — the same ``401``, counted as anonymous and not written."""

    async def expired(self: NodeEnrollment, code: str, **declared: Any) -> Any:
        raise EnrollmentExpiredError(datetime.now(UTC))

    monkeypatch.setattr(NodeEnrollment, "enroll", expired)

    response = await enroll(client, "a-code-past-its-expiry")

    assert response.status_code == 401
    assert (await client.get("/diagnostics")).json()["refused"] == {"expired_code": 1}


async def test_a_node_revoked_after_the_middleware_let_it_in_gets_the_same_401(
    client: AsyncClient, anonymous: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The revocation lands between the middleware's check and the conditional ``UPDATE``, which
    carries ``revoked_at IS NULL`` for exactly this (ADR 0037 §12): the answer is the one the
    middleware would have given a moment later."""
    _, node = await enrolled(client)

    async def revoked_meanwhile(self: DeviceRegistry, device_id: Any, **declared: Any) -> Any:
        raise DeviceRevokedError(device_id, datetime.now(UTC))

    monkeypatch.setattr(DeviceRegistry, "announce", revoked_meanwhile)

    response = await client.put("/nodes/me", json=DECLARATION, headers={**node, "If-Match": "1"})

    assert response.status_code == 401
    assert response.json() == (await anonymous.get("/health")).json()


async def test_an_if_match_that_is_not_a_revision_is_refused(client: AsyncClient) -> None:
    _, node = await enrolled(client)

    response = await client.put(
        "/nodes/me", json=DECLARATION, headers={**node, "If-Match": 'W/"abc"'}
    )

    assert response.status_code == 422
    assert "If-Match" in response.json()["error"]["message"]
