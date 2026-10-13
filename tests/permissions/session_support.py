"""What the tests of a session's cover share (M13.9, decision 29): a ``MEDIUM`` read on declared
sites, the capability of a session that declares it, the room's word, and the child a gesture is.

The two types the cover needs — what a capability declares it covers, and the room's word — are
imported where they are used and not when a module is read: the tests that were written before
them had to be able to fail on what they assert, not on an import.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from ela.domain import (
    CapabilityId,
    CapabilitySpec,
    PlanAuthor,
    PlanAuthorKind,
    RiskLevel,
    StepId,
    TaskId,
    TaskStep,
)
from ela.permissions import browser_act, browser_read
from tests.domain.examples import NOW, STEP_ID, TASK
from tests.permissions.policy_support import GUIDED, MODEL

SITES = ("posta.example", "video.example")
SESSION_STEP = StepId(UUID("00000000-0000-4000-8000-0000000005e5"))
SESSION_TASK = TaskId(UUID("00000000-0000-4000-8000-0000000005e6"))
CHILD = TASK.model_copy(update={"parent_id": SESSION_TASK})
ARGS: dict[str, Any] = {"site": "posta.example", "path": "/inbox", "purpose": "leggere la posta"}

READ: CapabilitySpec = browser_read(SITES).model_copy(
    update={
        "id": CapabilityId("test.read_as_you"),
        "risk": RiskLevel.MEDIUM,
        "requires_authorization": True,
    }
)
"""A ``MEDIUM`` read on declared sites: what a session with the profile covers."""
ACT: CapabilitySpec = browser_act(SITES)
"""``HIGH``: it asks at every use, and nothing but a yes covers it."""
LOW_READ: CapabilitySpec = browser_read(SITES)


def session_capability(covered: CapabilitySpec | None, **changes: Any) -> CapabilitySpec:
    """A session's capability that declares what its reads are — built here and not when the
    module is imported, because until M13.9 a capability could not say it."""
    from ela.domain import Covered

    declared = None
    if covered is not None:
        declared = Covered(capability_id=covered.id, input_schema=covered.input_schema)
    return GUIDED.model_copy(
        update={"id": CapabilityId("test.session"), "covers": declared, **changes}
    )


def cover(**changes: Any) -> Any:
    """What the room attests of an open session."""
    from ela.domain import SessionCover

    attested = SessionCover(
        session=SESSION_STEP,
        task_id=SESSION_TASK,
        capability_id=CapabilityId("test.session"),
        sites=SITES,
    )
    return attested.model_copy(update=changes)


AUTHOR = PlanAuthor(by=PlanAuthorKind.SESSION, session=SESSION_STEP, model=MODEL)


def step(capability: CapabilitySpec = READ, **changes: Any) -> TaskStep:
    made = TaskStep(
        id=STEP_ID,
        created_at=NOW,
        goal="a gesture the model of the session asked for",
        required_capabilities=(capability.id,),
        arguments=ARGS,
        risk=capability.risk,
        expected_result="what the page says",
        requires_authorization=capability.requires_authorization,
        within=SITES,
    )
    return made.model_copy(update=changes)
