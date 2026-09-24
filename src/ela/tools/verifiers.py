"""The verifiers of v0.1 (spec §63; ADR 0014 §2): one per tool, each read-only by construction.

* :class:`EchoVerifier` for ``core.echo``: the output repeats the message. It is the whole
  observable world of an echo, and a declared limit.
* :class:`ModelCompleteVerifier` for ``model.complete``: the tool **answered and can account
  for it** — a text, the provider and the model that produced it, and a
  :class:`~ela.domain.ProviderUsage` — and it **went where the policy sends it**. It cannot check
  that the answer is *good*, and it must not ask the model again: a second call would cost money
  and send the user's content out twice (§57). What it can refuse is a success nobody can account
  for (§32) and a call that went somewhere nobody chose (§25, §33), and the rest is a declared
  limit, as the echo's is.
* :class:`WriteNoteVerifier` for ``workspace.write_note``: the note **exists** as a regular
  file inside the workspace, and its **content matches** the body that was asked — the file is
  read back from the disk with ``O_RDONLY | O_NOFOLLOW`` and its SHA-256 compared with the
  SHA-256 of ``body`` encoded as UTF-8. The comparison is with the *intent* (the arguments),
  never with what the tool claimed in its output: a verifier that trusted the tool's report
  would verify nothing. The hashes stay in memory; a failure carries only sizes (§57). Where
  the path leads is classified by :mod:`ela.tools.paths`, the same function the tool uses, so a
  path the tool refused is refused here with the same code, and a note the tool wrote is found.

This module writes nothing: no ``open`` in a writing mode, no ``os.write``, no ``unlink``,
``rename``, ``mkdir`` or ``chmod`` — rule 18 (``check_verifier_read_only``) reads its AST and
says so, with negative cases. A missing workspace root is a missing note, never a directory
to create.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import stat
from abc import abstractmethod
from datetime import timedelta
from pathlib import Path
from typing import ClassVar, Final

from ela.domain import (
    CapabilityId,
    CommandOutput,
    ErrorMetadata,
    ExecutionResult,
    JsonMapping,
)
from ela.ports import ModelRouterPort, RoutingError
from ela.tools.captures import (
    CAPTURE_CODES,
    Capture,
    CaptureProblem,
    TextArtefact,
    TranscriptArtefact,
    inspect,
    inspect_text,
    inspect_transcript,
)
from ela.tools.echo import CORE_ECHO
from ela.tools.fs import FS_READ, FS_WRITE
from ela.tools.listen import PERCEPTION_LISTEN
from ela.tools.model import MODEL_COMPLETE, routing_arguments
from ela.tools.notes import WORKSPACE_WRITE_NOTE
from ela.tools.paths import PATH_CODES, classify, resolve_workspace
from ela.tools.programs import (
    PROGRAM_CHANGED,
    PROGRAM_CODES,
    PROGRAM_GONE,
    ProgramProblem,
    Programs,
)
from ela.tools.screen import PERCEPTION_CAPTURE_SCREEN
from ela.tools.screen_text import PERCEPTION_READ_SCREEN_TEXT
from ela.tools.terminal import TERMINAL_RUN
from ela.tools.verify import COMMON_FAILURE_CODES, VERIFICATION_ARGUMENTS_INVALID, Verifier
from ela.tools.voice import VOICE_SPEAK, digest_of

__all__ = [
    "TERMINAL_EXIT_CODE_MATCHES",
    "TERMINAL_EXIT_MISMATCH",
    "TERMINAL_OUTPUT_INCOMPLETE",
    "TERMINAL_OUTPUT_WHOLE",
    "TERMINAL_PROGRAM_UNCHANGED",
    "TERMINAL_VERIFIER_NAME",
    "TerminalRunVerifier",
    "CAPTURE_DECLARED_MISMATCH",
    "CAPTURE_EXISTS",
    "CAPTURE_MATCHES",
    "CAPTURE_VERIFIER_NAME",
    "SpeakVerifier",
    "ONLINE_SPEECH_VERIFIER_NAME",
    "SPEECH_VERIFIER_NAME",
    "SPEECH_TOO_FAST",
    "SPEECH_TOOK_REAL_TIME",
    "SPEECH_TEXT_MISMATCH",
    "SPEECH_TEXT_MATCHES",
    "MIN_SECONDS_PER_CHARACTER",
    "LISTEN_VERIFIER_NAME",
    "ListenVerifier",
    "TEXT_DECLARED_MISMATCH",
    "TRANSCRIPT_DECLARED_MISMATCH",
    "TRANSCRIPT_EXISTS",
    "TRANSCRIPT_MATCHES",
    "TEXT_EXISTS",
    "TEXT_MATCHES",
    "TEXT_VERIFIER_NAME",
    "ReadScreenTextVerifier",
    "ECHO_MESSAGE_MATCHES",
    "ECHO_MESSAGE_MISMATCH",
    "ECHO_VERIFIER_NAME",
    "MODEL_ANSWERED",
    "MODEL_MISROUTED",
    "MODEL_NO_ANSWER",
    "MODEL_ROUTED_AS_ASKED",
    "MODEL_UNACCOUNTED",
    "MODEL_VERIFIER_NAME",
    "NOTES_VERIFIER_NAME",
    "NOTE_CONTENT_MATCHES",
    "NOTE_CONTENT_MISMATCH",
    "NOTE_EXISTS",
    "NOTE_UNREADABLE",
    "CaptureScreenVerifier",
    "EchoVerifier",
    "ModelCompleteVerifier",
    "FsReadVerifier",
    "FsWriteVerifier",
    "WriteNoteVerifier",
]

ECHO_VERIFIER_NAME: Final = "core-echo-verifier"
NOTES_VERIFIER_NAME: Final = "workspace-notes-verifier"
MODEL_VERIFIER_NAME: Final = "model-complete-verifier"
CAPTURE_VERIFIER_NAME: Final = "perception-screen-verifier"
TEXT_VERIFIER_NAME: Final = "perception-screen-text-verifier"
SPEECH_VERIFIER_NAME: Final = "voice-speak-verifier"
ONLINE_SPEECH_VERIFIER_NAME: Final = "voice-speak-online-verifier"
"""The same verifier, registered for the online capability: one class, two names, because a name
is what appears in a result and two capabilities must not report the same one (M11.3)."""

CAPTURE_EXISTS: Final = "capture.exists"
"""The name the tool reported leads to a regular file, through no link, inside the capture store,
and its bytes are a PNG with a usable IHDR: :func:`~ela.tools.captures.inspect` answers a
:class:`~ela.tools.captures.Capture`, else its code is the failure's."""
CAPTURE_MATCHES: Final = "capture.matches"
"""What the disk says — size in bytes, SHA-256, width and height — is what the result declared."""
CAPTURE_DECLARED_MISMATCH: Final = "capture.declared_mismatch"
"""The artefact is there and is not the one the tool described. Unlike the other verifiers, the
comparison here is against the **output** and not against the arguments, and that is not the
"trusting the tool's word" mistake: ``purpose`` and ``display`` do not determine a single pixel,
so there is no intent to compare with. What is under test *is* the claim — "I wrote a PNG of this
size with this digest" — and the source of truth is the disk. That is precisely §20's "non deve
assumere che un click sia riuscito solo perché è stato inviato"."""

