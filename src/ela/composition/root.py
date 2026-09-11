"""The composition root: the one place that builds ELA (spec §46, §54; ADR 0023 §1, §5).

Every piece of §27 has existed for milestones — catalogue, Guardian, authorizations, executor,
tools, verifiers, device registry, orchestrator, runner, provider, router, the SQL adapters — and
nothing put them in a row: each test built its own world by hand, and outside the tests ELA did
not exist as a process. :func:`build` is that row, written once.

It is the only module in ``src/ela`` that names concrete implementations (architecture rule 27):
everybody else receives a port. That is what makes "provider abstraction" (§50) a property of the
code rather than a habit — there is exactly one file to read to know what ELA is wired to.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ela.audit.verifier import AuditVerifier
from ela.composition.errors import ConfigurationError
from ela.composition.settings import Settings
from ela.composition.system import SystemClock, UuidGenerator
from ela.context import ContextCore
from ela.devices import (
    DeviceOrchestrator,
    DeviceRegistry,
    NodeEnrollment,
)
from ela.devices.local import LOCAL_DEVICE_ID
from ela.domain import Actor, ActorKind, RawSpeech
from ela.executive import Assignments, Executor, TaskRunner
from ela.infrastructure.machine import (
    Audition,
    DarwinListening,
    DarwinProbe,
    OnlineSpeechCommand,
    Play,
    SaySpeechCommand,
    ScreenCaptureCommand,
    Speak,
    UnsupportedListening,
    UnsupportedProbe,
    UnsupportedScreenCapture,
    UnsupportedSpeech,
    UnsupportedTextRecognition,
    VisionTextRecognition,
    sweep_speech_files,
)
from ela.infrastructure.persistence import (
    SqlApprovalStore,
    SqlAssignmentStore,
    SqlAuditLog,
    SqlAuthorizationStore,
    SqlDeviceRegistry,
    SqlEnrollmentStore,
    SqlExecutionResultStore,
    SqlTaskRepository,
    make_engine,
    missing_tables,
)
from ela.perception import PerceptionCore
from ela.permissions import PermissionGuardian, production_catalogue
from ela.ports import (
    SPEECH_NO_KEY,
    SPEECH_NO_PLAYER,
    ApprovalStore,
    AuditLog,
    AuthorizationStore,
    CapabilityRegistryPort,
    Clock,
    ExecutionResultStore,
    IdGenerator,
    ListeningPort,
    PerceptionProbe,
    RoutingError,
    ScreenCapturePort,
    SpeechPort,
    TaskRepository,
    TextRecognitionPort,
)
from ela.providers.anthropic import anthropic_provider
from ela.providers.elevenlabs import ElevenLabsVoice
from ela.providers.registry import ProviderRegistry
from ela.routing import ModelRouter
from ela.tasks.engine import LIVE_STATES, TaskEngine
from ela.tools import (
    DIRECTORY_MODE,
    CaptureStore,
    ToolRegistry,
    VerifierRegistry,
    production_tools,
    production_verifiers,
)
from ela.tools.settings import speech_dir_beside

__all__ = ["ELA_ACTOR", "WORKSPACE_MODE", "Database", "Ela", "build"]

ELA_ACTOR = Actor(kind=ActorKind.ELA, id="ela")
"""Who ELA says it is in the audit trail when it acts on its own (§32)."""
WORKSPACE_MODE = 0o700
"""The workspace holds the user's notes (§57): nobody else on the machine reads them."""


class Database(Protocol):
    """The one thing the composition root does about the database engine: close it.

    A ``Protocol`` and not ``AsyncEngine`` because this package may not import SQLAlchemy
    (architecture rule 3): the engine arrives from :mod:`ela.infrastructure.persistence` already
    built, and what is left here is its lifetime.
    """

    async def dispose(self) -> None: ...


