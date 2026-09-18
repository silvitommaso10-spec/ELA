"""What a node is made of — and, as much to the point, what it is not (M12.3 dec. E; ADR 0039).

A node is not a small ELA. It holds the four tools that travel, a clock of its own, and the two
things needed to call a model; it holds no database, no task engine, no Guardian, no audit log, no
device registry, no orchestrator and no API. That list is the decision, not an omission: every one
of those is something that *decides*, and a node decides nothing (M12.1 D1).

Why the wiring passes through here at all, when a node could build its own tools: architecture rule
27 — only ``ela.composition`` names concrete implementations. And ADR 0024 §2 has already written
what a second process that builds a whole world does: "two processes writing the same database
would have the lock of ``run`` in one of them", and "a world built declares the node ``local``
alive" and then exits, leaving a TTL valid for a process that is no longer there. A node calling
:func:`~ela.composition.root.build` would be that bug; :func:`build_node` is the composition root
composing **less**.
"""

from __future__ import annotations

import platform
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Final

from ela.composition.errors import ConfigurationError
from ela.composition.settings import NodeConfig
from ela.composition.system import PowerReading, SystemClock, UuidGenerator, power_reading
from ela.devices import UnsupportedOperatingSystemError, operating_system
from ela.domain import OperatingSystem
from ela.infrastructure.machine import (
    AFPLAY,
    OnlineSpeechCommand,
    SapiSpeechCommand,
    SaySpeechCommand,
    UnsupportedSpeech,
    sweep_speech_files,
)
from ela.ports import Clock, IdGenerator, RoutingError, SpeechPort
from ela.providers.anthropic import anthropic_provider
from ela.providers.elevenlabs import ElevenLabsVoice
from ela.providers.registry import ProviderRegistry
from ela.routing import ModelRouter
from ela.tools import (
    DIRECTORY_MODE,
    VOICE_ONLINE_TOOL_NAME,
    VOICE_TOOL_NAME,
    ToolRegistry,
    node_tools,
)

__all__ = [
    "ACL_SINCE",
    "NodeWorld",
    "PermissionMode",
    "build_node",
    "mkdir_applies_the_acl",
    "online_player",
]


class PermissionMode(StrEnum):
    """How a node's secret is protected on the machine it was built for (M12.4 dec. B).

    **Here, and not in** :mod:`ela.node.state` **which reads it**, for a reason of imports:
    ``ela.node`` imports this module, and this package's ``__init__`` imports it too, so a
    composition that imported ``ela.node.state`` would find one of the two half-initialised. The
    direction stays one: ``ela.node`` reads from the composition, never the other way.
    """

    BITS = "bits"
    """Permission bits: the file is narrowed to ``0o600`` with ``fchmod`` before its first byte, and
    ``O_NOFOLLOW`` refuses a planted link. Darwin and Linux."""

    ACL = "acl"
    """The directory's ACL: made first with ``mkdir(0o700)``, which on Windows applies a protected
    ACL — SYSTEM, Administrators, OWNER RIGHTS, nothing inherited — that the file inherits the
    moment it exists. No ``fchmod``, which Windows has only from 3.13, and no ``O_NOFOLLOW``, which
    it has not at all. Measured on the user's PC by P2 (2026-09-15)."""


ACL_SINCE: Final = (3, 12, 4)
"""The first Python whose ``os.mkdir(path, 0o700)`` protects a directory on Windows (CVE-2024-4030,
gh-118486). Before it the mode is ignored **in silence**."""


def mkdir_applies_the_acl(version: tuple[int, int, int]) -> bool:
    """Whether a Windows Python of ``version`` gives a new ``0o700`` directory the protected ACL.

    The part that decides, apart from what the world answers (ADR 0031 §5): the composition hands it
    ``sys.version_info``, and a test hands it the two versions either side of the line.
    """
    return version >= ACL_SINCE


def online_player(system: str) -> str | None:
    """The player of the online voice on the named system: ``afplay`` on Darwin, nobody elsewhere.

    One place that chooses (M12.4 dec. E, F), asked by :func:`build_node` and by whoever needs to
    know what it would build — the conformance kit, which fakes a player only where this names a
    real one. What *nobody* is, and why it is ``None``, is said once, in the docstring of
    ``OnlineSpeechCommand``.
    """
    if system == "Darwin":
        return AFPLAY
    return None