TEXT_EXISTS: Final = "text.exists"
"""The name the tool reported leads to a regular file, through no link, inside the capture store,
and its bytes are the JSON Lines this store writes."""
TEXT_MATCHES: Final = "text.matches"
"""What the disk says — size in bytes, SHA-256, how many lines and how many characters — is what
the result declared."""
TEXT_DECLARED_MISMATCH: Final = "text.declared_mismatch"
"""The recognition is there and is not the one the tool described.

Same shape as :data:`CAPTURE_DECLARED_MISMATCH` and the same limit, stated so nobody reads more
into it: this can say the artefact exists, that it is well formed, and that it is exactly what the
tool declared. It **cannot** say the text is what was on the screen — that would need a second
recognition to compare against, which is redoing the work and not verifying it (§20 asks that
execution not be taken as proof of success; it does not ask for an oracle)."""

MODEL_ANSWERED: Final = "model.answered"
"""The result carries a non-empty text, the provider and the model that produced it, and the
:class:`~ela.domain.ProviderUsage` of the call (§32)."""
MODEL_NO_ANSWER: Final = "model.no_answer"
MODEL_UNACCOUNTED: Final = "model.unaccounted"
"""A SUCCEEDED completion with no usage: the call cannot be accounted for, and §32 asks that a
provider call be. A tool that answers without saying what it consumed has not been verified."""
MODEL_ROUTED_AS_ASKED: Final = "model.routed_as_asked"
"""The provider that answered, and the profile that was asked for, are the ones the routing
policy prescribes for these arguments (§25; ADR 0022 §10)."""
MODEL_MISROUTED: Final = "model.misrouted"
"""The call went to a provider — or asked for a profile — the policy does not prescribe for these
arguments, or the policy cannot route them at all any more. Not a fault of the model: a fact
about *where the request went*, which §25 made a decision and §33 forbids taking silently."""

ECHO_MESSAGE_MATCHES: Final = "echo.message_matches"
"""``output["message"]`` is the string ``arguments["message"]``."""
ECHO_MESSAGE_MISMATCH: Final = "echo.message_mismatch"

NOTE_EXISTS: Final = "note.exists"
"""``root / path`` is a regular file, reached through no symbolic link, inside the workspace:
:func:`~ela.tools.paths.classify` answers ``None``, else its code is the failure's."""
NOTE_CONTENT_MATCHES: Final = "note.content_matches"
"""The note exists and its bytes hash to the same SHA-256 as ``body`` encoded as UTF-8."""
NOTE_CONTENT_MISMATCH: Final = "note.content_mismatch"
NOTE_UNREADABLE: Final = "note.unreadable"

READ_FLAGS: Final = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
"""How a note is opened to be read back: never through a link, never for writing."""


class EchoVerifier(Verifier):
    """``core.echo`` echoed: the output carries the very message that was asked (§29)."""

    reads_the_machine: ClassVar[bool] = False
    """The output against the arguments: nothing of any disk. From a node it proves what it proved
    here, and the limit is the node's word (ADR 0038 §14)."""
    conditions: ClassVar[frozenset[str]] = frozenset({ECHO_MESSAGE_MATCHES})
    failure_codes: ClassVar[frozenset[str]] = COMMON_FAILURE_CODES | {ECHO_MESSAGE_MISMATCH}

    def __init__(self, *, name: str = ECHO_VERIFIER_NAME) -> None:
        super().__init__(CORE_ECHO, name=name)

    async def _check(
        self, condition: str, arguments: JsonMapping, result: ExecutionResult
    ) -> ErrorMetadata | None:
        expected = arguments.get("message")
        if not isinstance(expected, str):
            return self._failure(
                condition,
                VERIFICATION_ARGUMENTS_INVALID,
                "message must be a string",
                retryable=False,
            )
        actual = result.output.get("message")
        if isinstance(actual, str) and actual == expected:
            return None
        return self._failure(
            condition,
            ECHO_MESSAGE_MISMATCH,
            "output.message differs from arguments.message",
            retryable=False,
            details={
                "expected_length": len(expected),
                "actual_length": len(actual) if isinstance(actual, str) else None,
            },
        )


