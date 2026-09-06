"""Tools: the implementations of the capabilities of §29 (M5.1, ADR 0013).

A tool executes under a :class:`~ela.domain.PermissionDecision` it receives as data and never
sees the Guardian; the only module that calls a tool is the executor (rule 16).
"""

from ela.tools.base import ARGUMENTS_INVALID, Outcome, Tool, check_decision
from ela.tools.echo import CORE_ECHO, ECHO_TOOL_NAME, EchoTool
from ela.tools.errors import ToolNotFound, ToolsError
from ela.tools.notes import (
    DIRECTORY_MODE,
    FILE_MODE,
    IO_ERROR,
    NOTES_TOOL_NAME,
    PATH_INVALID,
    PATH_IS_DIRECTORY,
    PATH_OUTSIDE_WORKSPACE,
    PATH_SYMLINK,
    WORKSPACE_WRITE_NOTE,
    WriteNoteTool,
    is_relative_note_path,
)
from ela.tools.registry import ToolRegistry, tools_v01
from ela.tools.settings import WorkspaceSettings, default_workspace_dir

__all__ = [
    "ARGUMENTS_INVALID",
    "CORE_ECHO",
    "DIRECTORY_MODE",
    "ECHO_TOOL_NAME",
    "FILE_MODE",
    "IO_ERROR",
    "NOTES_TOOL_NAME",
    "PATH_INVALID",
    "PATH_IS_DIRECTORY",
    "PATH_OUTSIDE_WORKSPACE",
    "PATH_SYMLINK",
    "WORKSPACE_WRITE_NOTE",
    "EchoTool",
    "Outcome",
    "Tool",
    "ToolNotFound",
    "ToolRegistry",
    "ToolsError",
    "WorkspaceSettings",
    "WriteNoteTool",
    "check_decision",
    "default_workspace_dir",
    "is_relative_note_path",
    "tools_v01",
]
