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
* **Bounded risk.** A specification above :data:`MAX_RISK` never enters. Until M13.1 the cap was
  MEDIUM (§29: "le capability HIGH e CRITICAL non vengono introdotte in produzione nella prima
  versione"); since M13.1 it is HIGH, revised in the open by ADR 0045, and a HIGH asks at every
  use. The Guardian denies CRITICAL anyway (M4.2); the catalogue makes sure the question never
  arises.

The JSON Schema draft is 2020-12 and the validator is ``jsonschema`` (ADR 0010 §4): a
hand-written validator for "the subset we use" is exactly the security-critical code this
project does not want to own. No ``$ref`` is ever resolved over the network — the validator is
built without a resolver, so a remote reference is an error, not a fetch.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Final

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from ela.domain import CapabilityId, CapabilitySpec, RiskLevel, SensorName
from ela.permissions.errors import (
    CapabilityNotFound,
    InvalidArgumentsError,
    InvalidCapabilityError,
    RiskNotAllowedError,
)
from ela.ports import AlreadyExistsError

__all__ = [
    "CORE_ECHO",
    "DECLARES_AN_EMPTY_SCOPE",
    "DEFAULT_NOTES_SCOPE",
    "FS_READ",
    "FS_WRITE",
    "MAX_RISK",
    "PHASE_13_INTRODUCED_AT",
    "TERMINAL_RUN",
    "UNDECLARED_FS_SCOPE",
    "UNDECLARED_PROGRAMS",
    "MODEL_COMPLETE",
    "MAX_LISTEN_SECONDS",
    "PERCEPTION_CAPTURE_SCREEN",
    "PERCEPTION_LISTEN",
    "PERCEPTION_READ_SCREEN_TEXT",
    "PHASE_10_INTRODUCED_AT",
    "SCHEMA_VALIDATOR",
    "V01_INTRODUCED_AT",
    "WORKSPACE_WRITE_NOTE",
    "CapabilityRegistry",
    "catalogue_v01",
    "check_capability",
    "core_echo",
    "fs_read",
    "fs_write",
    "is_valid_scope_entry",
    "model_complete",
    "perception_capture_screen",
    "perception_read_screen_text",
    "production_catalogue",
    "terminal_run",
    "validate_arguments",
    "workspace_write_note",
]

MAX_RISK: Final = RiskLevel.HIGH
"""The highest risk a specification may carry (§29, revised openly by ADR 0045).

It was ``MEDIUM`` until M13.1, because §29 said HIGH and CRITICAL were not introduced in
production "nella prima versione". v0.1 was tagged on 2026-09-07 and this work stands outside it,
so the cap moves — **in the same milestone that opens the HIGH row of the policy**, never before
it (ADR 0026 §7: a capability the Guardian would deny anyway is not a capability).

``CRITICAL`` stays above the cap, and the day it has a use it moves the same way: in the open,
with the row that admits it.
"""

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


PROMPTABLE_TYPES: Final = ("string", "integer")
"""The JSON types a ``prompt_argument`` may have (M10.2, ADR 0029 §6; M11.2 dec. G2).

An allow-list rather than "anything", because the point of the mechanism is a question a person
can read: an object or an array rendered into a sentence is not a question, it is a dump. And
deliberately without ``number`` or ``boolean`` until something needs them — a type admitted before
it has a caller is a door with nobody behind it (ADR 0026 §7)."""


def _promptable() -> str:
    return " or ".join(PROMPTABLE_TYPES)


def check_capability(spec: CapabilitySpec) -> None:
    """Refuse a specification the catalogue must not hold; return ``None`` if it may.

    In order: risk within :data:`MAX_RISK` (:class:`RiskNotAllowedError`); ``input_schema`` a
    valid schema of the draft; every scope entry well-formed; every scoped argument a ``string``
    property of the schema; scope and scoped arguments both present or both absent — a scope
    that constrains no argument, or a scoped argument with no scope, is a doubt (§33), except for
    a capability in :data:`DECLARES_AN_EMPTY_SCOPE`, whose empty scope is an answer; every
    prompt argument a property of a type in :data:`PROMPTABLE_TYPES` **and required**. Each of the
    last five is an :class:`InvalidCapabilityError` naming the capability and the reason.

    Why a prompt argument must be required (M10.2, ADR 0029 §6): its value goes into the question
    the user is asked, and a question that may be missing half its words is not a question. §30
    is about exactly this — a "yes" out of context authorises nothing — so a capability that
    declared an optional argument here would be building a defence that sometimes says nothing.

    Why the types are an allow-list and not just ``string`` (M11.2 dec. G2): a microphone is
    opened **for a number of seconds**, and how long it stays open is half of what is being
    approved — an approval that does not name it is not informed. What the narrow rule was
    protecting is untouched: the default is still empty, and what must never appear is the user's
    *content* (``model.complete``'s ``input``, the words ELA is about to say). An integer is not
    content, so admitting one widens the question without widening what can leak into a stored
    ``Approval``.
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
    declared_empty = spec.id in DECLARES_AN_EMPTY_SCOPE and not spec.scope
    if bool(spec.scope) != bool(spec.scoped_arguments) and not declared_empty:
        raise InvalidCapabilityError(
            spec.id, "scope and scoped_arguments must be both present or both absent"
        )
    required = schema.get("required", [])
    for name in spec.prompt_arguments:
        declared = properties.get(name)
        if not isinstance(declared, dict) or declared.get("type") not in PROMPTABLE_TYPES:
            raise InvalidCapabilityError(
                spec.id,
                f"prompt argument {name!r} is not a {_promptable()} property of input_schema",
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
PERCEPTION_LISTEN: Final = CapabilityId("perception.listen")
PERCEPTION_READ_SCREEN_TEXT: Final = CapabilityId("perception.read_screen_text")
VOICE_SPEAK: Final = CapabilityId("voice.speak")
VOICE_SPEAK_ONLINE: Final = CapabilityId("voice.speak_online")
FS_READ: Final = CapabilityId("fs.read")
FS_WRITE: Final = CapabilityId("fs.write")
TERMINAL_RUN: Final = CapabilityId("terminal.run")

DECLARES_AN_EMPTY_SCOPE: Final[frozenset[CapabilityId]] = frozenset({TERMINAL_RUN})
"""The capabilities whose empty scope is **an answer** and not a doubt (M13.2 dec. 16).

``ELA_TERMINAL_PROGRAMS=[]`` means «no program», and ELA starts with it: the capability exists and
the Guardian denies every call with ``Rule.SCOPE`` and ``[]`` in the reason — «an empty scope with
targets covers none» (``ela.permissions.scope``). Everywhere else a scoped argument with no scope
stays what :func:`check_capability` says it is, a doubt (§33), and a capability is here because it
is named, never because its scope happens to be empty.
"""

DEFAULT_NOTES_SCOPE: Final = "workspace/notes"
"""Where ``workspace.write_note`` may write unless the caller says otherwise (ADR 0010 §5).

The **default**, and no longer a convention: since M8.3 the composition root passes
``ELA_NOTES_SCOPE`` here (ADR 0025 §5), so this is what ELA uses when nobody says otherwise.
"""

UNDECLARED_FS_SCOPE: Final = "undeclared"
"""A placeholder, and **never a boundary** (M13.1 dec. A-bis).

The catalogue must be constructible without settings — ``production_catalogue()`` is called with
no arguments by the tests and by ``scripts/generate_stato.py`` — but the boundary of ``fs.read``
and ``fs.write`` is the **pair** ``ELA_FS_ROOT`` + ``ELA_FS_SCOPE``, and neither has a default:
without them ELA does not start. So this value can never be the boundary anybody runs under, and
``tests/composition/test_root.py`` proves the production path never uses it.

**Why a placeholder rather than a real folder**: a default like ``ELA`` would let the user declare
a root and still not be able to write in it, for a value they never saw and a folder nobody
created — and a silent narrowing is worse than a refusal at start-up, because a refusal is read.
"""

UNDECLARED_PROGRAMS: Final[tuple[str, ...]] = (UNDECLARED_FS_SCOPE,)
"""The placeholder of ``terminal.run``'s factory, and **never a boundary** (M13.2 dec. 16).

Not ``()``: with ``[]`` an admitted answer, an empty default would read a forgotten wiring as a
declaration — the difference M13.1 A-bis kept for the filesystem. ``undeclared`` is ``/undeclared``,
which is not a program; ``tests/composition/test_terminal_wiring.py`` proves the production path
never runs under it.
"""

V01_INTRODUCED_AT: Final = datetime(2026, 9, 5, tzinfo=UTC)
"""``created_at`` of the three specifications: the catalogue is declared, it is not born at
runtime, so it has no clock."""

PHASE_13_INTRODUCED_AT: Final = datetime(2026, 9, 21, tzinfo=UTC)
"""``created_at`` of what phase 13 adds: the first two capabilities that touch the filesystem
outside the workspace, and the first ``HIGH`` ELA has ever had."""

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


def perception_read_screen_text() -> CapabilitySpec:
    """``perception.read_screen_text``, MEDIUM: reads the text in a capture ELA already has.

    MEDIUM for the reason ADR 0029 §6 gave the capture, read one step further on. There the
    content was *born*; here it is made **legible**. A PNG in a directory with five minutes of
    life and a searchable text file in the same directory are not the same risk, and the second
    is not the smaller one: text is what fits in a prompt, in a paste, in a grep.

    **It reads no permission and takes none.** macOS's Vision framework recognises text with no
    TCC grant at all — measured from a process that was its own responsible process — and answers
    identically with the network denied. The Screen Recording grant was spent by
    ``perception.capture_screen``; this capability adds no new one.

    **No scope**, for ADR 0029 §6's reason: a capture id is a UUID and the Guardian's scope is
    path-shaped. The protection is the authorization.

    **A second ``purpose``, and it is not a doubled question.** The capture had one, and the
    tempting shortcut is to say whoever approved the photograph approved the reading. §30
    generalised says otherwise — *a "yes" is only worth something if the question was complete* —
    and "I photograph the screen to attach it to a ticket" and "I read the text of that screen to
    find a code in it" are two acts with two consequences. §57 asks *why* for both.
    """
    return CapabilitySpec(
        id=PERCEPTION_READ_SCREEN_TEXT,
        created_at=PHASE_10_INTRODUCED_AT,
        description="Reads the text in a capture ELA holds, on this machine, without sending it.",
        risk=RiskLevel.MEDIUM,
        input_schema={
            "type": "object",
            "properties": {
                "capture_id": {"type": "string", "minLength": 1},
                "purpose": {"type": "string", "minLength": 1},
                "region": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number", "minimum": 0, "maximum": 1},
                        "y": {"type": "number", "minimum": 0, "maximum": 1},
                        "width": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
                        "height": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
                    },
                    "required": ["x", "y", "width", "height"],
                    "additionalProperties": False,
                },
            },
            "required": ["capture_id", "purpose"],
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


MAX_SPOKEN_CHARACTERS: Final = 600
"""The longest sentence ``voice.speak`` accepts (M11.1 dec. E).

Restated here rather than imported: ``ela.permissions`` may import nothing but the standard
library and the domain (architecture rule: ``permissions-imports``), and the catalogue is a
constant that must not depend on a settings module. ``tests/tools/test_voice.py`` asserts the two
agree, so a divergence is a failing test and not a silent disagreement about how long ELA may
talk.
"""

PHASE_11_INTRODUCED_AT: Final = datetime(2026, 9, 8, tzinfo=UTC)
"""``created_at`` of what phase 11 adds. A date of its own, and not
:data:`PHASE_10_INTRODUCED_AT`, for the reason ADR 0029 §13 gave for that one: a phase does not
get folded into the one before it."""


def voice_speak() -> CapabilitySpec:
    """``voice.speak``, MEDIUM: ELA says a sentence out loud on this machine (M11.1 dec. A).

    The first capability whose effect is **outside the screen**. Everything before it landed
    somewhere a person could go and look — a row, a file that expires, an HTTP response. A spoken
    sentence is heard, once, by whoever happens to be in the room.

    **MEDIUM**, and the argument is ADR 0029 §6's applied to a different direction. There the
    reasoning about ``perception.capture_screen`` was that §29 calls ``model.complete`` MEDIUM
    "perché il contenuto dell'utente può essere inviato a un provider AI esterno", read one step
    earlier: the content does not leave, it is *born*. Here it leaves, just not over a network —
    **it leaves into the room**, and the audience is not something ELA chooses or can even
    observe. A colleague at the next desk is a recipient ELA never decided on.

    **Always requires an authorization**, because the protection cannot be a scope. The Guardian's
    scope is path-shaped, and the natural scope of speaking is *to whom* and *when*, which is not
    a path — the same reason the capture has none (ADR 0029 §6). Forcing one in would produce a
    scope pretending to be one.

    That means, today, an approval for every sentence, and that cost is real. **The answer is not
    a lower risk level**: it is that "you may speak freely while I am at the Mac" is an
    ``Authorization`` of §59 with a TTL and a condition — a reusable grant under
    ``Rule.APPROVAL_UNLESS_AUTHORIZED``, which is already how ``model.complete`` and
    ``perception.capture_screen`` work. Registered as the road, and deliberately not built here:
    a grant written before anybody has had reason to ask for it is what ADR 0028 §4 refused.

    ``purpose`` is **required** and is what the user reads when asked (§30, ADR 0029 §6). ``text``
    is **not** in ``prompt_arguments``, and that is a decision (M11.1 dec. B): the sentence is
    ELA's words, and a prompt carrying it would write them into a persisted ``Approval``. The
    oddity of approving without reading is smaller here than anywhere else — **you hear the words
    a second later** — because the question is about ELA making a sound, not about the sound.
    """
    return CapabilitySpec(
        id=VOICE_SPEAK,
        created_at=PHASE_11_INTRODUCED_AT,
        description="Says a sentence out loud on this machine, through its own speakers.",
        risk=RiskLevel.MEDIUM,
        input_schema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": MAX_SPOKEN_CHARACTERS,
                },
                "purpose": {"type": "string", "minLength": 1},
            },
            "required": ["text", "purpose"],
            "additionalProperties": False,
        },
        prompt_arguments=("purpose",),
        requires_authorization=True,
        metadata={"introduced_in": "0.2"},
    )


def voice_speak_online() -> CapabilitySpec:
    """``voice.speak_online``, MEDIUM: ELA speaks in the voice of §9, and the words leave (M11.3).

    The seventh capability, and the first outside ``model.complete`` whose execution **sends the
    user's content off this machine**. It is deliberately *not* the same capability as
    :func:`voice_speak` with a different provider behind it, and the name is deliberately not
    "cloud" — both are decisions, and the user's own words are the reason for the second:

        «cloud» dice dove sta il server, «online» dice cosa succede: **questa frase esce da questa
        macchina.** È quella la cosa che l'utente deve leggere nell'approvazione.

    And it is read literally: the prompt of an ``Approval`` is built from the capability **id**,
    the step's goal and ``purpose`` (ADR 0013 §5) — the description below never reaches it. The
    name of the capability *is* the sentence the person deciding reads, and it has to be the true
    one.

    **Two capabilities and not one, because a permission is not inherited.** The Guardian consumes
    authorizations by ``capability_id``, and the protection here cannot be a scope — speaking has
    no path-shaped scope (ADR 0033 §3). So a grant that says "you may speak" must not become "you
    may send my words to a supplier" the day somebody sets a different environment variable. With
    two ids, nobody can say yes to one by saying yes to the other.

    **MEDIUM, like its local sister, and the level is not what separates them.** §29 calls
    ``model.complete`` MEDIUM *«perché il contenuto dell'utente può essere inviato a un provider
    AI esterno»*, which is literally this. And HIGH is not a stricter MEDIUM: when this was
    decided HIGH was ``DENY`` in the Guardian's policy, so a HIGH capability would not have been
    watched more closely, it would have been unusable (ADR 0034 §4). That was the row until M13.1;
    since then HIGH asks at every use (ADR 0045 §3), and choosing it here would be a new decision,
    not this one.

    ``text`` stays out of ``prompt_arguments`` for M11.1's reason (dec. B) — the words would be
    written into a persisted ``Approval``, which is the accumulation §57 forbids reached by
    another road — and the oddity of approving without reading is no larger here than there: the
    sentence is heard a second later. What the person reads is the id, which says the words leave,
    and ``purpose``, which says what for.
    """
    return CapabilitySpec(
        id=VOICE_SPEAK_ONLINE,
        created_at=PHASE_11_INTRODUCED_AT,
        description=(
            "Says a sentence out loud in ELA's own voice; the text is sent to a speech provider, "
            "which keeps it."
        ),
        risk=RiskLevel.MEDIUM,
        input_schema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": MAX_SPOKEN_CHARACTERS,
                },
                "purpose": {"type": "string", "minLength": 1},
            },
            "required": ["text", "purpose"],
            "additionalProperties": False,
        },
        prompt_arguments=("purpose",),
        requires_authorization=True,
        metadata={"introduced_in": "0.2"},
    )


MAX_LISTEN_SECONDS: Final = 30
"""The longest the microphone may stay open in one call (M11.2).

Not a round number chosen for looking sensible: it is the voice's ceiling read back. 600
characters at the measured 18 characters a second is ≈ 33 seconds of speech (M11.1 dec. E), so
**ELA does not listen for longer than it is allowed to speak.** At 16 kHz mono that is 960 KB,
which fits in an anonymous inode without thinking about it.

And it is what bounds the worst case that has no owner: a child outlives its parent, so if ELA is
killed mid-recording the longest an orphaned microphone can live is this plus the child's margin
— a number, rather than "until somebody notices"."""


def perception_listen() -> CapabilitySpec:
    """``perception.listen``, MEDIUM: opens this machine's microphone for a stated number of
    seconds and writes down what was said.

    **The name is the surface of the consent** (ADR 0034 §3): an ``Approval``'s prompt shows the
    ``capability_id`` and never the description, so the id is the only place the right word
    reaches whoever decides. ``perception.listen`` says the thing that happens.

    MEDIUM and always authorised, for the reason ADR 0028 §9 registered: this is a reading of
    **content**, and the first that is neither a screen nor a word of ELA's. HIGH was not an
    option — in ``RISK_POLICY`` it meant ``DENY``, so it would not have made listening more
    careful, it would have made it impossible (ADR 0034 §4). That was the row until M13.1; since
    then HIGH asks at every use (ADR 0045 §3), and choosing it here would be a new decision, not
    this one.

    **No scope**, for the reason ADR 0029 §6 gave the capture: the Guardian's scope is
    path-shaped, and the natural scope of listening is *when* and *who else is in the room*,
    which are not paths.

    ``seconds`` is **required, has no default, and is named in the question** (M11.2 dec. G2). A
    capability that opened a microphone for a length written in a configuration file would be
    hiding the very thing the person answering wants to know; and §30, in the form ADR 0029 §6
    gave it, says a yes is only worth something if the question was complete.
    """
    return CapabilitySpec(
        id=PERCEPTION_LISTEN,
        created_at=PHASE_11_INTRODUCED_AT,
        description="Opens this machine's microphone for a while and writes down what it heard.",
        risk=RiskLevel.MEDIUM,
        input_schema={
            "type": "object",
            "properties": {
                "purpose": {"type": "string", "minLength": 1},
                "seconds": {"type": "integer", "minimum": 1, "maximum": MAX_LISTEN_SECONDS},
            },
            "required": ["purpose", "seconds"],
            "additionalProperties": False,
        },
        prompt_arguments=("purpose", "seconds"),
        activates_sensor=SensorName.MICROPHONE,
        requires_authorization=True,
        metadata={"introduced_in": "0.2"},
    )


def fs_read(fs_scope: str = UNDECLARED_FS_SCOPE) -> CapabilitySpec:
    """``fs.read``, MEDIUM: reads one file under the declared root (§18, M13.1 dec. E).

    **MEDIUM and not HIGH**, and the difference is not a feeling. Today both rows ask at every use,
    because every grant is single-use; what separates them is what they promise about tomorrow:
    a standing policy of §59 will be able to cover a MEDIUM, and it will never reach a HIGH
    (dec. D). Reading is not writing — a read is undone by forgetting it, a write outside the
    workspace is irreversible while §37 does not exist — so the level that can one day be widened
    is the honest one for reading.

    **Not LOW**, which would ask nothing inside the scope: a file outside the workspace is the
    user's own content (§57), and LOW would turn a permission into a line of configuration
    nobody is ever asked about again.

    The risk is the capability's and never the arguments': ``fs.read`` is not HIGH for some paths
    and MEDIUM for others. Where it may read at all is the scope's business. The rule is ADR 0026
    §7 — «tutto ciò che la policy legge viene dal catalogo» —; until M13.2 this line cited ADR 0038
    §16, whose «level» is the task's sensitivity and not a risk (ADR 0047 names the correction).
    """
    return CapabilitySpec(
        id=FS_READ,
        created_at=PHASE_13_INTRODUCED_AT,
        description="Reads one file inside the authorised folder, outside the workspace.",
        risk=RiskLevel.MEDIUM,
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "purpose": {"type": "string", "minLength": 1},
            },
            "required": ["path", "purpose"],
            "additionalProperties": False,
        },
        scope=(fs_scope,),
        scoped_arguments=("path",),
        prompt_arguments=("purpose",),
        requires_authorization=True,
        metadata={"introduced_in": "0.2"},
    )


def fs_write(fs_scope: str = UNDECLARED_FS_SCOPE) -> CapabilitySpec:
    """``fs.write``, **HIGH**: writes one file under the declared root (§18, M13.1 dec. E).

    The first ``HIGH`` capability ELA has ever had, and it arrives in the same milestone that
    turns the ``HIGH`` row from ``DENY`` into a question at every use — because neither half
    means anything alone (ADR 0026 §7).

    **Why HIGH and not MEDIUM.** §59's own example — "puoi modificare liberamente i file dentro
    questa cartella" — is already honoured, today, by ``workspace.write_note``: LOW, inside its
    scope, no question. ``fs.write`` is the same action on a house instead of a folder, and
    outside the workspace **a write is irreversible while §37 does not exist**: there is no
    rollback to appeal to. HIGH is the row no standing policy reaches (dec. D).

    ``overwrite`` is **an assertion about the world, not a request** (dec. Q): the question shows
    what the machine answers, and the tool reads it again before writing and refuses if it has
    changed **either way** — created where an overwrite was approved, or gone where one was. A
    criterion that names one direction is half a defence, and the missing case is the one a race
    loses.
    """
    return CapabilitySpec(
        id=FS_WRITE,
        created_at=PHASE_13_INTRODUCED_AT,
        description="Writes one file inside the authorised folder, outside the workspace.",
        risk=RiskLevel.HIGH,
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "body": {"type": "string"},
                "overwrite": {"type": "boolean"},
                "purpose": {"type": "string", "minLength": 1},
            },
            "required": ["path", "body", "overwrite", "purpose"],
            "additionalProperties": False,
        },
        scope=(fs_scope,),
        scoped_arguments=("path",),
        prompt_arguments=("purpose",),
        requires_authorization=True,
        metadata={"introduced_in": "0.2"},
    )


def terminal_run(programs: Sequence[str] = UNDECLARED_PROGRAMS) -> CapabilitySpec:
    """``terminal.run``, **HIGH**: runs one program of those declared, and returns what it printed.

    The second capability of the Action Core of §18, and the one the ``HIGH`` row exists to
    protect. **The boundary is which programs** (M13.2 dec. 2): the scope is the list of
    ``ELA_TERMINAL_PROGRAMS``, written relative to ``/`` in the grammar every scope has — so the
    four comparisons that read a scope did not change — and the one scoped argument is ``program``.
    The arguments of each call are **not** in the scope: they are shown in the question, one by one,
    and judged by the user **at every use**, which is what the ``HIGH`` row guarantees and no policy
    of §59 will ever reach.

    Said as plainly as ADR 0047 says it: *admitting an interpreter — ``sh``, ``python``, ``env``,
    ``xargs``, ``find`` — is admitting anything, and the defence is the question at every use.*
    There is no list of interpreters or of dangerous flags: it would be incomplete on its first day,
    and it would teach that what is not on it is safe.

    ``args`` is a **list** and reaches the process as one — never a string, never a shell. ``cwd``
    is relative to the folder of the scope of M13.1; ``expect_exit`` is the code the plan expects,
    and the verifier compares it (dec. 9). ``purpose`` is what the user reads (§30).
    """
    return CapabilitySpec(
        id=TERMINAL_RUN,
        created_at=PHASE_13_INTRODUCED_AT,
        description=(
            "Runs one of the programs you declared, with the arguments of this call, and returns "
            "what it printed."
        ),
        risk=RiskLevel.HIGH,
        input_schema={
            "type": "object",
            "properties": {
                "program": {"type": "string"},
                "args": {"type": "array", "items": {"type": "string"}},
                "purpose": {"type": "string", "minLength": 1},
                "cwd": {"type": "string"},
                "expect_exit": {"type": "integer", "minimum": 0, "maximum": 255},
            },
            "required": ["program", "args", "purpose"],
            "additionalProperties": False,
        },
        scope=tuple(programs),
        scoped_arguments=("program",),
        prompt_arguments=("purpose",),
        requires_authorization=True,
        metadata={"introduced_in": "0.2"},
    )


def production_catalogue(
    *,
    notes_scope: str = DEFAULT_NOTES_SCOPE,
    fs_scope: str = UNDECLARED_FS_SCOPE,
    programs: Sequence[str] = UNDECLARED_PROGRAMS,
) -> CapabilityRegistry:
    """What the composition root builds: v0.1's three, plus what the phases after it added.

    This says *when it is used*; :func:`catalogue_v01` says *what it contains*. Both exist and
    neither is redundant, for the reason of ADR 0029 §13: **v0.1 does not get folded into, it
    gets stood beside.** A ``catalogue_v01`` that answered four would be a function that lies,
    and the precedent is M10.1's, where ``/perception`` was left out of the v0.1 route count
    rather than quietly folded into it.
    """
    return CapabilityRegistry(
        (
            *catalogue_v01(notes_scope=notes_scope).specs(),
            perception_capture_screen(),
            perception_read_screen_text(),
            voice_speak(),
            voice_speak_online(),
            # In the order the ADRs added them, which is what the catalogue's table is checked
            # against: a capability is added with an ADR and a row, never by accident.
            perception_listen(),
            fs_read(fs_scope),
            fs_write(fs_scope),
            terminal_run(programs),
        )
    )
