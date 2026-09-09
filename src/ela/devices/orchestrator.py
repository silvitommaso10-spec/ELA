"""The Device Orchestrator: which node runs a step, and why (§17; ADR 0017).

§13 forbids a plan from naming a node — a step declares *capabilities*, not a machine — and §17
gives the reason: **the task belongs to ELA, not to the device**. So the choice cannot be in the
plan, and it must not be improvised at the point of execution either: it lives here, as one
explicit function that can be read, tested row by row and argued with.

The decision has two halves that never mix:

* **Eligibility** (:func:`refusals`) is a set of hard filters. A node that fails one is discarded
  and can never be chosen, whatever else it offers — availability, privacy and "somebody can
  actually run this" are questions where a wrong yes is unsafe (§33).
* **Score** (:func:`score`) ranks the nodes that passed. It is a sum of small integers, one per
  criterion of §17, and it can only reorder eligible nodes: no amount of points rescues a refused
  one. Integers, not floats, because two almost-equal floats are not a deterministic tie.

Availability is read from :class:`~ela.devices.registry.DeviceRegistry`, never from the stored
column: the registry answers "does it answer *now*" from the last heartbeat, and the row would
answer "it answered once" (ADR 0016 §3). This module is the second reader of
:class:`~ela.ports.DeviceRegistryPort` and the first with a motive to trust that column, which is
why M6.2 turns the convention into architecture rules 20 and 21.

When no node is eligible the answer is a :class:`Placement` with no device, never an exception:
the orchestrator only advises. It cannot fail a task even by accident, because it cannot reach
the Task Engine at all — ``ela.devices`` does not import ``ela.tasks``, and rule 22 keeps it so.
What the caller must do with an empty placement is fixed by ADR 0017 §6: the task stays
``QUEUED`` and the wait is already in the audit log.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final, NamedTuple

from ela.devices.errors import NotPlacedError
from ela.devices.registry import AVAILABLE, DeviceRegistry
from ela.domain import (
    Actor,
    ActorKind,
    AuditEvent,
    AuditEventId,
    AuditEventType,
    CapabilityId,
    Device,
    DeviceCapabilityName,
    DeviceId,
    DeviceStatus,
    JsonValue,
    NetworkKind,
    PerformanceClass,
    PowerSource,
    PrivacyLevel,
    RiskLevel,
    StepId,
    TaskId,
    TaskStep,
)
from ela.ports import AuditLog, Clock, IdGenerator, NotFoundError, ToolRegistryPort

__all__ = [
    "NETWORK_POINTS",
    "ORCHESTRATOR_ACTOR",
    "PERFORMANCE_POINTS",
    "POWER_POINTS",
    "PRIVACY_ORDER",
    "STATUS_POINTS",
    "TRAIT_POINTS",
    "UNGUARDED_RISK",
    "WORKLOAD_POINTS",
    "DeviceOrchestrator",
    "Placement",
    "PlacementDecision",
    "Refusal",
    "Requirements",
    "Score",
    "choose",
    "ensure_placed",
    "refusals",
    "score",
]

ORCHESTRATOR_ACTOR: Final = Actor(kind=ActorKind.SYSTEM, id="device-orchestrator")
"""Who signs a placement: nobody asked for it, ELA decides where to run its own work (§32)."""

PRIVACY_ORDER: Final[Mapping[PrivacyLevel, int]] = MappingProxyType(
    {
        PrivacyLevel.LOCAL_ONLY: 0,
        PrivacyLevel.TRUSTED: 1,
        PrivacyLevel.CLOUD_ALLOWED: 2,
    }
)
"""How far data may travel from a node, least to most permissive (§16, §57; ADR 0017 §5).

Not comparison operators on :class:`~ela.domain.PrivacyLevel` itself, as :class:`RiskLevel` has:
risk is compared by the catalogue, the Guardian and the executor, privacy by this module alone,
and ADR 0003 keeps the domain minimal. A second comparer promotes this table to the domain.
"""

UNGUARDED_RISK: Final = RiskLevel.HIGH
"""From this level up a node that reports itself DEGRADED is not eligible (ADR 0017 §4).