@dataclass(frozen=True, slots=True)
class Ela:
    """ELA, built: every port bound to an implementation, ready to be used or served.

    Frozen, because the wiring of a running assistant is not something a request should be able
    to change. What holds state is behind the ports — the database, the workspace — not here.
    """

    settings: Settings
    clock: Clock
    ids: IdGenerator
    database: Database
    audit: AuditLog
    audit_verifier: AuditVerifier
    """The same log, asked a different question (ADR 0024 §4).

    A second name and not a second object: the adapter that appends is the only one that can say
    whether what was appended still hangs together. Kept apart from ``audit`` because the port a
    caller receives says what that caller may do, and whoever verifies must not gain an
    ``append``.
    """
    repository: TaskRepository
    authorizations: AuthorizationStore
    approvals: ApprovalStore
    results: ExecutionResultStore
    capabilities: CapabilityRegistryPort
    guardian: PermissionGuardian
    providers: ProviderRegistry
    router: ModelRouter
    tools: ToolRegistry
    verifiers: VerifierRegistry
    devices: DeviceRegistry
    enrollment: NodeEnrollment
    """How a node gets an identity: codes issued, and spent by the nodes they create (M12.1)."""
    engine: TaskEngine
    orchestrator: DeviceOrchestrator
    executor: Executor
    runner: TaskRunner
    assignments: Assignments
    """The work handed to remote nodes, as it is now, and every write of it (M12.2, ADR 0038 §6).

    The service and never the store: the store returns rows as written, and whoever decides reads
    the expiry through the service, which also writes a heartbeat in front of every expiry it sets
    (architecture rule 48)."""
    captures: CaptureStore
    """Where screen captures are kept, and for how long (M10.2, ADR 0029 §1).

    Exposed on ``Ela`` because three places must agree about it and none of them is the tool: the
    start-up purge in the ``lifespan``, ``/diagnostics``, and the tool itself. A retention nobody
    outside the tool can see is a promise that cannot be checked (§57).
    """
    context: ContextCore
    """The answer to §44, composed on read and never stored (M10.4, ADR 0032).

    It holds ports and reads them; it writes nothing, executes nothing and observes nothing by
    itself — the perception view is handed to ``assemble`` by whoever decided to look. Which
    states count as live is given to it here rather than derived by it: that knowledge is the
    state machine's (ADR 0004) and a second copy of the list is how two lists drift apart.
    """
    speech: SpeechPort
    """How ELA speaks on this machine (§9; M11.1).

    Held here, and not only inside the tool, for the reason ``captures`` is: ``/diagnostics`` has
    to be able to ask *whether ELA has a voice here* without going through a capability, an
    approval and a step. Asking is free and silent — two syscalls, no permission, no sound.
    """
    listening: ListeningPort
    """What ELA hears with (M11.2, ADR 0036).

    Held so that ``/diagnostics`` can ask it directly: whether the transcriber is there
    **and is the one ELA was told to expect** is a question with an answer, and a limit
    nobody can read is a limit somebody discovers. Asking is a stat and a digest remembered
    against the file's size and mtime, so it is cheap enough to ask on every read.
    """
    speech_online: SpeechPort
    """How ELA speaks in the voice of §9 — and the only path on which what ELA says leaves this
    machine (M11.3, ADR 0034).

    A second field and not a replacement: the local voice does not go away. It is what speaks when
    there is no network, when the provider is unusable, and for the sentences that must not leave
    — and nothing chooses between the two by itself, because the two are different permissions
    (ADR 0034 §5).
    """
    audition: Audition
    """Hearing a voice before choosing it, without a task per attempt (ADR 0034 §9).

    On ``Ela`` because the routes need it and the CLI may not build it: architecture rule 27 keeps
    adapters out of everything but the composition root, and rule 28 keeps the CLI a client. What
    it can say is fixed in its own module — two sentences from §9, written in the repository.
    """
    perception: PerceptionCore
    """What ELA believes about the machine it runs on (§10, §11; M10.1, ADR 0028).

    Built last and wired to nothing else: in v0.1 nobody consumes perception — no task reads it,
    no decision depends on it. That is the milestone's shape, not an omission, and it is why the
    continuous loop is off by default: an observer nobody reads should not be watching.
    """

    speech_dir: Path
    """Where the audio of a sentence exists while it plays, and where nothing should ever be.

    On ``Ela`` for the reason ``captures`` is: the start-up sweep lives in the ``lifespan``, and
    ``ela.api`` may not name an adapter (architecture rule 27) — so what the API reaches is this
    object and :meth:`sweep_speech`, not :mod:`ela.infrastructure.machine`.
    """

    def sweep_speech(self) -> int:
        """Delete what a crash between making the audio's file and unlinking it would leave.

        Normally zero (ADR 0034 §7). It is not a retention policy — there is nothing kept to
        retain — it is a floor being swept at the one moment ELA is certain to reach.
        """
        return sweep_speech_files(self.speech_dir)

    async def aclose(self) -> None:
        """Release the database connections. Idempotent, as ``dispose`` is."""
        await self.database.dispose()


