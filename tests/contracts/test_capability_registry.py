"""Contract of ``CapabilityRegistryPort`` (spec §28, §29): a declared catalogue, synchronous."""

from __future__ import annotations

import pytest

from ela.domain import RiskLevel
from ela.ports import AlreadyExistsError, CapabilityRegistryPort, NotFoundError
from tests.domain.examples import CAPABILITY_SPEC, MODEL_COMPLETE

OTHER_SPEC = CAPABILITY_SPEC.model_copy(update={"id": MODEL_COMPLETE, "risk": RiskLevel.MEDIUM})


def test_register_then_get(capability_registry: CapabilityRegistryPort) -> None:
    capability_registry.register(CAPABILITY_SPEC)
    assert capability_registry.get(CAPABILITY_SPEC.id) == CAPABILITY_SPEC


def test_register_twice_is_rejected(capability_registry: CapabilityRegistryPort) -> None:
    capability_registry.register(CAPABILITY_SPEC)
    with pytest.raises(AlreadyExistsError):
        capability_registry.register(CAPABILITY_SPEC.model_copy(update={"risk": RiskLevel.SAFE}))
    assert capability_registry.get(CAPABILITY_SPEC.id) == CAPABILITY_SPEC


def test_get_unknown_is_not_found(capability_registry: CapabilityRegistryPort) -> None:
    with pytest.raises(NotFoundError):
        capability_registry.get(MODEL_COMPLETE)


def test_specs_in_registration_order_as_a_tuple(
    capability_registry: CapabilityRegistryPort,
) -> None:
    assert capability_registry.specs() == ()
    capability_registry.register(OTHER_SPEC)
    capability_registry.register(CAPABILITY_SPEC)
    specs = capability_registry.specs()
    assert isinstance(specs, tuple)
    assert specs == (OTHER_SPEC, CAPABILITY_SPEC)
