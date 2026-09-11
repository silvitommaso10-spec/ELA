"""The routes of the nodes: enrolled, heard from, announced, revoked (M12.1; ADR 0037 §4).

Five routes. Two are the Core's — issuing a code and revoking a node — and three are called by the
nodes themselves, each by the one identity the middleware lets through there: the code on
``POST /nodes/enroll``, the node on ``POST /nodes/heartbeat`` and ``PUT /nodes/me``. No id in the
paths of a node: the identity *is* the id, a node speaks only for itself, and "the id in the path
is not the credential's" is a class of error that does not exist (ADR 0037 §4).

The announcement is conditional on the revision the node last saw, and the revision travels as
HTTP's own condition: ``If-Match`` in, ``ETag`` out, ``412`` when it does not match and ``428``
when it is missing — never in the body, where ``revision`` is a field the node may not write
(criterion 13; ADR 0037 §9).
"""

from __future__ import annotations

import re
from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse

from ela.api.deps import ElaDep, IdentityDep
from ela.api.errors import RevisionRequiredError
from ela.api.schemas import (
    DeclarationIn,
    DeviceOut,
    EnrolledOut,
    EnrollmentCodeOut,
    EnrollmentIn,
    HeartbeatIn,
)
from ela.api.security import Anonymous, count, unauthorized
from ela.composition import Ela
from ela.domain import Device, DeviceId
from ela.ports import (
    DeviceRevokedError,
    EnrollmentConsumedError,
    EnrollmentExpiredError,
    NotFoundError,
)

__all__ = ["router"]

router = APIRouter(prefix="/nodes", tags=["nodes"])

REVISION: Final = re.compile(r'^"?(\d+)"?$')
"""``If-Match: "3"`` or ``If-Match: 3``: an entity tag that is a revision number."""


@router.post("/enrollments", status_code=201)
async def issue_code(body: EnrollmentIn, ela: ElaDep) -> EnrollmentCodeOut:
    """A one-shot code that will impose ``privacy`` on the node that presents it (ADR 0037 §5).

    Answered once, kept as its hash. Nothing is audited: a code that expires unused changes
    nothing in ELA's world, and the admission is one fact, written when it happens (§13).
    """
    issued = await ela.enrollment.issue(body.privacy)
    return EnrollmentCodeOut(code=issued.code, privacy=issued.privacy, expires_at=issued.expires_at)


@router.post("/enroll", status_code=201, response_model=EnrolledOut)
async def enroll(
    body: DeclarationIn, request: Request, ela: ElaDep, identity: IdentityDep
) -> EnrolledOut | JSONResponse:
    """Spend the code the middleware let through, and give birth to the node (ADR 0037 §5).

    A code that cannot be spent gets the same ``401`` as a credential nobody knows. An unknown or
    expired one is anonymous and counted; one already spent is written by the registry as
    ``DEVICE_REJECTED`` ``code_reused``, naming the node it gave birth to.
    """
    assert identity.code is not None  # the middleware lets only a code through here
    try:
        enrolled = await ela.enrollment.enroll(identity.code, **body.declared())
    except NotFoundError:
        return count(request, Anonymous.UNKNOWN_CODE)
    except EnrollmentExpiredError:
        return count(request, Anonymous.EXPIRED_CODE)
    except EnrollmentConsumedError:
        return unauthorized()
    return EnrolledOut(
        device_id=enrolled.device.id, secret=enrolled.secret, revision=enrolled.device.revision
    )


@router.post("/heartbeat")
async def heartbeat(body: HeartbeatIn, ela: ElaDep, identity: IdentityDep) -> DeviceOut:
    """A sign of life, with what the node reports of itself — and no event (ADR 0016 §6)."""
    device = await ela.devices.heartbeat(
        identity.node,
        status=body.status,
        current_workload=body.current_workload,
        power_source=body.power_source,
    )
    return await _judged(ela, device)


@router.put("/me", response_model=DeviceOut)
async def announce(
    body: DeclarationIn,
    response: Response,
    ela: ElaDep,
    identity: IdentityDep,
    if_match: Annotated[str | None, Header()] = None,
) -> DeviceOut | JSONResponse:
    """The node rewrites the half it declares, at the revision it last saw (ADR 0037 §9).

    ``412`` — the precondition of ``If-Match`` failed — and ``DEVICE_IDENTITY_CONFLICT`` if the
    revision is stale; the new one comes back as the ``ETag``. A node revoked after the middleware
    let it through gets the same ``401``.
    """
    expected = _revision(if_match)
    try:
        device = await ela.devices.announce(
            identity.node,
            **body.declared(),
            expected_revision=expected,
        )
    except DeviceRevokedError:
        return unauthorized()
    response.headers["ETag"] = f'"{device.revision}"'
    return await _judged(ela, device)


@router.post("/{device_id}/revoke")
async def revoke(device_id: UUID, ela: ElaDep, identity: IdentityDep) -> DeviceOut:
    """Revoke a node: the row stays, and its secret opens nothing (ADR 0037 §12)."""
    device = await ela.devices.revoke(DeviceId(device_id), by=identity.actor)
    return await _judged(ela, device)


async def _judged(ela: Ela, device: Device) -> DeviceOut:
    """``device`` with ``available`` answered by the registry, never read off the row (rule 20)."""
    usable = {one.id for one in await ela.devices.available()}
    return DeviceOut.of(device, available=device.id in usable)


def _revision(header: str | None) -> int:
    """The revision ``If-Match`` carries (ADR 0037 §9)."""
    if header is None:
        raise RevisionRequiredError()
    match = REVISION.match(header.strip())
    if match is None:
        raise ValueError("If-Match must carry the revision this node last saw, as a number")
    return int(match.group(1))
