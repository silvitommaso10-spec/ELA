"""Executive Core (spec §12): the executor of the pipeline of §27 (M5.1, ADR 0013; M5.2, ADR
0014).

:mod:`ela.executive.executor` runs one step of a plan through Capability → Guardian →
Authorization → Tool → Audit → **Verification**, and is the only caller of ``Tool.execute``
(rule 16) and of ``complete_step`` (rule 17) in the Core. The Planner (§13) and the orchestrator
that walks the graph arrive with M6.2.
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
    VERIFICATION_EXCEPTION,
    VERIFICATION_FAILED,
    Execution,
    Executor,
    Verification,
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
    "VERIFICATION_EXCEPTION",
    "VERIFICATION_FAILED",
    "Execution",
    "Executor",
    "ExecutorError",
    "Verification",
    "approved_targets",
    "select_authorization",
]
