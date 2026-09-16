"""What a node is built out of, and what it deliberately is not (M12.3 dec. E; ADR 0039).

The list of what is missing is the decision, not an omission: every one of the Core's pieces that
is absent here is something that *decides*, and a node decides nothing (M12.1 D1).
"""

from __future__ import annotations

import os
import platform
import stat
from pathlib import Path

import pytest

from ela.composition import ConfigurationError, NodeConfig, NodeSettings, build_node
from ela.composition.node import NodeWorld, PermissionMode, mkdir_applies_the_acl
from ela.domain import OperatingSystem
from ela.infrastructure.machine import SapiSpeechCommand, SaySpeechCommand, UnsupportedSpeech
from ela.providers.anthropic import AnthropicSettings
from ela.providers.elevenlabs import ElevenLabsSettings
from ela.routing import RoutingSettings
from ela.routing.policy import Route
from ela.testing.fakes import FakeClock, FakeSpeech
from ela.tools import DIRECTORY_MODE, VOICE_ONLINE_TOOL_NAME, VOICE_TOOL_NAME
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
        "os",
        "clock",
        "ids",
        "tools",
        "voices",
        "power",
        "permissions",
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


def test_without_the_seam_the_voice_is_the_named_system_s(tmp_path: Path) -> None:
    """An ``if`` and never a ternary (architecture rule 37): both arms are measured, so the
    platform this did *not* run on is proved too, and M12.4's Windows node arrives here.

    **Named, not patched** (ADR 0031 §3, M12.4 dec. G): until M12.4 this test replaced
    ``platform.system`` for the length of a call, which is the shape ``build_node``'s own docstring
    argues against. The system is a parameter now, and each arm is asked for by name.
    """
    darwin = build_node(config(tmp_path), system="Darwin")
    windows = build_node(config(tmp_path), system="Windows")
    elsewhere = build_node(config(tmp_path), system="Linux")

    assert isinstance(_speech_of(darwin), SaySpeechCommand)
    assert isinstance(_speech_of(windows), SapiSpeechCommand)
    assert isinstance(_speech_of(elsewhere), UnsupportedSpeech)


def test_the_system_it_is_not_told_is_the_one_this_machine_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default, and the one place a patch is the test: what is proved is that an unnamed system
    is read from ``platform.system()`` and not from a constant — which only an answer this machine
    would not give can show."""
    monkeypatch.setattr(platform, "system", lambda: "Linux")

    built = build_node(config(tmp_path))

    assert isinstance(_speech_of(built), UnsupportedSpeech)


@pytest.mark.parametrize(
    ("system", "declared"),
    [
        ("Darwin", OperatingSystem.MACOS),
        ("Windows", OperatingSystem.WINDOWS),
        ("Linux", OperatingSystem.LINUX),
    ],
)
def test_the_operating_system_is_the_one_the_node_was_built_for(
    tmp_path: Path, system: str, declared: OperatingSystem
) -> None:
    """M12.4 dec. A. Until M12.4 a node declared ``"MACOS"`` as a literal wherever it ran. The value
    comes from the map the Core's ``local`` is declared with (``ela.devices.local``), and not from a
    second list here."""
    built = build_node(config(tmp_path), speech=FakeSpeech(), system=system)

    assert built.os is declared


@pytest.mark.parametrize(
    ("system", "permissions"),
    [
        ("Darwin", PermissionMode.BITS),
        ("Windows", PermissionMode.ACL),
        ("Linux", PermissionMode.BITS),
    ],
)
def test_the_secret_is_protected_the_way_the_named_system_allows(
    tmp_path: Path, system: str, permissions: PermissionMode
) -> None:
    """M12.4 dec. B, criterion 15. ``BITS`` where there are permission bits to narrow; ``ACL`` on
    Windows, where ``os.fchmod`` does not exist on 3.12 and the protection is the directory's."""
    built = build_node(config(tmp_path), speech=FakeSpeech(), system=system)

    assert built.permissions is permissions


@pytest.mark.parametrize(("version", "applies"), [((3, 12, 3), False), ((3, 12, 4), True)])
def test_before_3_12_4_mkdir_ignores_the_mode_on_windows(
    version: tuple[int, int, int], applies: bool
) -> None:
    """M12.4 dec. B, criterion 8, the pure half. CVE-2024-4030 (gh-118486): from 3.12.4
    ``os.mkdir(path, 0o700)`` on Windows applies a protected ACL; before it the mode is ignored,
    **in silence**. The version is the whole question, so it is the whole argument."""
    assert mkdir_applies_the_acl(version) is applies


