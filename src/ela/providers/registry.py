"""The providers ELA can route to, by name (spec §26, §50; port ``ProviderRegistryPort``).

An in-memory table of providers already built, in the shape the other registries of ELA have
(``CapabilityRegistry``, ``ToolRegistry``, ``DeviceRegistry``): synchronous, closed at
registration, and unforgiving about a duplicate name — two providers answering to ``anthropic``
would make ``get`` a coin toss.

Registration does not check that a provider works: a provider with no credentials registers all
the same and says so through :attr:`~ela.ports.ModelProvider.status` (ADR 0020 §2). That is what
lets ELA start on a machine where a key is missing, instead of failing at composition time.
"""

from __future__ import annotations

from ela.ports import AlreadyExistsError, ModelProvider, NotFoundError

__all__ = ["ProviderRegistry"]


class ProviderRegistry:
    """Providers by name (port :class:`~ela.ports.ProviderRegistryPort`)."""

    def __init__(self, providers: tuple[ModelProvider, ...] = ()) -> None:
        self._providers: dict[str, ModelProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: ModelProvider) -> None:
        """Add a provider; :class:`~ela.ports.AlreadyExistsError` if its name is taken."""
        if provider.name in self._providers:
            raise AlreadyExistsError("provider", provider.name)
        self._providers[provider.name] = provider

    def get(self, name: str) -> ModelProvider:
        """The provider with this name; :class:`~ela.ports.NotFoundError` if there is none."""
        try:
            return self._providers[name]
        except KeyError:
            raise NotFoundError("provider", name) from None

    def names(self) -> tuple[str, ...]:
        """The registered names, sorted."""
        return tuple(sorted(self._providers))
