"""What the API accepts and returns, written out (ADR 0023 §6).

The wire shape is a **decision**, so it is declared here instead of being ``model_dump()`` of a
domain entity: a field added to the domain tomorrow must not leave the machine because nobody
noticed. The names follow the domain's — ``required_capabilities``, ``dependencies`` — because a
second vocabulary for the same things would be a translation table nobody asked for.

Two leaf values are reused as they are: :class:`~ela.domain.ProviderUsage` and
:class:`~ela.domain.ErrorMetadata`. They are values and not entities, and what an
:class:`~ela.domain.AuditEvent` carries in them *is* their shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ela.audit.chain import ChainSummary
from ela.domain import (
    Actor,
    Approval,
    ApprovalStatus,
    AuditEvent,
    AuditEventType,
    CapabilityId,
    ContextActivity,
    ContextDeadlines,
    ContextDevice,
    ContextQuestionStatus,
    ContextRecent,
    ContextWork,
    Device,
    DeviceCapability,
    DeviceCapabilityName,
    DeviceId,
    DeviceStatus,
    ErrorMetadata,
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    JsonMapping,
    NetworkKind,
    OperatingSystem,
    PerceptionChange,
    PerformanceClass,
    PermissionState,
    PlanId,
    PowerSource,
    PrivacyLevel,
    ProviderUsage,
    RiskLevel,
    SensorStatus,
    StepId,
    StepState,
    SystemPermission,
    Task,
    TaskPlan,
    TaskState,
    TaskStep,
)
from ela.tasks.graph import GraphState

__all__ = [
    "AnswerIn",
    "ApprovalOut",
    "AuditEventOut",
    "CancelIn",
    "CaptureStoreOut",
    "ChainOut",
    "ContextOut",
    "DeviceOut",
    "DiagnosticsOut",
    "ExecutionResultOut",
    "HealthOut",
    "PerceptionOut",
    "PerceptionSummaryOut",
    "PlanIn",
    "RunOut",
    "StepIn",
    "StepOut",
    "TaskCreate",
    "TaskDetail",
    "TaskOut",
    "TraitOut",
]


def _plain(entity: BaseModel, field: str) -> JsonMapping:
    """A frozen JSON field as plain JSON containers again.

    The domain stores free-form JSON deeply immutable — mappings become ``MappingProxyType``,
    arrays become tuples — and a tuple is not a JSON value: handing one straight to a response
    model would be refused by the very type that describes it. The domain's own serializer is
    what turns it back, so the API does not keep a second opinion about what JSON is.
    """
    return cast(JsonMapping, entity.model_dump()[field])


PLAN_EXTRA = ConfigDict(extra="ignore")
"""An unknown key in a plan is **ignored**, and that is a decision (M8.3, ADR 0025 §8).