def test_a_windows_python_older_than_3_12_4_is_refused_before_anything_is_built(
    tmp_path: Path,
) -> None:
    """M12.4 dec. B, criterion 8, the composition's half: **the only guarantee**, not a caution.

    The project does not choose the PC's Python — ``uv`` uses the 3.12 it finds, and P0 found a
    3.12.10 it had not installed —, so a 3.12.3 found the same way would be used the same way. And
    refused **before the state directory exists**: made by an interpreter that ignores the mode, it
    would carry the profile's inherited ACL, and a directory that already exists is left as it is.

    The version is named, never patched into the interpreter: the seam ``system`` already has.
    """
    state = tmp_path / "state"

    with pytest.raises(ConfigurationError, match=r"3\.12\.4"):
        build_node(config(state), speech=FakeSpeech(), system="Windows", python_version=(3, 12, 3))

    assert not state.exists()
    assert (
        build_node(
            config(state), speech=FakeSpeech(), system="Windows", python_version=(3, 12, 4)
        ).permissions
        is PermissionMode.ACL
    )


def test_the_refusal_is_windows_s_and_a_mac_does_not_ask_the_version(tmp_path: Path) -> None:
    """``BITS`` narrows the file itself, whatever ``mkdir`` does with its mode."""
    built = build_node(
        config(tmp_path), speech=FakeSpeech(), system="Darwin", python_version=(3, 12, 3)
    )

    assert built.permissions is PermissionMode.BITS


def test_a_system_no_node_knows_stops_it_before_anything_is_built(tmp_path: Path) -> None:
    """A node declares what it runs on, and on a system ELA has no value for it would have nothing
    true to say: refused at start-up, with the system named, as a configuration it cannot use."""
    state = tmp_path / "state"

    with pytest.raises(ConfigurationError, match="Plan 9"):
        build_node(config(state), speech=FakeSpeech(), system="Plan 9")

    assert not state.exists()


def test_the_online_voice_is_a_declared_parameter_too(tmp_path: Path) -> None:
    """M12.4 dec. F: since a node declares only the voices its machine can use, the online voice's
    player decides what a node promises, and a test must be able to name it as it names the local
    one. What was wired into the tool is what the declaration asks."""
    local, online = FakeSpeech(), FakeSpeech()

    built = build_node(config(tmp_path), speech=local, speech_online=online)

    assert _port_of(built, VOICE_ONLINE_TOOL_NAME) is online
    assert built.voices == {VOICE_TOOL_NAME: local, VOICE_ONLINE_TOOL_NAME: online}


def test_the_voices_the_declaration_asks_are_the_ones_the_tools_speak_through(
    tmp_path: Path,
) -> None:
    """Without the seams too: a declaration that asked one port while the tool spoke through
    another would promise what nobody checked."""
    built = build_node(config(tmp_path), system="Darwin")

    assert built.voices[VOICE_TOOL_NAME] is _port_of(built, VOICE_TOOL_NAME)
    assert built.voices[VOICE_ONLINE_TOOL_NAME] is _port_of(built, VOICE_ONLINE_TOOL_NAME)


def _speech_of(built: NodeWorld) -> object:
    return _port_of(built, VOICE_TOOL_NAME)


def _port_of(built: NodeWorld, name: str) -> object:
    """The port a voice tool was built with, found by the tool's name and not by its position."""
    (tool,) = (one for one in built.tools.tools() if one.name == name)
    return tool._speech  # type: ignore[attr-defined]  # noqa: SLF001 — not on the public surface


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits: Windows has no 0o700")
def test_the_state_directory_is_born_0o700_where_no_core_made_it_first(tmp_path: Path) -> None:
    """M12.3b. The directory that holds the node's secret is ``0o700`` from the moment it exists.

    On this Mac ``~/.ela`` was always ``0o700``, and not because of the node: the Core had made it
    first, as the parent of its database. On a machine that runs **only** a node nobody had, and
    ``build_node`` made ``<state>/speech`` with ``parents=True`` — which makes every missing parent
    with the default mode — so the state directory came out ``0o755`` and ``write_identity``'s own
    ``mkdir(0o700)`` found it already there. ADR 0039 §6 says "in a ``0o700`` directory".

    The ``umask`` is the test, as in ``tests/node/test_state.py``: with ``0o000`` a directory made
    with the default mode shows up as ``0o777``, whatever this machine's umask is.
    """
    state = tmp_path / "a-machine-with-no-core" / ".ela"
    was = os.umask(0o000)
    try:
        build_node(config(state), speech=FakeSpeech())
    finally:
        os.umask(was)

    assert stat.S_IMODE(state.stat().st_mode) == DIRECTORY_MODE
    assert stat.S_IMODE((state / "speech").stat().st_mode) == DIRECTORY_MODE


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
