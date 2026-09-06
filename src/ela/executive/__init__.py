"""Executive Core (spec §12): the executor of the pipeline of §27 (M5.1, ADR 0013).

:mod:`ela.executive.executor` runs one step of a plan through Capability → Guardian →
Authorization → Tool → Audit, and is the only caller of ``Tool.execute`` in the Core (rule 16).
The Planner (§13) and the orchestrator that walks the graph arrive with M6.2.
"""

from ela.executive.errors import ExecutorError
from ela.executive.executor import (
    AUTHORIZATION_NAMESPACE,
    CONSUMING_RULES,
    DEFAULT_APPROVAL_TTL,
    GRANT_VANISHED,
    LOCAL_DEVICE,
    MAX_APPROVAL_TTL,
    TOOL_EXCEPTION,
    TOOL_REFUSED,
    Execution,
    Executor,
    approved_targets,
    select_authorization,
)

__all__ = [
    "AUTHORIZATION_NAMESPACE",
    "CONSUMING_RULES",
    "DEFAULT_APPROVAL_TTL",
    "GRANT_VANISHED",
    "LOCAL_DEVICE",
    "MAX_APPROVAL_TTL",
    "TOOL_EXCEPTION",
    "TOOL_REFUSED",
    "Execution",
    "Executor",
    "ExecutorError",
    "approved_targets",
    "select_authorization",
]
