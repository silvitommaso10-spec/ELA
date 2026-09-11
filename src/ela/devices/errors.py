"""The failures of this package: registering a node (§16, ADR 0016), running on one (ADR 0026 §3),
and revoking the one that cannot be revoked (ADR 0037 §12)."""

from __future__ import annotations

from ela.domain import (
    DeviceId,
    StepId,
    TaskId,
)

__all__ = [
    "LocalDeviceNotRevocableError",
    "NotPlacedError",
    "UnsupportedOperatingSystemError",
]


class UnsupportedOperatingSystemError(ValueError):
    """The running system is one :class:`~ela.domain.OperatingSystem` does not name.

    ``OperatingSystem`` has no ``UNKNOWN`` on purpose (ADR 0003): a node whose system ELA does
    not know is not a node ELA can register, and picking a value at random here would put a
    wrong fact in the registry the orchestrator reads (§17).
    """

    def __init__(self, system: str) -> None:
        self.system = system
        super().__init__(f"unsupported operating system {system!r}: this node cannot be registered")


class NotPlacedError(Exception):
    """The placement handed in does not allow this step to run on any node (ADR 0026 §3).

    Raised by :func:`~ela.devices.orchestrator.ensure_placed`, and the counterpart of
    :class:`~ela.ports.NotAllowedError`: that one guards *what* may happen, this one *where*.
    A precondition, not an outcome — it is raised before anything is written, so a caller that
    hands in a placement of another step leaves no trace of an execution that never began.

    It is not a ``ValueError`` like :class:`UnsupportedOperatingSystemError`: that one says a
    value is malformed, this one says a decision does not cover the call, which is the same kind
    of thing ``NotAllowedError`` says.
    """

    def __init__(self, task_id: TaskId, step_id: StepId, reason: str) -> None:
        self.task_id = task_id
        self.step_id = step_id
        self.reason = reason
        super().__init__(f"step {step_id} of task {task_id} cannot run: {reason}")


class LocalDeviceNotRevocableError(Exception):
    """``local`` is refused a revocation (ADR 0037 §12).

    It is this machine and has no secret, and revoking it would leave the Core with no node to run
    on and no enrollment to recover with. Raised before anything is read or written.
    """

    def __init__(self, device_id: DeviceId) -> None:
        self.device_id = device_id
        super().__init__(f"node {device_id} is this machine: it cannot be revoked")
