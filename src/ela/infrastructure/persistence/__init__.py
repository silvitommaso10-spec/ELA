"""Persistence of the Core's state on SQLite (spec §54 "persistence"; ADR 0006).

SQLAlchemy 2 async on ``aiosqlite``; ORM rows kept apart from the domain entities and translated
by an explicit mapper; schema owned by alembic (``migrations/``). Configuration comes from
:class:`PersistenceSettings` (``ELA_DB_URL``). The audit log (§32) is append-only at every level
and hash-chained; :func:`verify_chain` checks the chain (ADR 0007). Requests for consent and
what tools produced live in ``approvals`` and ``execution_results`` (M5.3, ADR 0015),
the nodes of §16 in ``devices`` (M6.1, ADR 0016), the one-shot codes that enroll a node
in ``enrollments`` (M12.1, ADR 0037), and the work handed to a remote node in ``assignments``
(M12.2, ADR 0038).
"""

from ela.infrastructure.persistence.approval_store import SqlApprovalStore
from ela.infrastructure.persistence.assignment_store import SqlAssignmentStore
from ela.infrastructure.persistence.audit_log import SqlAuditLog, verify_chain
from ela.infrastructure.persistence.authorization_store import SqlAuthorizationStore
from ela.infrastructure.persistence.device_registry import SqlDeviceRegistry
from ela.infrastructure.persistence.engine import (
    async_url,
    ensure_directory,
    make_engine,
    make_session_factory,
    sync_url,
)
from ela.infrastructure.persistence.enrollment_store import SqlEnrollmentStore
from ela.infrastructure.persistence.execution_result_store import SqlExecutionResultStore
from ela.infrastructure.persistence.schema import missing_tables
from ela.infrastructure.persistence.settings import PersistenceSettings, default_db_url
from ela.infrastructure.persistence.task_repository import SqlTaskRepository

__all__ = [
    "PersistenceSettings",
    "SqlApprovalStore",
    "SqlAssignmentStore",
    "SqlAuditLog",
    "SqlAuthorizationStore",
    "SqlDeviceRegistry",
    "SqlEnrollmentStore",
    "SqlExecutionResultStore",
    "SqlTaskRepository",
    "async_url",
    "default_db_url",
    "ensure_directory",
    "make_engine",
    "make_session_factory",
    "missing_tables",
    "sync_url",
    "verify_chain",
]
