"""Contract of ``VerifierRegistryPort`` (spec §63; ADR 0014 §1): one verifier per capability,
read-only, keyed by the verifier's own ``capability_id`` like the tool registry.
"""

from __future__ import annotations

import pytest

from ela.domain import CapabilityId
from ela.ports import AlreadyExistsError, NotFoundError, VerifierRegistryPort
from ela.testing.fakes import FakeVerifier, FakeVerifierRegistry
from ela.tools import VerifierRegistry
from tests.contracts.implementations import REGISTRY_VERIFIERS
from tests.contracts.protocols import members

NOTE_VERIFIER, ECHO_VERIFIER = REGISTRY_VERIFIERS


def test_get_returns_the_verifier_keyed_by_its_own_capability(
    verifier_registry: VerifierRegistryPort,
) -> None:
    assert verifier_registry.get(NOTE_VERIFIER.capability_id) is NOTE_VERIFIER
    assert verifier_registry.get(ECHO_VERIFIER.capability_id) is ECHO_VERIFIER


def test_get_unknown_is_not_found(verifier_registry: VerifierRegistryPort) -> None:
    with pytest.raises(NotFoundError):
        verifier_registry.get(CapabilityId("nobody.knows_this"))


def test_verifiers_in_construction_order_as_a_tuple(
    verifier_registry: VerifierRegistryPort,
) -> None:
    verifiers = verifier_registry.verifiers()
    assert isinstance(verifiers, tuple)
    assert verifiers == REGISTRY_VERIFIERS


def test_no_public_member_beyond_the_port(verifier_registry: VerifierRegistryPort) -> None:
    public = {name for name in dir(verifier_registry) if not name.startswith("_")}
    assert public == set(members(VerifierRegistryPort)) == {"get", "verifiers"}


@pytest.mark.parametrize(
    "registry", [FakeVerifierRegistry, VerifierRegistry], ids=lambda c: c.__name__
)
def test_two_verifiers_for_one_capability_are_refused(registry: type) -> None:
    twin = FakeVerifier(NOTE_VERIFIER.capability_id, name="twin")
    with pytest.raises(AlreadyExistsError):
        registry((NOTE_VERIFIER, twin))