def _audition_speaker(online: ElevenLabsVoice, player: OnlineSpeechCommand) -> Speak:
    """Say one repository phrase with one voice on one model, and report (ADR 0034 §9).

    The audition is the only caller that chooses a voice, because choosing is what it is for. It
    reaches the provider directly rather than through ``voice.speak_online``: the capability
    requires an authorization, and six voices would be six approvals — which is exactly the cost
    the user refused. What makes that safe is not this function, it is that nothing on this path
    can carry a sentence of the user's: the words are literals in
    :mod:`ela.infrastructure.machine.audition`, and architecture rule 43 keeps them so.
    """

    async def speak(phrase: str, voice_id: str, model: str) -> RawSpeech:
        # The key before the player, as everywhere else on this path: what a person can fix
        # before what the machine happens to be (see ``OnlineSpeechCommand.speak``).
        if online.api_key_missing:
            return RawSpeech(error=SPEECH_NO_KEY)
        if not await player.available():
            return RawSpeech(error=SPEECH_NO_PLAYER)
        said = await online.synthesise(phrase, voice_id=voice_id, model=model)
        if said.failure is not None:
            return RawSpeech(
                error=said.failure.code,
                retryable=said.failure.retryable,
                synthesis_seconds=said.seconds,
            )
        return await player.play(said)

    return speak


def _sample(online: ElevenLabsVoice, player: OnlineSpeechCommand) -> Play:
    """Play the sample the provider already holds — **nothing of ELA's is sent** (ADR 0034 §9).

    Two downloads and no synthesis: no characters, no credits, and no sentence on the wire. It is
    the step that lets somebody hear twenty voices before spending anything, and it is best effort
    — a library voice's metadata answers ``voice_not_found`` sometimes and ``200`` other times,
    measured on the same voice minutes apart.
    """

    async def play(voice_id: str) -> RawSpeech:
        if online.api_key_missing:
            return RawSpeech(error=SPEECH_NO_KEY)
        if not await player.available():
            return RawSpeech(error=SPEECH_NO_PLAYER)
        said = await online.preview(voice_id)
        if said.failure is not None:
            return RawSpeech(error=said.failure.code, retryable=said.failure.retryable)
        return await player.play(said)

    return play


