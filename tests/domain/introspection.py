"""Introspection helper shared by the domain tests: which models exist right now."""

from __future__ import annotations

from collections.abc import Iterator

from pydantic import BaseModel

from ela import domain


def domain_models() -> Iterator[type[BaseModel]]:
    """Every public pydantic model defined in :mod:`ela.domain`."""
    for name, value in vars(domain).items():
        if name.startswith("_"):
            continue
        if not (isinstance(value, type) and issubclass(value, BaseModel)):
            continue
        if value.__module__ == domain.__name__:
            yield value
