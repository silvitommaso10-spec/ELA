"""Which Anthropic models ELA uses, and how a vendor-independent hint chooses one (§25, §26).

``ProviderRequest.model_hint`` is a field of the domain, and the domain does not know a vendor's
model ids: the example in ``tests/domain/examples.py`` says ``"reasoning"``, not
``"claude-opus-5"``. Translating one into the other is the adapter's job, and the table below is
that translation — the two lists of §25 ("un modello molto potente può essere utilizzato per…" /
"un modello più economico può essere utilizzato per…") turned into code.

The table is **closed**: a hint nobody has mapped is an error before any byte leaves the machine
(ADR 0020 §5), never a silent fallback to the default. Routing the user somewhere they did not
ask, without a trace, is exactly what §33 forbids.

Facts about each model are from the official model overview (read on 2026-09-07); ADR 0020 §4
holds the same table for review, and ``tests/docs/test_adr_provider.py`` keeps the two equal.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

__all__ = [
    "DEFAULT_MODEL",
    "EFFORT_LEVELS",
    "HAIKU_4_5",
    "MODELS",
    "OPUS_5",
    "PROFILES",
    "SONNET_5",
    "Model",
    "model_for_hint",
]

OPUS_5: Final = "claude-opus-5"
SONNET_5: Final = "claude-sonnet-5"
HAIKU_4_5: Final = "claude-haiku-4-5"

DEFAULT_MODEL: Final = SONNET_5
"""The model that runs when nobody asked for one.

Deliberately not the most capable one: the default is what starts when no one has thought about
cost, so it is the "balanced" profile. §25 gives the expensive model to planning, coding and
reasoning — and those arrive as *explicit* hints from whoever routes (the Model Router, §25).
"""

EFFORT_LEVELS: Final = ("low", "medium", "high", "xhigh", "max")
"""The values ``parameters["effort"]`` may take, on a model that supports effort."""


@dataclass(frozen=True, slots=True)
class Model:
    """What ELA needs to know about a model before calling it."""

    id: str
    max_output_tokens: int
    supports_effort: bool


MODELS: Final[Mapping[str, Model]] = MappingProxyType(
    {
        OPUS_5: Model(OPUS_5, max_output_tokens=128_000, supports_effort=True),
        SONNET_5: Model(SONNET_5, max_output_tokens=128_000, supports_effort=True),
        HAIKU_4_5: Model(HAIKU_4_5, max_output_tokens=64_000, supports_effort=False),
    }
)
"""The three models of v0.1. ``claude-fable-5-1`` is out: it costs twice an Opus call and needs a
30-day retention setting on the organisation, and no profile of §25 asks for it (ADR 0020 §4)."""

PROFILES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "quality": OPUS_5,
        "reasoning": OPUS_5,
        "planning": OPUS_5,
        "coding": OPUS_5,
        "analysis": OPUS_5,
        "balanced": SONNET_5,
        "fast": HAIKU_4_5,
        "cheap": HAIKU_4_5,
        "classification": HAIKU_4_5,
        "extraction": HAIKU_4_5,
        "routine": HAIKU_4_5,
    }
)
"""``model_hint`` → model. The keys are §25's two lists, plus the middle the spec implies."""


def model_for_hint(hint: str | None, default: str) -> Model | None:
    """The model a hint asks for, or ``None`` if the hint names nothing (ADR 0020 §5).

    Three ways to name a model, in order: no hint at all is the configured default; a *profile*
    is what §25 talks about and what a router will send; a model id already in :data:`MODELS` is
    accepted as itself, so an operator can pin one without inventing a profile for it.
    """
    if hint is None:
        return MODELS[default]
    if hint in PROFILES:
        return MODELS[PROFILES[hint]]
    return MODELS.get(hint)
