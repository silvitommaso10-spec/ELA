"""Decisions for the tool tests: ALLOWED for a capability, or deliberately not."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ela.domain import CapabilityId, PermissionDecision, PermissionOutcome
from tests.domain.examples import PERMISSION_DECISION

FAR_AHEAD = datetime(2100, 1, 1, tzinfo=UTC)


def allowed(capability_id: CapabilityId, **update: Any) -> PermissionDecision:
    """An ALLOWED, unexpired decision about ``capability_id``, then ``update`` applied."""
    base = {
        "capability_id": capability_id,
        "outcome": PermissionOutcome.ALLOWED,
        "expires_at": None,
    }
    return PERMISSION_DECISION.model_copy(update={**base, **update})


def permissions_bite() -> bool:
    """Whether ``chmod(0o000)`` really denies **this** process, measured instead of assumed.

    A test that needs the OS to refuse has a precondition — *I am not the user who is allowed
    anyway* — and root is allowed anyway. The precondition is not a property of the platform, so
    it is not declared by naming one (ADR 0031 §6): it is **constructed and measured**, the way
    ``available()`` reads the filesystem instead of asking ``platform.system()``.

    On the ubuntu runner the job is the ``runner`` user and this answers ``True``; in a container
    that runs as root it answers ``False``, and the tests that need it say so in the summary
    instead of failing for a reason that has nothing to do with the code under test.
    """
    with tempfile.NamedTemporaryFile(delete=False) as handle:
        target = Path(handle.name)
    try:
        target.chmod(0o000)
        try:
            with target.open("rb"):
                return False
        except OSError:
            return True
    finally:
        target.chmod(0o600)
        target.unlink()


PERMISSIONS_BITE = permissions_bite()
"""Measured once, at import: a ``skipif`` needs an answer before collection."""