FS_READ_VERIFIER_NAME: Final = "fs-read-verifier"
FS_WRITE_VERIFIER_NAME: Final = "fs-write-verifier"

FS_FILE_EXISTS: Final = "fs.file_exists"
"""The file the call named is there, and is a regular file."""
FS_CONTENT_MATCHES: Final = "fs.content_matches"
"""Its bytes are the bytes the call asked for — the intent, never the tool's report."""

FS_CONTENT_MISMATCH: Final = "fs.content_mismatch"
FS_UNREADABLE: Final = "fs.unreadable"


class WriteNoteVerifier(Verifier):
    """``workspace.write_note`` verified from the disk, not from the tool's word (§63).

    ``root`` is resolved the way the tool resolves it — expanded, absolute, real — so that the
    two agree on where the workspace is; it is **not** created: a workspace that does not exist
    holds no note.
    """

    reads_the_machine: ClassVar[bool] = True
    """The workspace of this machine: from a node it would read the Core's workspace, where a note
    with the same path may exist — a false positive (ADR 0038 §14). It does not travel."""
    conditions: ClassVar[frozenset[str]] = frozenset({NOTE_EXISTS, NOTE_CONTENT_MATCHES})
    failure_codes: ClassVar[frozenset[str]] = (
        COMMON_FAILURE_CODES | PATH_CODES | {NOTE_CONTENT_MISMATCH, NOTE_UNREADABLE}
    )

    def __init__(self, root: Path | str, *, name: str = NOTES_VERIFIER_NAME) -> None:
        super().__init__(WORKSPACE_WRITE_NOTE, name=name)
        self._root = resolve_workspace(root)

    async def _check(
        self, condition: str, arguments: JsonMapping, result: ExecutionResult
    ) -> ErrorMetadata | None:
        path = arguments.get("path")
        body = arguments.get("body")
        if not isinstance(path, str) or not isinstance(body, str):
            return self._failure(
                condition,
                VERIFICATION_ARGUMENTS_INVALID,
                "path and body must be strings",
                retryable=False,
            )
        problem = classify(self._root, path)
        if problem is not None:
            return self._failure(condition, problem.code, problem.message(path), retryable=True)
        if condition == NOTE_EXISTS:
            return None
        expected = body.encode("utf-8")
        try:
            data = self._read(self._root / path)
        except OSError as error:
            return self._failure(
                condition,
                NOTE_UNREADABLE,
                f"{path!r} could not be read: {type(error).__name__}: {error.strerror or error}",
                retryable=True,
            )
        if hashlib.sha256(data).digest() == hashlib.sha256(expected).digest():
            return None
        return self._failure(
            condition,
            NOTE_CONTENT_MISMATCH,
            f"{path!r} does not contain the body that was asked",
            retryable=True,
            details={"expected_bytes": len(expected), "actual_bytes": len(data)},
        )

    @staticmethod
    def _read(target: Path) -> bytes:
        """The bytes of ``target``, opened read-only and never through a link; ``fstat`` on the
        open descriptor reconfirms the regular file the checks saw (a directory slipped in
        between is refused, not read)."""
        descriptor = os.open(target, READ_FLAGS)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise OSError(None, "not a regular file")
            chunks = []
            while chunk := os.read(descriptor, 65536):
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            os.close(descriptor)


class _FsVerifier(Verifier):
    """What ``fs.read`` and ``fs.write`` are both verified against: the disk of this machine.

    One base and two names, because the two capabilities are verified by asking the **same**
    question of the same place — is the file there, and does it hold the bytes the call named —
    and a second copy of that question is the thing ADR 0014 §2 exists to prevent.

    ``root`` is resolved the way the tools resolve it and is **never created**: a root that does
    not exist holds no file, and ELA does not invent the user's folder (M13.1 dec. A).

    The comparison is with the **intent** — the arguments — and never with what the tool put in
    its output: for ``fs.write`` that is ``body``, for ``fs.read`` it is the content the tool
    claims to have read, which is checked against the file itself. A verifier that trusted the
    tool's report would verify nothing.
    """

    reads_the_machine: ClassVar[bool] = True
    """The disk of this machine: from a node it would read the Core's disk, where a file with the
    same path may exist — the false positive of ADR 0038 §14. Neither capability travels."""
    conditions: ClassVar[frozenset[str]] = frozenset({FS_FILE_EXISTS, FS_CONTENT_MATCHES})
    failure_codes: ClassVar[frozenset[str]] = (
        COMMON_FAILURE_CODES | PATH_CODES | {FS_CONTENT_MISMATCH, FS_UNREADABLE}
    )

    def __init__(self, capability_id: CapabilityId, root: Path | str, *, name: str) -> None:
        super().__init__(capability_id, name=name)
        self._root = resolve_workspace(root)

    @abstractmethod
    def _expected(self, arguments: JsonMapping, result: ExecutionResult) -> str | None:
        """The text the file must hold, or ``None`` if the call cannot say.

        The one thing the two differ in: a write knows it from the arguments, a read from what the
        tool says it read — and in both cases the file is what settles it.
        """

    async def _check(
        self, condition: str, arguments: JsonMapping, result: ExecutionResult
    ) -> ErrorMetadata | None:
        path = arguments.get("path")
        if not isinstance(path, str):
            return self._failure(
                condition, VERIFICATION_ARGUMENTS_INVALID, "path must be a string", retryable=False
            )
        problem = classify(self._root, path)
        if problem is not None:
            return self._failure(condition, problem.code, problem.message(path), retryable=True)
        if condition == FS_FILE_EXISTS:
            return None
        expected = self._expected(arguments, result)
        if expected is None:
            return self._failure(
                condition,
                VERIFICATION_ARGUMENTS_INVALID,
                "the call says nothing about what the file should hold",
                retryable=False,
            )
        try:
            data = WriteNoteVerifier._read(self._root / path)  # noqa: SLF001
        except OSError as error:
            return self._failure(
                condition,
                FS_UNREADABLE,
                f"{path!r} could not be read: {type(error).__name__}: {error.strerror or error}",
                retryable=True,
            )
        if hashlib.sha256(data).digest() == hashlib.sha256(expected.encode("utf-8")).digest():
            return None
        return self._failure(
            condition,
            FS_CONTENT_MISMATCH,
            f"{path!r} does not hold what the call named",
            retryable=True,
            details={"expected_bytes": len(expected.encode("utf-8")), "actual_bytes": len(data)},
        )


