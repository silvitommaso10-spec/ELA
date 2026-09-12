"""The registries of tools and verifiers (spec §28, §63; ADR 0013 §10, ADR 0014 §2).

:class:`ToolRegistry` implements :class:`~ela.ports.ToolRegistryPort` and
:class:`VerifierRegistry` implements :class:`~ela.ports.VerifierRegistryPort`: one entry per
capability, fixed at construction. Like the capability catalogue (ADR 0010 §1) neither has a
way to change after it is built: what ELA can *execute* and what it can *verify* are decided
when the registries are, and every entry is keyed by its own ``capability_id`` — there is no
argument through which a tool or a verifier could claim another capability.
:func:`tools_v01` and :func:`verifiers_v01` build the pairs of v0.1, mirrors of
``catalogue_v01``; :func:`production_tools` and :func:`production_verifiers` build what the
composition root runs, mirrors of ``production_catalogue``. Every tool has its verifier, and a
capability without both is not executable.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from types import MappingProxyType

from ela.domain import CapabilityId
from ela.ports import (
    AlreadyExistsError,
    Clock,
    IdGenerator,
    ListeningPort,
    ModelRouterPort,
    PerceptionProbe,
    ProviderRegistryPort,
    ScreenCapturePort,
    SpeechPort,
    TextRecognitionPort,
    ToolPort,
    VerifierPort,
)
from ela.tools.echo import EchoTool
from ela.tools.errors import (
    NotIdempotentError,
    SilentVerifierError,
    ToolNotFound,
    VerifierNotFound,
)
from ela.tools.listen import ListenTool
from ela.tools.model import ModelCompleteTool
from ela.tools.notes import WriteNoteTool
from ela.tools.screen import CaptureScreenTool, CaptureStore
from ela.tools.screen_text import ReadScreenTextTool
from ela.tools.verifiers import (
    ONLINE_SPEECH_VERIFIER_NAME,
    CaptureScreenVerifier,
    EchoVerifier,
    ListenVerifier,
    ModelCompleteVerifier,
    ReadScreenTextVerifier,
    SpeakVerifier,
    WriteNoteVerifier,
)
from ela.tools.voice import SpeakTool
from ela.tools.voice_online import VOICE_SPEAK_ONLINE, SpeakOnlineTool

__all__ = [
    "ToolRegistry",
    "VerifierRegistry",
    "node_tools",
    "production_tools",
    "production_verifiers",
    "tools_v01",
    "verifiers_v01",
]


class ToolRegistry:
    """Tools by capability id, frozen at construction (port ``ToolRegistryPort``).

    **Every tool declares whether it is idempotent, and none may stay silent** (M5.3, then M7.2).
    Until M7.2 the registry accepted only ``True``, because crash window 7a was repaired by
    running the tool again and that repair is safe only while twice is once. ADR 0021 §1 brings
    the STARTED protocol the guard was waiting for, so ``False`` is now a legal answer: the
    executor writes a STARTED record before such a tool acts and never runs it twice for one
    step. What is still refused is a tool that declares *nothing*, or something that is not a
    boolean — the executor reads this flag to choose between repeating a run and refusing to,
    and a doubt is not a yes (§33).
    """

    __slots__ = ("_tools",)

    def __init__(self, tools: Iterable[ToolPort]) -> None:
        table: dict[CapabilityId, ToolPort] = {}
        for tool in tools:
            declared = getattr(tool, "idempotent", None)
            if not isinstance(declared, bool):
                raise NotIdempotentError(tool.capability_id, tool.name, declared)
            if tool.capability_id in table:
                raise AlreadyExistsError("tool", tool.capability_id)
            table[tool.capability_id] = tool
        self._tools: Mapping[CapabilityId, ToolPort] = MappingProxyType(table)

    def get(self, capability_id: CapabilityId) -> ToolPort:
        """The tool for this capability; :class:`ToolNotFound` if there is none."""
        try:
            return self._tools[capability_id]
        except KeyError:
            raise ToolNotFound(capability_id) from None

    def tools(self) -> tuple[ToolPort, ...]:
        """Every tool, in construction order."""
        return tuple(self._tools.values())


class VerifierRegistry:
    """Verifiers by capability id, frozen at construction (port ``VerifierRegistryPort``).

    **Every verifier declares whether it reads the machine it runs on, and none may stay silent**
    (M12.2, ADR 0038 §14) — the rule :class:`ToolRegistry` applies to ``idempotent``. The
    orchestrator reads the flag to keep on this machine a capability whose verifier reads this
    machine's disk, and a verifier that forgot to say must not read as one that may travel.
    """

    __slots__ = ("_verifiers",)

    def __init__(self, verifiers: Iterable[VerifierPort]) -> None:
        table: dict[CapabilityId, VerifierPort] = {}
        for verifier in verifiers:
            declared = getattr(verifier, "reads_the_machine", None)
            if not isinstance(declared, bool):
                raise SilentVerifierError(verifier.capability_id, verifier.name, declared)
            if verifier.capability_id in table:
                raise AlreadyExistsError("verifier", verifier.capability_id)
            table[verifier.capability_id] = verifier
        self._verifiers: Mapping[CapabilityId, VerifierPort] = MappingProxyType(table)

    def get(self, capability_id: CapabilityId) -> VerifierPort:
        """The verifier of this capability; :class:`VerifierNotFound` if there is none."""
        try:
            return self._verifiers[capability_id]
        except KeyError:
            raise VerifierNotFound(capability_id) from None

    def verifiers(self) -> tuple[VerifierPort, ...]:
        """Every verifier, in construction order."""
        return tuple(self._verifiers.values())


def tools_v01(
    *,
    root: Path | str,
    clock: Clock,
    ids: IdGenerator,
    router: ModelRouterPort,
    providers: ProviderRegistryPort,
) -> ToolRegistry:
    """The three tools of v0.1, in the order of the catalogue (§29).

    ``router`` decides which provider answers ``model.complete`` and with which profile (§25,
    ADR 0022), and ``providers`` is where the name it chose is resolved. Both are mandatory: a
    registry that quietly dropped the third tool when nobody passed them would make a capability
    disappear from what ELA can do, and a provider with no credentials already has a way to say
    so — it registers ``UNAVAILABLE``, the router skips it, and if there is nothing else the call
    fails with ``provider.unavailable`` without touching the network (ADR 0020 §2).
    """
    return ToolRegistry(
        (
            EchoTool(clock, ids),
            WriteNoteTool(root, clock, ids),
            ModelCompleteTool(router, providers, clock, ids),
        )
    )


def production_tools(
    *,
    root: Path | str,
    clock: Clock,
    ids: IdGenerator,
    router: ModelRouterPort,
    providers: ProviderRegistryPort,
    captures: CaptureStore,
    screen: ScreenCapturePort,
    probe: PerceptionProbe,
    recognition: TextRecognitionPort,
    languages: tuple[str, ...],
    listening: ListeningPort,
    listen_enabled: bool,
    speech: SpeechPort,
    voice: str,
    voice_enabled: bool,
    speech_online: SpeechPort,
    voice_id: str | None,
    model: str,
) -> ToolRegistry:
    """What the composition root builds: v0.1's three, plus what the phases after it added.

    ``production_`` says **when** it is used; :func:`tools_v01` says **what it contains**. Both
    exist and neither is redundant — ADR 0029 §13: *v0.1 does not get folded into, it gets stood
    beside*, and the precedent is M10.1's, where ``/perception`` was left out of the v0.1 route
    count rather than quietly folded in.
    """
    return ToolRegistry(
        (
            *tools_v01(root=root, clock=clock, ids=ids, router=router, providers=providers).tools(),
            CaptureScreenTool(captures, screen, probe, clock, ids),
            ListenTool(captures, listening, probe, clock, ids, enabled=listen_enabled),
            ReadScreenTextTool(captures, recognition, clock, ids, languages=languages),
            SpeakTool(speech, clock, ids, voice=voice, enabled=voice_enabled),
            SpeakOnlineTool(
                speech_online, clock, ids, voice_id=voice_id, model=model, enabled=voice_enabled
            ),
        )
    )


def verifiers_v01(*, root: Path | str, router: ModelRouterPort) -> VerifierRegistry:
    """The verifiers of the tools of :func:`tools_v01`, on the same workspace ``root``.

    No clock and no id source: a verifier creates no entity. ``router`` is the **same** port the
    tools were given, and it is asked the same question again: a verifier that read the route out
    of the result would be checking the tool's word, and a verifier that had a policy of its own
    would be checking a second opinion (ADR 0022 §10). No provider: the verifier of
    ``model.complete`` reads the result of the call and never makes another one.
    """
    return VerifierRegistry(
        (EchoVerifier(), WriteNoteVerifier(root), ModelCompleteVerifier(router))
    )


def node_tools(
    *,
    clock: Clock,
    ids: IdGenerator,
    router: ModelRouterPort,
    providers: ProviderRegistryPort,
    speech: SpeechPort,
    voice: str,
    voice_enabled: bool,
    speech_online: SpeechPort,
    voice_id: str | None,
    model: str,
) -> ToolRegistry:
    """What a node runs: the four capabilities that travel (M12.1 D15, M12.2 dec. L, M12.3 dec. F).

    Three families — the echo, the model, the voice — and four classes, because the voice has two
    implementations and both are a voice. Beside :func:`production_tools` and :func:`tools_v01`
    rather than derived from either, for the reason ADR 0029 §13 gives and this milestone needs
    twice over: a list is something a reader can see and a test can pin, and a subset computed at
    run time would make **a capability added to the Core start travelling by itself** — which is
    exactly the decision D15 reserves for a person.

    What is missing is the point. ``workspace.write_note``, the screen and the microphone stay on
    the Core because their verifiers read *this* machine, and the first of the three is the one
    that matters: its verifier rereads the Core's workspace and its sha256, so a note written on a
    node would be checked against a folder the node never touched — and could come back **true**,
    for a note the Core had of its own. A false yes is worse than a failure, which is why the
    filter refuses that node before the question is asked (M12.2 dec. L).

    No workspace root and no capture store among the arguments, and that is the shape of the
    claim: a node has nothing to write them to.
    """
    return ToolRegistry(
        (
            EchoTool(clock, ids),
            ModelCompleteTool(router, providers, clock, ids),
            SpeakTool(speech, clock, ids, voice=voice, enabled=voice_enabled),
            SpeakOnlineTool(
                speech_online, clock, ids, voice_id=voice_id, model=model, enabled=voice_enabled
            ),
        )
    )


def production_verifiers(
    *, root: Path | str, router: ModelRouterPort, captures: CaptureStore
) -> VerifierRegistry:
    """The verifiers of :func:`production_tools`, one per capability.

    ``captures`` is the same store the tool writes into, and only its *directory* and its TTL are
    taken: the verifier reaches the read-only classification of :mod:`ela.tools.captures` and
    never the store's writing side (architecture rule 18). See :func:`production_tools` for why
    this and :func:`verifiers_v01` both exist.
    """
    return VerifierRegistry(
        (
            *verifiers_v01(root=root, router=router).verifiers(),
            CaptureScreenVerifier(captures.directory, captures.settings.capture_ttl),
            ListenVerifier(captures.directory, captures.settings.capture_ttl),
            ReadScreenTextVerifier(captures.directory, captures.settings.capture_ttl),
            SpeakVerifier(),
            # The same class, a second capability: two permissions over one act, verified by the
            # same two conditions (ADR 0034 §6). What differs is which grant was spent.
            SpeakVerifier(VOICE_SPEAK_ONLINE, name=ONLINE_SPEECH_VERIFIER_NAME),
        )
    )