async def build(settings: Settings) -> Ela:
    """Build ELA from ``settings``, in one function and in the order of ADR 0023 §5.

    :raises ConfigurationError: for anything that makes this configuration unusable — a schema
        nobody migrated, a routing table naming a provider that is not registered, an empty one.
        The message names what to change, and the database engine is released before it is raised.

    A provider with **no key** is not one of those: it registers ``UNAVAILABLE``, the router skips
    it, and a call fails with ``provider.unavailable`` without touching the network (ADR 0020 §2).
    ELA starts on a machine where nobody has configured a key — it just cannot call a model.

    One function rather than several: the value of a composition root is that the whole wiring is
    readable in one place, and a reader who has to jump between helpers to know what ELA is bound
    to has lost exactly what this module exists to give.
    """
    clock, ids = SystemClock(), UuidGenerator()
    database = make_engine(settings.persistence.db_url)
    try:
        absent = await missing_tables(database)
        if absent:
            raise ConfigurationError(
                f"the database at {settings.persistence.db_url} is missing the tables "
                f"{', '.join(absent)}. ELA does not migrate on start-up (ADR 0006): run "
                "`uv run alembic upgrade head` first."
            )

        audit = SqlAuditLog(database)
        repository = SqlTaskRepository(database)
        authorizations = SqlAuthorizationStore(database)
        approvals = SqlApprovalStore(database)
        results = SqlExecutionResultStore(database)
        devices = DeviceRegistry(
            SqlDeviceRegistry(database),
            clock,
            audit,
            ids,
            heartbeat_ttl=settings.devices.heartbeat_ttl,
        )
        enrollment = NodeEnrollment(SqlEnrollmentStore(database), devices, clock, ids)

        # The scope of ``workspace.write_note`` and the life of a decision are configuration
        # since M8.3 (ADR 0025 §5, §6): the catalogue and the Guardian have always accepted them,
        # and until now this line was the reason they were constants.
        capabilities = production_catalogue(notes_scope=settings.core.notes_scope)
        guardian = PermissionGuardian(
            capabilities, clock, ids, audit, decision_ttl=settings.core.decision_ttl
        )

        # The order of ADR 0022 §7: a provider, a registry that holds it, a router over the two.
        provider = anthropic_provider(clock, ids, settings=settings.anthropic)
        providers = ProviderRegistry((provider,))
        try:
            router = ModelRouter(settings.routing.policy(), providers)
        except RoutingError as wrong:
            raise ConfigurationError(
                f"ELA_MODEL_ROUTES cannot be used ({wrong.code}): {wrong}. Unset it to fall back "
                "to the routing table of spec §25."
            ) from wrong

        # The same router object for both (ADR 0022 §10): the verifier of ``model.routed_as_asked``
        # recomputes the route, and a second policy would fail every verification.
        root = settings.workspace.workspace_dir
        root.mkdir(mode=WORKSPACE_MODE, parents=True, exist_ok=True)

        # Beside the database and never inside the workspace, and that is a permanent constraint
        # rather than this milestone's convenience (ADR 0029 §1): the workspace is what §23 calls
        # synchronised, and content in a folder something may one day sync leaves the machine
        # without anybody having decided it.
        captures = CaptureStore(settings.captures)

        # The one place that knows which operating system this is (architecture rule 27), for the
        # capture as for the probe: on anything but macOS ELA photographs nothing, and that is a
        # named object with a test rather than a branch buried in an adapter (ADR 0028, ADR 0029).
        #
        # An ``if``, never ``X if darwin else Y`` (ADR 0031, architecture rule 37): the side a
        # conditional *expression* does not take costs the 100% branch gate nothing — no missing
        # line, no missing arc — so a wiring written that way is proved on the runner it happens
        # to run on and nowhere else. As a statement the gate measures both arcs and refuses the
        # direction no test names. Recognition has its own timeout, measured against its own work:
        # unlike the capture it runs inside ELA's process and does degrade under load (2,7x
        # measured), so it does not inherit the capture's number (ADR 0030 §14).
        darwin = platform.system() == "Darwin"
        probe: PerceptionProbe
        screen: ScreenCapturePort
        recognition: TextRecognitionPort
        speech: SpeechPort
        listening: ListeningPort
        # The provider is built on every platform and answers everywhere: without a key or
        # without a voice it reports which of the two is missing and touches no network
        # (ADR 0020 §2's shape, ADR 0034 §5's two codes).
        online = ElevenLabsVoice(settings.elevenlabs)
        scratch = speech_dir_beside(settings.captures.capture_dir)
        # **Not behind the platform branch, and this is the correction of 2026-09-09.** The online
        # voice is not a macOS adapter: it holds a callable and a runner, and it answers
        # ``available()`` by looking for the player. Wiring ``UnsupportedSpeech`` here on Linux put
        # a port that reports *nothing at all* on the path — a silence the tool would have read as
        # success — and it also forced the machine's question in front of the key's. One object,
        # every platform, and it says which of the two things is missing.
        playing = OnlineSpeechCommand(
            synthesise=online.synthesise, unconfigured=online.unconfigured, directory=scratch
        )
        # Created here, with the mode every private directory of ELA has, because ``mkstemp`` on
        # a directory that is not there raises — and the adapter would report that as a player
        # that ended badly, for a player that was never started (found on the machine, M11.3).
        scratch.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
        if darwin:
            probe = DarwinProbe(timeout=settings.perception.probe_timeout)
            screen = ScreenCaptureCommand(timeout=settings.captures.capture_timeout)
            recognition = VisionTextRecognition(timeout=settings.captures.ocr_timeout)
            speech = SaySpeechCommand(
                timeout=settings.voice.voice_timeout, voice=settings.voice.voice_name
            )
            # The transcriber is named by absolute path and checked against its digest, so an
            # unconfigured install answers "I cannot listen" instead of trusting what is there.
            listening = DarwinListening(
                binary=settings.listen.stt_binary,
                model=settings.listen.stt_model,
                expected=(settings.listen.stt_binary_sha256, settings.listen.stt_model_sha256),
                language=settings.listen.listen_language,
                transcribe_timeout=settings.listen.stt_timeout.total_seconds(),
                directory=scratch,
            )
        else:
            probe = UnsupportedProbe()
            screen = UnsupportedScreenCapture()
            recognition = UnsupportedTextRecognition()
            speech = UnsupportedSpeech()
            listening = UnsupportedListening()
        tools = production_tools(
            root=root,
            clock=clock,
            ids=ids,
            router=router,
            providers=providers,
            captures=captures,
            screen=screen,
            probe=probe,
            recognition=recognition,
            languages=settings.captures.ocr_languages,
            listening=listening,
            listen_enabled=settings.listen.listen_enabled,
            speech=speech,
            voice=settings.voice.voice_name,
            voice_enabled=settings.voice.voice_enabled,
            speech_online=playing,
            voice_id=settings.elevenlabs.elevenlabs_voice_id,
            model=settings.elevenlabs.elevenlabs_model,
        )
        verifiers = production_verifiers(root=root, router=router, captures=captures)

        # Which tools this machine has is not something the registry can know (ADR 0016 §4), and
        # without the names no node is ever eligible and every task waits. Since M6.1b this also
        # *reconciles*: a capability added since the last start is written into the row here, and
        # one withdrawn disappears from it (ADR 0035 §2). It comes **before** the heartbeat on
        # purpose — the reconciliation writes the row it read, so it must not be able to lose the
        # sign of life ELA is about to write two lines below.
        await devices.ensure_local(available_tools=tuple(tool.name for tool in tools.tools()))
        # And it is alive: the local node *is* this process, so ELA can say so about itself
        # without claiming anything it does not know (§16). A node registered and never heard
        # from is UNAVAILABLE, and no step would ever be placed on it (ADR 0016 §3). Keeping it
        # alive over time is another matter: every run says so again (ADR 0023 §9), and the
        # periodic heartbeat of a node that reports itself is M8.3.
        await devices.heartbeat(LOCAL_DEVICE_ID)

        engine = TaskEngine(
            repository,
            audit,
            clock,
            ids,
            approvals=approvals,
            actor=ELA_ACTOR,
            orphan_after=settings.core.orphan_after,
        )
        orchestrator = DeviceOrchestrator(devices, tools, audit, ids, clock, verifiers=verifiers)
        assignments = Assignments(
            SqlAssignmentStore(database),
            engine=engine,
            repository=repository,
            results=results,
            devices=devices,
            audit=audit,
            clock=clock,
            ids=ids,
            ttl=settings.core.assignment_ttl,
            cap=settings.core.assignment_cap,
        )
        executor = Executor(
            registry=capabilities,
            tools=tools,
            verifiers=verifiers,
            guardian=guardian,
            engine=engine,
            repository=repository,
            authorizations=authorizations,
            approvals=approvals,
            results=results,
            audit=audit,
            clock=clock,
            ids=ids,
            actor=ELA_ACTOR,
            authorization_ttl=settings.core.authorization_ttl,
            approval_ttl=settings.core.approval_ttl,
        )
        runner = TaskRunner(
            engine=engine,
            orchestrator=orchestrator,
            executor=executor,
            repository=repository,
            results=results,
            audit=audit,
        )

        # The same probe object the capture tool preflights with: one reader of this machine, so
        # "what ELA believes" and "what ELA checks before acting" cannot come from two places
        # that disagree. They are still two *reads* — a periodic belief never decides an action
        # (ADR 0029 §7).
        perception = PerceptionCore(probe, clock, settings.perception)

        # ``live_states`` is data the root supplies, not a judgement the composer makes: the
        # composer may not import the state machine (rule 10, import-linter contract 7), and
        # inventing a second copy of "which states are still alive" is how two lists drift apart.
        # ``LIVE_STATES`` is the engine's own, derived from the terminal set it already owns.
        context = ContextCore(
            repository=repository,
            approvals=approvals,
            devices=devices,
            clock=clock,
            settings=settings.context,
            live_states=LIVE_STATES,
            local_device_id=LOCAL_DEVICE_ID,
        )
    except BaseException:
        await database.dispose()
        raise

    return Ela(
        settings=settings,
        clock=clock,
        ids=ids,
        database=database,
        audit=audit,
        audit_verifier=audit,
        repository=repository,
        authorizations=authorizations,
        approvals=approvals,
        results=results,
        capabilities=capabilities,
        guardian=guardian,
        providers=providers,
        router=router,
        tools=tools,
        verifiers=verifiers,
        devices=devices,
        enrollment=enrollment,
        engine=engine,
        orchestrator=orchestrator,
        executor=executor,
        runner=runner,
        assignments=assignments,
        captures=captures,
        context=context,
        speech=speech,
        speech_dir=scratch,
        speech_online=playing,
        listening=listening,
        audition=Audition(speak=_audition_speaker(online, playing), play=_sample(online, playing)),
        perception=perception,
    )
