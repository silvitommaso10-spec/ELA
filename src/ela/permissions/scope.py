"""What "within scope" means (spec §28, §29; ADR 0011 §4, M4.2).

A scope entry is a relative POSIX path (``workspace/notes``, syntax fixed by the catalogue in
M4.1). A *target* is the value of one of the arguments the capability declares in
``scoped_arguments``: it is inside an entry when it is a string with the same syntax whose
segments start with the entry's segments. ``workspace/notes`` and ``workspace/notes/a/b.md``
are inside ``workspace/notes``; ``workspace/notes-old/x``, ``../workspace/notes/x`` and
``/workspace/notes/x`` are not.

Every rule here is fail-safe (§33): a target that is missing, not a string, absolute or with
``..`` is outside every scope; a scope that constrains nothing is a doubt, not a pass. The module
is pure — no I/O, no clock, no state — so the Guardian's most delicate comparison is a function
the tests can exhaust.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ela.domain import CapabilitySpec
from ela.permissions.capabilities import is_valid_scope_entry

__all__ = ["scope_covers", "targets_of", "within_scope"]


def targets_of(spec: CapabilitySpec, arguments: Mapping[str, object]) -> tuple[object, ...]:
    """The values of the arguments ``spec.scoped_arguments`` names, in that order.

    A missing argument yields ``None``: the tuple always has one item per scoped argument, so a
    scope that constrains an argument is applied even when the caller left it out.
    """
    return tuple(arguments.get(name) for name in spec.scoped_arguments)


def within_scope(scope: Sequence[str], target: object) -> bool:
    """Whether ``target`` lies inside at least one entry of ``scope``.

    False for anything that is not a well-formed relative path (``None``, a number, an absolute
    path, ``.`` or ``..`` segments, backslashes) and for entries that are themselves malformed:
    the real catalogue never holds one, the fake may, and a malformed entry protects nothing.
    """
    if not isinstance(target, str) or not is_valid_scope_entry(target):
        return False
    parts = target.split("/")
    for entry in scope:
        if not is_valid_scope_entry(entry):
            continue
        prefix = entry.split("/")
        if parts[: len(prefix)] == prefix:
            return True
    return False


def scope_covers(scope: Sequence[str], targets: Sequence[object]) -> bool:
    """Whether ``scope`` covers every target of a call.

    A non-empty scope with no target to constrain is a doubt (§33): the capability — or the
    authorization — declares a boundary that the call cannot be checked against, so it is not
    covered. An empty scope with no targets is covered: nothing was declared, nothing is
    constrained (``core.echo``, ``model.complete``). An empty scope with targets covers none.
    """
    if scope and not targets:
        return False
    return all(within_scope(scope, target) for target in targets)
