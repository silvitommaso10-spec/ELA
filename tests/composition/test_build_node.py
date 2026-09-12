"""What a node is built out of, and what it deliberately is not (M12.3 dec. E; ADR 0039).

The list of what is missing is the decision, not an omission: every one of the Core's pieces that
is absent here is something that *decides*, and a node decides nothing (M12.1 D1).
"""

from __future__ import annotations

import platform
from pathlib import Path

import pytest

from ela.composition import ConfigurationError, NodeConfig, NodeSettings, build_node
from ela.composition.node import NodeWorld
from ela.infrastructure.machine import SaySpeechCommand, UnsupportedSpeech
from ela.providers.anthropic import AnthropicSettings
from ela.providers.elevenlabs import ElevenLabsSettings
from ela.routing import RoutingSettings
from ela.routing.policy import Route
from ela.testing.fakes import FakeClock, FakeSpeech
from ela.tools.settings import VoiceSettings


def config(directory: Path, **sections: object) -> NodeConfig:
    base = {
        "node": NodeSettings(node_state_dir=directory),
        "anthropic": AnthropicSettings(),
        "routing": RoutingSettings(),
        "voice": VoiceSettings(),
        "elevenlabs": ElevenLabsSettings(),
    }
    return NodeConfig(**{**base, **sections})  # type: ignore[arg-type]


def test_it_builds_the_four_tools_that_travel_and_no_others(tmp_path: Path) -> None:
    """Three families, four classes — and what is missing is the point: ``workspace.write_note``,
    the screen and the microphone stay on the Core, because their verifiers read *that* machine."""
    built = build_node(config(tmp_path), speech=FakeSpeech())

    assert {tool.name for tool in built.tools.tools()} == {
        "core-echo",
        "model-complete",
        "voice-speak",
        "voice-speak-online",
    }


def test_it_builds_nothing_that_decides(tmp_path: Path) -> None:
    """No database, no engine, no Guardian, no audit log, no registry, no orchestrator, no API.

    Asserted over the object's own fields rather than by naming absences one by one: a field added
    here in a later milestone has to be looked at, which is the point of a closed list.
    """
    built = build_node(config(tmp_path), speech=FakeSpeech())

    assert {field for field in NodeWorld.__dataclass_fields__} == {
        "config",
        "clock",
        "ids",
        "tools",
        "speech_dir",
    }
    assert not hasattr(built, "database")
    assert not hasattr(built, "guardian")
    assert not hasattr(built, "devices")


