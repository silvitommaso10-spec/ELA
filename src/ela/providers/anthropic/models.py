"""Which Anthropic models ELA uses, and how a vendor-independent hint chooses one (§25, §26).

``ProviderRequest.model_hint`` is a field of the domain, and the domain does not know a vendor's
model ids: the example in ``tests/domain/examples.py`` says ``"reasoning"``, not
``"claude-opus-5"``. Translating one into the other is the adapter's job, and the table below is
that translation — the two lists of §25 ("un modello molto potente può essere utilizzato per…" /
"un modello più economico può essere utilizzato per…") turned into code.

The table is **closed**: a hint nobody has mapped is an error before any byte leaves the machine
(ADR 0020 §5), never a silent fallback to the default. Routing the user somewhere they did not
ask, without a trace, is exactly what §33 forbids.

Facts about each model are from the official model overview (read on 2026-10-08, M14.6); ADR 0061
holds the same table for review — it revises the one of ADR 0057 §3, read on 2026-10-06, which
revised ADR 0020 §4 — and ``tests/docs/test_adr_provider.py`` keeps the two equal.
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
    "HAIKU_5_5",
    "LARGEST_OUTPUT_TOKENS",
    "MODELS",
    "OPUS_5_5",
    "PROFILES",
    "SONNET_5_5",
    "Model",
    "model_for_hint",
]

OPUS_5_5: Final = "claude-opus-5-5"
SONNET_5_5: Final = "claude-sonnet-5-5"
HAIKU_5_5: Final = "claude-haiku-5-5"
"""Haiku 5.5, whose Claude API ID and alias are the same name (the models page, 2026-10-08)."""
HAIKU_4_5: Final = "claude-haiku-4-5-20251001"
"""Haiku 4.5 by its Claude API ID, the pinned snapshot, and not by the alias ``claude-haiku-4-5``
(M14.1, review decision 8). An alias of a model before the 4.6 generation "resolves to the dated
ID", and the price is looked up on the name the answer reports: with the pinned id the name asked
for and the name served are one, and a cost is never ``None`` because of a second spelling."""

DEFAULT_MODEL: Final = SONNET_5_5
"""The model that runs when a request names no profile at all.

Deliberately not the most capable one: the default is what starts when no one has thought about
cost, so it is the "balanced" profile. §25 gives the expensive model to planning, coding and
reasoning, and those arrive as profiles from whoever routes — the Model Router, which since M7.3
names a profile on **every** call it makes (ADR 0022 §3). So this is the answer for a
``ProviderRequest`` built outside that path, and nothing else.

It is a **constant, not a setting**: ``ELA_ANTHROPIC_MODEL`` was retired in M7.3 (ADR 0022 §8).
Choosing the model per kind of task is the routing table's job, and a variable that overrode the
default of one adapter while a table decided everything else would be a second, quieter policy.
"""

EFFORT_LEVELS: Final = ("low", "medium", "high", "xhigh", "max")
"""The values ``parameters["effort"]`` may take, on a model that supports effort."""


@dataclass(frozen=True, slots=True)
class Model:
    """What ELA needs to know about a model before calling it."""

    id: str
    max_output_tokens: int
    supports_effort: bool
    context_window: int
    """Input and output of one call together, in tokens. The only upper bound on a call's input
    the documentation writes — an input that alone exceeds it is a ``400`` — and so the input side
    of the worst case a cap reserves (M14.1, ADR 0057)."""


MODELS: Final[Mapping[str, Model]] = MappingProxyType(
    {
        OPUS_5_5: Model(
            OPUS_5_5, max_output_tokens=128_000, supports_effort=True, context_window=1_000_000
        ),
        SONNET_5_5: Model(
            SONNET_5_5, max_output_tokens=128_000, supports_effort=True, context_window=1_000_000
        ),
        HAIKU_5_5: Model(
            HAIKU_5_5, max_output_tokens=128_000, supports_effort=True, context_window=1_000_000
        ),
        HAIKU_4_5: Model(
            HAIKU_4_5, max_output_tokens=64_000, supports_effort=False, context_window=200_000
        ),
    }
)
"""The three models the profiles name, and Haiku 4.5 (M14.1, ADR 0057; M14.6, ADR 0061).

Haiku 4.5 is named by no profile since M14.6 — the cheap profile is Haiku 5.5 — and stays here for
the month: its costs are still counted and its reservations still closed on its name, and a model
gone from the table would turn an open reservation of it into a call without a price.

A model in this table is one a route can pin with a ``model_hint``: ``claude-opus-5`` costs more
than ``claude-opus-5-5`` and answers worse, and keeping it would be a spend no profile asked for.
``claude-fable-5-1`` stays out: it costs two and a half Opus 5.5 calls and needs a 30-day retention
setting on the organisation, and no profile of §25 asks for it."""

LARGEST_OUTPUT_TOKENS: Final = max(model.max_output_tokens for model in MODELS.values())
"""The most output any model of :data:`MODELS` can produce.

An output budget above this asks for something no model can give and is a misconfiguration
(``AnthropicSettings``); a budget between this and a *particular* model's limit is clamped for
that model when the payload is built, which is a smaller model answering a call, not an error.
"""

PROFILES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "quality": OPUS_5_5,
        "reasoning": OPUS_5_5,
        "planning": OPUS_5_5,
        "coding": OPUS_5_5,
        "analysis": OPUS_5_5,
        "balanced": SONNET_5_5,
        "fast": HAIKU_5_5,
        "cheap": HAIKU_5_5,
        "classification": HAIKU_5_5,
        "extraction": HAIKU_5_5,
        "routine": HAIKU_5_5,
    }
)
"""``model_hint`` → model. The keys are §25's two lists, plus the middle the spec implies."""


def model_for_hint(hint: str | None) -> Model | None:
    """The model a hint asks for, or ``None`` if the hint names nothing (ADR 0020 §5).

    Three ways to name a model, in order: no hint at all is :data:`DEFAULT_MODEL`; a *profile* is
    what §25 talks about and what the router sends; a model id already in :data:`MODELS` is
    accepted as itself, so an operator can pin one in a route without inventing a profile for it.
    """
    if hint is None:
        return MODELS[DEFAULT_MODEL]
    if hint in PROFILES:
        return MODELS[PROFILES[hint]]
    return MODELS.get(hint)