JSON has no comments, and the example plans in ``docs/examples/`` are sent to this endpoint byte
for byte by a test, so the only way one of them can explain itself is a key that survives the
trip and means nothing. ``"_nota"`` is that key. Pydantic would ignore it anyway — this says so
on purpose, because behaviour that a file on disk relies on must not be a default somebody else
can change.
"""


class TaskCreate(BaseModel):
    """What the user asked. The plan comes separately, and today by hand (ADR 0023 §6)."""

    text: Annotated[str, Field(min_length=1)]
    goal: str | None = None
    deadline: datetime | None = None


class StepIn(BaseModel):
    """One step of a plan written by the caller, until the Planner (§13) writes them.

    ``id`` is the caller's: ``dependencies`` name the other steps by id, and a step id minted here
    would leave the caller with no way to express the shape of its own plan.

    :data:`PLAN_EXTRA` applies here too: an unknown key is ignored, so a step can carry a note.
    """

    model_config = PLAN_EXTRA

    id: UUID
    goal: str
    required_capabilities: tuple[CapabilityId, ...] = ()
    arguments: JsonMapping = Field(default_factory=dict)
    preferred_device_traits: tuple[DeviceCapabilityName, ...] = ()
    dependencies: tuple[UUID, ...] = ()
    risk: RiskLevel
    expected_result: str
    success_conditions: tuple[str, ...] = ()
    requires_authorization: bool = False

    def to_domain(self, created_at: datetime) -> TaskStep:
        return TaskStep(
            id=StepId(self.id),
            created_at=created_at,
            goal=self.goal,
            required_capabilities=self.required_capabilities,
            arguments=self.arguments,
            preferred_device_traits=self.preferred_device_traits,
            dependencies=tuple(StepId(one) for one in self.dependencies),
            risk=self.risk,
            expected_result=self.expected_result,
            success_conditions=self.success_conditions,
            requires_authorization=self.requires_authorization,
        )


class PlanIn(BaseModel):
    """A plan for a task that has none. That it is a DAG is checked where every plan is."""

    model_config = PLAN_EXTRA

    goal: str
    steps: Annotated[tuple[StepIn, ...], Field(min_length=1)]

    def to_domain(self, task_id: UUID, plan_id: UUID, created_at: datetime) -> TaskPlan:
        return TaskPlan(
            id=PlanId(plan_id),
            created_at=created_at,
            task_id=task_id,  # type: ignore[arg-type]  # TaskId is a NewType over UUID
            goal=self.goal,
            steps=tuple(step.to_domain(created_at) for step in self.steps),
        )


class AnswerIn(BaseModel):
    """Which request is being answered. *Who* answers is ``ELA_USER_NAME`` (ADR 0023 §8)."""

    approval_id: UUID


class CancelIn(BaseModel):
    """Why the user stopped the task (§65). It reaches the audit trail as the reason."""

    reason: str = ""


class TaskOut(BaseModel):
    id: UUID
    created_at: datetime
    goal: str
    state: TaskState
    intent_id: UUID | None
    plan_id: UUID | None
    parent_id: UUID | None
    deadline: datetime | None

    @classmethod
    def of(cls, task: Task) -> TaskOut:
        return cls(
            id=task.id,
            created_at=task.created_at,
            goal=task.goal,
            state=task.state,
            intent_id=task.intent_id,
            plan_id=task.plan_id,
            parent_id=task.parent_id,
            deadline=task.deadline,
        )


class StepOut(BaseModel):
    """A step and where it stands.

    ``arguments`` are here: they are the user's own content coming back to the user, on loopback,
    behind the user's token — and a task whose steps show no arguments does not say what it does.
    The audit log is another matter, and architecture rule 23 keeps them out of it (ADR 0023 §6).
    """

    id: UUID
    goal: str
    state: StepState
    required_capabilities: tuple[CapabilityId, ...]
    arguments: JsonMapping
    preferred_device_traits: tuple[DeviceCapabilityName, ...]
    dependencies: tuple[UUID, ...]
    risk: RiskLevel
    expected_result: str
    success_conditions: tuple[str, ...]
    requires_authorization: bool

    @classmethod
    def of(cls, step: TaskStep, state: StepState) -> StepOut:
        return cls(
            id=step.id,
            goal=step.goal,
            state=state,
            required_capabilities=step.required_capabilities,
            arguments=_plain(step, "arguments"),
            preferred_device_traits=step.preferred_device_traits,
            dependencies=tuple(step.dependencies),
            risk=step.risk,
            expected_result=step.expected_result,
            success_conditions=step.success_conditions,
            requires_authorization=step.requires_authorization,
        )


class TaskDetail(TaskOut):
    """A task with its plan, in topological order. Empty steps means: no plan yet."""

    steps: tuple[StepOut, ...] = ()

    @classmethod
    def of_graph(cls, task: Task, graph: GraphState | None) -> TaskDetail:
        detail = cls(**TaskOut.of(task).model_dump())
        if graph is None:
            return detail
        steps = tuple(
            StepOut.of(graph.graph.step(step_id), graph.states[step_id])
            for step_id in graph.graph.order
        )
        return detail.model_copy(update={"steps": steps})


class RunOut(BaseModel):
    """What one call of ``run`` did: where the task is now, which steps it executed, and why it
    stopped when the outcome alone does not say."""

    task: TaskOut
    outcome: str
    steps: tuple[UUID, ...]
    reason: str | None = None
    """Why the run is waiting. ``null`` unless it is: an outcome that explains itself needs none.

    ``waiting_device`` used to arrive as a bare word while the audit already held the sentence —
    which nodes were considered, why each was refused, and for a missing tool its name. That
    sentence travels with the answer now (M6.1b dec. F).
    """


class ApprovalOut(BaseModel):
    """A request for the user's consent (§30). ``prompt`` is what the user is asked."""

    id: UUID
    created_at: datetime
    task_id: UUID
    step_id: UUID
    capability_id: CapabilityId
    targets: tuple[str, ...]
    prompt: str
    status: ApprovalStatus
    expires_at: datetime | None
    responded_at: datetime | None
    responded_by: str | None

    @classmethod
    def of(cls, approval: Approval) -> ApprovalOut:
        return cls(
            id=approval.id,
            created_at=approval.created_at,
            task_id=approval.task_id,
            step_id=approval.step_id,
            capability_id=approval.capability_id,
            targets=approval.targets,
            prompt=approval.prompt,
            status=approval.status,
            expires_at=approval.expires_at,
            responded_at=approval.responded_at,
            responded_by=approval.responded_by,
        )


