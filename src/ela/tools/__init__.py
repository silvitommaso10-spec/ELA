"""Tools and verifiers: the implementations of the capabilities of §29 and their checks (M5.1,
ADR 0013; M5.2, ADR 0014).

A tool executes under a :class:`~ela.domain.PermissionDecision` it receives as data and never
sees the Guardian; the only module that calls a tool is the executor (rule 16). A verifier
checks the world against the success conditions of a step after the tool ran, is a separate
object from the tool by construction, and writes nothing (rule 18). Where a note path leads is
classified once, in :mod:`ela.tools.paths`, for both.
"""

from ela.tools.base import ARGUMENTS_INVALID, Outcome, Tool, check_decision
from ela.tools.echo import CORE_ECHO, ECHO_TOOL_NAME, EchoTool
from ela.tools.errors import NotIdempotentError, ToolNotFound, ToolsError, VerifierNotFound
from ela.tools.notes import (
    DIRECTORY_MODE,
    FILE_MODE,
    IO_ERROR,
    NOTES_TOOL_NAME,
    WORKSPACE_WRITE_NOTE,
    WriteNoteTool,
)
from ela.tools.paths import (
    PATH_CODES,
    PATH_INVALID,
    PATH_IS_DIRECTORY,
    PATH_MISSING,
    PATH_NOT_REGULAR,
    PATH_OUTSIDE_WORKSPACE,
    PATH_SYMLINK,
    PATH_UNREACHABLE,
    PathProblem,
    classify,
    is_relative_note_path,
    resolve_workspace,
)
from ela.tools.registry import ToolRegistry, VerifierRegistry, tools_v01, verifiers_v01
from ela.tools.settings import WorkspaceSettings, default_workspace_dir
from ela.tools.verifiers import (
    ECHO_MESSAGE_MATCHES,
    ECHO_MESSAGE_MISMATCH,
    ECHO_VERIFIER_NAME,
    NOTE_CONTENT_MATCHES,
    NOTE_CONTENT_MISMATCH,
    NOTE_EXISTS,
    NOTE_UNREADABLE,
    NOTES_VERIFIER_NAME,
    EchoVerifier,
    WriteNoteVerifier,
)
from ela.tools.verify import COMMON_FAILURE_CODES, VERIFICATION_ARGUMENTS_INVALID, Verifier

__all__ = [
    "ARGUMENTS_INVALID",
    "COMMON_FAILURE_CODES",
    "CORE_ECHO",
    "DIRECTORY_MODE",
    "ECHO_MESSAGE_MATCHES",
    "ECHO_MESSAGE_MISMATCH",
    "ECHO_TOOL_NAME",
    "ECHO_VERIFIER_NAME",
    "FILE_MODE",
    "IO_ERROR",
    "NOTES_TOOL_NAME",
    "NOTES_VERIFIER_NAME",
    "NOTE_CONTENT_MATCHES",
    "NOTE_CONTENT_MISMATCH",
    "NOTE_EXISTS",
    "NOTE_UNREADABLE",
    "PATH_CODES",
    "PATH_INVALID",
    "PATH_IS_DIRECTORY",
    "PATH_MISSING",
    "PATH_NOT_REGULAR",
    "PATH_OUTSIDE_WORKSPACE",
    "PATH_SYMLINK",
    "PATH_UNREACHABLE",
    "VERIFICATION_ARGUMENTS_INVALID",
    "WORKSPACE_WRITE_NOTE",
    "EchoTool",
    "EchoVerifier",
    "NotIdempotentError",
    "Outcome",
    "PathProblem",
    "Tool",
    "ToolNotFound",
    "ToolRegistry",
    "ToolsError",
    "Verifier",
    "VerifierNotFound",
    "VerifierRegistry",
    "WorkspaceSettings",
    "WriteNoteTool",
    "WriteNoteVerifier",
    "check_decision",
    "classify",
    "default_workspace_dir",
    "is_relative_note_path",
    "resolve_workspace",
    "tools_v01",
    "verifiers_v01",
]