class FsWriteVerifier(_FsVerifier):
    """``fs.write``: the file holds the ``body`` that was approved."""

    def __init__(self, root: Path | str, *, name: str = FS_WRITE_VERIFIER_NAME) -> None:
        super().__init__(FS_WRITE, root, name=name)

    def _expected(self, arguments: JsonMapping, result: ExecutionResult) -> str | None:
        body = arguments.get("body")
        return body if isinstance(body, str) else None


class FsReadVerifier(_FsVerifier):
    """``fs.read``: the file holds what the tool says it read.

    The intent of a read is not in the arguments — nobody says in advance what a file contains —
    so the thing to check is that the **content in the result is the content on disk**: the one
    way a reader can lie is by returning something the file does not hold. The bytes stay in the
    result and in memory here; what a failure carries is the two **sizes** (M13.1 dec. P), the
    form ``WriteNoteVerifier`` already uses because a short file's hash inverts by dictionary.
    """

    def __init__(self, root: Path | str, *, name: str = FS_READ_VERIFIER_NAME) -> None:
        super().__init__(FS_READ, root, name=name)

    def _expected(self, arguments: JsonMapping, result: ExecutionResult) -> str | None:
        content = result.output.get("content")
        return content if isinstance(content, str) else None


class ModelCompleteVerifier(Verifier):
    """``model.complete`` answered, can be accounted for, and went where it was routed (§25, §32).

    Read-only like every verifier, and read-only in a stronger sense here: the world it could
    look at is a model, and looking would mean asking again — a second charge and the user's
    content across the network a second time (§57). So what it checks is what the run left
    behind: a text, who produced it, what it cost, and whether that provider is the one the
    policy prescribes. It cannot judge whether the answer is right; nothing in v0.1 can, and
    that is written down rather than implied.

    ``router`` is the same port the tool used, and the route is **recomputed from the arguments**
    rather than read from anything the tool wrote: a verifier that took the tool's word for where
    the call went would be verifying the tool's report, which is the thing verification exists
    not to do. Recomputing is reliable because :class:`~ela.domain.ProviderStatus` is static
    (ADR 0020 §2) — the same question gets the same answer, skipped providers included — and that
    is a dependency, written down here and in ADR 0022, that a mutable status would break.
    """

    reads_the_machine: ClassVar[bool] = False
    """The output and the route recomputed by the Core's router: nothing of any disk. From a node,
    that the call really went to that provider is the node's word (ADR 0038 §14)."""
    conditions: ClassVar[frozenset[str]] = frozenset({MODEL_ANSWERED, MODEL_ROUTED_AS_ASKED})
    failure_codes: ClassVar[frozenset[str]] = COMMON_FAILURE_CODES | {
        MODEL_NO_ANSWER,
        MODEL_UNACCOUNTED,
        MODEL_MISROUTED,
    }

    def __init__(self, router: ModelRouterPort, *, name: str = MODEL_VERIFIER_NAME) -> None:
        super().__init__(MODEL_COMPLETE, name=name)
        self._router = router

    async def _check(
        self, condition: str, arguments: JsonMapping, result: ExecutionResult
    ) -> ErrorMetadata | None:
        if not isinstance(arguments.get("input"), str):
            return self._failure(
                condition,
                VERIFICATION_ARGUMENTS_INVALID,
                "input must be a string",
                retryable=False,
            )
        if condition == MODEL_ROUTED_AS_ASKED:
            return self._routed(condition, arguments, result)
        return self._answered(condition, result)

    def _routed(
        self, condition: str, arguments: JsonMapping, result: ExecutionResult
    ) -> ErrorMetadata | None:
        """The route these arguments ask for, against the provider and profile that answered.

        The comparison is strongest on the **provider**: ``output["provider"]`` is the name the
        provider itself put in its result. The profile can only be compared with what the tool
        declared — the model that answered is a vendor's id, which the Core does not translate
        (§26) — and that is a declared limit of this condition.

        A policy that no longer routes these arguments fails the condition rather than passing
        it: a run that cannot be justified today is not a run that was verified.
        """
        routing = routing_arguments(arguments)
        if routing is None:
            return self._failure(
                condition,
                VERIFICATION_ARGUMENTS_INVALID,
                "task_type and model_hint must be strings",
                retryable=False,
            )
        try:
            route = self._router.route(*routing)
        except RoutingError as error:
            return self._failure(
                condition,
                MODEL_MISROUTED,
                f"the policy does not route this call any more: {error.code}",
                retryable=False,
                details={"routing_error": error.code},
            )
        actual = (result.output.get("provider"), result.output.get("profile"))
        if actual == (route.provider, route.profile):
            return None
        return self._failure(
            condition,
            MODEL_MISROUTED,
            "the call did not go where the policy routes it",
            retryable=False,
            details={
                "expected_provider": route.provider,
                "actual_provider": actual[0],
                "expected_profile": route.profile,
                "actual_profile": actual[1],
            },
        )

    def _answered(self, condition: str, result: ExecutionResult) -> ErrorMetadata | None:
        missing = tuple(
            key for key in ("output", "provider", "model") if not self._text(result, key)
        )
        if missing:
            return self._failure(
                condition,
                MODEL_NO_ANSWER,
                f"the result carries no {', '.join(missing)}",
                retryable=False,
                details={"missing": list(missing)},
            )
        if result.usage is None:
            return self._failure(
                condition,
                MODEL_UNACCOUNTED,
                "the result carries no provider usage: the call cannot be accounted for",
                retryable=False,
            )
        return None

    @staticmethod
    def _text(result: ExecutionResult, key: str) -> bool:
        """Whether ``output[key]`` is a non-empty string. The value never leaves this frame: a
        verifier reports that something is missing, never what was there (§57)."""
        value = result.output.get(key)
        return isinstance(value, str) and value != ""