Risk raises the bar of evidence and never grants anything: whether an action may happen at all is
the Guardian's question (§27, §33), and a second, unaudited permission system here would be worse
than none.
"""


class Refusal(StrEnum):
    """Why a node was discarded. One member per hard filter, in the order they are checked."""

    UNAVAILABLE = "UNAVAILABLE"
    """No heartbeat within the TTL: the node is not answering now (§17; ADR 0016 §3)."""
    PRIVACY = "PRIVACY"
    """The node may let data travel further than this step allows (§57, §33)."""
    UNKNOWN_CAPABILITY = "UNKNOWN_CAPABILITY"
    """No tool implements a capability the step requires: nowhere can run it, so nowhere does."""
    MISSING_TOOL = "MISSING_TOOL"
    """The tool that implements a required capability is not installed on the node (§16, §17)."""
    DEGRADED = "DEGRADED"
    """The node reports itself degraded and the step's risk is at least :data:`UNGUARDED_RISK`."""


TRAIT_POINTS: Final = 40
"""Full marks for a node offering every trait the step prefers (§13 "dispositivo preferito").

The heaviest component, so the GPU node wins the render — and a *preference*, not a filter: a
node without the trait stays eligible and simply loses, which is what keeps a one-node system
able to run anything.
"""

NETWORK_POINTS: Final[Mapping[NetworkKind, int]] = MappingProxyType(
    {
        NetworkKind.LOCAL: 20,
        NetworkKind.REMOTE: 5,
        NetworkKind.OFFLINE: 0,
        NetworkKind.UNKNOWN: 0,
    }
)
"""§17 "latenza", and §57 "local first where practical": distance stands in for latency."""

PERFORMANCE_POINTS: Final[Mapping[PerformanceClass, int]] = MappingProxyType(
    {
        PerformanceClass.HIGH: 15,
        PerformanceClass.MEDIUM: 10,
        PerformanceClass.LOW: 5,
        PerformanceClass.UNKNOWN: 0,
    }
)
"""§17 "CPU", "GPU", "RAM", as the one class the domain carries for the three."""

POWER_POINTS: Final[Mapping[PowerSource, int]] = MappingProxyType(
    {
        PowerSource.AC: 10,
        PowerSource.BATTERY: 0,
        PowerSource.UNKNOWN: 0,
    }
)
"""§17 "consumo energetico": work goes to the machine that is plugged in, all else being equal."""

WORKLOAD_POINTS: Final = 10
"""§16 "workload attuale": full marks for an idle node, none for a saturated one."""

STATUS_POINTS: Final[Mapping[DeviceStatus, int]] = MappingProxyType(
    {
        DeviceStatus.IDLE: 10,
        DeviceStatus.UNKNOWN: 0,
        DeviceStatus.BUSY: -10,
        DeviceStatus.DEGRADED: -20,
    }
)
"""§16 "stato": a node can answer and still be a bad place to send work.

The only negative component, and deliberately: an unknown status must score zero — worse than
idle, better than busy — so that a fact nobody observed is never mistaken for a good one.
"""


class Requirements(NamedTuple):
    """What a step needs, in terms a :class:`~ela.domain.Device` can be compared against.

    A step speaks in :class:`~ela.domain.CapabilityId`; a node lists tool names and hardware
    traits. :meth:`DeviceOrchestrator.requirements` does the translation once, here, so the pure
    half of the decision never needs a registry.
    """

    tools: frozenset[str]
    """Names of the tools that implement ``required_capabilities`` (ADR 0017 §3)."""
    traits: tuple[DeviceCapabilityName, ...]
    """``preferred_device_traits`` of the step: a score, never a filter (ADR 0017 §2)."""
    risk: RiskLevel
    max_privacy: PrivacyLevel
    """The most permissive node this step tolerates; ``LOCAL_ONLY`` unless the caller says more."""
    unresolved: tuple[CapabilityId, ...] = ()
    """Required capabilities no tool implements: every node is refused, and the task waits."""


