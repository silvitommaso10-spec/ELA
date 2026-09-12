"""What a verifier proves when the effect happened on another machine (M12.2, D15; ADR 0038 §14).

Three groups, each the test of a sentence of ADR 0038 §14:

* every verifier *says* whether it reads the machine it runs on, and the registry refuses one that
  stays silent — the rule ``ToolRegistry`` applies to ``idempotent``: forgetting must not read as
  "it may travel";
* what a verifier that reads the machine would prove about a remote effect: nothing, and worse —
  ``WriteNoteVerifier`` passes a note the node never left behind when the Core's workspace holds
  one at the same path. The false positive, written as a test;
* what the four verifiers that travel accept on the node's word alone, one test each in the form
  of ``tests/tools/test_listen_verifier.py`` (the transcript of words nobody said) — and that a
  verifier declaring ``False`` touches no disk, with a verifier that reads in secret as the case
  proving the check can fail.
"""

from __future__ import annotations

import builtins
import io
import os
import shutil
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar

import pytest

from ela.domain import CapabilityId, ErrorMetadata, ExecutionResult, JsonMapping, ProviderRequest
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeModelProvider
from ela.tools import (
    COMMON_FAILURE_CODES,
    CORE_ECHO,
    ECHO_MESSAGE_MATCHES,
    MODEL_ANSWERED,
    MODEL_COMPLETE,
    MODEL_ROUTED_AS_ASKED,
    NOTE_CONTENT_MATCHES,
    NOTE_EXISTS,
    PERCEPTION_CAPTURE_SCREEN,
    PERCEPTION_LISTEN,
    PERCEPTION_READ_SCREEN_TEXT,
    VOICE_SPEAK,
    VOICE_SPEAK_ONLINE,
    WORKSPACE_WRITE_NOTE,
    CaptureSettings,
    CaptureStore,
    EchoVerifier,
    SilentVerifierError,
    Verifier,
    VerifierRegistry,
    WriteNoteTool,
    WriteNoteVerifier,
    production_verifiers,
)
from ela.tools.verifiers import SPEECH_TEXT_MATCHES, SPEECH_TOOK_REAL_TIME
from tests.routing.support import routing_for
from tests.tools.support import allowed
from tests.tools.test_verifiers import MODEL_ARGUMENTS, completion, succeeded
from tests.tools.test_voice_verifier import ARGUMENTS as SPEECH_ARGUMENTS
from tests.tools.test_voice_verifier import spoken

TRAVELS = frozenset({CORE_ECHO, MODEL_COMPLETE, VOICE_SPEAK, VOICE_SPEAK_ONLINE})
"""ADR 0038 §14: the four capabilities whose verifier reads no disk."""
STAYS = frozenset(
    {
        WORKSPACE_WRITE_NOTE,
        PERCEPTION_CAPTURE_SCREEN,
        PERCEPTION_READ_SCREEN_TEXT,
        PERCEPTION_LISTEN,
    }
)
"""ADR 0038 §14: the four whose verifier reads the disk or the store of the machine it runs on."""
NOTE = "notes/riunione.md"
NOTE_ARGUMENTS = {"path": NOTE, "body": "# Riunione\n\nGiovedì alle dieci.\n"}


def _never_called(request: ProviderRequest) -> str:
    raise AssertionError("the provider was asked: a verifier holds no provider (§57)")


@pytest.fixture
def provider() -> FakeModelProvider:
    """The one provider the router knows, and one that fails the test if anybody asks it."""
    return FakeModelProvider(FakeClock(), FakeIdGenerator(), reply=_never_called)


@pytest.fixture
def production(tmp_path: Path, provider: FakeModelProvider) -> VerifierRegistry:
    """The verifiers the Core runs, wired as :func:`production_verifiers` wires them."""
    router, _ = routing_for(provider)
    captures = CaptureStore(CaptureSettings(capture_dir=tmp_path / "captures"))
    return production_verifiers(root=tmp_path / "workspace", router=router, captures=captures)


# ----------------------------------------------------------------------------------------
# Every verifier says it, and none may stay silent
# ----------------------------------------------------------------------------------------


class _Silent:
    """A verifier that forgot to say where it reads: never registered, never called."""

    capability_id = CORE_ECHO
    name = "silent"


def test_the_registry_refuses_a_verifier_that_does_not_say_where_it_reads() -> None:
    """A doubt is not a no (§33): a verifier that forgot the declaration reads as one that reads
    this machine, and the registry refuses it rather than let the orchestrator guess."""
    with pytest.raises(SilentVerifierError) as caught:
        VerifierRegistry((_Silent(),))  # type: ignore[arg-type]

    assert caught.value.declared is None
    assert caught.value.capability_id == CORE_ECHO
    assert "reads_the_machine" in str(caught.value)
    assert not hasattr(Verifier, "reads_the_machine")  # the base gives no default to inherit


