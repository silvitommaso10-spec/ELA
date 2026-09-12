"""The Device Registry: which nodes exist, and which of them answered recently (§16, ADR 0016).

:class:`~ela.ports.DeviceRegistryPort` is storage — add a node, replace a node, read nodes. What
it cannot answer is the question §16 actually asks, "posso usarlo *adesso*": a stored
``availability`` says what was true when someone last wrote it, and keeps saying it after the node
has gone quiet. :class:`DeviceRegistry` puts the missing half on top of the port: a ``heartbeat``
that records a sign of life, and a deadline that turns silence into ``UNAVAILABLE`` **as the node
is read**, so no reader can be told a stale node is reachable because no sweeper has run yet
(ADR 0016 §3; §33: in doubt, no).

The vocabulary of §16 is AVAILABLE/UNAVAILABLE; the domain's is
:class:`~ela.domain.DeviceAvailability`. :data:`AVAILABLE` and :data:`UNAVAILABLE` are the mapping,
in one place: a fresh heartbeat is evidence the node answers (``ONLINE``), silence past the TTL is
evidence of nothing (``UNREACHABLE``) — not of ``OFFLINE``, which would claim the node is down
when all we know is that it stopped talking to us.

Since M6.1b the registry also **writes**, and therefore audits (ADR 0035 §3). ``ensure_local`` no
longer returns whatever row it finds: it reconciles the declared half of that row with what the
caller declares, so a capability added after the first start becomes runnable at the next one and
a capability withdrawn stops being runnable at the same one. A registration and a refresh are
configuration changes — which machines ELA may use, with which tools — and §32 wants them
readable: whoever investigates an action must be able to reconstruct which nodes could do what
*then*. The heartbeat stays out of the log, as ADR 0016 §6 decided: a sign of life is not an act.

Since M12.1 a node can also enter from the network and speak for itself (ADR 0037). Each half of
its row has its own write (§9, §10): the node announces its declared half at the revision it last
saw, the heartbeat writes only what it observed, the user revokes. The registry audits all five
facts of an identity — enrolled, announced, in conflict, rejected, revoked — and never a secret,
a code or a hash (architecture rule 46).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from enum import StrEnum, auto
from typing import Any, Final

from ela.devices.errors import (
    LocalDeviceNotRevocableError,
)
from ela.devices.local import (
    LOCAL_DEVICE_ID,
    local_device,
)
from ela.devices.refresh import DECLARED_FIELDS, changes, difference, refreshed, tool_names
from ela.domain import (
    Actor,
    ActorKind,
    AuditEvent,
    AuditEventId,
    AuditEventType,
    Device,
    DeviceAvailability,
    DeviceCapability,
    DeviceId,
    DeviceStatus,
    JsonValue,
    NetworkKind,
    OperatingSystem,
    PerformanceClass,
    PowerSource,
    PrivacyLevel,
)
from ela.ports import (
    AlreadyExistsError,
    AuditLog,
    Clock,
    DeviceRegistryPort,
    IdentityConflictError,
    IdGenerator,
    NotFoundError,
)

__all__ = [
    "AVAILABLE",
    "REGISTRY_ACTOR",
    "UNAVAILABLE",
    "DeviceRegistry",
    "is_available",
    "Rejection",
]

REGISTRY_ACTOR: Final = Actor(kind=ActorKind.SYSTEM, id="device-registry")
"""Who signs a registration: nobody asked for it, ELA writes down the machine it is running on.

