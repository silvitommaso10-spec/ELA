"""The variables ELA used to read, and what replaced them: one table, one refusal (ADR 0037 §15).

«Sparisce» has a form in this repository, and it is not deleting: with ``extra="ignore"`` a deleted
setting would be ignored in silence, and «Una configurazione che smette di funzionare in silenzio
lascia chi l'ha scritta convinto che funzioni ancora (§33)» (ADR 0022 §8). A retired variable is
**refused**, at start-up, and the refusal says why and what to do instead.

Until M12.1 the table was a provider's, and its validator knew one variable: it read the first
entry. It lives here, in a module that imports only the standard library and pydantic, so that the
settings of ``providers`` and of ``composition`` can both import it without reversing the direction
of the dependencies (ADR 0037 §15). Each settings class still declares its tombstone field —
``str | None``, never a value — so the refusal covers every source pydantic-settings reads: the
environment, a ``.env`` file, a keyword argument.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from pydantic import BaseModel

__all__ = ["RETIRED_SETTINGS", "Retirement", "refuse_retired"]


@dataclass(frozen=True, slots=True)
class Retirement:
    """When a variable was retired, why, and what whoever still sets it should do instead."""

    milestone: str
    reason: str
    instead: str


RETIRED_SETTINGS: Final[Mapping[str, Retirement]] = MappingProxyType(
    {
        "ELA_ANTHROPIC_MODEL": Retirement(
            milestone="M7.3",
            reason="which model answers is decided by the routing table (spec §25, ADR 0022)",
            instead="set ELA_MODEL_ROUTES and ELA_MODEL_DEFAULT_ROUTE instead",
        ),
        "ELA_USER_NAME": Retirement(
            milestone="M12.1",
            reason=(
                "who answers is the identity the API resolves for the call — with the Core's "
                "token, the user at this machine (ADR 0037 §15)"
            ),
            instead="nothing replaces it, and there is nothing to set",
        ),
    }
)
"""Every retired variable: the union of ADR 0022 §8's table and ADR 0037 §15's."""


def refuse_retired(settings: BaseModel, *, prefix: str) -> None:
    """Stop at the first retired variable ``settings`` was given, saying what replaced it.

    Any value counts, the empty one included: it was set on purpose, and telling whoever set it
    that it is gone is the point (ADR 0022 §8).

    :raises ValueError: for a retired variable that has a value, whatever its source.
    """
    for field in type(settings).model_fields:
        variable = f"{prefix}{field}".upper()
        retired = RETIRED_SETTINGS.get(variable)
        if retired is not None and getattr(settings, field) is not None:
            raise ValueError(
                f"{variable} was retired in {retired.milestone}: {retired.reason}. "
                f"Remove it: {retired.instead}."
            )