class Score(NamedTuple):
    """One node judged: why it was refused, or how many points it scored."""

    device_id: DeviceId
    points: int
    components: Mapping[str, int]
    """The score broken down by criterion of §17, so a choice can be argued with, not just read."""
    refusals: tuple[Refusal, ...]

    @property
    def eligible(self) -> bool:
        """Whether every hard filter passed. A refused node is never chosen, at any score."""
        return not self.refusals


class Placement(NamedTuple):
    """Where a step should run — or nowhere, which is an answer and not an error.

    ``scores`` holds **every** candidate in registration order, refused ones included: whoever
    reads the audit log must be able to see why a node lost, not only which one won.

    The answer alone, with no trace of the question: :func:`choose` is pure and knows nothing
    about tasks. What travels to whoever executes is a :class:`PlacementDecision`, which carries
    the question too — see ADR 0026 §2.
    """

    device: Device | None
    scores: tuple[Score, ...]
    reason: str

    @property
    def waits(self) -> bool:
        """No node was eligible. The task stays ``QUEUED``; it does not fail (ADR 0017 §6)."""
        return self.device is None


class PlacementDecision(NamedTuple):
    """A placement plus what it is a placement *of*: the mirror of a decision (ADR 0026 §2).

    A bare :class:`~ela.domain.DeviceId` says "here" without saying "for what", so whoever
    receives one can only trust the sender. This says which task, which step, at what instant and
    against which :class:`Requirements` the node was judged — which is exactly enough for the
    receiver to check the claim instead of believing it (:func:`ensure_placed`).

    Modelled on :class:`~ela.domain.PermissionDecision`, deliberately: the Guardian decides, the
    decision travels as data, and the tool re-checks it before acting (ADR 0005 §5). The same
    three pieces, for the other question — *which node may see this content* (§57).

    It is **not** a domain entity: it is never persisted and it crosses no port, so it stays a
    value of this package (ADR 0026 §2). Nobody outside ``ela.devices`` may build one that names
    a node — architecture rule 30, the mirror of rule 12.
    """

    created_at: datetime
    task_id: TaskId
    step_id: StepId
    requirements: Requirements
    device: Device | None
    scores: tuple[Score, ...]
    reason: str

    @property
    def waits(self) -> bool:
        """No node was eligible. The task stays ``QUEUED``; it does not fail (ADR 0017 §6)."""
        return self.device is None


def ensure_placed(decision: PlacementDecision, task_id: TaskId, step_id: StepId) -> Device:
    """The node ``decision`` allows for this step; :class:`NotPlacedError` if it allows none.

    The mirror of ``ela.tools.base.ensure_allowed`` (ADR 0005 §5, ADR 0026 §3), and it checks the
    same three kinds of thing: that the decision is about *this* call, that it decided in favour,
    and that what it decided on still holds. Three refusals, in order:

    * the decision is about another task or another step — a placement is not transferable;
    * it names no node (``waits``): nothing was chosen, so nothing may run;
    * :func:`refusals` on the node it names, against the requirements it was judged under, is not
      empty — the decision disagrees with itself.

    The third is the one that matters and the reason this is not a formality. It re-runs the
    **same pure function** the orchestrator ran, on the **same data** the orchestrator judged: no
    second read of the registry, no second instant, no second policy. One implementation, two
    call sites — as the executor and the tool both call ``ensure_allowed``.

    What it cannot see is the world moving between the choice and the run: a node that lost its
    heartbeat a moment ago still passes. That is a declared limit, not an oversight — a placement
    does not expire in v0.1 (ADR 0026, vincoli dichiarati).
    """
    if decision.task_id != task_id or decision.step_id != step_id:
        raise NotPlacedError(
            task_id,
            step_id,
            f"the placement is for step {decision.step_id} of task {decision.task_id}",
        )
    if decision.device is None:
        raise NotPlacedError(task_id, step_id, f"no node was chosen: {decision.reason}")
    found = refusals(decision.device, decision.requirements)
    if found:
        named = ", ".join(refusal.value for refusal in found)
        raise NotPlacedError(
            task_id,
            step_id,
            f"node {decision.device.name} ({decision.device.id}) is refused by its own "
            f"placement: {named}",
        )
    return decision.device


