"""The capability catalogue (spec §28, §29; ADR 0010, M4.1).

A capability is a specification the Guardian reasons about; a tool is its implementation
(§28). This module holds the specifications: a :class:`CapabilityRegistry` that validates and
freezes them when it is built, :func:`validate_arguments` that checks a call's arguments
against a capability's JSON Schema, :func:`catalogue_v01` — the three capabilities of §29 and
nothing else — and :func:`production_catalogue`, which is those plus what the phases after v0.1
added. The two names answer different questions and both stay (ADR 0029 §13).

Two properties of the registry are security properties, not conveniences:

* **Immutable after construction.** There is no ``register``: what ELA may do is decided when
  the registry is built, and nothing that runs later — a planner, a provider's answer, a tool —
  can widen it.
* **Bounded risk.** A specification above :data:`MAX_RISK` never enters (§29: "le capability
  HIGH e CRITICAL non vengono introdotte in produzione nella prima versione"). The Guardian
  denies HIGH and CRITICAL anyway (M4.2); the catalogue makes sure the question never arises.

The JSON Schema draft is 2020-12 and the validator is ``jsonschema`` (ADR 0010 §4): a
hand-written validator for "the subset we use" is exactly the security-critical code this
project does not want to own. No ``$ref`` is ever resolved over the network — the validator is
built without a resolver, so a remote reference is an error, not a fetch.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Final

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from ela.domain import CapabilityId, CapabilitySpec, RiskLevel
from ela.permissions.errors import (
    CapabilityNotFound,
    InvalidArgumentsError,
    InvalidCapabilityError,
    RiskNotAllowedError,
)
from ela.ports import AlreadyExistsError

__all__ = [
    "CORE_ECHO",
    "DEFAULT_NOTES_SCOPE",
    "MAX_RISK",
    "MODEL_COMPLETE",
    "PERCEPTION_CAPTURE_SCREEN",
    "PHASE_10_INTRODUCED_AT",
    "SCHEMA_VALIDATOR",
    "V01_INTRODUCED_AT",
    "WORKSPACE_WRITE_NOTE",
    "CapabilityRegistry",
    "catalogue_v01",
    "check_capability",
    "core_echo",
    "is_valid_scope_entry",
    "model_complete",
    "perception_capture_screen",
    "production_catalogue",
    "validate_arguments",
    "workspace_write_note",
]

MAX_RISK: Final = RiskLevel.MEDIUM
"""The highest risk a specification may carry in v0.1 (§29)."""

SCHEMA_VALIDATOR: Final = Draft202012Validator
"""The JSON Schema draft every ``input_schema`` is read as."""

FORBIDDEN_SCOPE_PARTS: Final[frozenset[str]] = frozenset({"", ".", ".."})
"""Path segments a scope entry may not contain: empty (``a//b``, leading or trailing ``/``),
current and parent directory."""


def _plain(value: Any) -> Any:
    """Frozen JSON (``MappingProxyType``, tuples) back to plain ``dict``/``list``.

    ``jsonschema`` types an "object" as ``dict`` and an "array" as ``list``; the domain keeps
    its payloads frozen (ADR 0003). The copy is local to one validation and never escapes.
    """
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    return value


def is_valid_scope_entry(entry: str) -> bool:
    """Whether ``entry`` is a relative POSIX path with no empty, ``.`` or ``..`` segment.

    ``workspace/notes`` is; ``/workspace``, ``workspace/``, ``./notes``, ``a/../b`` and anything
    with a backslash are not. The same syntax will be applied to a call's targets when the
    Guardian compares them with the scope (M4.2).
    """
    if "\\" in entry:
        return False
    return not any(part in FORBIDDEN_SCOPE_PARTS for part in entry.split("/"))


def check_capability(spec: CapabilitySpec) -> None:
    """Refuse a specification the catalogue must not hold; return ``None`` if it may.

    In order: risk within :data:`MAX_RISK` (:class:`RiskNotAllowedError`); ``input_schema`` a
    valid schema of the draft; every scope entry well-formed; every scoped argument a ``string``
    property of the schema; scope and scoped arguments both present or both absent — a scope
    that constrains no argument, or a scoped argument with no scope, is a doubt (§33); every
    prompt argument a ``string`` property **and required**. Each of the last five is an
    :class:`InvalidCapabilityError` naming the capability and the reason.

    Why a prompt argument must be required (M10.2, ADR 0029 §6): its value goes into the question
    the user is asked, and a question that may be missing half its words is not a question. §30
    is about exactly this — a "yes" out of context authorises nothing — so a capability that
    declared an optional argument here would be building a defence that sometimes says nothing.
    """
    if spec.risk > MAX_RISK:
        raise RiskNotAllowedError(spec.id, spec.risk, MAX_RISK)
    schema = _plain(spec.input_schema)
    try:
        SCHEMA_VALIDATOR.check_schema(schema)
    except SchemaError as error:
        raise InvalidCapabilityError(
            spec.id, f"input_schema is not a valid JSON Schema: {error.message}"
        ) from error
    for entry in spec.scope:
        if not is_valid_scope_entry(entry):
            raise InvalidCapabilityError(
                spec.id, f"scope entry {entry!r} is not a relative path without '.' or '..'"
            )
    properties = schema.get("properties", {})
    for name in spec.scoped_arguments:
        declared = properties.get(name)
        if not isinstance(declared, dict) or declared.get("type") != "string":
            raise InvalidCapabilityError(
                spec.id, f"scoped argument {name!r} is not a string property of input_schema"
            )
    if bool(spec.scope) != bool(spec.scoped_arguments):
        raise InvalidCapabilityError(
            spec.id, "scope and scoped_arguments must be both present or both absent"
        )
    required = schema.get("required", [])
    for name in spec.prompt_arguments:
        declared = properties.get(name)
        if not isinstance(declared, dict) or declared.get("type") != "string":
            raise InvalidCapabilityError(
                spec.id, f"prompt argument {name!r} is not a string property of input_schema"
            )
        if name not in required:
            raise InvalidCapabilityError(
                spec.id, f"prompt argument {name!r} is not required by input_schema"
            )


def validate_arguments(spec: CapabilitySpec, arguments: Mapping[str, object]) -> None:
    """Refuse ``arguments`` that do not satisfy ``spec.input_schema``; return ``None`` if they do.

    Every violation is collected, not only the first, and reported as ``<json path>: <message>``
    in path order (:class:`InvalidArgumentsError`). Pure: no I/O, no state. The Guardian runs
    this on the *registered* specification before any other check (M4.2).
    """
    validator = SCHEMA_VALIDATOR(_plain(spec.input_schema))
    errors = sorted(validator.iter_errors(_plain(arguments)), key=lambda e: e.json_path)
    if errors:
        raise InvalidArgumentsError(
            spec.id, tuple(f"{error.json_path}: {error.message}" for error in errors)
        )


class CapabilityRegistry:
    """The catalogue: specifications validated and frozen at construction (§28, §29).

    Implements :class:`~ela.ports.CapabilityRegistryPort`: ``get`` and ``specs``, nothing
    else. Every specification passes :func:`check_capability`; a repeated id is an
    :class:`~ela.ports.AlreadyExistsError`. Any failure means no registry at all (§33): a
    catalogue is never half built.
    """

    __slots__ = ("_specs",)

    def __init__(self, specs: Iterable[CapabilitySpec]) -> None:
        catalogue: dict[CapabilityId, CapabilitySpec] = {}
        for spec in specs:
            check_capability(spec)
            if spec.id in catalogue:
                raise AlreadyExistsError("capability", spec.id)
            catalogue[spec.id] = spec
        self._specs: Mapping[CapabilityId, CapabilitySpec] = MappingProxyType(catalogue)

    def get(self, capability_id: CapabilityId) -> CapabilitySpec:
        """The specification with this id; :class:`CapabilityNotFound` if there is none."""
        try:
            return self._specs[capability_id]
        except KeyError:
            raise CapabilityNotFound(capability_id) from None

    def specs(self) -> tuple[CapabilitySpec, ...]:
        """Every specification, in construction order."""
        return tuple(self._specs.values())


# --------------------------------------------------------------------------------------
# The catalogue of v0.1 (§29)
# --------------------------------------------------------------------------------------

CORE_ECHO: Final = CapabilityId("core.echo")
WORKSPACE_WRITE_NOTE: Final = CapabilityId("workspace.write_note")
MODEL_COMPLETE: Final = CapabilityId("model.complete")
PERCEPTION_CAPTURE_SCREEN: Final = CapabilityId("perception.capture_screen")

DEFAULT_NOTES_SCOPE: Final = "workspace/notes"
"""Where ``workspace.write_note`` may write unless the caller says otherwise (ADR 0010 §5).

The **default**, and no longer a convention: since M8.3 the composition root passes
``ELA_NOTES_SCOPE`` here (ADR 0025 §5), so this is what ELA uses when nobody says otherwise.
"""

V01_INTRODUCED_AT: Final = datetime(2026, 9, 5, tzinfo=UTC)
"""``created_at`` of the three specifications: the catalogue is declared, it is not born at
runtime, so it has no clock."""

PHASE_10_INTRODUCED_AT: Final = datetime(2026, 9, 8, tzinfo=UTC)
"""``created_at`` of what phase 10 adds. A date of its own, and not :data:`V01_INTRODUCED_AT`,
for the reason of ADR 0029 §13: v0.1 does not get folded into, it gets stood beside."""


def core_echo() -> CapabilitySpec:
    """``core.echo``, SAFE: returns its message. The capability that proves the pipeline works."""
    return CapabilitySpec(
        id=CORE_ECHO,
        created_at=V01_INTRODUCED_AT,
        description="Returns the message it receives; exists to verify the system end to end.",
        risk=RiskLevel.SAFE,
        input_schema={
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
            "additionalProperties": False,
        },
        requires_authorization=False,
        metadata={"introduced_in": "0.1"},
    )


def workspace_write_note(notes_scope: str = DEFAULT_NOTES_SCOPE) -> CapabilitySpec:
    """``workspace.write_note``, LOW: writes a note, only inside ``notes_scope`` (§29).

    The scope is what protects it, so it needs no authorization: the Guardian allows it when
    ``path`` lies within the scope and denies it otherwise (M4.2).
    """
    return CapabilitySpec(
        id=WORKSPACE_WRITE_NOTE,
        created_at=V01_INTRODUCED_AT,
        description="Writes a note at a path inside the authorised notes folder.",
        risk=RiskLevel.LOW,
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}, "body": {"type": "string"}},
            "required": ["path", "body"],
            "additionalProperties": False,
        },
        scope=(notes_scope,),
        scoped_arguments=("path",),
        requires_authorization=False,
        metadata={"introduced_in": "0.1"},
    )


def model_complete() -> CapabilitySpec:
    """``model.complete``, MEDIUM: sends the user's content to an external model provider (§29).

    The arguments mirror :class:`~ela.domain.ProviderRequest` so the tool builds the request
    without translating: ``input`` is mandatory; ``purpose``, ``instructions``, ``model_hint``
    and ``parameters`` are optional. Always requires an authorization: content leaves ELA.

    ``task_type`` is the key the Model Router routes on (§25, ADR 0022 §2), and it is an argument
    of its own rather than a reading of ``purpose``: ``purpose`` is documented as a human
    description that travels into the audit trail, and a description must not be able to change
    which model answers because somebody rewrote it. It carries **no ``enum``**: the vocabulary
    of task types is the routing table's, and the table is configurable (``ELA_MODEL_ROUTES``)
    while this catalogue is a constant. A type outside the table is refused by the router, with
    a name of its own (``routing.unknown_task_type``) and before any call.
    """
    return CapabilitySpec(
        id=MODEL_COMPLETE,
        created_at=V01_INTRODUCED_AT,
        description="Completes a text with an external model provider.",
        risk=RiskLevel.MEDIUM,
        input_schema={
            "type": "object",
            "properties": {
                "input": {"type": "string"},
                "purpose": {"type": "string"},
                "instructions": {"type": "string"},
                "task_type": {"type": "string"},
                "model_hint": {"type": "string"},
                "parameters": {"type": "object"},
            },
            "required": ["input"],
            "additionalProperties": False,
        },
        requires_authorization=True,
        metadata={"introduced_in": "0.1"},
    )


def perception_capture_screen() -> CapabilitySpec:
    """``perception.capture_screen``, MEDIUM: photographs one display of this Mac (M10.2).

    The first capability that reads **content**, and the one ADR 0028 §9 registered as a
    constraint rather than shipping early: "la prima lettura di contenuto nasce con la propria
    capability MEDIUM, nella milestone che la introduce e non prima".

    MEDIUM for the reason §29 gives ``model.complete`` — "perché il contenuto dell'utente può
    essere inviato a un provider AI esterno" — read one step earlier: here the content does not
    leave, but it is *born*, and nobody dictated it. It always requires an authorization: the
    protection is the grant, not a scope.

    **No scope, and that is a decision** (ADR 0029 §6). The Guardian's scope is path-shaped —
    relative POSIX segments, compared with a call's targets — and the natural scope of a screen
    capture is *which display*, which is not a path. Forcing it in would produce a scope
    pretending to be one.

    ``purpose`` is **required** and is the only ``prompt_arguments`` entry in ELA: it is what the
    user reads when asked (§30). "ELA wants to photograph your screen" is not a question anybody
    can answer; the reason is what makes the yes worth something.

    ``display`` is the 1-based index ``screencapture -D`` takes. It is **not** correlated with
    the ``display_count`` of M10.1 beyond the count — two enumerations of the same hardware, and
    promising they line up is a promise ELA cannot keep.
    """
    return CapabilitySpec(
        id=PERCEPTION_CAPTURE_SCREEN,
        created_at=PHASE_10_INTRODUCED_AT,
        description="Captures one display of this machine to a private file that expires.",
        risk=RiskLevel.MEDIUM,
        input_schema={
            "type": "object",
            "properties": {
                "purpose": {"type": "string", "minLength": 1},
                "display": {"type": "integer", "minimum": 1},
            },
            "required": ["purpose"],
            "additionalProperties": False,
        },
        prompt_arguments=("purpose",),
        requires_authorization=True,
        metadata={"introduced_in": "0.2"},
    )


def catalogue_v01(*, notes_scope: str = DEFAULT_NOTES_SCOPE) -> CapabilityRegistry:
    """The catalogue **of v0.1**: exactly the three capabilities of §29, in its order.

    This says *what it contains*, and it will keep containing those three: §29 enumerates them,
    ADR 0010 tabulates them, and ``tests/docs/test_v01_surface.py`` counts them. It is not the
    older version of :func:`production_catalogue` — see there for why both exist.
    """
    return CapabilityRegistry((core_echo(), workspace_write_note(notes_scope), model_complete()))


def production_catalogue(*, notes_scope: str = DEFAULT_NOTES_SCOPE) -> CapabilityRegistry:
    """What the composition root builds: v0.1's three, plus what the phases after it added.

    This says *when it is used*; :func:`catalogue_v01` says *what it contains*. Both exist and
    neither is redundant, for the reason of ADR 0029 §13: **v0.1 does not get folded into, it
    gets stood beside.** A ``catalogue_v01`` that answered four would be a function that lies,
    and the precedent is M10.1's, where ``/perception`` was left out of the v0.1 route count
    rather than quietly folded into it.
    """
    return CapabilityRegistry(
        (*catalogue_v01(notes_scope=notes_scope).specs(), perception_capture_screen())
    )
