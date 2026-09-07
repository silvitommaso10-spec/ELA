"""Executive Core (spec §12): the executor of the pipeline of §27 (M5.1, ADR 0013; M5.2, ADR
0014; M5.3, ADR 0015).

:mod:`ela.executive.executor` runs one step of a plan through Capability → Guardian →
Authorization → Tool → Audit → **Verification**, and is the only caller of ``Tool.execute``
(rule 16) and of ``complete_step`` (rule 17) in the Core. Since M5.3 nothing it needs lives only
in memory: requests for approval and results are stored, and a retry after a crash resumes the
step from the first write that is missing instead of running the tool again.

:mod:`ela.executive.runner` is the driver above it (M6.3, ADR 0019): the loop that chooses a
ready step, asks the Device Orchestrator where it runs, executes it and closes the task. It
writes nothing of its own — every fact it produces is already an event of ``place``, of the
engine or of the executor. The Planner (§13) is still to come; M6.3 executes plans, it does not
produce them.
"""

from ela.executive.errors import ExecutorError, RunnerError
from ela.executive.executor import (
    APPROVAL_NAMESPACE,
    AUTHORIZATION_NAMESPACE,
    CONSUMING_RULES,
    DEFAULT_APPROVAL_TTL,
    EXECUTION_INTERRUPTED,
    GRANT_VANISHED,
    MAX_APPROVAL_TTL,
    RECOVERED,
    STARTED_ID,
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
from ela.executive.runner import OUTCOMES, RUNNABLE_STATES, Run, RunOutcome, TaskRunner

__all__ = [
    "APPROVAL_NAMESPACE",
    "AUTHORIZATION_NAMESPACE",
    "CONSUMING_RULES",
    "DEFAULT_APPROVAL_TTL",
    "EXECUTION_INTERRUPTED",
    "GRANT_VANISHED",
    "MAX_APPROVAL_TTL",
    "OUTCOMES",
    "RUNNABLE_STATES",
    "RECOVERED",
    "STARTED_ID",
    "TOOL_EXCEPTION",
    "TOOL_REFUSED",
    "VERIFICATION_EXCEPTION",
    "VERIFICATION_FAILED",
    "Execution",
    "Executor",
    "ExecutorError",
    "Run",
    "RunOutcome",
    "RunnerError",
    "TaskRunner",
    "Verification",
    "approved_targets",
    "select_authorization",
]
