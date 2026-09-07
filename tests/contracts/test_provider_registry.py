"""Contract of ``ProviderRegistryPort`` (spec §50): providers by name, synchronous."""

from __future__ import annotations

import pytest

from ela.domain import ProviderRequest, ProviderResult, ProviderStatus
from ela.ports import AlreadyExistsError, ModelProvider, NotFoundError, ProviderRegistryPort


class _Provider:
    """The smallest thing that is a ``ModelProvider``: the registry only needs its name."""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def status(self) -> ProviderStatus:
        return ProviderStatus.AVAILABLE

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        raise NotImplementedError


def test_stub_is_a_provider() -> None:
    assert isinstance(_Provider("x"), ModelProvider)


def test_register_then_get(provider_registry: ProviderRegistryPort) -> None:
    provider = _Provider("claude")
    provider_registry.register(provider)
    assert provider_registry.get("claude") is provider


def test_register_same_name_twice_is_rejected(provider_registry: ProviderRegistryPort) -> None:
    first = _Provider("claude")
    provider_registry.register(first)
    with pytest.raises(AlreadyExistsError):
        provider_registry.register(_Provider("claude"))
    assert provider_registry.get("claude") is first


def test_get_unknown_is_not_found(provider_registry: ProviderRegistryPort) -> None:
    with pytest.raises(NotFoundError):
        provider_registry.get("nobody")


def test_names_are_sorted_as_a_tuple(provider_registry: ProviderRegistryPort) -> None:
    assert provider_registry.names() == ()
    provider_registry.register(_Provider("local"))
    provider_registry.register(_Provider("claude"))
    names = provider_registry.names()
    assert isinstance(names, tuple)
    assert names == ("claude", "local")
