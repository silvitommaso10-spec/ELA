"""The domain exports exactly the entities of spec §49, and every model is covered by tests."""

from __future__ import annotations

from ela import domain
from tests.domain.examples import EXAMPLES
from tests.domain.introspection import domain_models
from tests.domain.strategies import MODEL_STRATEGIES

SECTION_49_ENTITIES = frozenset(
    {
        "ELAIdentity",
        "UserIntent",
        "Task",
        "TaskStep",
        "TaskPlan",
        "TaskState",
        "TaskEvent",
        "Device",
        "DeviceCapability",
        "CapabilitySpec",
        "RiskLevel",
        "PermissionDecision",
        "Authorization",
        "Approval",
        "AuditEvent",
        "ProviderRequest",
        "ProviderResult",
        "ProviderUsage",
        "ExecutionResult",
        "ErrorMetadata",
    }
)
"""The entities spec §49 asks for, with the names the milestone fixed."""

REVIEW_ADDITIONS = frozenset({"Actor"})
"""Models added in review, on top of §49, with the reason written in ADR 0003.

``Actor`` replaces the free-form ``AuditEvent.actor`` string: §32 requires knowing *who* acted,
and a string cannot say whether "ela" is ELA, a user or a node.
"""

LATER_ADDITIONS = frozenset(
    {
        "ModelRoute",
        "SensorStatus",
        "RawObservation",
        "Observation",
        "PerceptionChange",
        "RawCapture",
        "RawRecognition",
        "RawTextLine",
        "ContextSnapshot",
        "ContextActivity",
        "ContextDevice",
        "ContextTask",
        "ContextApproval",
        "ContextWork",
        "ContextDeadline",
        "ContextDeadlines",
        "ContextEvent",
        "ContextRecent",
        "ContextQuestionStatus",
    }
)
"""Models a later milestone added, each argued in its own ADR.

``ModelRoute`` (M7.3, ADR 0022 §2) is the decision of the Model Router, and it is a domain value
for the reason ``PermissionDecision`` is: whoever decides answers with data, and whoever acts
executes it. §49 lists what v0.1 starts from, not what it may never grow.

The four of perception (M10.1, ADR 0028) are values, not entities, and they are in the domain for
one reason: :class:`~ela.ports.PerceptionProbe` names ``RawObservation``, and a port may import
nothing but :mod:`ela.domain` (rule 2). That is the same criterion ADR 0026 §2 used to keep
``PlacementDecision`` *out* — it crosses no port — applied in the other direction.

``RawCapture`` (M10.2, ADR 0029 §11) is there for exactly that reason and no other: it is what
:class:`~ela.ports.ScreenCapturePort` answers with. It carries how the helper ended and nothing
about the image — no bytes, no path — because what the capture *is* is read from the artefact,
never from a report (§20).

``RawRecognition`` and ``RawTextLine`` (M10.3, ADR 0030 §11) are the same, with one difference
argued rather than assumed: **the payload is in them**, where the capture's never was. The image
stayed out of the pipe because a truncated base64 string decodes into a partial image — a shorter
answer shaped like an answer — and JSON Lines is self-delimiting, so the same truncation is a
parse error instead. The text therefore crosses the port, and the discipline that comes with it is
that it goes into the caller's file and nowhere else: never a log line, never an error message,
never an ``ExecutionResult`` (§57).

The eleven of the context (M10.4, ADR 0032) are **values and never entities**, and the difference
is the whole boundary with §21: a snapshot is composed on read and never stored, so nothing in it
has a life cycle to date. They quote the ids of entities — ``task_id``, ``device_id`` — instead of
carrying one, because a projection that called its reference ``id`` would be claiming an identity
it does not have. They are in the domain rather than in ``ela.context`` for the reason ADR 0026 §2
gives: :class:`~ela.domain.ContextSnapshot` is what the API returns, so it is vocabulary and not
an internal shape — and being here is also what puts them under architecture rule 39, which is
what keeps a snapshot out of an audit event and out of a provider request.
"""


def test_all_section_49_entities_are_exported() -> None:
    missing = sorted(name for name in SECTION_49_ENTITIES if name not in domain.__all__)
    assert missing == []
    for name in SECTION_49_ENTITIES:
        assert getattr(domain, name) is not None


def test_every_public_model_belongs_to_section_49() -> None:
    """A model outside §49 is a spec change: it must be declared here and argued in an ADR."""
    known = SECTION_49_ENTITIES | REVIEW_ADDITIONS | LATER_ADDITIONS
    unexpected = sorted(model.__name__ for model in domain_models() if model.__name__ not in known)
    assert unexpected == []


def test_every_model_has_an_example() -> None:
    missing = sorted(model.__name__ for model in domain_models() if model not in EXAMPLES)
    assert missing == []


def test_every_model_has_a_strategy() -> None:
    missing = sorted(model.__name__ for model in domain_models() if model not in MODEL_STRATEGIES)
    assert missing == []


def test_all_is_sorted_and_complete() -> None:
    assert domain.__all__ == sorted(domain.__all__)
    for name in domain.__all__:
        assert hasattr(domain, name), name
