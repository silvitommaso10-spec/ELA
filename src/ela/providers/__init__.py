"""Model providers: the edge where ELA talks to a model (spec §26, §50).

This package holds the registry the Core routes through and one sub-package per provider. The
sub-package is the only place a vendor's SDK may be imported (architecture rule 24): importing
``ela.providers`` gives you the registry and *not* a vendor library, which is why the Anthropic
adapter is reached explicitly, as ``from ela.providers.anthropic import anthropic_provider``.
"""

from __future__ import annotations

from ela.providers.registry import ProviderRegistry

__all__ = ["ProviderRegistry"]
