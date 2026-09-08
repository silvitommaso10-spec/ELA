"""Harness of the Guardian tests: a catalogue wider than production, fakes for the rest.

The fake registry admits what the real one refuses — a HIGH capability, a scope that constrains
nothing, a loose schema — because the Guardian must deny those too (ADR 0011): the catalogue is
the first line, the Guardian does not rely on it being the only one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

from ela.domain import (
    Authorization,
    AuthorizationId,
    CapabilityId,
    CapabilitySpec,
    JsonMapping,
    RiskLevel,
    TaskId,
    TaskStep,
)
from ela.permissions import (
    DEFAULT_DECISION_TTL,
    PermissionGuardian,
    core_echo,
    model_complete,
    workspace_write_note,
)
from ela.ports import CapabilityRegistryPort
from ela.testing.fakes import FakeAuditLog, FakeCapabilityRegistry, FakeClock, FakeIdGenerator
from tests.domain.examples import NOW, OTHER_STEP_ID, STEP_ID

ECHO: Final = core_echo()
NOTE: Final = workspace_write_note()
COMPLETE: Final = model_complete()
GUARDED_ECHO: Final = ECHO.model_copy(
    update={"id": CapabilityId("core.echo_guarded"), "requires_authorization": True}
)
GUARDED_NOTE: Final = NOTE.model_copy(
    update={"id": CapabilityId("workspace.write_guarded"), "requires_authorization": True}
)
HIGH: Final = ECHO.model_copy(update={"id": CapabilityId("system.shell"), "risk": RiskLevel.HIGH})
CRITICAL: Final = ECHO.model_copy(
    update={"id": CapabilityId("finance.pay"), "risk": RiskLevel.CRITICAL}
)
LOOSE_NOTE: Final = NOTE.model_copy(
    update={
        "id": CapabilityId("workspace.write_loose"),
        "input_schema": {
            "type": "object",
            "properties": {"path": {}, "body": {"type": "string"}},
        },
    }
)
"""A LOW capability whose schema lets ``path`` be missing or anything: the scope check must
catch what the schema does not (the real catalogue would refuse this specification)."""
STATED_ECHO: Final = ECHO.model_copy(
    update={
        "id": CapabilityId("core.echo_stated"),
        "requires_authorization": True,
        "input_schema": {
            "type": "object",
            "properties": {"message": {"type": "string"}, "purpose": {"type": "string"}},
            "required": ["message", "purpose"],
        },
        "prompt_arguments": ("purpose",),
    }
)
"""A capability that declares what the question the user reads must carry (M10.2, ADR 0029 §6).

MEDIUM-shaped in the one way that matters here: it always asks. ``perception.capture_screen`` is
the only real one, and this stands in for it wherever the executor is exercised without a capture
store — the mechanism is the catalogue's and the executor's, not the screen's.
"""
UNCONSTRAINED_SCOPE: Final = ECHO.model_copy(
    update={"id": CapabilityId("broken.scope"), "risk": RiskLevel.LOW, "scope": ("workspace",)}
)
"""A LOW capability with a scope and no scoped argument: a boundary nothing can be checked
against (the real catalogue would refuse this specification too)."""

CATALOGUE: Final = (
    ECHO,
    NOTE,
    COMPLETE,
    GUARDED_ECHO,
    STATED_ECHO,
    GUARDED_NOTE,
    HIGH,
    CRITICAL,
    LOOSE_NOTE,
    UNCONSTRAINED_SCOPE,
)

ECHO_ARGS: Final = {"message": "hello"}
STATED_ARGS: Final = {"message": "hello", "purpose": "showing the reviewer the failing test"}
NOTE_ARGS: Final = {"path": "workspace/notes/briefing.md", "body": "..."}
COMPLETE_ARGS: Final = {"input": "Riassumi le email della riunione."}

ARGUMENTS: Final[Mapping[CapabilityId, JsonMapping]] = MappingProxyType(
    {
        ECHO.id: ECHO_ARGS,
        GUARDED_ECHO.id: ECHO_ARGS,
        STATED_ECHO.id: STATED_ARGS,
        HIGH.id: ECHO_ARGS,
        CRITICAL.id: ECHO_ARGS,
        UNCONSTRAINED_SCOPE.id: ECHO_ARGS,
        NOTE.id: NOTE_ARGS,
        GUARDED_NOTE.id: NOTE_ARGS,
        LOOSE_NOTE.id: NOTE_ARGS,
        COMPLETE.id: COMPLETE_ARGS,
    }
)
"""Arguments that satisfy each capability of the catalogue (ADR 0018).

Since M6.3 the arguments belong to the step, not to whoever calls the executor, so a test that
builds a step needs to know what its capability is called with. One table so that no test invents
a payload of its own and the executor can be exercised on a plan that is complete.
"""

OTHER_TASK_ID: Final = TaskId(UUID("00000000-0000-4000-8000-000000000099"))


@dataclass
class Harness:
    clock: FakeClock
    ids: FakeIdGenerator
    audit: FakeAuditLog
    registry: CapabilityRegistryPort
    guardian: PermissionGuardian

    @property
    def now(self) -> datetime:
        return self.clock.now()


def harness(
    *,
    registry: CapabilityRegistryPort | None = None,
    ttl: timedelta = DEFAULT_DECISION_TTL,
) -> Harness:
    clock, ids, audit = FakeClock(), FakeIdGenerator(), FakeAuditLog()
    catalogue = FakeCapabilityRegistry(CATALOGUE) if registry is None else registry
    guardian = PermissionGuardian(catalogue, clock, ids, audit, decision_ttl=ttl)
    return Harness(clock, ids, audit, catalogue, guardian)


def grant(spec: CapabilitySpec, **changes: Any) -> Authorization:
    """A standing authorization for ``spec`` — no task, no step, no expiry, no use limit — then
    ``changes`` applied. Its scope is the specification's scope unless overridden."""
    base = Authorization(
        id=AuthorizationId(UUID("00000000-0000-4000-8000-000000000777")),
        created_at=NOW,
        capability_id=spec.id,
        scope=spec.scope,
        granted_by="tommaso",
    )
    return base.model_copy(update=changes)


def step_for(*required: CapabilityId, requires_authorization: bool = False) -> TaskStep:
    return TaskStep(
        id=STEP_ID,
        created_at=NOW,
        goal="one step of the approved plan",
        required_capabilities=required,
        arguments=ARGUMENTS.get(required[0], {}) if required else {},
        risk=RiskLevel.LOW,
        expected_result="something",
        requires_authorization=requires_authorization,
    )


OTHER_STEP: Final = step_for().model_copy(update={"id": OTHER_STEP_ID})
