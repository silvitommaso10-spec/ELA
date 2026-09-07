"""``ProviderRegistry`` (spec §50): providers by name, and no two providers with one name."""

from __future__ import annotations

import pytest

from ela.domain import ProviderStatus
from ela.ports import AlreadyExistsError, ModelProvider, NotFoundError
from ela.providers import ProviderRegistry
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeModelProvider


def _provider(name: str, status: ProviderStatus = ProviderStatus.AVAILABLE) -> FakeModelProvider:
    return FakeModelProvider(FakeClock(), FakeIdGenerator(), name=name, status=status)


def test_is_a_provider_registry() -> None:
    assert isinstance(ProviderRegistry(), object)
    assert isinstance(_provider("x"), ModelProvider)


def test_built_from_providers() -> None:
    first, second = _provider("anthropic"), _provider("local")
    registry = ProviderRegistry((first, second))
    assert registry.names() == ("anthropic", "local")
    assert registry.get("anthropic") is first


def test_register_then_get() -> None:
    registry = ProviderRegistry()
    provider = _provider("anthropic")
    registry.register(provider)
    assert registry.get("anthropic") is provider


def test_a_duplicate_name_is_refused_and_the_first_one_stays() -> None:
    registry = ProviderRegistry()
    first = _provider("anthropic")
    registry.register(first)
    with pytest.raises(AlreadyExistsError):
        registry.register(_provider("anthropic"))
    assert registry.get("anthropic") is first


def test_unknown_name_is_not_found() -> None:
    with pytest.raises(NotFoundError):
        ProviderRegistry().get("nobody")


def test_an_unavailable_provider_registers_like_any_other() -> None:
    """The point of the status (ADR 0020 §2): missing credentials are a fact, not a crash."""
    provider = _provider("anthropic", ProviderStatus.UNAVAILABLE)
    registry = ProviderRegistry((provider,))
    assert registry.names() == ("anthropic",)
    assert registry.get("anthropic").status is ProviderStatus.UNAVAILABLE