class CaptureScreenVerifier(Verifier):
    """``perception.capture_screen`` verified from the disk, not from the tool's word (§20, §63).

    ``directory`` is the capture store's, and ``ttl`` its retention: both are read, neither is
    created — a store that does not exist holds no capture. Every number the tool reported is
    re-derived here by reading the file again through the same read-only classification the tool
    used, so a capture the tool accepted is one this finds, with the same code when it is not.

    **A declared limit**: this must run inside the capture's TTL, or it will not find an artefact
    that expired in the meantime. In the pipeline it runs in the same step, milliseconds later; it
    is written down for whoever one day verifies in arrears.
    """

    reads_the_machine: ClassVar[bool] = True
    """The capture store of this machine: it does not travel (ADR 0038 §14)."""
    conditions: ClassVar[frozenset[str]] = frozenset({CAPTURE_EXISTS, CAPTURE_MATCHES})
    failure_codes: ClassVar[frozenset[str]] = (
        COMMON_FAILURE_CODES | CAPTURE_CODES | {CAPTURE_DECLARED_MISMATCH}
    )

    def __init__(
        self, directory: Path | str, ttl: timedelta, *, name: str = CAPTURE_VERIFIER_NAME
    ) -> None:
        super().__init__(PERCEPTION_CAPTURE_SCREEN, name=name)
        self._directory = Path(directory).expanduser().absolute()
        self._ttl = ttl

    async def _check(
        self, condition: str, arguments: JsonMapping, result: ExecutionResult
    ) -> ErrorMetadata | None:
        del arguments  # the intent determines no pixel; what is under test is the claim
        name = result.output.get("path")
        if not isinstance(name, str):
            return self._failure(
                condition,
                VERIFICATION_ARGUMENTS_INVALID,
                "output.path must be a string",
                retryable=False,
            )
        found = inspect(self._directory, name, self._ttl)
        if isinstance(found, CaptureProblem):
            return self._failure(condition, found.code, found.message(name), retryable=False)
        if condition == CAPTURE_EXISTS:
            return None
        differs = self._differences(found, result.output)
        if not differs:
            return None
        return self._failure(
            condition,
            CAPTURE_DECLARED_MISMATCH,
            f"{name!r} is not the capture the result describes: {', '.join(differs)}",
            retryable=False,
        )

    @staticmethod
    def _differences(found: Capture, declared: JsonMapping) -> tuple[str, ...]:
        """Which of the four declared facts the disk contradicts, named and never quantified.

        A digest is reported as differing and never printed beside the other: two hashes in a
        message are two fingerprints of the user's screen in the audit trail (§57).
        """
        checks = (
            ("bytes", found.bytes),
            ("sha256", found.sha256),
            ("width", found.size.width),
            ("height", found.size.height),
        )
        return tuple(key for key, actual in checks if declared.get(key) != actual)


class ReadScreenTextVerifier(Verifier):
    """``perception.read_screen_text`` verified from the disk (§20, §63; ADR 0030 §14).

    The sibling of :class:`CaptureScreenVerifier`, reading the other artefact of the same store
    with the same read-only classification the tool wrote through — so a recognition the tool
    accepted is one this finds, and the two cannot disagree about what a readable artefact is.

    It **re-reads and does not re-recognise**: verifying is not redoing. It parses the JSON Lines
    back and counts them, which is how ``lines`` and ``characters`` are re-derived rather than
    believed.

    Two declared limits, and they are different sizes. The small one is the capture's: this must
    run inside the TTL. The large one is that it cannot say the text is what was on the screen —
    only that it is what the tool said it wrote.
    """

    reads_the_machine: ClassVar[bool] = True
    """The capture store of this machine: it does not travel (ADR 0038 §14)."""
    conditions: ClassVar[frozenset[str]] = frozenset({TEXT_EXISTS, TEXT_MATCHES})
    failure_codes: ClassVar[frozenset[str]] = (
        COMMON_FAILURE_CODES | CAPTURE_CODES | {TEXT_DECLARED_MISMATCH}
    )

    def __init__(
        self, directory: Path | str, ttl: timedelta, *, name: str = TEXT_VERIFIER_NAME
    ) -> None:
        super().__init__(PERCEPTION_READ_SCREEN_TEXT, name=name)
        self._directory = Path(directory).expanduser().absolute()
        self._ttl = ttl

    async def _check(
        self, condition: str, arguments: JsonMapping, result: ExecutionResult
    ) -> ErrorMetadata | None:
        del arguments  # ``purpose`` and ``region`` determine no character; the claim is under test
        name = result.output.get("path")
        if not isinstance(name, str):
            return self._failure(
                condition,
                VERIFICATION_ARGUMENTS_INVALID,
                "output.path must be a string",
                retryable=False,
            )
        found = inspect_text(self._directory, name, self._ttl)
        if isinstance(found, CaptureProblem):
            return self._failure(condition, found.code, found.message(name), retryable=False)
        if condition == TEXT_EXISTS:
            return None
        differs = self._differences(found, result.output)
        if not differs:
            return None
        return self._failure(
            condition,
            TEXT_DECLARED_MISMATCH,
            f"{name!r} is not the recognition the result describes: {', '.join(differs)}",
            retryable=False,
        )

    @staticmethod
    def _differences(found: TextArtefact, declared: JsonMapping) -> tuple[str, ...]:
        """Which declared facts the disk contradicts, named and never quantified.

        The names of what differs, never the values: a digest printed beside another is two
        fingerprints of the user's screen in the audit trail, and a character count is harmless
        while the text it counts is not (§57).
        """
        checks = (
            ("bytes", found.bytes),
            ("sha256", found.sha256),
            ("lines", found.lines),
            ("characters", found.characters),
        )
        return tuple(key for key, actual in checks if declared.get(key) != actual)