@dataclass(frozen=True, slots=True)
class NodeWorld:
    """A node, built: what it can run, the clock it runs against, and where audio waits.

    Frozen for the reason :class:`~ela.composition.root.Ela` is: the wiring of a running process is
    not something a work order should be able to change — and a work order comes from another
    machine.
    """

    config: NodeConfig
    os: OperatingSystem
    """The system this node was built for, and what it declares (M12.4 dec. A).

    The composition's answer and never the cycle's: until M12.4 the declaration said ``"MACOS"`` as
    a literal, and a node on any other machine would have told the Core it was a Mac.
    """
    clock: Clock
    """**The node's own, and it is a parameter** (M12.1 D1).

    ``Tool.execute`` compares the ``PermissionDecision`` against the clock of whoever executes, so
    this is not a convenience for the tests: it is the difference between a node that runs a call
    and a node that answers ``refused`` to every one of them. The conformance suite is the caller
    that needs to name it, its Core mints decisions on a clock stopped in 2026, and an hour of real
    waiting is not a test (ADR 0038 §18).
    """
    ids: IdGenerator
    tools: ToolRegistry
    voices: Mapping[str, SpeechPort]
    """The machine's half of each tool that has one, by tool name (M12.4 dec. F).

    What the declaration asks before it promises a tool. A voice whose port answers ``available()``
    false is still built — an order that reaches it answers as it always did — but it is not
    declared, because the orchestrator filters by name and would otherwise place a step on a
    machine that cannot run it. Only the voices have a half that reads the machine.
    """
    power: PowerReading
    """What this machine runs on, read on every sign of life (M12.3c).

    The composition's choice for the named system — ``pmset`` on Darwin, ``powershell.exe`` on
    Windows, nobody elsewhere — and never the cycle's: the node asks and sends, and does not know
    which machine answered. Until M12.3c no node sent a power source at all, and the orchestrator
    weighed one nobody could produce.
    """
    permissions: PermissionMode
    """How the secret is written on this machine, chosen for the named system (M12.4 dec. B).

    The composition's and never the writer's: until M12.4 ``write_identity`` asked ``os`` whether it
    had ``O_NOFOLLOW`` and called ``fchmod`` unconditionally, and on the PC every first run died on
    that line after ``O_EXCL`` had made the file and before its first byte.
    """
    speech_dir: Path

    def sweep_speech(self) -> int:
        """Delete what a crash between making the audio's file and unlinking it would leave.

        Normally zero, and the same floor :class:`~ela.composition.root.Ela` sweeps for the same
        reason: a node plays audio too, and start-up is the one moment it is certain to reach.
        """
        return sweep_speech_files(self.speech_dir)