class AuditEventOut(BaseModel):
    """One entry of the append-only trail (§32), as it is stored.

    It carries no arguments and no output, and not because this schema leaves them out: an
    ``AuditEvent`` never holds them (§57, architecture rule 23).
    """

    id: UUID
    created_at: datetime
    event_type: AuditEventType
    actor: Actor
    summary: str
    task_id: UUID | None
    step_id: UUID | None
    capability_id: CapabilityId | None
    decision_id: UUID | None
    authorization_id: UUID | None
    device_id: DeviceId | None
    tool_name: str | None
    usage: ProviderUsage | None
    error: ErrorMetadata | None
    payload: JsonMapping

    @classmethod
    def of(cls, event: AuditEvent) -> AuditEventOut:
        return cls(
            id=event.id,
            created_at=event.created_at,
            event_type=event.event_type,
            actor=event.actor,
            summary=event.summary,
            task_id=event.task_id,
            step_id=event.step_id,
            capability_id=event.capability_id,
            decision_id=event.decision_id,
            authorization_id=event.authorization_id,
            device_id=event.device_id,
            tool_name=event.tool_name,
            usage=event.usage,
            error=event.error,
            payload=_plain(event, "payload"),
        )


class TraitOut(BaseModel):
    """A hardware or software trait of a node (§16), not a capability the Guardian rules on."""

    name: DeviceCapabilityName
    available: bool

    @classmethod
    def of(cls, trait: DeviceCapability) -> TraitOut:
        return cls(name=trait.name, available=trait.available)


class DeviceOut(BaseModel):
    """A node as the registry judges it right now (§16; ADR 0024 §5).

    ``available`` is the **derived** answer — whether the last heartbeat is still worth
    something — and never the stored column, which keeps saying what was true when someone wrote
    it (architecture rule 20). Which is why it arrives as an argument rather than being read off
    the entity.
    """

    id: DeviceId
    created_at: datetime
    name: str
    os: OperatingSystem
    available: bool
    status: DeviceStatus
    capabilities: tuple[TraitOut, ...]
    available_tools: tuple[str, ...]
    performance: PerformanceClass
    network: NetworkKind
    power_source: PowerSource
    privacy: PrivacyLevel
    current_workload: float | None
    last_seen_at: datetime | None

    @classmethod
    def of(cls, device: Device, *, available: bool) -> DeviceOut:
        return cls(
            id=device.id,
            created_at=device.created_at,
            name=device.name,
            os=device.os,
            available=available,
            status=device.status,
            capabilities=tuple(TraitOut.of(trait) for trait in device.capabilities),
            available_tools=device.available_tools,
            performance=device.performance,
            network=device.network,
            power_source=device.power_source,
            privacy=device.privacy,
            current_workload=device.current_workload,
            last_seen_at=device.last_seen_at,
        )