def refusals(device: Device, requirements: Requirements) -> tuple[Refusal, ...]:
    """Every hard filter ``device`` fails, in the order of :class:`Refusal`; empty if eligible.

    ``device`` must come from :class:`~ela.devices.registry.DeviceRegistry`, whose
    ``availability`` is derived from the last heartbeat: this function trusts the field it is
    given, and the registry is what makes that field true (ADR 0016 §3).
    """
    found: list[Refusal] = []
    if device.availability is not AVAILABLE:
        found.append(Refusal.UNAVAILABLE)
    if PRIVACY_ORDER[device.privacy] > PRIVACY_ORDER[requirements.max_privacy]:
        found.append(Refusal.PRIVACY)
    if requirements.unresolved:
        found.append(Refusal.UNKNOWN_CAPABILITY)
    if not requirements.tools <= set(device.available_tools):
        found.append(Refusal.MISSING_TOOL)
    if requirements.risk >= UNGUARDED_RISK and device.status is DeviceStatus.DEGRADED:
        found.append(Refusal.DEGRADED)
    return tuple(found)


def _traits(device: Device, requirements: Requirements) -> int:
    """Marks for the preferred traits the node offers, proportional to how many it has."""
    if not requirements.traits:
        return 0
    offered = {trait.name for trait in device.capabilities if trait.available}
    satisfied = sum(1 for trait in requirements.traits if trait in offered)
    return TRAIT_POINTS * satisfied // len(requirements.traits)


def _workload(device: Device) -> int:
    """Marks for how free the node says it is; none when it does not say (§33: silence is not a
    claim)."""
    if device.current_workload is None:
        return 0
    return round(WORKLOAD_POINTS * (1.0 - device.current_workload))


def score(device: Device, requirements: Requirements) -> Score:
    """Judge one node: its refusals, its points, and where the points come from.

    A refused node is scored too. The score is computed for everybody so that the audit log can
    say "it would have won, but its heartbeat was stale" instead of only "refused".
    """
    components = {
        "traits": _traits(device, requirements),
        "network": NETWORK_POINTS[device.network],
        "performance": PERFORMANCE_POINTS[device.performance],
        "power": POWER_POINTS[device.power_source],
        "workload": _workload(device),
        "status": STATUS_POINTS[device.status],
    }
    return Score(
        device_id=device.id,
        points=sum(components.values()),
        components=MappingProxyType(components),
        refusals=refusals(device, requirements),
    )


def _strings(values: Iterable[str]) -> list[JsonValue]:
    """A list of strings as JSON data: ``list`` is invariant, so the payload needs the widening."""
    return list(values)


def _missing(devices: Iterable[Device], requirements: Requirements) -> tuple[str, ...]:
    """Every required tool at least one of ``devices`` does not have, sorted (M6.1b dec. F).

    ``MISSING_TOOL`` on its own says a node lacks something and not *what*, and with seven tools
    "what" is the whole of the diagnosis. The names are computed here, where the requirements and
    the nodes are both in hand: it is the only place that holds the two halves.
    """
    lacking: set[str] = set()
    for device in devices:
        lacking |= requirements.tools - set(device.available_tools)
    return tuple(sorted(lacking))


def _named(found: Iterable[Refusal], missing: tuple[str, ...]) -> str:
    """Refusals as words, with the tools named on the one refusal that has names to give."""
    return ", ".join(
        refusal.value + (f" ({', '.join(missing)})" if refusal is Refusal.MISSING_TOOL else "")
        for refusal in found
    )