def test_a_node_needs_no_token_of_the_core_to_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 11. ``Settings.load`` refuses to start without ``ELA_API_TOKEN`` — "ELA does not
    open an unauthenticated API" — and a node opens none, so it must not be stopped by that line.

    The precedent is ``cli/client.py``'s: a command must not refuse to answer because of a line
    that is not about the question being asked. On a second machine, where nothing of the Core is
    configured, this is the normal case and not the exception.
    """
    from ela.composition import Settings

    monkeypatch.delenv("ELA_API_TOKEN", raising=False)

    with pytest.raises(ConfigurationError, match="ELA_API_TOKEN"):
        Settings.load()

    assert NodeConfig.load().node.node_core_url


def test_a_routing_table_it_cannot_use_stops_it_with_the_variable_named(tmp_path: Path) -> None:
    """And the message says the thing a node's user needs to know and the Core's does not: the
    table has to be the Core's, or every call this node answers fails verification (M12.2 dec. L).
    """
    with pytest.raises(ConfigurationError, match="ELA_MODEL_ROUTES"):
        build_node(
            config(
                tmp_path,
                routing=RoutingSettings(
                    model_routes={"planning": Route(providers=("nessuno",), profile="quality")}
                ),
            ),
            speech=FakeSpeech(),
        )


def test_a_provider_with_no_key_is_not_a_broken_configuration(tmp_path: Path) -> None:
    """ADR 0020 §2: it registers UNAVAILABLE, the router skips it, and a call fails without
    touching the network. A node whose user never configured a key still runs."""
    built = build_node(config(tmp_path), speech=FakeSpeech())

    assert built.tools.tools()


def test_the_clock_is_a_declared_parameter_and_not_a_patched_module(tmp_path: Path) -> None:
    """Dec. H. ``Tool.execute`` compares the decision against the clock of whoever executes, so
    this is the difference between a node that runs calls and one that refuses every one."""
    clock = FakeClock()

    built = build_node(config(tmp_path), clock=clock, speech=FakeSpeech())

    assert built.clock is clock


def test_the_voice_is_a_declared_parameter_too(tmp_path: Path) -> None:
    """Dec. G, and it is not a convenience: the conformance suite runs ``voice.speak`` for real,
    and a node built from settings alone would speak out loud during the suite."""
    speech = FakeSpeech()

    built = build_node(config(tmp_path), speech=speech)

    # **What was wired, not what it is called.** The first version asserted only the tool's name,
    # which is true whatever got wired — so a ``build_node`` that ignored this parameter passed,
    # and the conformance suite would then have spoken out loud on this Mac, which is the one
    # thing the parameter exists to prevent.
    assert _speech_of(built) is speech


def test_without_the_seam_the_voice_is_this_machine_s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An ``if`` and never a ternary (architecture rule 37): both arms are measured, so the
    platform this did *not* run on is proved too, and M12.4's Windows node arrives here."""
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    darwin = build_node(config(tmp_path))

    monkeypatch.setattr(platform, "system", lambda: "Linux")
    elsewhere = build_node(config(tmp_path))

    assert isinstance(_speech_of(darwin), SaySpeechCommand)
    assert isinstance(_speech_of(elsewhere), UnsupportedSpeech)


def _speech_of(built: NodeWorld) -> object:
    local = built.tools.get(built.tools.tools()[2].capability_id)
    return local._speech  # noqa: SLF001 — what was wired is not on the public surface


def test_it_sweeps_the_audio_a_crash_would_have_left(tmp_path: Path) -> None:
    """A node plays audio too, and start-up is the one moment it is certain to reach
    (ADR 0034 §7). Normally zero: the file loses its name one syscall after it is made."""
    built = build_node(config(tmp_path), speech=FakeSpeech())
    left = built.speech_dir / "ela-speech-abandoned.aiff"
    left.write_bytes(b"")

    assert built.sweep_speech() == 1
    assert not left.exists()


def test_the_speech_directory_is_beside_the_node_s_state_and_never_in_a_workspace(
    tmp_path: Path,
) -> None:
    """ADR 0029 §1, the reason ``ELA_CAPTURE_DIR`` exists: private working files of ELA go where
    nothing syncs them. A node has no workspace and no capture store, so what a test redirects
    here is ``ELA_NODE_STATE_DIR``."""
    built = build_node(config(tmp_path), speech=FakeSpeech())

    assert built.speech_dir.parent == tmp_path
    assert built.speech_dir.is_dir()


def test_a_node_variable_that_is_wrong_stops_it_naming_the_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whoever reads this wrote the ``.env``, so it is a sentence and never a ``ValidationError``
    dumped on a terminal (ADR 0023 §2)."""
    monkeypatch.setenv("ELA_NODE_RETRY_CEILING", "0")

    with pytest.raises(ConfigurationError, match="ELA_NODE_RETRY_CEILING"):
        NodeConfig.load()


def test_a_node_variable_that_cannot_be_read_stops_it_the_same_way(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed JSON is a ``SettingsError`` and not a ``ValidationError`` — a different exception
    on the way out, and it must not escape as a stack trace either."""
    monkeypatch.setenv("ELA_MODEL_ROUTES", "{non json")

    with pytest.raises(ConfigurationError, match="ELA_MODEL_ROUTES"):
        NodeConfig.load()
