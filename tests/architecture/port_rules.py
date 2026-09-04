"""Architecture rules about the *shape* of the ports (CLAUDE.md, spec §27, §32, §49, §52).

Like ``model_rules.py`` for the domain: each rule takes protocol classes and returns the
violations it finds, so the same function runs on ``ela.ports`` and on the deliberately broken
protocols of ``test_ports.py``.
"""

from __future__ import annotations

from typing import Any, get_type_hints

from ela.domain import PermissionDecision
from tests.contracts.protocols import is_runtime_checkable, members

#: A member of an append-only log whose name contains one of these is a way to change the past.
MUTATING_WORDS = ("update", "delete", "remove", "clear", "pop", "replace", "truncate", "set")
#: The only members an append-only log may have (§32).
APPEND_ONLY_MEMBERS = frozenset({"append", "read"})


def unchecked_protocols(protocols: tuple[type, ...]) -> list[str]:
    """Every port must be ``runtime_checkable``: a contract test asks ``isinstance``."""
    return [p.__name__ for p in protocols if not is_runtime_checkable(p)]


def undocumented_protocols(protocols: tuple[type, ...]) -> list[str]:
    """Every port cites the spec section it implements."""
    return [p.__name__ for p in protocols if not (p.__doc__ and "§" in p.__doc__)]


def append_only_violations(log: type) -> list[str]:
    """An audit log has ``append`` and ``read`` and nothing that could alter what was written."""
    found = members(log)
    violations = [
        f"{log.__name__}.{name} is a mutating member"
        for name in sorted(found)
        if any(word in name.lower() for word in MUTATING_WORDS)
    ]
    extra = found - APPEND_ONLY_MEMBERS
    violations.extend(f"{log.__name__}.{name} is not append or read" for name in sorted(extra))
    missing = APPEND_ONLY_MEMBERS - found
    violations.extend(f"{log.__name__} lacks {name}" for name in sorted(missing))
    return violations


def execute_without_decision(tool: type, forbidden: tuple[Any, ...] = ()) -> list[str]:
    """``execute`` takes a ``PermissionDecision`` first, and never a Guardian or a store (§27)."""
    execute = getattr(tool, "execute", None)
    if execute is None:
        return [f"{tool.__name__} has no execute"]
    hints = get_type_hints(execute)
    hints.pop("return", None)
    parameters = list(hints.items())
    violations: list[str] = []
    if not parameters or parameters[0][1] is not PermissionDecision:
        violations.append(f"{tool.__name__}.execute does not take a PermissionDecision first")
    violations.extend(
        f"{tool.__name__}.execute({name}) is typed with {hint.__name__}"
        for name, hint in parameters
        if hint in forbidden
    )
    return violations