class ChainOut(BaseModel):
    """A verified audit chain in the two numbers worth keeping outside the log (ADR 0007).

    Anchor them somewhere the log cannot reach and a truncated tail becomes detectable too: the
    chain alone cannot prove that its own end is still there.
    """

    length: int
    head_hash: str

    @classmethod
    def of(cls, summary: ChainSummary) -> ChainOut:
        return cls(length=summary.length, head_hash=summary.head_hash)


class HealthOut(BaseModel):
    """Alive, and the database answered: ``/health`` reads through the port to say so."""

    status: str
    database: str
    now: datetime


class ExecutionResultOut(BaseModel):
    """What a tool produced (§63; M8.3, ADR 0025 §4).

    ``output`` is the user's own content coming back to the user, on loopback, behind the user's
    token — the answer of a model, the note that was written — and it is the reason this schema
    exists: until M8.3 it left the machine nowhere, so a plan could complete and show nothing.
    Architecture rule 29 keeps it to one module of ``ela.api``, which is the route that serves
    this schema; the audit trail still never carries it (§57, rule 23).
    """

    id: ExecutionId
    created_at: datetime
    capability_id: CapabilityId
    status: ExecutionStatus
    task_id: UUID | None
    step_id: UUID | None
    tool_name: str | None
    device_id: DeviceId | None
    decision_id: UUID | None
    authorization_id: UUID | None
    output: JsonMapping
    error: ErrorMetadata | None
    usage: ProviderUsage | None
    duration_ms: int | None

    @classmethod
    def of(cls, result: ExecutionResult) -> ExecutionResultOut:
        return cls(
            id=result.id,
            created_at=result.created_at,
            capability_id=result.capability_id,
            status=result.status,
            task_id=result.task_id,
            step_id=result.step_id,
            tool_name=result.tool_name,
            device_id=result.device_id,
            decision_id=result.decision_id,
            authorization_id=result.authorization_id,
            output=_plain(result, "output"),
            error=result.error,
            usage=result.usage,
            duration_ms=result.duration_ms,
        )


class CaptureStoreOut(BaseModel):
    """What content ELA is holding right now, and under which limits (M10.2, ADR 0029 §15).

    In ``/diagnostics`` because §57 makes "what are you keeping of mine, at this moment" a
    question the user must be able to ask, and a store of screenshots that only the filesystem
    knows about is exactly what must not exist. It is ELA's own state and not the world, which is
    why it is here and not on ``/perception`` — the line of ADR 0028 §8.

    ``retained`` and ``bytes`` are a listing of at most ``max_count`` entries, so ``/diagnostics``
    keeps its promise of not observing the world: it reads what ELA holds, the way it already
    counts providers and tasks.
    """

    retained: int
    bytes: int
    ttl_seconds: float
    max_count: int
    max_bytes: int


class PerceptionSummaryOut(BaseModel):
    """The composition-shaped half of perception: what ELA *can* see on this machine (§10, §57).

    In ``/diagnostics`` and not only in ``/perception`` because a missing permission is not the
    world, it is the wiring: "Screen Recording denied" belongs next to ``providers`` and
    ``tools`` — it says what ELA is able to do here. The state of the microphone is the world,
    and lives on the other route.

    ``observed_at`` travels with it because these permissions are as old as the last look, and a
    reader who is not told the age of an answer will read it as current.
    """

    enabled: bool
    watching: bool
    """Whether the continuous loop is on. Off by default: ELA answers when asked, and does not
    observe on its own until somebody turns it on (ADR 0028 §7)."""
    observed_at: datetime
    permissions: dict[SystemPermission, PermissionState]
    captures: CaptureStoreOut