def _summary(scores: Iterable[Score], devices: Iterable[Device], requirements: Requirements) -> str:
    """How many nodes each refusal took out, in the declaration order of :class:`Refusal`.

    Every member of the enum is asked, so a refusal of any kind reaches whoever is waiting — and
    a member added tomorrow is rendered without anybody remembering to render it. What one member
    adds is the names: ``MISSING_TOOL`` carries the tools nobody had.
    """
    missing = _missing(devices, requirements)
    counted = {
        refusal: sum(1 for candidate in scores if refusal in candidate.refusals)
        for refusal in Refusal
    }
    return ", ".join(
        f"{count} {_named((refusal,), missing)}" for refusal, count in counted.items() if count
    )


def choose(devices: Iterable[Device], requirements: Requirements) -> Placement:
    """The node that runs this step, or none — pure, deterministic, no I/O.

    Ties go to the first node in registration order, which is the order
    :meth:`~ela.ports.DeviceRegistryPort.devices` promises: ``max`` returns the first maximum, so
    the same registry and the same step always give the same answer.
    """
    candidates = tuple(devices)
    scores = tuple(score(device, requirements) for device in candidates)
    eligible = [
        (candidate, device)
        for candidate, device in zip(scores, candidates, strict=True)
        if candidate.eligible
    ]
    if not eligible:
        found = _summary(scores, candidates, requirements)
        return Placement(
            device=None,
            scores=scores,
            reason=(
                f"no eligible node among {len(candidates)}: {found}"
                if found
                else "no node is registered"
            ),
        )
    best, device = max(eligible, key=lambda pair: pair[0].points)
    return Placement(
        device=device,
        scores=scores,
        reason=(
            f"{device.name} ({device.id}) with {best.points} points, "
            f"{len(eligible)} of {len(candidates)} node(s) eligible"
        ),
    )


