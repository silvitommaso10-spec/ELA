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


def test_all_section_49_entities_are_exported() -> None:
    missing = sorted(name for name in SECTION_49_ENTITIES if name not in domain.__all__)
    assert missing == []
    for name in SECTION_49_ENTITIES:
        assert getattr(domain, name) is not None


def test_every_public_model_belongs_to_section_49() -> None:
    """A model outside §49 is a spec change: it must be declared here and argued in an ADR."""
    known = SECTION_49_ENTITIES | REVIEW_ADDITIONS
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