@pytest.mark.parametrize("declared", ["no", 0, 1, None], ids=repr)
def test_a_declaration_that_is_not_a_bool_is_refused_like_silence(declared: object) -> None:
    """``0`` and ``1`` are not answers either: the orchestrator reads a boolean or nothing."""

    class _Vague(_Silent):
        reads_the_machine = declared

    with pytest.raises(SilentVerifierError) as caught:
        VerifierRegistry((_Vague(),))  # type: ignore[arg-type]

    assert caught.value.declared == declared


def test_the_refusal_comes_before_the_duplicate_check() -> None:
    """A silent duplicate is refused for what makes it dangerous, not for its key."""
    with pytest.raises(SilentVerifierError):
        VerifierRegistry((EchoVerifier(), _Silent()))  # type: ignore[arg-type]


def test_four_production_verifiers_read_the_machine_and_four_do_not(
    production: VerifierRegistry,
) -> None:
    declared = {
        verifier.capability_id: verifier.reads_the_machine for verifier in production.verifiers()
    }

    assert {capability for capability, reads in declared.items() if not reads} == TRAVELS
    assert {capability for capability, reads in declared.items() if reads} == STAYS


# ----------------------------------------------------------------------------------------
# What a verifier that reads the machine proves about another one: the false positive
# ----------------------------------------------------------------------------------------


async def test_the_note_verifier_passes_a_note_the_node_did_not_leave_behind(
    tmp_path: Path,
) -> None:
    """The reason ``workspace.write_note`` does not travel, made a test.

    A node writes the note in *its* workspace and reports the outcome; whatever it did, nothing of
    it is left to read. The Core's workspace happens to hold a note at the same path with the same
    body — yesterday's, the user's own. Verified on the Core, both conditions pass: the verifier
    read the Core's disk, which is the only disk it can read, and nobody looked at the node's.
    ``bytes == len(body)`` checked from afar would pass the same way without a file at all, which
    is why no remote verifier of coherence was written (ADR 0038 §14).
    """
    node = tmp_path / "node"
    reported = await WriteNoteTool(node, FakeClock(), FakeIdGenerator()).execute(
        allowed(WORKSPACE_WRITE_NOTE), NOTE_ARGUMENTS
    )
    shutil.rmtree(node)
    core = tmp_path / "core"
    await WriteNoteTool(core, FakeClock(), FakeIdGenerator()).execute(
        allowed(WORKSPACE_WRITE_NOTE), NOTE_ARGUMENTS
    )
    verifier = WriteNoteVerifier(core)

    failures = await verifier.verify((NOTE_EXISTS, NOTE_CONTENT_MATCHES), NOTE_ARGUMENTS, reported)

    assert failures == ()
    assert verifier.reads_the_machine is True


# ----------------------------------------------------------------------------------------
# The four that travel, and what each takes on the node's word
# ----------------------------------------------------------------------------------------


async def test_echo_passes_a_message_the_node_only_says_it_echoed(
    production: VerifierRegistry,
) -> None:
    """The output against the arguments, and nothing else: a node that wrote the message into the
    result without running anything is indistinguishable from one that echoed it."""
    written_by_hand = succeeded(CORE_ECHO, output={"message": "ciao"})

    failures = await production.get(CORE_ECHO).verify(
        (ECHO_MESSAGE_MATCHES,), {"message": "ciao"}, written_by_hand
    )

    assert failures == ()


async def test_the_model_verifier_passes_a_call_the_provider_never_received(
    production: VerifierRegistry, provider: FakeModelProvider
) -> None:
    """The route is recomputed by the Core's router, so the provider a node names is checked
    against the policy; that the call went there is the node's word. Here the only provider fails
    whoever asks it, and a completion naming it passes both conditions."""
    failures = await production.get(MODEL_COMPLETE).verify(
        (MODEL_ANSWERED, MODEL_ROUTED_AS_ASKED), MODEL_ARGUMENTS, completion()
    )

    assert failures == ()
    assert provider.requests == ()


@pytest.mark.parametrize("capability_id", [VOICE_SPEAK, VOICE_SPEAK_ONLINE], ids=str)
async def test_a_voice_passes_a_duration_the_node_made_up(
    production: VerifierRegistry, capability_id: CapabilityId
) -> None:
    """The clock is the only witness of a sound (M11.1 dec. C), and from afar the clock is the
    node's: an hour for one sentence is as good as a second and a half. What stops a node from
    saying it is the node, which is the limit of D1."""
    invented = spoken(spoken_seconds=3600.0).model_copy(update={"capability_id": capability_id})

    failures = await production.get(capability_id).verify(
        (SPEECH_TOOK_REAL_TIME, SPEECH_TEXT_MATCHES), SPEECH_ARGUMENTS, invented
    )

    assert failures == ()