class DeviceOrchestrator:
    """Decides where a step runs and writes the decision to the audit log (§17, §32).

    Advice only: it returns a :class:`Placement` and never moves a task. The guarantee is
    structural rather than promised — this package cannot import ``ela.tasks`` (rule 22), so
    there is no path from here to a task that fails.
    """

    __slots__ = ("_audit", "_clock", "_ids", "_registry", "_tools")

    def __init__(
        self,
        registry: DeviceRegistry,
        tools: ToolRegistryPort,
        audit: AuditLog,
        ids: IdGenerator,
        clock: Clock,
    ) -> None:
        self._registry = registry
        self._tools = tools
        self._audit = audit
        self._ids = ids
        self._clock = clock

    def requirements(
        self, step: TaskStep, *, max_privacy: PrivacyLevel = PrivacyLevel.LOCAL_ONLY
    ) -> Requirements:
        """What ``step`` needs, with its capabilities resolved into the tools that implement them.

        A capability no tool implements is collected in ``unresolved`` instead of raising: the
        answer to "nobody can run this" is that the task waits, not that it fails (§33).
        """
        tools: set[str] = set()
        unresolved: list[CapabilityId] = []
        for capability_id in step.required_capabilities:
            try:
                tools.add(self._tools.get(capability_id).name)
            except NotFoundError:
                unresolved.append(capability_id)
        return Requirements(
            tools=frozenset(tools),
            traits=step.preferred_device_traits,
            risk=step.risk,
            max_privacy=max_privacy,
            unresolved=tuple(unresolved),
        )

    async def place(
        self,
        step: TaskStep,
        *,
        task_id: TaskId,
        max_privacy: PrivacyLevel = PrivacyLevel.LOCAL_ONLY,
    ) -> PlacementDecision:
        """Choose a node for ``step`` and record the choice — or the wait — in the audit log.

        ``max_privacy`` is the most permissive node the caller tolerates, and defaults to the
        most restrictive level: a privacy nobody declared is not a permission (§33, §57; ADR 0017
        §5). Exactly one audit event per call, whatever the answer.

        The answer comes back as a :class:`PlacementDecision` and not as a bare id, so that
        whoever executes can check it instead of trusting it (ADR 0026 §2).
        """
        requirements = self.requirements(step, max_privacy=max_privacy)
        placement = choose(await self._registry.devices(), requirements)
        await self._audit.append(self._event(placement, step, task_id, requirements))
        return PlacementDecision(
            created_at=self._clock.now(),
            task_id=task_id,
            step_id=step.id,
            requirements=requirements,
            device=placement.device,
            scores=placement.scores,
            reason=placement.reason,
        )

    async def confirm(
        self,
        device_id: DeviceId,
        step: TaskStep,
        *,
        task_id: TaskId,
        max_privacy: PrivacyLevel = PrivacyLevel.LOCAL_ONLY,
    ) -> PlacementDecision:
        """A decision for the node a **resumed** step was already given (ADR 0026 §4).

        A step left RUNNING by a crash or by an approval has already been placed, and placing it
        again could name a different node while a tool ran on the first (ADR 0019 §4). So the
        caller reads its node back from the audit and asks here whether that node is *still*
        eligible: this reads it from the registry, judges it against the same
        :class:`Requirements` the step would get today, and names it only if :func:`refusals` is
        empty. A node no longer registered, or no longer eligible, comes back as a decision that
        names nobody — and the run waits, which is the answer ADR 0017 §6 already gives.

        It **confirms** and never chooses, so it writes **no audit event**: a second
        ``DEVICE_SELECTED`` would claim a choice nobody made, and the choice this confirms is
        already in the log.
        """
        requirements = self.requirements(step, max_privacy=max_privacy)
        found = [node for node in await self._registry.devices() if node.id == device_id]
        if not found:
            return self._confirmation(
                task_id, step, requirements, None, (), f"node {device_id} is no longer registered"
            )
        judged = score(found[0], requirements)
        if not judged.eligible:
            named = _named(judged.refusals, _missing((found[0],), requirements))
            return self._confirmation(
                task_id,
                step,
                requirements,
                None,
                (judged,),
                f"node {found[0].name} ({device_id}) is no longer eligible: {named}",
            )
        return self._confirmation(
            task_id,
            step,
            requirements,
            found[0],
            (judged,),
            f"{found[0].name} ({device_id}) still eligible, confirmed without a new choice",
        )

    def _confirmation(
        self,
        task_id: TaskId,
        step: TaskStep,
        requirements: Requirements,
        device: Device | None,
        scores: tuple[Score, ...],
        reason: str,
    ) -> PlacementDecision:
        return PlacementDecision(
            created_at=self._clock.now(),
            task_id=task_id,
            step_id=step.id,
            requirements=requirements,
            device=device,
            scores=scores,
            reason=reason,
        )

    def _event(
        self,
        placement: Placement,
        step: TaskStep,
        task_id: TaskId,
        requirements: Requirements,
    ) -> AuditEvent:
        """The one event a placement writes: what was asked, and how each node answered."""
        chosen = placement.device
        candidates: list[JsonValue] = [
            {
                "device_id": str(candidate.device_id),
                "points": candidate.points,
                "components": dict(candidate.components),
                "refusals": [refusal.value for refusal in candidate.refusals],
            }
            for candidate in placement.scores
        ]
        return AuditEvent(
            id=AuditEventId(self._ids.new_uuid()),
            created_at=self._clock.now(),
            event_type=(
                AuditEventType.DEVICE_UNAVAILABLE
                if chosen is None
                else AuditEventType.DEVICE_SELECTED
            ),
            actor=ORCHESTRATOR_ACTOR,
            summary=f"place step {step.id}: {placement.reason}",
            task_id=task_id,
            step_id=step.id,
            device_id=None if chosen is None else chosen.id,
            payload={
                "required_tools": _strings(sorted(requirements.tools)),
                "preferred_traits": _strings(requirements.traits),
                "risk": requirements.risk.value,
                "max_privacy": requirements.max_privacy.value,
                "unresolved_capabilities": _strings(requirements.unresolved),
                "candidates": candidates,
            },
        )
