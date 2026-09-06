"""How the contract tests look at a ``Protocol``: members, signatures, sync/async.

Shared with ``tests/architecture/test_ports.py`` and ``tests/docs/test_adr_ports.py``: the three
must agree on what "the members of a port" means. Python 3.12 has no ``typing.get_protocol_members``
yet, so ``__protocol_attrs__`` is read directly.
"""

from __future__ import annotations

import inspect
from typing import Any

from ela import ports

REQUIRED_PORTS = frozenset(
    {
        "TaskRepository",
        "AuditLog",
        "DeviceRegistryPort",
        "CapabilityRegistryPort",
        "ToolPort",
        "PermissionGuardianPort",
        "AuthorizationStore",
        "AuthorizingGuardianPort",
        "ToolRegistryPort",
        "ModelProvider",
        "ProviderRegistry",
        "Clock",
        "IdGenerator",
    }
)
"""The eleven ports of M1.3 plus the two of M5.1 (ADR 0013: the audited Guardian, the tools), by
name."""


def is_protocol(obj: object) -> bool:
    return isinstance(obj, type) and bool(getattr(obj, "_is_protocol", False))


def is_runtime_checkable(protocol: type) -> bool:
    return bool(getattr(protocol, "_is_runtime_protocol", False))


def protocols_of(module: Any) -> list[type]:
    """The protocols a module exports, in ``__all__`` order."""
    return [obj for name in module.__all__ if is_protocol(obj := getattr(module, name))]


def port_protocols() -> list[type]:
    return protocols_of(ports)


def members(protocol: type) -> frozenset[str]:
    """Public members declared by the protocol: methods and properties."""
    attrs: set[str] = getattr(protocol, "__protocol_attrs__", set())
    return frozenset(name for name in attrs if not name.startswith("_"))


def is_property(protocol: type, name: str) -> bool:
    return isinstance(inspect.getattr_static(protocol, name), property)


def method_names(protocol: type) -> frozenset[str]:
    return frozenset(name for name in members(protocol) if not is_property(protocol, name))


def is_async(owner: type, name: str) -> bool:
    return inspect.iscoroutinefunction(inspect.getattr_static(owner, name))


def parameter_shape(owner: type, name: str) -> list[tuple[str, Any, Any]]:
    """Names, kinds and defaults of a method's parameters, ``self`` excluded."""
    function = inspect.getattr_static(owner, name)
    return [(p.name, p.kind, p.default) for p in inspect.signature(function).parameters.values()][
        1:
    ]
