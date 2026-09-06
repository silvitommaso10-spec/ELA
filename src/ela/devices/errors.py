"""The failures of the device registry (§16, ADR 0016)."""

from __future__ import annotations

__all__ = ["UnsupportedOperatingSystemError"]


class UnsupportedOperatingSystemError(ValueError):
    """The running system is one :class:`~ela.domain.OperatingSystem` does not name.

    ``OperatingSystem`` has no ``UNKNOWN`` on purpose (ADR 0003): a node whose system ELA does
    not know is not a node ELA can register, and picking a value at random here would put a
    wrong fact in the registry the orchestrator reads (§17).
    """

    def __init__(self, system: str) -> None:
        self.system = system
        super().__init__(f"unsupported operating system {system!r}: this node cannot be registered")