# ----------------------------------------------------------------------------------------
# A verifier that declares False reads no disk — and the check that would see one that does
# ----------------------------------------------------------------------------------------

DISK_CALLS: tuple[tuple[object, str], ...] = (
    (os, "stat"),
    (os, "lstat"),
    (os, "open"),
    (os, "scandir"),
    (os, "listdir"),
    (os, "access"),
    (io, "open"),
    (builtins, "open"),
)
"""Where every read of a disk in Python goes through: ``pathlib`` and ``os.path`` call these by
attribute, so replacing them sees ``Path.exists``, ``Path.read_bytes`` and ``os.path.realpath``."""


def _recording(
    touched: list[str], label: str, real: Callable[..., object]
) -> Callable[..., object]:
    def recorded(*args: object, **kwargs: object) -> object:
        touched.append(label)
        return real(*args, **kwargs)

    return recorded


@contextmanager
def watching_the_disk() -> Iterator[list[str]]:
    """Every disk call made inside the block, by name; each still reaches the disk."""
    touched: list[str] = []
    with pytest.MonkeyPatch.context() as patch:
        for module, name in DISK_CALLS:
            real = getattr(module, name)
            patch.setattr(module, name, _recording(touched, f"{name}", real))
        yield touched


async def disk_reads_of(
    verifier: Verifier, arguments: JsonMapping, result: ExecutionResult
) -> list[str]:
    """The disk calls ``verifier`` makes answering every condition it knows."""
    with watching_the_disk() as touched:
        await verifier.verify(tuple(sorted(verifier.conditions)), arguments, result)
    return touched


TRAVELLING: dict[CapabilityId, tuple[JsonMapping, ExecutionResult]] = {
    CORE_ECHO: ({"message": "ciao"}, succeeded(CORE_ECHO, output={"message": "ciao"})),
    MODEL_COMPLETE: (MODEL_ARGUMENTS, completion()),
    VOICE_SPEAK: (SPEECH_ARGUMENTS, spoken()),
    VOICE_SPEAK_ONLINE: (
        SPEECH_ARGUMENTS,
        spoken().model_copy(update={"capability_id": VOICE_SPEAK_ONLINE}),
    ),
}
"""One plausible call per capability that travels. Keyed so that a fifth verifier declaring
``False`` tomorrow fails at the door, before anybody has checked what it reads."""


def test_every_verifier_that_travels_has_a_call_here(production: VerifierRegistry) -> None:
    travelling = {v.capability_id for v in production.verifiers() if not v.reads_the_machine}
    assert set(TRAVELLING) == travelling


@pytest.mark.parametrize("capability_id", sorted(TRAVELLING), ids=str)
async def test_a_verifier_that_declares_false_reads_no_disk(
    production: VerifierRegistry, capability_id: CapabilityId
) -> None:
    arguments, result = TRAVELLING[capability_id]
    verifier = production.get(capability_id)
    assert isinstance(verifier, Verifier)

    assert await disk_reads_of(verifier, arguments, result) == []


class _ReadsInSecret(Verifier):
    """A verifier that declares it reads nothing and reads the disk: the case the check is for."""

    reads_the_machine: ClassVar[bool] = False
    conditions: ClassVar[frozenset[str]] = frozenset({ECHO_MESSAGE_MATCHES})
    failure_codes: ClassVar[frozenset[str]] = COMMON_FAILURE_CODES

    def __init__(self, root: Path) -> None:
        super().__init__(CORE_ECHO, name="reads-in-secret")
        self._root = root

    async def _check(
        self, condition: str, arguments: JsonMapping, result: ExecutionResult
    ) -> ErrorMetadata | None:
        self._root.joinpath(NOTE).exists()  # the read its declaration hides
        return None


async def test_the_check_sees_a_verifier_that_reads_in_secret(tmp_path: Path) -> None:
    """The negative: were a verifier declaring ``False`` to read the disk, the test above fails."""
    arguments, result = TRAVELLING[CORE_ECHO]

    assert await disk_reads_of(_ReadsInSecret(tmp_path), arguments, result) != []


async def test_the_check_sees_what_the_note_verifier_reads(tmp_path: Path) -> None:
    """And it sees the reads of a verifier that declares them, which is why that one stays."""
    root = tmp_path / "workspace"
    result = await WriteNoteTool(root, FakeClock(), FakeIdGenerator()).execute(
        allowed(WORKSPACE_WRITE_NOTE), NOTE_ARGUMENTS
    )

    assert await disk_reads_of(WriteNoteVerifier(root), NOTE_ARGUMENTS, result) != []
