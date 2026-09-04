"""Architecture rules about the *shape* of the domain models (CLAUDE.md, spec §13, §49, §51).

The rules of ``rules.py`` read the source tree and answer "who imports what". These answer
"what does a model look like": each one takes pydantic model classes and returns the violations
it finds, so the same function runs on ``ela.domain`` and on the deliberately broken models of
``test_domain_models.py``.

Annotations are read with ``get_type_hints(..., include_extras=True)`` on the class, not through
``model_fields``: pydantic keeps ``NewType`` aliases there, and telling ``DeviceId`` from any
other UUID is the whole point of rule ``plan_is_device_independent``.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any, get_args, get_type_hints

from pydantic import BaseModel

MUTABLE_CONTAINERS = (list, set, dict)
DATETIME_TYPES = (datetime,)


def annotation_parts(annotation: Any) -> Iterator[Any]:
    """The annotation itself and, recursively, every type argument inside it."""
    yield annotation
    for arg in get_args(annotation):
        yield from annotation_parts(arg)


def hints(model: type[BaseModel]) -> dict[str, Any]:
    return get_type_hints(model, include_extras=True)


def referenced_models(model: type[BaseModel]) -> Iterator[type[BaseModel]]:
    """Every model reachable from ``model`` through its fields, ``model`` included."""
    seen: set[type[BaseModel]] = set()
    pending = [model]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        yield current
        for annotation in hints(current).values():
            for part in annotation_parts(annotation):
                if isinstance(part, type) and issubclass(part, BaseModel):
                    pending.append(part)


def mentions(model: type[BaseModel], forbidden: frozenset[Any]) -> list[str]:
    """Fields of ``model`` whose annotation mentions one of ``forbidden``."""
    found: list[str] = []
    for name, annotation in hints(model).items():
        for part in annotation_parts(annotation):
            if any(part is item for item in forbidden):
                found.append(f"{model.__name__}.{name} references {_label(part)}")
    return found


def _label(part: Any) -> str:
    return getattr(part, "__name__", repr(part))


def device_reference_violations(
    roots: tuple[type[BaseModel], ...], forbidden: frozenset[Any]
) -> list[str]:
    """A plan must not name a node: only capabilities and device traits (§13, §17)."""
    violations: list[str] = []
    for root in roots:
        for model in referenced_models(root):
            violations.extend(mentions(model, forbidden))
    return sorted(set(violations))


def frozen_violations(models: tuple[type[BaseModel], ...]) -> list[str]:
    """Every model is immutable and closed: ``frozen=True`` and ``extra="forbid"``."""
    violations: list[str] = []
    for model in models:
        config = model.model_config
        if config.get("frozen") is not True:
            violations.append(f"{model.__name__} is not frozen")
        if config.get("extra") != "forbid":
            violations.append(f"{model.__name__} does not forbid extra fields")
    return violations


def clock_default_violations(models: tuple[type[BaseModel], ...]) -> list[str]:
    """No field may invent a timestamp: reading the clock is I/O and belongs to a port (§51)."""
    violations: list[str] = []
    for model in models:
        annotations = hints(model)
        for name, field in model.model_fields.items():
            parts = list(annotation_parts(annotations.get(name)))
            if not any(part in DATETIME_TYPES for part in parts):
                continue
            if field.default_factory is not None:
                violations.append(f"{model.__name__}.{name} has a default_factory")
            elif not field.is_required() and field.default is not None:
                violations.append(f"{model.__name__}.{name} has a non-None default")
    return violations


def mutable_collection_violations(models: tuple[type[BaseModel], ...]) -> list[str]:
    """No ``list``, ``set`` or ``dict`` in an annotation: immutability must be deep."""
    violations: list[str] = []
    for model in models:
        for name, annotation in hints(model).items():
            for part in annotation_parts(annotation):
                origin = getattr(part, "__origin__", None)
                if part in MUTABLE_CONTAINERS or origin in MUTABLE_CONTAINERS:
                    violations.append(f"{model.__name__}.{name} uses {_label(part)}")
    return sorted(set(violations))