TRANSCRIPT_EXISTS: Final = "transcript.exists"
"""At the declared name there is a regular file inside the store, and it parses as JSON Lines."""
TRANSCRIPT_MATCHES: Final = "transcript.matches"
"""Bytes, digest, segments and characters read from the disk are the ones the result declares."""
TRANSCRIPT_DECLARED_MISMATCH: Final = "transcript.declared_mismatch"
"""The disk contradicts the result. Names what differs and never the values (§57)."""
LISTEN_VERIFIER_NAME: Final = "perception-listen-verifier"


class ListenVerifier(Verifier):
    """``perception.listen`` verified from the disk (§20, §63; M11.2, ADR 0036).

    It **re-reads and does not re-listen**: verifying is not redoing, and here it could not be —
    the audio is gone by construction, and the room has moved on.

    **What it proves, and the limit is bigger than the capture's.** It proves that ELA wrote what
    it says it wrote: a transcript at the declared name, inside the store, with the byte count,
    the digest, the segment count and the character count the result declares. It does **not**
    prove that those are the words somebody said — nothing ELA has can prove that, because the
    only thing that could is the recording, and the milestone decided not to keep it (dec. E).

    Said plainly because a verifier that sounded stronger than it is would be worse than none
    (M11.1 dec. C, applied to a reading instead of a sound): *this says ELA's transcript is on the
    disk as described, not that the room said it.*
    """

    reads_the_machine: ClassVar[bool] = True
    """The capture store of this machine: it does not travel (ADR 0038 §14)."""
    conditions: ClassVar[frozenset[str]] = frozenset({TRANSCRIPT_EXISTS, TRANSCRIPT_MATCHES})
    failure_codes: ClassVar[frozenset[str]] = (
        COMMON_FAILURE_CODES | CAPTURE_CODES | {TRANSCRIPT_DECLARED_MISMATCH}
    )

    def __init__(
        self, directory: Path | str, ttl: timedelta, *, name: str = LISTEN_VERIFIER_NAME
    ) -> None:
        super().__init__(PERCEPTION_LISTEN, name=name)
        self._directory = Path(directory).expanduser().absolute()
        self._ttl = ttl

    async def _check(
        self, condition: str, arguments: JsonMapping, result: ExecutionResult
    ) -> ErrorMetadata | None:
        del arguments  # ``purpose`` and ``seconds`` determine no word; the claim is under test
        name = result.output.get("path")
        if not isinstance(name, str):
            return self._failure(
                condition,
                VERIFICATION_ARGUMENTS_INVALID,
                "output.path must be a string",
                retryable=False,
            )
        found = inspect_transcript(self._directory, name, self._ttl)
        if isinstance(found, CaptureProblem):
            return self._failure(condition, found.code, found.message(name), retryable=False)
        if condition == TRANSCRIPT_EXISTS:
            return None
        differs = self._differences(found, result.output)
        if not differs:
            return None
        return self._failure(
            condition,
            TRANSCRIPT_DECLARED_MISMATCH,
            f"{name!r} is not the transcript the result describes: {', '.join(differs)}",
            retryable=False,
        )

    @staticmethod
    def _differences(found: TranscriptArtefact, declared: JsonMapping) -> tuple[str, ...]:
        """Which declared facts the disk contradicts, named and never quantified (§57)."""
        checks = (
            ("bytes", found.bytes),
            ("sha256", found.sha256),
            ("segments", found.segments),
            ("characters", found.characters),
        )
        return tuple(key for key, actual in checks if declared.get(key) != actual)


SPEECH_TOOK_REAL_TIME: Final = "speech.took_real_time"
"""The helper was alive long enough for those words to have been spoken at the speed of speech."""
SPEECH_TEXT_MATCHES: Final = "speech.text_matches"
"""What the result says was said hashes to the text that was asked for."""
SPEECH_TOO_FAST: Final = "speech.too_fast"
SPEECH_TEXT_MISMATCH: Final = "speech.text_mismatch"

MIN_SECONDS_PER_CHARACTER: Final = 0.005
"""The floor below which a "spoken" sentence was not spoken (M11.1 dec. C).

**Measured on 2026-09-08 on this machine**: 600 characters took 31,5 s at ``say``'s default rate
and 37,8 s at its slowest — 52 and 63 ms per character. The floor is 5 ms, roughly **ten times
below** the fastest reading, because it is not a performance budget: it is the line under which
the only explanation is that no sound was produced.

It works at all because speech is played in real time. There is no faster machine that speaks
faster; a ``say`` that returned early returned without playing, which is exactly the failure this
condition exists to catch — an exit status of zero that means nothing came out.
"""


