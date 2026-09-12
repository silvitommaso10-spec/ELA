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

import asyncio
import re
from contextlib import suppress
from datetime import timedelta
from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse

from ela.api.deps import ElaDep, IdentityDep, RunningDep
from ela.api.errors import RevisionRequiredError, TaskAlreadyRunningError
from ela.api.schemas import (
    DeclarationIn,
    DeliveredOut,
    DeviceOut,
    EnrolledOut,
    EnrollmentCodeOut,
    EnrollmentIn,
    HeartbeatIn,
    RenewedOut,
    WorkOrderOut,
    WorkRenewIn,
    WorkResultIn,
)
from ela.api.security import Anonymous, count, unauthorized
from ela.composition import Ela
from ela.domain import Assignment, AssignmentId, Device, DeviceId, TaskId
from ela.executive import Claimed
from ela.ports import (
    AssignmentNotUsableError,
    DeviceRevokedError,
    EnrollmentConsumedError,
    EnrollmentExpiredError,
    NotFoundError,
)

__all__ = ["WORK_REREAD_INTERVAL", "router", "work_order"]

router = APIRouter(prefix="/nodes", tags=["nodes"])

REVISION: Final = re.compile(r'^"?(\d+)"?$')
"""``If-Match: "3"`` or ``If-Match: 3``: an entity tag that is a revision number."""

WORK_REREAD_INTERVAL: Final = timedelta(seconds=1)
"""How often a held request for work reads the service again (ADR 0038 §11).

Declared and to be reviewed with real nodes: it is the best case of the latency a node sees, and
the worst case is its own polling cycle. A constant and not a variable because two knobs for one
wait would let them contradict each other.
"""


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


@router.post("/work", response_model=WorkOrderOut)
async def take_work(
    request: Request, ela: ElaDep, identity: IdentityDep, running: RunningDep
) -> WorkOrderOut | Response:
    """A node asks for work, and holds the request until there is some (ADR 0038 §11).

    ``POST`` and not ``GET`` because it **takes**: a request that moves a row from offered to taken
    is not a read. Inside the window the service is reread every
    :data:`WORK_REREAD_INTERVAL` — not a channel in memory woken by the executor, which would be
    state of the transport held in one process's memory and would tie ``ela.executive`` to
    ``ela.api``. It degrades into polling by itself: a connection that drops, or a ``204``, and the
    node asks again. The latency is the polling interval, and nothing here promises a third thing.

    Between two rereads it waits on ``app.state.stopping`` rather than sleeping, so a process being
    stopped answers "no work" at the instant of the signal and the node retries against the ELA that
    comes back (dec. I). The clock of the window is the loop's, not the injected one: how long a
    request is held is wall time, while the :class:`~ela.ports.Clock` is for facts that get written.
    """
    stopping: asyncio.Event = request.app.state.stopping
    loop = asyncio.get_running_loop()
    deadline = loop.time() + ela.settings.core.node_poll.total_seconds()
    reread = WORK_REREAD_INTERVAL.total_seconds()
    while True:
        order = await _taken(ela, identity.node, running)
        if order is not None:
            return order
        left = deadline - loop.time()
        if stopping.is_set() or left <= 0:
            return Response(status_code=204)
        with suppress(TimeoutError):
            await asyncio.wait_for(stopping.wait(), timeout=min(left, reread))


@router.post("/work/result")
async def deliver_work(
    body: WorkResultIn, ela: ElaDep, identity: IdentityDep, running: RunningDep
) -> DeliveredOut:
    """A node brings the work back (ADR 0038 §12). The id is in the body, never in the path.

    Under the lock of the task, because a claim, a delivery and a ``run`` of the user are three
    callers of the executor on one step and the executor has no lock of its own (ADR 0015 §8). With
    the lock taken the answer is the ``409`` of a refused ``run``, **and nothing is written**: it is
    a "not now" and not a "no", which is the case the node keeps the envelope for (D7).

    Every other answer is the executor's refusal, translated and never re-worded: ``404`` for work
    this node does not hold, ``409`` for a second envelope, ``410`` for a late one or a task that
    closed. The reason reaches the audit as a ``DEVICE_REJECTED`` of the way of the work.
    """
    assignment_id = AssignmentId(body.assignment_id)
    held = await _known(ela, assignment_id)
    if held is None:
        # An id the Core never minted: there is no task to lock, and the refusal — with its
        # ``DEVICE_REJECTED`` — is the executor's (ADR 0038 §12).
        return await _delivered(ela, assignment_id, identity.node, body)
    if held.task_id in running:
        raise TaskAlreadyRunningError(held.task_id)
    running.add(held.task_id)
    try:
        return await _delivered(ela, assignment_id, identity.node, body)
    finally:
        running.discard(held.task_id)


