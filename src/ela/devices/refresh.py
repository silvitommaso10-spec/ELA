"""What a re-registration rewrites of a node's row, and what it must never touch (ADR 0035 §2).

The row has three halves (ADR 0037 §10). The **declared** one — the name, the operating system,
the traits, the tools and the performance class — is what the node states about itself (for
``local``, what whoever composes ELA knows without probing anything), and it is a statement about
the code that is running: a capability added after the first start is a longer
``available_tools``, and a row that keeps the old list makes the node ineligible for a step nothing
else can run (§16, §17). The **observed** one is the registry's — what the heartbeat reports, and
the network the node came in by: it says what was seen of the node, not what ELA was built with.
The **imposed** one, ``privacy``, is the user's.

So a refresh replaces the declared half and leaves the rest exactly as it was read. That is not a
promise made here: :func:`refreshed` names no field at all — it carries the stored row through and
overwrites the keys it was handed — and architecture rule 44 forbids this module every name that
is not declared and the constructor of a *new* row, which sets the observed half to "nothing known
yet" and would make an available node unavailable until the next heartbeat.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Final

from ela.domain import Device, DeviceCapability
from ela.ports import (
    ANNOUNCED_FIELDS,
)

__all__ = ["DECLARED_FIELDS", "TOOLS_FIELD", "changes", "difference", "refreshed", "tool_names"]

DECLARED_FIELDS: Final[tuple[str, ...]] = ANNOUNCED_FIELDS
"""The half a node declares about itself (ADR 0037 §10): for ``local``, whoever composes ELA; for a
remote node, the node, through :meth:`~ela.ports.DeviceRegistryPort.announce`.

One tuple, owned by the port, so the reconciliation of ``local`` and the announcement of a remote
node cannot come to disagree about what "declared" means. Not only the tools, and the reason is
that the defect is not about tools: a database copied onto another machine says ``MACOS`` on a
Linux box, and the orchestrator decides on a lie (ADR 0035 §2).

Since M12.1 ``network`` and ``privacy`` are not here: the network is the registry's, fixed when the
row is born, and the privacy is the user's, imposed at enrollment — both are born with the row, and
a restart does not restate them (ADR 0016 §4). ``performance`` is: a node that describes itself can
probe itself (ADR 0037 §10). ``created_at`` is not here either — a row is born once.
"""

TOOLS_FIELD: Final = "available_tools"
"""The one declared field whose difference is read as names rather than as a before and an after."""


def changes(current: Device, declared: Device) -> Mapping[str, Any]:
    """The declared fields on which ``current`` and ``declared`` disagree, mapped to the new value.

    Empty means there is nothing to write, and nothing to write means nothing is written: an ELA
    restarted with the same code produces no ``UPDATE`` and no audit event (ADR 0035 §3).
    """
    return MappingProxyType(
        {
            field: getattr(declared, field)
            for field in DECLARED_FIELDS
            if getattr(declared, field) != getattr(current, field)
        }
    )


def refreshed(current: Device, change: Mapping[str, Any]) -> Device:
    """``current`` with ``change`` applied and everything else carried through, revalidated.

    The stored row is the base, so every field this milestone has no business in — the instant the
    node was born, what was observed of it, what nobody can state without probing — arrives on the
    other side exactly as it was read. ``model_validate`` and not ``model_copy``: a value that
    cannot be a ``Device`` is refused here rather than written (ADR 0016 §7).
    """
    return Device.model_validate({**current.model_dump(), **change})


def tool_names(current: Device, declared: Device) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The tools the declaration adds, and the ones it takes away — sorted, and by name.

    "One tool more" is not a diagnosis: with seven of them, *which* one is the whole of it
    (ADR 0035 §3). A shorter list is an answer as good as a longer one — a capability that was
    withdrawn stops being runnable at the next start, and that is the point.
    """
    before, after = set(current.available_tools), set(declared.available_tools)
    return tuple(sorted(after - before)), tuple(sorted(before - after))


def difference(current: Device, change: Mapping[str, Any]) -> str:
    """What a refresh rewrites, in words: every field, and for the tools every name.

    The summary of the audit event, and the reason it carries the whole difference instead of a
    count: whoever reads the log later must be able to say which capability a node gained or lost,
    not that it gained one.
    """
    return ", ".join(
        _field(field, getattr(current, field), after) for field, after in change.items()
    )


def _field(field: str, before: Any, after: Any) -> str:
    """One field's difference: ``+name -name`` for the tools, ``before -> after`` for the rest."""
    if field == TOOLS_FIELD:
        added = sorted(set(after) - set(before))
        removed = sorted(set(before) - set(after))
        marks = [*(f"+{name}" for name in added), *(f"-{name}" for name in removed)]
        return f"{field} {' '.join(marks)}"
    return f"{field} {_shown(before)} -> {_shown(after)}"


def _shown(value: Any) -> str:
    """A declared value as the summary shows it: names, and ``none`` for nothing at all."""
    if isinstance(value, tuple):
        return ", ".join(_shown(one) for one in value) or "none"
    if isinstance(value, DeviceCapability):
        return value.name
    return str(value)