class SpeakVerifier(Verifier):
    """``voice.speak`` verified against the clock and the argument (§20, §63; M11.1 dec. C).

    **What no verifier of a voice can do, said plainly, because saying it is the point.** Sound
    leaves no artefact. There is no file to re-read the way the note and the capture are re-read,
    and no runner has ears. So this verifier is built to be honest about its reach rather than to
    look as strong as its siblings:

    > It proves that ELA asked macOS to speak the words it was given, and that macOS spent the
    > time speaking them. **It does not prove that anybody heard anything.**

    That distinction is ADR 0030 §8 applied to a write instead of a read: *a reading that can mean
    two things must be split before it is handed on*. "The helper exited zero" can mean the
    sentence was spoken or that it was rendered to nothing at all, and the two are separated here
    by the only witness available — the clock. A ``say`` that returned in a tenth of the time the
    words take did not play them.

    **One class, two capabilities** (M11.3). ``voice.speak`` and ``voice.speak_online`` are two
    permissions over the same act, and the two conditions hold for both without a line changing:
    the digest proves ELA asked for the words it was given, and the clock proves the sound took
    the time those words take. The only care needed was on the other side — the online tool
    reports **playback** in ``spoken_seconds`` and the round-trip apart, because a duration that
    included the network would inflate exactly the number this verifier leans on.

    **What it deliberately does not check: that an audio output device existed.** Reading that
    would need a new perception family and a new field on ``RawObservation``, which M11.1 declared
    out of scope; and :data:`MIN_SECONDS_PER_CHARACTER` catches the case that reading was wanted
    for — a helper that succeeds without producing sound — from the outside, with no new port.
    Recorded so that whoever wants the device itself knows it was considered and why it is absent.
    """

    reads_the_machine: ClassVar[bool] = False
    """The text described and ``spoken_seconds``: nothing of any disk. From a node, that the time
    is true is the node's word — its clock measured it (ADR 0038 §14)."""
    conditions: ClassVar[frozenset[str]] = frozenset({SPEECH_TOOK_REAL_TIME, SPEECH_TEXT_MATCHES})
    failure_codes: ClassVar[frozenset[str]] = COMMON_FAILURE_CODES | {
        SPEECH_TOO_FAST,
        SPEECH_TEXT_MISMATCH,
    }

    def __init__(
        self, capability_id: CapabilityId = VOICE_SPEAK, *, name: str = SPEECH_VERIFIER_NAME
    ) -> None:
        super().__init__(capability_id, name=name)

    async def _check(
        self, condition: str, arguments: JsonMapping, result: ExecutionResult
    ) -> ErrorMetadata | None:
        text = arguments.get("text")
        if not isinstance(text, str) or not text:
            return self._failure(
                condition,
                VERIFICATION_ARGUMENTS_INVALID,
                "text must be a non-empty string",
                retryable=False,
            )
        if condition == SPEECH_TEXT_MATCHES:
            return self._matches(condition, text, result)
        return self._took_real_time(condition, text, result)

    def _matches(self, condition: str, text: str, result: ExecutionResult) -> ErrorMetadata | None:
        """The digest the tool reported against the digest of the argument.

        Never the words, on either side of the comparison or in the failure: a message carrying
        what ELA said would put it in the audit trail, which is the thing the tool went out of its
        way not to do (§57).
        """
        declared = result.output.get("sha256")
        if declared == digest_of(text):
            return None
        return self._failure(
            condition,
            SPEECH_TEXT_MISMATCH,
            "the result does not describe the text that was asked for",
            retryable=False,
            details={"expected_characters": len(text), "declared": result.output.get("characters")},
        )

    def _took_real_time(
        self, condition: str, text: str, result: ExecutionResult
    ) -> ErrorMetadata | None:
        """Whether the helper lived long enough for those words to have been said aloud."""
        spoken = result.output.get("spoken_seconds")
        if not isinstance(spoken, int | float) or isinstance(spoken, bool):
            return self._failure(
                condition,
                VERIFICATION_ARGUMENTS_INVALID,
                "output.spoken_seconds must be a number",
                retryable=False,
            )
        floor = len(text) * MIN_SECONDS_PER_CHARACTER
        if spoken >= floor:
            return None
        return self._failure(
            condition,
            SPEECH_TOO_FAST,
            "the helper finished too quickly for the words to have been spoken aloud",
            retryable=True,
            details={"spoken_seconds": spoken, "at_least": round(floor, 3)},
        )


# --------------------------------------------------------------------------------------
# terminal.run (M13.2, ADR 0047)
# --------------------------------------------------------------------------------------

TERMINAL_VERIFIER_NAME: Final = "terminal-run-verifier"
TERMINAL_EXIT_CODE_MATCHES: Final = "terminal.exit_code_matches"
"""The program ended **by itself** with the code the **plan** expects (``expect_exit``, 0 by
default) — not a signal, not ELA stopping it."""
TERMINAL_OUTPUT_WHOLE: Final = "terminal.output_whole"
"""Nothing of either stream was cut, and no sequence was replaced."""
TERMINAL_PROGRAM_UNCHANGED: Final = "terminal.program_unchanged"
"""The file the declared path leads to, **read now from the disk**, still has the identity of the
start-up, and the result names that very file."""
TERMINAL_EXIT_MISMATCH: Final = "terminal.exit_code_mismatch"
TERMINAL_OUTPUT_INCOMPLETE: Final = "terminal.output_incomplete"