class VoiceOut(BaseModel):
    """Whether ELA has a voice on this machine, and which one (§9; M11.1).

    In ``/diagnostics`` and nowhere else, for the line ADR 0028 §8 drew: this route says *what
    ELA is connected to*, not *what ELA is doing*. Whether ELA can speak here is composition — it
    sits next to ``providers`` and ``tools``. There is no route that says whether ELA **is**
    speaking, and there is not meant to be one in M11.1: a sentence lasts as long as a sentence,
    and a status that is true for thirty seconds is a status nobody can act on.

    ``max_characters`` is here because it is the only thing a caller can get wrong before the
    Guardian ever sees the step, and a limit nobody can read is a limit somebody discovers.
    """

    enabled: bool
    """The user's switch, ``ELA_VOICE_ENABLED``. Separate from ``available`` because "you turned
    it off" and "this machine has no voice" are different facts (M10.3's lesson, ADR 0030 §8)."""
    available: bool
    """Whether this operating system has a speech helper ELA knows about."""
    voice: str
    """Which voice ELA speaks with locally. **Not the voice §9 asks for** — see M11.1 dec. D."""
    max_characters: int
    timeout_seconds: float
    online: VoiceOnlineOut
    """The voice of §9 and what it costs to have it (M11.3, ADR 0034 §11)."""


class VoiceOnlineOut(BaseModel):
    """The online voice: whether it is there, which one it is, and what the provider keeps.

    ``text_retained_by_provider`` is here because the user chose this knowingly and **the choice
    has to stay visible** (ADR 0034 §11). Not a warning before every sentence — one that repeats
    is one people learn to skip — but a fact stated where somebody looks at which voice ELA is
    using, which is here and in ``ela voice``.
    """

    configured: bool
    """Whether there is both a key and a voice. Which of the two is missing is a question the
    tool answers with two different codes; here what matters is whether ELA can use it at all."""
    available: bool
    """Whether this machine can play audio (``afplay``). Separate from ``configured`` for the
    reason every pair in this file is separate: they are two facts and one of them is yours."""
    voice_id: str | None
    model: str
    text_retained_by_provider: bool
    """**What ELA says with this voice is kept by the provider**, and can be read back in the
    account's own history. Measured, not quoted (ADR 0034 §1.2)."""
    timeout_seconds: float


class VoiceCandidateOut(BaseModel):
    """One voice offered for listening (ADR 0034 §9)."""

    voice_id: str
    name: str
    chosen: bool


class HeardOut(BaseModel):
    """One thing that was played during an audition, and what it cost.

    ``phrase`` is echoed back because it is a **constant of the repository** — §9's own words —
    and showing what was said is the point of an audition. It is not an argument: there is no
    field anywhere in this route for a caller to put words in (ADR 0034 §9).
    """

    voice_id: str
    model: str
    phrase: str
    spoken_seconds: float | None = None
    synthesis_seconds: float | None = None
    credits: int | None = None
    history_item_id: str | None = None
    error: str | None = None


class AuditionOut(BaseModel):
    """What an audition played, in order, and what the whole of it cost."""

    heard: tuple[HeardOut, ...]
    credits: int | None
    """The sum of what the provider charged, or ``None`` when it charged nothing it stated."""


class AuditionIn(BaseModel):
    """Which voice to hear, and whether to hear it on both models. **No field for text.**

    The absence is the design (ADR 0034 §9): an audition that accepted a sentence would be a way
    to say anything out loud, and send it to a provider, with no capability anywhere in sight.
    Architecture rule 43 says the same thing about the code; this says it about the wire.
    """

    voice_id: str = Field(min_length=1)
    both_models: bool = False


class PreviewIn(BaseModel):
    """Which voice's own sample to play. Nothing is synthesised and nothing is sent."""

    voice_id: str = Field(min_length=1)


