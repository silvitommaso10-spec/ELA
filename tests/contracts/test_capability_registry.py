"""Contract of ``CapabilityRegistryPort`` (spec §28, §29; ADR 0010): declared, read-only.

Every implementation is built by ``implementations.py`` with the same two specifications
(``REGISTRY_CATALOGUE``): the contract reads them back and checks that
nothing can be added afterwards — the port has ``get`` and ``specs`` and an implementation may
have no public member beyond them.
"""

from __future__ import annotations

import pytest

from ela.ports import CapabilityRegistryPort, NotFoundError
from tests.contracts.implementations import REGISTRY_CATALOGUE as CATALOGUE
from tests.contracts.protocols import members

CAPABILITY_SPEC, OTHER_SPEC = CATALOGUE


def test_get_returns_what_was_built_in(capability_registry: CapabilityRegistryPort) -> None:
    assert capability_registry.get(CAPABILITY_SPEC.id) == CAPABILITY_SPEC
    assert capability_registry.get(OTHER_SPEC.id) == OTHER_SPEC


def test_get_unknown_is_not_found(capability_registry: CapabilityRegistryPort) -> None:
    unknown = CAPABILITY_SPEC.model_copy(update={"id": "nobody.knows_this"})
    with pytest.raises(NotFoundError):
        capability_registry.get(unknown.id)


def test_specs_in_construction_order_as_a_tuple(
    capability_registry: CapabilityRegistryPort,
) -> None:
    specs = capability_registry.specs()
    assert isinstance(specs, tuple)
    assert specs == CATALOGUE


def test_no_public_member_beyond_the_port(capability_registry: CapabilityRegistryPort) -> None:
    """Read-only means read-only: not even a method the port does not know about."""
    public = {name for name in dir(capability_registry) if not name.startswith("_")}
    assert public == set(members(CapabilityRegistryPort)) == {"get", "specs"}
