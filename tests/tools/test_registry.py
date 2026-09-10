"""``ToolRegistry``, ``VerifierRegistry``, ``tools_v01`` and ``verifiers_v01`` beyond the
contract (ADR 0013 §10, ADR 0014 §2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ela.domain import CapabilityId
from ela.permissions import MODEL_COMPLETE, catalogue_v01
from ela.ports import AlreadyExistsError
from ela.testing.fakes import (
    FakeClock,
    FakeIdGenerator,
    FakeListening,
    FakeModelProvider,
    FakeModelRouter,
    FakeProbe,
    FakeProviderRegistry,
    FakeScreenCapture,
    FakeSpeech,
    FakeTextRecognition,
    FakeTool,
)
from ela.tools import (
    CORE_ECHO,
    PERCEPTION_CAPTURE_SCREEN,
    PERCEPTION_LISTEN,
    PERCEPTION_READ_SCREEN_TEXT,
    VOICE_SPEAK,
    VOICE_SPEAK_ONLINE,
    CaptureSettings,
    CaptureStore,
    EchoTool,
    EchoVerifier,
    ModelCompleteTool,
    ModelCompleteVerifier,
    NotIdempotentError,
    Tool,
    ToolNotFound,
    ToolRegistry,
    VerifierNotFound,
    VerifierRegistry,
    WriteNoteTool,
    WriteNoteVerifier,
    production_tools,
    production_verifiers,
    tools_v01,
    verifiers_v01,
)
from tests.routing.support import routing_for


def registry_of(root: Path) -> ToolRegistry:
    clock, ids = FakeClock(), FakeIdGenerator()
    router, providers = routing_for(FakeModelProvider(clock, ids))
    return tools_v01(root=root, clock=clock, ids=ids, router=router, providers=providers)


def test_get_unknown_names_the_capability() -> None:
    registry = ToolRegistry(())
    with pytest.raises(ToolNotFound) as caught:
        registry.get(CapabilityId("nobody.knows_this"))
    assert caught.value.capability_id == "nobody.knows_this"
    assert "tool 'nobody.knows_this' not found" in str(caught.value)


def test_tools_v01_implements_the_whole_catalogue(tmp_path: Path) -> None:
    """Since M7.2 every capability of §29 has a tool: the last hole was ``model.complete``."""
    registry = registry_of(tmp_path)
    implemented = {tool.capability_id for tool in registry.tools()}
    declared = {spec.id for spec in catalogue_v01().specs()}
    assert implemented == declared
    echo, notes, model = registry.tools()
    assert isinstance(echo, EchoTool)
    assert isinstance(notes, WriteNoteTool)
    assert isinstance(model, ModelCompleteTool)
    assert notes.root == tmp_path.resolve()
    assert registry.get(MODEL_COMPLETE) is model


def test_the_registry_needs_a_router_and_a_registry_for_the_model_tool(tmp_path: Path) -> None:
    """A registry that dropped the third tool when nobody passed a router would make a capability
    disappear; a provider with no key says so through its status instead, and the router skips
    it (ADR 0022 §7)."""
    with pytest.raises(TypeError):
        tools_v01(root=tmp_path, clock=FakeClock(), ids=FakeIdGenerator())  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        verifiers_v01(root=tmp_path)  # type: ignore[call-arg]


def test_the_registry_is_frozen() -> None:
    registry = ToolRegistry(())
    assert not hasattr(registry, "__dict__")
    with pytest.raises(AttributeError):
        registry.extra = 1  # type: ignore[attr-defined]


def test_verifier_get_unknown_names_the_capability() -> None:
    registry = VerifierRegistry(())
    with pytest.raises(VerifierNotFound) as caught:
        registry.get(CapabilityId("nobody.knows_this"))
    assert caught.value.capability_id == "nobody.knows_this"
    assert "verifier 'nobody.knows_this' not found" in str(caught.value)


def test_verifiers_v01_covers_exactly_the_tools_of_v01(tmp_path: Path) -> None:
    """Every tool has its verifier and no verifier lacks a tool: a capability without both is
    not executable (ADR 0014 §3)."""
    tools = registry_of(tmp_path)
    verifiers = verifiers_v01(root=tmp_path, router=FakeModelRouter())
    assert {v.capability_id for v in verifiers.verifiers()} == {
        t.capability_id for t in tools.tools()
    }
    echo, notes, model = verifiers.verifiers()
    assert isinstance(echo, EchoVerifier)
    assert isinstance(notes, WriteNoteVerifier)
    assert isinstance(model, ModelCompleteVerifier)
    assert verifiers.get(MODEL_COMPLETE) is model
    assert notes._root == tmp_path.resolve()  # noqa: SLF001


def test_the_verifier_registry_is_frozen() -> None:
    registry = VerifierRegistry(())
    assert not hasattr(registry, "__dict__")
    with pytest.raises(AttributeError):
        registry.extra = 1  # type: ignore[attr-defined]


# --------------------------------------------------------------------------------------
# Every tool declares whether it is idempotent; silence is refused (ADR 0015 §8, ADR 0021 §1)
# --------------------------------------------------------------------------------------


def test_every_tool_of_v01_says_whether_twice_is_once(tmp_path: Path) -> None:
    """Two tools are repaired by running them again; the third cannot be run again at all."""
    registry = registry_of(tmp_path)
    assert [tool.idempotent for tool in registry.tools()] == [True, True, False]  # type: ignore[attr-defined]
    assert EchoTool.idempotent is WriteNoteTool.idempotent is True
    assert ModelCompleteTool.idempotent is False


def test_a_declared_false_is_accepted_since_the_started_protocol_exists() -> None:
    """What the guard of ADR 0015 §8 was waiting for arrived (ADR 0021 §1): ``False`` is an
    answer, and the executor knows what to do with it."""
    tool = FakeTool(
        CapabilityId("model.complete"), FakeClock(), FakeIdGenerator(), name="x", idempotent=False
    )
    registry = ToolRegistry((tool,))
    assert registry.get(CapabilityId("model.complete")) is tool


def test_a_tool_that_does_not_declare_it_is_refused_too() -> None:
    """A doubt is not a yes (§33): forgetting the attribute reads as "no", never as "yes"."""

    class _Undeclared:
        capability_id = CapabilityId("core.echo")
        name = "undeclared"

        async def execute(self, decision: object, arguments: object) -> object:  # pragma: no cover
            raise AssertionError("never registered, never called")

    with pytest.raises(NotIdempotentError) as caught:
        ToolRegistry((_Undeclared(),))  # type: ignore[arg-type]
    assert caught.value.declared is None
    assert "declares no boolean idempotent" in str(caught.value)
    assert "STARTED protocol of ADR 0021 §1" in str(caught.value)
    assert not hasattr(Tool, "idempotent")  # the base gives no default to inherit by mistake


def test_a_non_boolean_declaration_is_refused_like_silence() -> None:
    """``idempotent = "yes"`` is not an answer either: the executor reads a boolean or nothing."""

    class _Chatty:
        capability_id = CapabilityId("core.echo")
        name = "chatty"
        idempotent = "yes"

        async def execute(self, decision: object, arguments: object) -> object:  # pragma: no cover
            raise AssertionError("never registered, never called")

    with pytest.raises(NotIdempotentError) as caught:
        ToolRegistry((_Chatty(),))  # type: ignore[arg-type]
    assert caught.value.declared == "yes"


def test_the_refusal_comes_before_the_duplicate_check() -> None:
    """A silent duplicate is refused for what makes it dangerous, not for its key."""

    class _Silent:
        capability_id = CORE_ECHO
        name = "silent"

        async def execute(self, decision: object, arguments: object) -> object:  # pragma: no cover
            raise AssertionError("never registered, never called")

    echo = EchoTool(FakeClock(), FakeIdGenerator())
    with pytest.raises(NotIdempotentError):
        ToolRegistry((echo, _Silent()))  # type: ignore[arg-type]
    with pytest.raises(AlreadyExistsError):
        ToolRegistry((echo, EchoTool(FakeClock(), FakeIdGenerator())))


# --------------------------------------------------------------------------------------
# The production registries: v0.1's, plus what the phases after it added (ADR 0029 §13)
# --------------------------------------------------------------------------------------


def _production(tmp_path: Path) -> tuple[ToolRegistry, VerifierRegistry, CaptureStore]:
    captures = CaptureStore(CaptureSettings(capture_dir=tmp_path / "captures"))
    router = FakeModelRouter()
    tools = production_tools(
        root=tmp_path,
        clock=FakeClock(),
        ids=FakeIdGenerator(),
        router=router,
        providers=FakeProviderRegistry(),
        captures=captures,
        screen=FakeScreenCapture(),
        probe=FakeProbe(),
        recognition=FakeTextRecognition(),
        languages=("it-IT",),
        listening=FakeListening(),
        listen_enabled=True,
        speech=FakeSpeech(),
        voice="Alice",
        voice_enabled=True,
        speech_online=FakeSpeech(),
        voice_id="VZOd9FMXDnXRZpGn0thg",
        model="eleven_flash_v2_5",
    )
    return tools, production_verifiers(root=tmp_path, router=router, captures=captures), captures


def test_the_production_registries_are_v01_plus_what_came_after(tmp_path: Path) -> None:
    """``production_`` says when it is used; ``_v01`` says what it contains, and keeps saying it.

    v0.1 does not get folded into, it gets stood beside — the same handling M10.1 gave the
    ``/perception`` route, which stayed out of the v0.1 route count. The list after the baseline
    grows with each milestone and the baseline does not, which is the whole property.
    """
    tools, verifiers, _ = _production(tmp_path)
    baseline = registry_of(tmp_path)

    assert [t.capability_id for t in tools.tools()][:3] == [
        t.capability_id for t in baseline.tools()
    ]
    assert [t.capability_id for t in tools.tools()][3:] == [
        PERCEPTION_CAPTURE_SCREEN,
        PERCEPTION_LISTEN,
        PERCEPTION_READ_SCREEN_TEXT,
        VOICE_SPEAK,
        VOICE_SPEAK_ONLINE,
    ]
    assert {v.capability_id for v in verifiers.verifiers()} == {
        t.capability_id for t in tools.tools()
    }


@pytest.mark.parametrize(
    "capability",
    [PERCEPTION_CAPTURE_SCREEN, PERCEPTION_LISTEN, PERCEPTION_READ_SCREEN_TEXT],
)
def test_both_store_verifiers_read_the_store_the_tools_write_into(
    tmp_path: Path, capability: CapabilityId
) -> None:
    """One directory and one retention, or a verifier would look somewhere else — or think an
    artefact still there had expired. Both artefacts of the store, and the same answer."""
    _, verifiers, captures = _production(tmp_path)
    verifier = verifiers.get(capability)

    assert verifier._directory == captures.directory  # noqa: SLF001
    assert verifier._ttl == captures.settings.capture_ttl  # noqa: SLF001