class VoiceStatusOut(BaseModel):
    """What ``ela voice`` shows: the two voices, and the ones worth listening to."""

    voice: VoiceOut
    candidates: tuple[VoiceCandidateOut, ...]
    phrases: tuple[str, ...]
    """What an audition would say — the two sentences of §9, from the repository."""


class ContextOut(BaseModel):
    """The answer to §44 at one instant — and what this ELA cannot answer (M10.4, ADR 0032).

    The sections are the domain's own values and are **not** transcribed into a second set of
    models here, which is a deliberate exception to this module's rule and not an oversight. The
    rule exists so that a field added to the domain cannot leave the machine because nobody
    noticed; this model has exactly one reader and the domain shape *is* the wire shape, so a
    transcription would be the translation table this file's docstring warns about — two places
    to keep in step. The guarantee is kept by ``tests/api/test_context.py``, which asserts the
    exact key set of every section: a field added to the domain fails that test until somebody
    decides it may leave. Derived, rather than copied.

    ``questions`` carries **all seven** questions of §44, including the ones with no source at
    all: each says what answers it here and what is missing by name. A question that vanished
    when ELA could not answer it would be a question nobody notices ELA is not answering.
    """

    at: datetime
    """The one instant every age in this response is relative to."""
    activity: ContextActivity
    device: ContextDevice | None
    work: ContextWork
    deadlines: ContextDeadlines
    recent: ContextRecent
    questions: tuple[ContextQuestionStatus, ...]


class PerceptionOut(BaseModel):
    """What ELA believes about this machine, and what changed when it last looked (§10, §11).

    Every sensor arrives as a :class:`~ela.domain.SensorStatus` — state **and** cause — because
    the two are one fact: ``OFF`` alone would tell a reader something ELA does not know
    (ADR 0028 §3). ``idle_seconds`` is a number and stays one: turning it into "present" or
    "away" is a threshold, and a threshold belongs to whoever decides, not to whoever observes.

    ``changes`` is the last look only. There is no history here on purpose — the perception is
    not the memory, and structured memory is §21, with rules this route does not have.

    The application fields (M10.3) are **state and not content**: which applications are running
    and which is in front, by bundle identifier, and how many windows there are. No window title
    appears here or anywhere else in ELA — a title costs the same permission a screenshot costs
    and carries a URL or a document name, so it goes through the Guardian if it ever goes
    anywhere (architecture rule 36).
    """

    enabled: bool
    watching: bool
    observed_at: datetime
    microphone: SensorStatus
    camera: SensorStatus
    permissions: dict[SystemPermission, PermissionState]
    display_count: int | None
    display_asleep: bool | None
    screen_locked: bool | None
    on_console: bool | None
    idle_seconds: float | None
    running_bundle_ids: tuple[str, ...] | None
    frontmost_bundle_id: str | None
    window_count: int | None
    changes: tuple[PerceptionChange, ...]


class DiagnosticsOut(BaseModel):
    """How ELA is composed right now — never a secret, never the user's content (ADR 0023 §6)."""

    version: str
    database: str
    workspace: str
    user_name: str
    providers: dict[str, str]
    task_types: tuple[str, ...]
    default_profile: str
    capabilities: tuple[CapabilityId, ...]
    tools: tuple[str, ...]
    devices: dict[str, str]
    undeclared_tools: tuple[str, ...]
    """Tools this process has that the ``local`` row does not list — empty almost always.

    After M6.1b the row cannot be behind, *almost*: it can if the write failed (a read-only
    database) or if two ELAs with different code share one database. So the comparison has
    somebody behind it and is worth making (ADR 0026 §7) — and when it is not empty it says
    exactly which capability the orchestrator will refuse to place (ADR 0035 §6).
    """
    tasks: dict[str, int]
    pending_approvals: int
    recovered: dict[str, int]
    perception: PerceptionSummaryOut
    voice: VoiceOut