The same actor kind the orchestrator uses for a placement (§32). Not ``DEVICE``: that one is for a
node that announces *itself* over the network, and the day it exists it will sign its own row —
which is the identity ADR 0035 §5 says has to be proved before it may."""

AVAILABLE: Final = DeviceAvailability.ONLINE
"""§16 "disponibile": the node answered within the TTL."""

UNAVAILABLE: Final = DeviceAvailability.UNREACHABLE
"""§16 "non disponibile": no sign of life within the TTL. Not ``OFFLINE`` — see the module doc."""


class Rejection(StrEnum):
    """Why a request that named a node that exists was refused (ADR 0037 §13): what is written.

    The four reasons **of identity** ``DEVICE_REJECTED`` carries, each valued as its name in lower
    case — how ADR 0037 §13 writes them, and what ``StrEnum``'s ``auto`` gives. A request naming
    nothing — no credential, an unknown id, an unknown or unspent-and-expired code — has no reason
    here: it is anonymous, and the 401 already says all there is to say.

    Since M12.2 the same event type has a **second writer** with a vocabulary of its own: the way of
    the work refuses a delivery or a renewal for reasons that are not about identity — late, the
    task closed, not this node's work, a second envelope — and those live beside their writer, in
    :class:`~ela.executive.assignments.WorkRejection` (ADR 0038 §12). One type, two writers, and
    this enum stays closed at the four it was born with.
    """

    BAD_SECRET = auto()
    """The secret presented is not the one kept for the id the request names."""
    REVOKED = auto()
    """The node was revoked: the same 401 as a wrong secret, and this reason in the audit."""
    ROUTE_NOT_ALLOWED = auto()
    """A node on a route outside its list (ADR 0037 §4)."""
    CODE_REUSED = auto()
    """A code already spent, presented again: it names the node it gave birth to."""


def _node(device_id: DeviceId) -> Actor:
    """The node as the signer of its own row (ADR 0035 §3): ``DEVICE``, with its own id."""
    return Actor(kind=ActorKind.DEVICE, id=str(device_id))


def is_available(device: Device, now: datetime, ttl: timedelta) -> bool:
    """Whether ``device`` answered recently enough to be used at ``now``.

    A node never seen (``last_seen_at is None``) is **not** available: registering a node is a
    statement that it exists, not that it answers (§33). The deadline is closed, like every
    deadline in the system (ADR 0005 §2-bis): at exactly ``last_seen_at + ttl`` it has passed.
    """
    return device.last_seen_at is not None and now < device.last_seen_at + ttl


def _with(device: Device, changes: Mapping[str, Any]) -> Device:
    """``device`` with ``changes`` applied, **revalidated**.

    ``model_copy(update=...)`` skips validation, so it alone would let a caller's
    ``current_workload=7.5`` into the registry past the domain's ``0.0..1.0``.
    """
    return Device.model_validate({**device.model_dump(), **changes})


def _strings(values: Iterable[str]) -> list[JsonValue]:
    """A list of strings as JSON data: ``list`` is invariant, so the payload needs the widening."""
    return list(values)


def _listed(names: Iterable[str]) -> str:
    """Names for a summary, and a word rather than an empty space when there are none."""
    return ", ".join(names) or "no tools"


class DeviceRegistry:
    """The nodes ELA can use, with the heartbeat deadline applied on every read.

    Not an implementation of :class:`~ela.ports.DeviceRegistryPort` and not usable as one: it
    *holds* a port and answers a different question. The port returns the row as stored; this
    returns the node as it is now.
    """

    __slots__ = ("_audit", "_clock", "_devices", "_ids", "_ttl")

    def __init__(
        self,
        devices: DeviceRegistryPort,
        clock: Clock,
        audit: AuditLog,
        ids: IdGenerator,
        *,
        heartbeat_ttl: timedelta,
    ) -> None:
        if heartbeat_ttl <= timedelta(0):
            raise ValueError(f"the heartbeat TTL must be positive, not {heartbeat_ttl}")
        self._devices = devices
        self._clock = clock
        self._audit = audit
        self._ids = ids
        self._ttl = heartbeat_ttl

    @property
    def heartbeat_ttl(self) -> timedelta:
        """How long a heartbeat keeps a node available."""
        return self._ttl

    def seen(self, device: Device, now: datetime) -> Device:
        """``device`` with ``availability`` answered from its last heartbeat, not from the row."""
        availability = AVAILABLE if is_available(device, now, self._ttl) else UNAVAILABLE
        return device.model_copy(update={"availability": availability})

    async def register(self, device: Device) -> Device:
        """Add a node and return it as it reads; :class:`AlreadyExistsError` if the id is taken.

        A node is registered ``UNAVAILABLE``, whatever the caller declared: nothing has been
        heard from it yet.

        Audited as ``DEVICE_REGISTERED`` — "a machine entered ELA's world" — and audited *after*
        the port answered, so a refused insert leaves no event about a node that was not added
        (ADR 0035 §3).
        """
        await self._devices.register(device)
        await self._audit.append(
            self._event(
                AuditEventType.DEVICE_REGISTERED,
                device,
                summary=(
                    f"node {device.name} ({device.id}) registered on {device.os.value} "
                    f"with {_listed(device.available_tools)}"
                ),
                changed=DECLARED_FIELDS,
                added=device.available_tools,
                removed=(),
            )
        )
        return self.seen(device, self._clock.now())

    async def update(self, device: Device) -> Device:
        """Replace a registered node — a configuration change; :class:`NotFoundError` if unknown.

        Not the way to report a sign of life: that is ``heartbeat``.
        """
        await self._devices.update(device)
        return self.seen(device, self._clock.now())

    async def get(self, device_id: DeviceId) -> Device:
        """The node with this id, as it is now; :class:`NotFoundError` if there is none."""
        return self.seen(await self._devices.get(device_id), self._clock.now())

    async def devices(self) -> tuple[Device, ...]:
        """Every node, in registration order, all judged against the same instant."""
        now = self._clock.now()
        return tuple(self.seen(device, now) for device in await self._devices.devices())

    async def available(self) -> tuple[Device, ...]:
        """The nodes whose last heartbeat is still worth something, in registration order.

        The question "which nodes can ELA use right now" belongs here, where availability is
        derived (ADR 0016 §3): a caller that filtered on the field itself would be reading a
        column that keeps saying ``AVAILABLE`` after a node went quiet — which is what
        architecture rule 20 exists to prevent.

        A revoked node is not among them, whatever its last heartbeat says (M12.1, ADR 0037 §12):
        "posso usarlo adesso" has one answer for a node the user revoked. The condition is read here
        and **not** in :meth:`seen`, whose ``availability`` stays the fact of the heartbeat — the
        one the orchestrator's ``UNAVAILABLE`` speaks of — so a revoked node with a fresh heartbeat
        is diagnosed ``REVOKED`` and not ``UNAVAILABLE``. Two facts, two names.
        """
        return tuple(
            device
            for device in await self.devices()
            if device.availability is AVAILABLE and device.revoked_at is None
        )

    async def heartbeat(
        self,
        device_id: DeviceId,
        *,
        status: DeviceStatus | None = None,
        current_workload: float | None = None,
        power_source: PowerSource | None = None,
    ) -> Device:
        """Record a sign of life from a node, optionally with what it reports of itself (§16).

        ``status``, ``current_workload`` and ``power_source`` are the node's own report — written
        by the registry, not guaranteed by it (ADR 0037 §10) — and are written only when given: a
        heartbeat that says nothing about them must not erase what was known.

        One statement on the observed columns (ADR 0037 §9), no longer a read-modify-write of the
        whole row (ADR 0016 §5): an announcement racing with a heartbeat cannot be lost to it. The
        row is read first only to hold what the node reported against the domain — a workload of
        ``7.5`` is refused before anything is written — and nothing of what was read is written:
        what comes back is this heartbeat's observation over the row as it was read.

        :raises NotFoundError: if the node is not registered. A heartbeat never registers one:
            a node enters by an enrollment (ADR 0037 §5) or, for ``local``, by ``ensure_local``.
        """
        now = self._clock.now()
        reported: dict[str, Any] = {}
        if status is not None:
            reported["status"] = status
        if current_workload is not None:
            reported["current_workload"] = current_workload
        if power_source is not None:
            reported["power_source"] = power_source
        observed = _with(
            await self._devices.get(device_id),
            {**reported, "last_seen_at": now, "availability": AVAILABLE},
        )
        await self._devices.observe(
            device_id,
            seen_at=now,
            availability=AVAILABLE,
            status=status,
            current_workload=current_workload,
            power_source=power_source,
        )
        return self.seen(observed, now)

    async def secret_hash(self, device_id: DeviceId) -> str | None:
        """The hash a node proves itself against, ``None`` for ``local`` (ADR 0037 §6).

        The one way the hash leaves the registry, and it goes to the comparison in
        ``api/security.py``, the only module that compares a credential (architecture rule 31).

        :raises NotFoundError: if the node is not registered.
        """
        return await self._devices.secret_hash(device_id)

    async def enroll(
        self,
        device_id: DeviceId,
        *,
        name: str,
        os: OperatingSystem,
        capabilities: tuple[DeviceCapability, ...],
        available_tools: tuple[str, ...],
        performance: PerformanceClass,
        privacy: PrivacyLevel,
        secret_hash: str,
        by: Actor,
        issued_at: datetime,
    ) -> Device:
        """A node born from a code: the row, its hash, and ``DEVICE_ENROLLED`` (ADR 0037 §5).

        The node gives the half it declares; the rest is not its to give. ``privacy`` is the code's
        — the user imposed it — and ``network`` is the registry's, ``REMOTE`` for every node that
        enters from the API (§10). Revision 1, never seen and therefore not available: enrolling a
        node says that it exists, not that it answers (ADR 0016 §3).

        Audited after the port answered, so a refused insert leaves no event about a node that was
        not added; signed by ``by``, the identity that issued the code (D12). The summary says what
        the node declared, the level imposed, and when the code was issued — never the code, the
        secret or a hash.
        """
        device = Device(
            id=device_id,
            created_at=self._clock.now(),
            name=name,
            os=os,
            availability=UNAVAILABLE,
            status=DeviceStatus.UNKNOWN,
            capabilities=capabilities,
            available_tools=available_tools,
            performance=performance,
            network=NetworkKind.REMOTE,
            power_source=PowerSource.UNKNOWN,
            privacy=privacy,
            revision=1,
        )
        await self._devices.enroll(device, secret_hash=secret_hash)
        await self._audit.append(
            self._event(
                AuditEventType.DEVICE_ENROLLED,
                device,
                actor=by,
                summary=(
                    f"node {device.name} ({device.id}) enrolled on {device.os.value} with "
                    f"{_listed(device.available_tools)}, privacy {device.privacy.value}, by a "
                    f"code issued at {issued_at.isoformat()}"
                ),
                changed=DECLARED_FIELDS,
                added=device.available_tools,
                removed=(),
            )
        )
        return self.seen(device, self._clock.now())

    async def announce(
        self,
        device_id: DeviceId,
        *,
        name: str,
        os: OperatingSystem,
        capabilities: tuple[DeviceCapability, ...],
        available_tools: tuple[str, ...],
        performance: PerformanceClass,
        expected_revision: int,
    ) -> Device:
        """A node rewrites the half it declares, at the revision it last saw (ADR 0037 §9, §10).

        The five keywords are :data:`~ela.devices.refresh.DECLARED_FIELDS` and nothing else: what
        is not declared cannot be passed, so it cannot be written. The write is the port's
        conditional ``UPDATE``; the read before it only computes the difference for the audit,
        and the difference is exact because the declared half moves only with the revision the
        write checks.

        ``DEVICE_ANNOUNCED``, signed by the node itself, if something changed; nothing otherwise —
        the revision still moves, because the node is told the revision to use next.
        ``DEVICE_IDENTITY_CONFLICT`` if the revision is stale, and the error is raised on.

        :raises NotFoundError: if the node is not registered.
        :raises IdentityConflictError: if the row is not at ``expected_revision``.
        :raises DeviceRevokedError: if the node was revoked.
        """
        current = await self._devices.get(device_id)
        declared = refreshed(
            current,
            {
                "name": name,
                "os": os,
                "capabilities": capabilities,
                "available_tools": available_tools,
                "performance": performance,
            },
        )
        change = changes(current, declared)
        try:
            revision = await self._devices.announce(declared, expected_revision=expected_revision)
        except IdentityConflictError as conflict:
            await self._audit.append(
                self._fact(
                    AuditEventType.DEVICE_IDENTITY_CONFLICT,
                    device_id,
                    actor=_node(device_id),
                    summary=(
                        f"node {current.name} ({device_id}) announced itself at revision "
                        f"{conflict.expected}, but the row is at {conflict.actual}: two processes "
                        "claim to be it"
                    ),
                    payload={
                        "expected_revision": conflict.expected,
                        "actual_revision": conflict.actual,
                    },
                )
            )
            raise
        announced = declared.model_copy(update={"revision": revision})
        if change:
            added, removed = tool_names(current, declared)
            await self._audit.append(
                self._event(
                    AuditEventType.DEVICE_ANNOUNCED,
                    announced,
                    actor=_node(device_id),
                    summary=f"node {announced.name} ({device_id}) announced: "
                    f"{difference(current, change)}",
                    changed=tuple(change),
                    added=added,
                    removed=removed,
                )
            )
        return self.seen(announced, self._clock.now())

    async def revoke(self, device_id: DeviceId, *, by: Actor) -> Device:
        """Revoke a node: the row stays, marked, and its secret opens nothing (ADR 0037 §12).

        ``DEVICE_REVOKED``, signed by ``by``, the first time. Revoking it again answers the row as
        it is and writes nothing: repeating an identical answer is not an error (ADR 0023 §8).

        :raises LocalDeviceNotRevocableError: for ``local``, before anything is read or written.
        :raises NotFoundError: if the node is not registered.
        """
        if device_id == LOCAL_DEVICE_ID:
            raise LocalDeviceNotRevocableError(device_id)
        now = self._clock.now()
        revoked = await self._devices.revoke(device_id, at=now)
        device = await self._devices.get(device_id)
        if revoked:
            await self._audit.append(
                self._fact(
                    AuditEventType.DEVICE_REVOKED,
                    device_id,
                    actor=by,
                    summary=f"node {device.name} ({device_id}) revoked",
                    payload={"revoked_at": now.isoformat()},
                )
            )
        return self.seen(device, now)

    async def reject(self, device_id: DeviceId, reason: Rejection) -> None:
        """Write that a request naming ``device_id`` was refused, and why (ADR 0037 §13).

        Only for a node that exists: the read raises :class:`NotFoundError` otherwise, so no caller
        can put a row about a node nobody enrolled into the chain of §32. Signed ``SYSTEM`` — the
        Core decided — with the node in the payload as what the request named, not as the actor.
        """
        device = await self._devices.get(device_id)
        await self._audit.append(
            self._fact(
                AuditEventType.DEVICE_REJECTED,
                None,
                actor=REGISTRY_ACTOR,
                summary=(
                    f"a request naming node {device.name} ({device_id}) was refused: {reason.value}"
                ),
                payload={"reason": reason.value, "named_device_id": str(device_id)},
            )
        )

    async def ensure_local(
        self, *, system: str | None = None, available_tools: tuple[str, ...] = ()
    ) -> Device:
        """The ``local`` node, registered the first time and **reconciled** every time (§54).

        Until M6.1b this returned whatever row it found, and a row written before a capability
        existed kept saying so for ever: a step that needed the new tool answered
        ``waiting_device`` on an ELA that had been running, and ran on a fresh database. What
        ``ensure`` promises is to make something true, and it used to make only the existence
        true.

        So the caller hands in the truth and this reconciles: it reads the row, compares the
        declared half — what can be stated without probing the machine — and writes **only if it
        differs** (ADR 0035 §2). Nothing changed means nothing written: no ``UPDATE``, no event.

        Who declares and who decides stay apart. The caller says which tools exist, because which
        tools exist depends on a workspace root the registry has no business knowing (ADR 0016
        §4); the registry decides that the row must change, because architecture rules 20 and 21
        make it the only one that may read the row to find out.

        Idempotent by construction: the id is deterministic, so the second call finds the node the
        first one wrote — in this process or in the next one. The ``AlreadyExistsError`` branch is
        two callers racing between the read and the insert, and the loser reconciles what the
        winner wrote instead of failing.
        """
        declared = local_device(self._clock.now(), system=system, available_tools=available_tools)
        try:
            current = await self._devices.get(LOCAL_DEVICE_ID)
        except NotFoundError:
            try:
                return await self.register(declared)
            except AlreadyExistsError:
                current = await self._devices.get(LOCAL_DEVICE_ID)
        return await self._reconcile(current, declared)

    async def _reconcile(self, current: Device, declared: Device) -> Device:
        """Write ``declared``'s half of the row over ``current``'s, if the two disagree.

        ``current`` is the row **as stored**, read through the port and not through :meth:`get`:
        what is compared, and what is written back untouched, has to be what is on disk. A
        derived ``availability`` carried in here would be written into the column that must only
        ever hold what a heartbeat observed (ADR 0016 §3).

        The observed half is not named — :mod:`ela.devices.refresh` carries it through and
        architecture rule 44 keeps it that way — so a node that was available is still available
        the instant after this returns: an update whose purpose is to keep a node usable cannot be
        the thing that stops it being used.
        """
        change = changes(current, declared)
        if not change:
            return self.seen(current, self._clock.now())
        row = refreshed(current, change)
        await self._devices.update(row)
        added, removed = tool_names(current, declared)
        await self._audit.append(
            self._event(
                AuditEventType.DEVICE_REFRESHED,
                row,
                summary=f"node {row.name} ({row.id}) refreshed: {difference(current, change)}",
                changed=tuple(change),
                added=added,
                removed=removed,
            )
        )
        return self.seen(row, self._clock.now())

    def _event(
        self,
        event_type: AuditEventType,
        device: Device,
        *,
        summary: str,
        changed: Iterable[str],
        added: Iterable[str],
        removed: Iterable[str],
        actor: Actor = REGISTRY_ACTOR,
    ) -> AuditEvent:
        """An event about the declared half, with the whole difference in it (ADR 0035 §3)."""
        return self._fact(
            event_type,
            device.id,
            actor=actor,
            summary=summary,
            payload={
                "changed": _strings(changed),
                "tools_added": _strings(added),
                "tools_removed": _strings(removed),
            },
        )

    def _fact(
        self,
        event_type: AuditEventType,
        device_id: DeviceId | None,
        *,
        actor: Actor,
        summary: str,
        payload: dict[str, JsonValue],
    ) -> AuditEvent:
        """One event of the registry, signed by whoever the fact belongs to."""
        return AuditEvent(
            id=AuditEventId(self._ids.new_uuid()),
            created_at=self._clock.now(),
            event_type=event_type,
            actor=actor,
            summary=summary,
            device_id=device_id,
            payload=payload,
        )