class TerminalRunVerifier(Verifier):
    """``terminal.run``: **what it verified, and never that the effect happened** (§63; dec. 9).

    For what a program printed there is no independent source — the case of ``core.echo``, whose
    arguments are its whole observable world, and of the voice, which «does not prove that anybody
    heard anything». Running the command again to check it is forbidden twice over (rules 18 and
    32) and would be a capability of its own. So the three conditions say what **can** be said:

    > the program ended by itself with the code the plan expected; nothing of what it printed is
    > missing or replaced; and the program on the disk is still the one ELA fixed at start-up.

    **A code is the program's word.** The effect on the world ELA does not see, and a plan that
    wants it adds a step that reads the world — an ``fs.read`` after a command that writes a file.
    «If it executes code, it must execute tests» (§63) becomes a ``terminal.run`` of ``pytest`` with
    ``terminal.exit_code_matches``: the tests are the verifier of the code, not the terminal.

    The expected code is read from the **arguments**, the plan's intent (ADR 0014 §2), never from
    the ``expect_exit`` the tool copied into its result. Every failure says it with numbers and
    never with the arguments or the output, which a failure carries into the audit (§57).
    """

    reads_the_machine: ClassVar[bool] = True
    """``terminal.program_unchanged`` reads the Core's disk: on a node it would compare the Core's
    ``/usr/bin/git`` with a run that happened elsewhere — the false positive of ADR 0038 §14. So
    ``terminal.run`` stays, and a test says so (dec. 11)."""
    conditions: ClassVar[frozenset[str]] = frozenset(
        {TERMINAL_EXIT_CODE_MATCHES, TERMINAL_OUTPUT_WHOLE, TERMINAL_PROGRAM_UNCHANGED}
    )
    failure_codes: ClassVar[frozenset[str]] = (
        COMMON_FAILURE_CODES | {TERMINAL_EXIT_MISMATCH, TERMINAL_OUTPUT_INCOMPLETE} | PROGRAM_CODES
    )

    def __init__(self, programs: Programs, *, name: str = TERMINAL_VERIFIER_NAME) -> None:
        super().__init__(TERMINAL_RUN, name=name)
        self._programs = programs

    async def _check(
        self, condition: str, arguments: JsonMapping, result: ExecutionResult
    ) -> ErrorMetadata | None:
        if condition == TERMINAL_EXIT_CODE_MATCHES:
            return self._ended_as_expected(condition, arguments, result)
        if condition == TERMINAL_OUTPUT_WHOLE:
            return self._whole(condition, result)
        return await self._unchanged(condition, arguments, result)

    def _ended_as_expected(
        self, condition: str, arguments: JsonMapping, result: ExecutionResult
    ) -> ErrorMetadata | None:
        expected = arguments.get("expect_exit", 0)
        if type(expected) is not int:
            return self._failure(
                condition,
                VERIFICATION_ARGUMENTS_INVALID,
                "expect_exit must be an integer",
                retryable=False,
            )
        ended, code = result.output.get("ended"), result.output.get("exit_code")
        code = code if type(code) is int else None
        if ended == "exited" and code == expected:
            return None
        return self._failure(
            condition,
            TERMINAL_EXIT_MISMATCH,
            f"the program did not end by itself with the expected code {expected}: "
            + (f"it ended with {code}" if ended == "exited" else "it did not end by itself"),
            retryable=False,
            details={"expected": expected, "exit_code": code},
        )

    def _whole(self, condition: str, result: ExecutionResult) -> ErrorMetadata | None:
        for name in ("stdout", "stderr"):
            try:
                kept = CommandOutput.model_validate(result.output.get(name))
            except ValueError:  # pydantic's ValidationError: numbers that are not a stream
                return self._failure(
                    condition,
                    TERMINAL_OUTPUT_INCOMPLETE,
                    f"the result does not say what it kept of {name}",
                    retryable=False,
                )
            if kept.missing or kept.replaced:
                return self._failure(
                    condition,
                    TERMINAL_OUTPUT_INCOMPLETE,
                    f"{name} is not whole: {kept.missing} bytes not kept, {kept.replaced} "
                    "sequences replaced",
                    retryable=False,
                    details={"missing": kept.missing, "replaced": kept.replaced},
                )
        return None

    async def _unchanged(
        self, condition: str, arguments: JsonMapping, result: ExecutionResult
    ) -> ErrorMetadata | None:
        """The program on the disk against the start-up, compared in a thread (it hashes the whole
        file), and each problem under its own code: a program that is not there any more is
        :data:`PROGRAM_GONE`, not changed — there is nothing to compare it with (review of M13.2,
        decision 4)."""
        program = arguments.get("program")
        if not isinstance(program, str):
            return self._failure(
                condition,
                VERIFICATION_ARGUMENTS_INVALID,
                "program must be a string",
                retryable=False,
            )
        problem = await asyncio.to_thread(self._programs.problem, program)
        if problem is not None:
            return self._failure(
                condition, problem.code, _unverified(problem, program), retryable=False
            )
        start = self._programs.at_start(program)
        if start is None or result.output.get("runs") != start.runs:
            return self._failure(
                condition,
                PROGRAM_CHANGED,
                f"the result names another file than the one {'/' + program!r} led to when ELA "
                "started",
                retryable=False,
            )
        return None


def _unverified(problem: ProgramProblem, program: str) -> str:
    """What the verifier could not verify, said as what it found on the disk.

    For a program that is gone the sentence of the tool — «nothing is left to run» — is the wrong
    one after the run: what matters now is that the comparison cannot be made, so the verifier
    cannot vouch for what ran, while what it printed stays in the result.
    """
    if problem.code == PROGRAM_GONE:
        return (
            f"{'/' + program!r} is not there any more, so there is nothing to compare with the "
            "file ELA fixed at start-up: ELA cannot confirm that the program that ran was the one "
            "declared — what it printed is in the result"
        )
    return problem.message
