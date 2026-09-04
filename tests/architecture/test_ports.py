"""The ports obey the rules of M1.3, and the rules fail when a port breaks them.

Every rule is also run against a protocol written on purpose to violate it (CLAUDE.md,
"Qualità"): a rule that only ever passes proves nothing.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pytest

from ela.domain import AuditEvent, ExecutionResult, JsonMapping, PermissionDecision
from ela.ports import AuditLog, AuthorizationStore, PermissionGuardianPort, ToolPort
from tests.architecture.port_rules import (
    append_only_violations,
    execute_without_decision,
    unchecked_protocols,
    undocumented_protocols,
)
from tests.contracts.protocols import port_protocols

PORTS = tuple(port_protocols())
GUARDIAN_AND_STORE = (PermissionGuardianPort, AuthorizationStore)


def test_the_module_actually_has_ports() -> None:
    """A rule applied to an empty tuple would hold vacuously."""
    assert len(PORTS) == 11


def test_every_port_is_runtime_checkable() -> None:
    assert unchecked_protocols(PORTS) == []


def test_every_port_cites_the_spec() -> None:
    assert undocumented_protocols(PORTS) == []


def test_audit_log_is_append_only() -> None:
    assert append_only_violations(AuditLog) == []


def test_tool_execute_requires_a_decision_and_nothing_that_decides() -> None:
    assert execute_without_decision(ToolPort, GUARDIAN_AND_STORE) == []


# ----------------------------------------------------------------------------------------
# The same rules, applied to protocols written to break them.
# ----------------------------------------------------------------------------------------


class _NotCheckable(Protocol):
    """Documented (§32) but not runtime_checkable."""

    def now(self) -> None: ...


@runtime_checkable
class _Undocumented(Protocol):
    def now(self) -> None: ...


@runtime_checkable
class _LogWithUpdate(Protocol):
    """§32, but with a way to rewrite history."""

    async def append(self, event: AuditEvent) -> None: ...
    async def read(self) -> tuple[AuditEvent, ...]: ...
    async def update(self, event: AuditEvent) -> None: ...


@runtime_checkable
class _LogWithPurge(Protocol):
    """§32, with a member that is not append or read even if its name looks innocent."""

    async def append(self, event: AuditEvent) -> None: ...
    async def read(self) -> tuple[AuditEvent, ...]: ...
    async def purge(self) -> None: ...


@runtime_checkable
class _LogWithoutRead(Protocol):
    async def append(self, event: AuditEvent) -> None: ...


@runtime_checkable
class _ToolWithoutDecision(Protocol):
    """§28, but execute can be called with no decision at all."""

    async def execute(self, arguments: JsonMapping) -> ExecutionResult: ...


@runtime_checkable
class _ToolDecidingLater(Protocol):
    """§28, with the decision present but not first: a positional call could skip it."""

    async def execute(
        self, arguments: JsonMapping, decision: PermissionDecision
    ) -> ExecutionResult: ...


@runtime_checkable
class _ToolWithAGuardian(Protocol):
    """§28, but the tool receives the Guardian and could ask for a friendlier decision."""

    async def execute(
        self,
        decision: PermissionDecision,
        arguments: JsonMapping,
        guardian: PermissionGuardianPort,
    ) -> ExecutionResult: ...


@runtime_checkable
class _ToolWithAStore(Protocol):
    async def execute(
        self,
        decision: PermissionDecision,
        arguments: JsonMapping,
        store: AuthorizationStore,
    ) -> ExecutionResult: ...


@runtime_checkable
class _NoExecute(Protocol):
    def name(self) -> str: ...


def test_checkable_rule_reports_a_plain_protocol() -> None:
    assert unchecked_protocols((_NotCheckable,)) == ["_NotCheckable"]
    assert unchecked_protocols((_Undocumented,)) == []


def test_documented_rule_reports_a_missing_section() -> None:
    assert undocumented_protocols((_Undocumented,)) == ["_Undocumented"]
    assert undocumented_protocols((_NotCheckable,)) == []


@pytest.mark.parametrize(
    "log", [_LogWithUpdate, _LogWithPurge, _LogWithoutRead], ids=lambda c: c.__name__
)
def test_append_only_rule_reports_an_altered_log(log: type) -> None:
    assert append_only_violations(log) != []


@pytest.mark.parametrize(
    "tool",
    [_ToolWithoutDecision, _ToolDecidingLater, _ToolWithAGuardian, _ToolWithAStore, _NoExecute],
    ids=lambda c: c.__name__,
)
def test_tool_rule_reports_execute_without_decision(tool: type) -> None:
    assert execute_without_decision(tool, GUARDIAN_AND_STORE) != []
