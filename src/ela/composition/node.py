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
from dataclasses import dataclass
from pathlib import Path

from ela.composition.errors import ConfigurationError
from ela.composition.settings import NodeConfig
from ela.composition.system import SystemClock, UuidGenerator
from ela.infrastructure.machine import (
    OnlineSpeechCommand,
    SaySpeechCommand,
    UnsupportedSpeech,
    sweep_speech_files,
)
from ela.ports import Clock, IdGenerator, RoutingError, SpeechPort
from ela.providers.anthropic import anthropic_provider
from ela.providers.elevenlabs import ElevenLabsVoice
from ela.providers.registry import ProviderRegistry
from ela.routing import ModelRouter
from ela.tools import DIRECTORY_MODE, ToolRegistry, node_tools

__all__ = ["NodeWorld", "build_node"]


@dataclass(frozen=True, slots=True)
class NodeWorld:
    """A node, built: what it can run, the clock it runs against, and where audio waits.

    Frozen for the reason :class:`~ela.composition.root.Ela` is: the wiring of a running process is
    not something a work order should be able to change — and a work order comes from another
    machine.
    """

    config: NodeConfig
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
) -> NodeWorld:
    """Build a node from ``config``, in one function and with two seams that are declared.

    ``clock`` and ``speech`` default to this machine's, and whoever wants another one **names it** —
    the shape :func:`~ela.composition.root.build` already has, and for the reason its docstring
    gives: "a declared parameter rather than a patched module, because a monkeypatch is invisible
    both to this text and to every architecture rule". ``speech`` is the second seam because the
    conformance suite runs ``voice.speak`` for real, and a node built from settings alone would
    speak out loud during the suite — ``ELA_VOICE_ENABLED`` is true by default and on macOS the
    voice is ``say``. The fake node has had a fake ``SpeechPort`` since M12.2 ("No TCC, no
    microphone, no screen, no keys"); this is how the real one gets the same thing without
    pretending to be something else.

    :raises ConfigurationError: if the routing table names a provider nobody registered, or is
        empty. A provider with **no key** is not that: it registers ``UNAVAILABLE``, the router
        skips it, and ``model.complete`` fails with ``provider.unavailable`` without touching the
        network (ADR 0020 §2) — a node whose user never configured a key still runs, it just
        cannot call a model.
    """
    the_clock = SystemClock() if clock is None else clock
    ids = UuidGenerator()

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
    scratch = config.node.node_state_dir / "speech"
    scratch.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)

    # Built on every platform and answering everywhere: without a key or without a voice it reports
    # which of the two is missing and touches no network (ADR 0034 §5). Not behind the platform
    # branch — it is not a macOS adapter — which is the correction of 2026-09-09.
    online = ElevenLabsVoice(config.elevenlabs)
    playing = OnlineSpeechCommand(
        synthesise=online.synthesise, unconfigured=online.unconfigured, directory=scratch
    )

    # An ``if``, never ``X if darwin else Y`` (architecture rule 37): a ternary's untaken side costs
    # the 100% branch gate nothing, so a platform choice written that way is proved on the runner it
    # happens to run on and nowhere else. M12.4's Windows node arrives here.
    local: SpeechPort
    if speech is not None:
        local = speech
    elif platform.system() == "Darwin":
        local = SaySpeechCommand(timeout=config.voice.voice_timeout, voice=config.voice.voice_name)
    else:
        local = UnsupportedSpeech()

    return NodeWorld(
        config=config,
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
        speech_dir=scratch,
    )
