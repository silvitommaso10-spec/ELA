"""Executive Core (spec §12): the executor of the pipeline of §27 (M5.1, ADR 0013; M5.2, ADR
0014; M5.3, ADR 0015).

:mod:`ela.executive.executor` runs one step of a plan through Capability → Guardian →
Authorization → Tool → Audit → **Verification**, and is the only caller of ``Tool.execute``
(rule 16) and of ``complete_step`` (rule 17) in the Core. Since M5.3 nothing it needs lives only
in memory: requests for approval and results are stored, and a retry after a crash resumes the
step from the first write that is missing instead of running the tool again. The Planner (§13)
and the orchestrator that walks the graph arrive with M6.2.
"""

from ela.executive.errors import ExecutorError
from ela.executive.executor import (
    APPROVAL_NAMESPACE,
    AUTHORIZATION_NAMESPACE,
    CONSUMING_RULES,
    DEFAULT_APPROVAL_TTL,
    GRANT_VANISHED,
    LOCAL_DEVICE,
    MAX_APPROVAL_TTL,
    RECOVERED,
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
    "APPROVAL_NAMESPACE",
    "AUTHORIZATION_NAMESPACE",
    "CONSUMING_RULES",
    "DEFAULT_APPROVAL_TTL",
    "GRANT_VANISHED",
    "LOCAL_DEVICE",
    "MAX_APPROVAL_TTL",
    "RECOVERED",
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
