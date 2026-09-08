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
    "PERCEPTION_READ_SCREEN_TEXT",
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
    "perception_read_screen_text",
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
PERCEPTION_READ_SCREEN_TEXT: Final = CapabilityId("perception.read_screen_text")
VOICE_SPEAK: Final = CapabilityId("voice.speak")
VOICE_SPEAK_ONLINE: Final = CapabilityId("voice.speak_online")

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
    AI esterno»*, which is literally this. And HIGH is not a stricter MEDIUM: in the Guardian's
    policy HIGH is ``DENY``, so a HIGH capability is not watched more closely, it is unusable
    (ADR 0034 §4).

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


def production_catalogue(*, notes_scope: str = DEFAULT_NOTES_SCOPE) -> CapabilityRegistry:
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
        )
    )
