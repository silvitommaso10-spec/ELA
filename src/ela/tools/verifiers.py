"""The verifiers of v0.1 (spec §63; ADR 0014 §2): one per tool, each read-only by construction.

* :class:`EchoVerifier` for ``core.echo``: the output repeats the message. It is the whole
  observable world of an echo, and a declared limit.
* :class:`ModelCompleteVerifier` for ``model.complete``: the tool **answered and can account
  for it** — a text, the provider and the model that produced it, and a
  :class:`~ela.domain.ProviderUsage`. It cannot check that the answer is *good*, and it must not
  ask the model again: a second call would cost money and send the user's content out twice
  (§57). What it can refuse is a success nobody can account for (§32), and that is a declared
  limit, as the echo's is. Whether the call went where a routing policy said is
  ``model.routed_as_asked``, and it arrives with the router in M7.3.
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

import hashlib
import os
import stat
from pathlib import Path
from typing import ClassVar, Final

from ela.domain import ErrorMetadata, ExecutionResult, JsonMapping
from ela.tools.echo import CORE_ECHO
from ela.tools.model import MODEL_COMPLETE
from ela.tools.notes import WORKSPACE_WRITE_NOTE
from ela.tools.paths import PATH_CODES, classify, resolve_workspace
from ela.tools.verify import COMMON_FAILURE_CODES, VERIFICATION_ARGUMENTS_INVALID, Verifier

__all__ = [
    "ECHO_MESSAGE_MATCHES",
    "ECHO_MESSAGE_MISMATCH",
    "ECHO_VERIFIER_NAME",
    "MODEL_ANSWERED",
    "MODEL_NO_ANSWER",
    "MODEL_UNACCOUNTED",
    "MODEL_VERIFIER_NAME",
    "NOTES_VERIFIER_NAME",
    "NOTE_CONTENT_MATCHES",
    "NOTE_CONTENT_MISMATCH",
    "NOTE_EXISTS",
    "NOTE_UNREADABLE",
    "EchoVerifier",
    "ModelCompleteVerifier",
    "WriteNoteVerifier",
]

ECHO_VERIFIER_NAME: Final = "core-echo-verifier"
NOTES_VERIFIER_NAME: Final = "workspace-notes-verifier"
MODEL_VERIFIER_NAME: Final = "model-complete-verifier"

MODEL_ANSWERED: Final = "model.answered"
"""The result carries a non-empty text, the provider and the model that produced it, and the
:class:`~ela.domain.ProviderUsage` of the call (§32)."""
MODEL_NO_ANSWER: Final = "model.no_answer"
MODEL_UNACCOUNTED: Final = "model.unaccounted"
"""A SUCCEEDED completion with no usage: the call cannot be accounted for, and §32 asks that a
provider call be. A tool that answers without saying what it consumed has not been verified."""

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


class WriteNoteVerifier(Verifier):
    """``workspace.write_note`` verified from the disk, not from the tool's word (§63).

    ``root`` is resolved the way the tool resolves it — expanded, absolute, real — so that the
    two agree on where the workspace is; it is **not** created: a workspace that does not exist
    holds no note.
    """

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


class ModelCompleteVerifier(Verifier):
    """``model.complete`` answered, and the answer can be accounted for (§29, §32, §63).

    Read-only like every verifier, and read-only in a stronger sense here: the world it could
    look at is a model, and looking would mean asking again — a second charge and the user's
    content across the network a second time (§57). So what it checks is what the run left
    behind: a text, who produced it, and what it cost. It cannot judge whether the answer is
    right; nothing in v0.1 can, and that is written down rather than implied.
    """

    conditions: ClassVar[frozenset[str]] = frozenset({MODEL_ANSWERED})
    failure_codes: ClassVar[frozenset[str]] = COMMON_FAILURE_CODES | {
        MODEL_NO_ANSWER,
        MODEL_UNACCOUNTED,
    }

    def __init__(self, *, name: str = MODEL_VERIFIER_NAME) -> None:
        super().__init__(MODEL_COMPLETE, name=name)

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