def build_node(
    config: NodeConfig,
    *,
    clock: Clock | None = None,
    speech: SpeechPort | None = None,
    speech_online: SpeechPort | None = None,
    system: str | None = None,
    power: PowerReading | None = None,
    python_version: tuple[int, int, int] | None = None,
) -> NodeWorld:
    """Build a node from ``config``, in one function and with six seams that are declared.

    ``system`` is what ``platform.system()`` answers, and it defaults to this machine's answer. It
    is a parameter so that a platform choice is proved by **naming** the system and never by being
    it (ADR 0031 §3): the conformance kit names the system it recites, and the composition it builds
    is then the same on every runner the suite happens to run on (M12.4 dec. G).

    ``clock`` and ``speech`` default to this machine's, and whoever wants another one **names it** —
    the shape :func:`~ela.composition.root.build` already has, and for the reason its docstring
    gives: "a declared parameter rather than a patched module, because a monkeypatch is invisible
    both to this text and to every architecture rule". ``speech`` is the second seam because the
    conformance suite runs ``voice.speak`` for real, and a node built from settings alone would
    speak out loud during the suite — ``ELA_VOICE_ENABLED`` is true by default and on macOS the
    voice is ``say``. The fake node has had a fake ``SpeechPort`` since M12.2 ("No TCC, no
    microphone, no screen, no keys"); this is how the real one gets the same thing without
    pretending to be something else.

    ``speech_online`` is the fourth, for the reason the declaration gave it (M12.4 dec. F): a node
    declares only the voices its machine can use, so the online voice's player — which looks for
    ``afplay`` on the filesystem — decides what a node promises, and a test asserting a declaration
    would otherwise say four tools on macOS and three on Ubuntu.

    ``power`` is the fifth, and it defaults to the reader of the named system (M12.3c). A test that
    asserts what a heartbeat carries names it, for the reason ``speech`` is named: otherwise the
    answer would depend on whether the machine running the suite is plugged in.

    ``python_version`` is the sixth, and it defaults to this interpreter's (M12.4 dec. B): on
    Windows a Python older than 3.12.4 is refused, and the refusal is proved by **naming** a
    version, never by patching the interpreter — the argument ``system`` already makes.

    :raises ConfigurationError: for a system no node of ELA knows (``operating_system``), before
        anything is built: a node declares what it runs on, and there it would have nothing true to
        say.

    :raises ConfigurationError: on Windows, for a Python older than :data:`ACL_SINCE`, before the
        state directory exists (M12.4 dec. B). **The only guarantee** of the directory that holds
        the secret: the project does not choose the PC's Python — ``uv`` uses the 3.12 it finds —,
        and a directory made by an interpreter that ignores the mode would keep the profile's
        inherited ACL, because one that already exists is left as it is.

    :raises ConfigurationError: if the routing table names a provider nobody registered, or is
        empty. A provider with **no key** is not that: it registers ``UNAVAILABLE``, the router
        skips it, and ``model.complete`` fails with ``provider.unavailable`` without touching the
        network (ADR 0020 §2) — a node whose user never configured a key still runs, it just
        cannot call a model.
    """
    the_clock = SystemClock() if clock is None else clock
    ids = UuidGenerator()
    # A statement and not ``platform.system() if system is None else system``: architecture rule 37,
    # because the arm a ternary does not take costs the 100% branch gate nothing.
    if system is None:
        system = platform.system()
    # The same map the Core's ``local`` is declared with, and not a second list beside it.
    try:
        declared = operating_system(system)
    except UnsupportedOperatingSystemError as unknown:
        raise ConfigurationError(
            f"ELA has no node for this operating system ({system}): a node declares what it runs "
            "on, and here it would have nothing true to say."
        ) from unknown
    if python_version is None:
        python_version = sys.version_info[:3]
    # One statement per system that protects the secret differently, and before anything is built:
    # the refusal must come before the state directory exists (dec. B).
    permissions = PermissionMode.BITS
    if system == "Windows":
        if not mkdir_applies_the_acl(python_version):
            raise ConfigurationError(
                f"this Python is {'.'.join(map(str, python_version))}, and a node on Windows needs "
                f"{'.'.join(map(str, ACL_SINCE))} or later: before it, os.mkdir ignores the mode "
                "without saying so, and the directory that holds the node's secret would keep the "
                "ACL inherited from the profile. Install a later 3.12 and run the node again."
            )
        permissions = PermissionMode.ACL
    if power is None:
        power = power_reading(system)

    # The order of ADR 0022 §7, and the same three objects the Core builds: a provider, a registry
    # that holds it, a router over the two. The key is the **node's** — the order carries the call,
    # never the credentials (M12.1 D1) — and the routing table must be the Core's, or the verifier
    # of ``model.routed_as_asked`` recomputes a different route and refuses whatever came back
    # (M12.2 dec. L). On one machine that is one ``.env`` and invisible; on two it is the first
    # thing to break, which is why criterion 12 makes it fail with a reason.
    providers = ProviderRegistry((anthropic_provider(the_clock, ids, settings=config.anthropic),))
    try:
        router = ModelRouter(config.routing.policy(), providers)
    except RoutingError as wrong:
        raise ConfigurationError(
            f"ELA_MODEL_ROUTES cannot be used ({wrong.code}): {wrong}. On a node it must be the "
            "same table the Core has, or every call the node answers fails verification."
        ) from wrong

    # Beside the node's own state and never inside a workspace — a node has none — for the reason
    # ADR 0029 §1 gives about ``ELA_CAPTURE_DIR``: private working files of ELA go where nothing
    # syncs them. Not derived from a capture store as the Core's is, because a node has no capture
    # store either: what a test redirects here is ``ELA_NODE_STATE_DIR``.
    #
    # The state directory **first**, with its own mode (M12.3b). ``Path.mkdir(parents=True)`` makes
    # every missing parent with the default mode, so making ``speech/`` first — as this did until
    # M12.3b — left the directory that holds the node's secret ``0o755`` on any machine where the
    # Core had not made it already; ``write_identity``'s ``mkdir(0o700)`` then found it there.
    config.node.node_state_dir.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
    scratch = config.node.node_state_dir / "speech"
    scratch.mkdir(mode=DIRECTORY_MODE, exist_ok=True)

    # Built on every platform and answering everywhere: without a key or without a voice it reports
    # which of the two is missing and touches no network (ADR 0034 §5). Not behind the platform
    # branch — it is not a macOS adapter — which is the correction of 2026-09-09.
    #
    # Its **player** is the named system's, chosen in one place: :func:`online_player`.
    playing: SpeechPort
    if speech_online is not None:
        playing = speech_online
    else:
        online = ElevenLabsVoice(config.elevenlabs)
        playing = OnlineSpeechCommand(
            synthesise=online.synthesise,
            unconfigured=online.unconfigured,
            directory=scratch,
            binary=online_player(system),
        )

    # An ``if``, never ``X if darwin else Y`` (architecture rule 37): a ternary's untaken side costs
    # the 100% branch gate nothing, so a platform choice written that way is proved on the runner it
    # happens to run on and nowhere else. The Windows node's voice is System.Speech (M12.4 dec. D).
    local: SpeechPort
    if speech is not None:
        local = speech
    elif system == "Darwin":
        local = SaySpeechCommand(timeout=config.voice.voice_timeout, voice=config.voice.voice_name)
    elif system == "Windows":
        local = SapiSpeechCommand(timeout=config.voice.voice_timeout, voice=config.voice.voice_name)
    else:
        local = UnsupportedSpeech()

    return NodeWorld(
        config=config,
        os=declared,
        clock=the_clock,
        ids=ids,
        tools=node_tools(
            clock=the_clock,
            ids=ids,
            router=router,
            providers=providers,
            speech=local,
            voice=config.voice.voice_name,
            voice_enabled=config.voice.voice_enabled,
            speech_online=playing,
            voice_id=config.elevenlabs.elevenlabs_voice_id,
            model=config.elevenlabs.elevenlabs_model,
        ),
        voices=MappingProxyType({VOICE_TOOL_NAME: local, VOICE_ONLINE_TOOL_NAME: playing}),
        power=power,
        permissions=permissions,
        speech_dir=scratch,
    )