@router.post("/work/renew")
async def renew_work(body: WorkRenewIn, ela: ElaDep, identity: IdentityDep) -> RenewedOut:
    """A tool working longer than the TTL asks for more time (ADR 0038 §13).

    No lock: the writes are a ``HEARTBEAT`` and a conditional ``UPDATE`` that excludes itself by
    the expiry. At the cap ``409`` and the work expires when it says; an offer is ``404``, like
    work that is not yours, and expired work is ``410``.
    """
    work = await ela.assignments.renew(AssignmentId(body.assignment_id), identity.node)
    return RenewedOut(assignment_id=work.id, expires_at=work.expires_at)


@router.post("/{device_id}/revoke")
async def revoke(device_id: UUID, ela: ElaDep, identity: IdentityDep) -> DeviceOut:
    """Revoke a node: the row stays, its secret opens nothing, and its work is over (§12; D17).

    Two writes, in this order: the revocation, then the expiry of every live assignment of that
    node — the offers it can no longer take as well as the work it took. The Core does not push
    (D4), so this is what "revoked" does to work already out: it brings the expiry to **now**,
    and the next ``run`` applies the answer of D14 instead of waiting out the TTL. A death between
    the two is repaired by revoking again (window ``A14``), which is why the cut runs on the
    already-revoked branch too.
    """
    device = await ela.devices.revoke(DeviceId(device_id), by=identity.actor)
    await ela.assignments.cut_short(device.id)
    return await _judged(ela, device)


async def _delivered(
    ela: Ela, assignment_id: AssignmentId, device_id: DeviceId, body: WorkResultIn
) -> DeliveredOut:
    """Hand the envelope to the executor and say where the work and the step stand."""
    delivered = await ela.executor.deliver(assignment_id, device_id, body.envelope())
    return DeliveredOut(
        assignment_id=delivered.assignment.id,
        state=delivered.assignment.state.value,
        step=delivered.step_state.value,
    )


async def _known(ela: Ela, assignment_id: AssignmentId) -> Assignment | None:
    """The work this delivery claims to be about, for the lock; ``None`` if the Core minted no such
    id — the refusal of that case is the executor's, with its ``DEVICE_REJECTED`` behind it."""
    try:
        return await ela.assignments.held(assignment_id)
    except NotFoundError:
        return None


async def _taken(ela: Ela, device_id: DeviceId, running: set[TaskId]) -> WorkOrderOut | None:
    """One attempt at taking the oldest offer for this node, or ``None`` to try again later.

    ``None`` for all three ways an attempt comes to nothing: nothing is offered, the task is busy
    — the lock, skipped for this reread rather than refused — and the offer stopped being takeable
    between the read and the claim, which is the race two nodes of one user can lose honestly.
    """
    offer = await ela.assignments.next_for(device_id)
    if offer is None or offer.task_id in running:
        return None
    running.add(offer.task_id)
    try:
        claimed = await ela.executor.begin(offer.id, device_id)
    except (AssignmentNotUsableError, NotFoundError):
        return None
    finally:
        running.discard(offer.task_id)
    return work_order(claimed, device_id)


def work_order(claimed: Claimed, device_id: DeviceId) -> WorkOrderOut:
    """The order of a claim, composed here and nowhere else (architecture rule 51).

    One module builds it and that module imports no network client, so the only way out of an order
    is the answer to the request of the node that claimed it. The identity is compared rather than
    trusted (criterion 21): an order for another node is a programming error, and it raises instead
    of being sent — which is the half of the rule an AST cannot see.
    """
    if claimed.assignment.device_id != device_id:
        raise ValueError(
            f"assignment {claimed.assignment.id} belongs to another node: an order goes only to "
            "the node it was handed to"
        )
    return WorkOrderOut(
        assignment_id=claimed.assignment.id,
        capability_id=claimed.assignment.decision.capability_id,
        tool_name=claimed.tool_name,
        decision=claimed.assignment.decision,
        arguments=claimed.arguments,
        expires_at=claimed.assignment.expires_at,
    )


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
