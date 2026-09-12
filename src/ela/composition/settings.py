"""All of ELA's configuration, read in one place (spec §54 "Configuration"; ADR 0023 §2, §3).

Until M8.1 five ``BaseSettings`` classes shared the ``ELA_`` prefix and nobody read them together:
:class:`~ela.infrastructure.persistence.PersistenceSettings`,
:class:`~ela.tools.settings.WorkspaceSettings`, :class:`~ela.devices.settings.DeviceSettings`,
:class:`~ela.providers.anthropic.AnthropicSettings` and
:class:`~ela.routing.RoutingSettings`. What was scattered was never the *validation* — each piece
is checked next to the code that uses it, by the ADR that decided it — but the **point of
reading**. :meth:`Settings.load` is now that point, and the only one.

Two classes are new here, and hold what only a running ELA needs: :class:`ApiSettings` (the
token, the address) and :class:`CoreSettings` (the durations the Executive Core runs on; who the
user is left it in M12.1, when the identity became the one the API resolves — ADR 0037 §15).
Both keep the ``ELA_`` prefix: one namespace, one ``.env``.
"""

from __future__ import annotations

import ipaddress
import platform
import re
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Final

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.exceptions import SettingsError

from ela.composition.errors import ConfigurationError
from ela.context import ContextSettings
from ela.devices.settings import DeviceSettings
from ela.domain import PerformanceClass
from ela.executive import (
    DEFAULT_APPROVAL_TTL,
    DEFAULT_ASSIGNMENT_CAP,
    DEFAULT_ASSIGNMENT_TTL,
    MAX_APPROVAL_TTL,
    MAX_ASSIGNMENT_CAP,
)
from ela.infrastructure.persistence import PersistenceSettings
from ela.perception import PerceptionSettings
from ela.permissions import (
    DEFAULT_AUTHORIZATION_TTL,
    DEFAULT_DECISION_TTL,
    DEFAULT_NOTES_SCOPE,
    MAX_AUTHORIZATION_TTL,
    MAX_DECISION_TTL,
    is_valid_scope_entry,
)
from ela.providers.anthropic import AnthropicSettings
from ela.providers.elevenlabs import ElevenLabsSettings
from ela.routing import RoutingSettings
from ela.tombstones import (
    refuse_retired,
)
from ela.tools.settings import (
    CaptureSettings,
    ListenSettings,
    VoiceSettings,
    WorkspaceSettings,
)

__all__ = [
    "DEFAULT_API_HOST",
    "DEFAULT_API_PORT",
    "DEFAULT_ORPHAN_AFTER_SECONDS",
    "MIN_TOKEN_LENGTH",
    "ApiSettings",
    "CoreSettings",
    "Settings",
    "TAILNET_RANGES",
]

DEFAULT_API_HOST: Final = "127.0.0.1"
"""Loopback, and only loopback (ADR 0023 §7): ELA on the network is the story of the nodes."""
TAILNET_RANGES: Final = (
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("fd7a:115c:a1e0::/48"),
)
"""The addresses of Tailscale, from its documentation — not from this repository — and verified on
this machine with ``tailscale ip`` on 2026-09-11, before the validator was written (ADR 0037 §2)."""
DEFAULT_API_PORT: Final = 8351
"""An uncommon port collides less with whatever else runs on a developer's machine."""
MIN_TOKEN_LENGTH: Final = 32
"""Short enough to type, long enough not to be guessed by whatever else runs on this machine."""
DEFAULT_ORPHAN_AFTER_SECONDS: Final = 900
"""Fifteen minutes, and the reason is ``run`` being synchronous inside an HTTP request
(ADR 0023 §9): an EXECUTING task may legitimately stay silent for as long as a model call takes,
and a shorter default would fail a live task as an orphan on every restart."""

_FIELD = re.compile(r'field "(\w+)"')
"""How pydantic-settings names what it could not read: as a field, not as a variable."""

_SECONDS_IN_AUTHORIZATION_TTL: Final = int(MAX_AUTHORIZATION_TTL.total_seconds())
_SECONDS_IN_APPROVAL_TTL: Final = int(MAX_APPROVAL_TTL.total_seconds())
_SECONDS_IN_DECISION_TTL: Final = int(MAX_DECISION_TTL.total_seconds())
_SECONDS_IN_ASSIGNMENT_CAP: Final = int(MAX_ASSIGNMENT_CAP.total_seconds())

DEFAULT_NODE_POLL_SECONDS: Final = 25
"""How long a node's request for work waits before answering "nothing" (ADR 0038 §11)."""
MAX_NODE_POLL_SECONDS: Final = 60
"""And its ceiling: no waiting without a cap, the rule of M4.2 applied to a held connection."""


def _is_loopback(host: str) -> bool:
    """Whether ``host`` names this machine and nothing else.

    ``localhost`` by name, and every address in ``127.0.0.0/8`` or ``::1`` by number. A name that
    is not an address at all is not loopback: ELA does not resolve it to find out, because what
    a name resolves to can change after the check.
    """
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class ApiSettings(BaseSettings):
    """The local API: the token that opens it and the address it listens on (ADR 0023 §7)."""

    model_config = SettingsConfigDict(env_prefix="ELA_", env_file=".env", extra="ignore")

    api_token: SecretStr | None = None
    """``ELA_API_TOKEN``, **required**: an API with no token is an API open to every process on
    this machine. Kept as a ``SecretStr`` so that printing the settings cannot print it."""

    api_host: str = DEFAULT_API_HOST
    """``ELA_API_HOST``: loopback only."""

    api_port: Annotated[int, Field(ge=1, le=65535)] = DEFAULT_API_PORT
    """``ELA_API_PORT``."""

    api_tailnet_host: str | None = None
    """``ELA_API_TAILNET_HOST``: the second address, on the tailnet, where the nodes reach ELA.

    Optional (ADR 0037 §2): without it ELA listens on loopback alone, and local use does not depend
    on a third party's daemon. With it, the same server serves the same application from both
    addresses, on ``ELA_API_PORT``. The boundary is the identity, not the address — which is why
    the address is still held to the tailnet: WireGuard is what keeps "no TLS" true there.
    """

    @field_validator("api_token")
    @classmethod
    def _a_real_token(cls, value: SecretStr | None) -> SecretStr:
        """A token that is missing, blank or short stops ELA here (§33)."""
        secret = "" if value is None else value.get_secret_value().strip()
        if not secret:
            raise ValueError(
                "ELA_API_TOKEN is required: ELA does not open an unauthenticated API. Generate "
                'one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )
        if len(secret) < MIN_TOKEN_LENGTH:
            raise ValueError(
                f"ELA_API_TOKEN must be at least {MIN_TOKEN_LENGTH} characters, not {len(secret)}"
            )
        return SecretStr(secret)

    @field_validator("api_host")
    @classmethod
    def _loopback_only(cls, value: str) -> str:
        """``0.0.0.0`` and a network address are refused at start-up, not warned about."""
        if not _is_loopback(value):
            raise ValueError(
                f"ELA_API_HOST must be a loopback address, not {value!r}: this API is local "
                "(spec §56 — reaching ELA over the network is what the nodes are for)"
            )
        return value

    @field_validator("api_tailnet_host")
    @classmethod
    def _tailnet_only(cls, value: str | None) -> str | None:
        """An address of the tailnet, by number; anything else stops ELA at start-up (§33).

        Not a name: what a name resolves to can change after the check. Not ``0.0.0.0``, and not
        an address of another network: either would open ELA to more than the machines of the
        user's tailnet. Blank is absent, as for an API key.
        """
        if value is None or not value.strip():
            return None
        host = value.strip()
        ranges = " or ".join(str(network) for network in TAILNET_RANGES)
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            raise ValueError(
                f"ELA_API_TAILNET_HOST must be an address of the tailnet ({ranges}), not {host!r}: "
                "a name is not resolved, because what it resolves to can change after the check"
            ) from None
        if not any(address in network for network in TAILNET_RANGES):
            raise ValueError(
                f"ELA_API_TAILNET_HOST must be in the range of the tailnet ({ranges}), "
                f"not {host!r}: any other address would open ELA beyond the machines of the "
                "tailnet (ADR 0037 §2)"
            )
        return host

    @property
    def token(self) -> str:
        """The token as a string, for the one comparison that needs it."""
        assert self.api_token is not None  # the validator refuses anything else
        return self.api_token.get_secret_value()


class CoreSettings(BaseSettings):
    """The durations ELA runs on, and where a note may be written.

    Three durations in M8.1 (ADR 0023 §3), four in M8.3, plus ``notes_scope`` (ADR 0025 §5, §6).

    ``notes_scope`` is a path inside the workspace and would read better next to
    ``ELA_WORKSPACE_DIR`` in :class:`~ela.tools.settings.WorkspaceSettings`. It is here instead
    because what it configures is the **catalogue**: validating it means asking
    :func:`~ela.permissions.is_valid_scope_entry` whether it is a well-formed scope entry, and
    ``ela.tools`` imports only ``ela.domain`` and ``ela.ports`` today — a tool implements a
    capability, it does not hold the catalogue. Copying the rule into ``ela.tools`` to avoid the
    import would leave two definitions of "a valid scope", which is worse than one variable
    sitting in the second-best class.
    """

    model_config = SettingsConfigDict(env_prefix="ELA_", env_file=".env", extra="ignore")

    user_name: str | None = None
    """``ELA_USER_NAME``, **retired** in M12.1: a tombstone, never a value (ADR 0037 §15).

    It signed an answer to a request for approval while one token meant one identity, and ADR 0023
    §4 said it would go the day the nodes brought an authenticated identity. Since M12.1 who answers
    is the identity the API resolves for the call — with the Core's token, the user at this machine
    — and setting this variable stops ELA at start-up, naming why."""

    authorization_ttl_seconds: Annotated[int, Field(gt=0, le=_SECONDS_IN_AUTHORIZATION_TTL)] = int(
        DEFAULT_AUTHORIZATION_TTL.total_seconds()
    )
    """``ELA_AUTHORIZATION_TTL_SECONDS``: how long a grant born from an approval lives
    (ADR 0012 §2). Capped, because a grant without a ceiling is a bearer token left open."""

    approval_ttl_seconds: Annotated[int, Field(gt=0, le=_SECONDS_IN_APPROVAL_TTL)] = int(
        DEFAULT_APPROVAL_TTL.total_seconds()
    )
    """``ELA_APPROVAL_TTL_SECONDS``: how long a request for consent waits (ADR 0013)."""

    decision_ttl_seconds: Annotated[int, Field(gt=0, le=_SECONDS_IN_DECISION_TTL)] = int(
        DEFAULT_DECISION_TTL.total_seconds()
    )
    """``ELA_DECISION_TTL_SECONDS``: how long an ``ALLOWED`` decision stays usable (ADR 0011 §9).

    Capped at :data:`~ela.permissions.MAX_DECISION_TTL`, and the reason is written there: past an
    hour it is not a decision any more, it is a permission — and permissions are
    ``Authorization``, which has a grant, a count of uses and an audit trail of its own."""

    notes_scope: str = DEFAULT_NOTES_SCOPE
    """``ELA_NOTES_SCOPE``: the only folder ``workspace.write_note`` may write in (§29).

    Relative to the workspace, and it is the **scope** of the capability — what makes writing a
    note LOW rather than something that needs consent every time. Changing it on an ELA that has
    already run does not move the notes already written, and puts the grants given for paths in
    the old scope out of scope: the Guardian will deny them, correctly and without warning."""

    task_orphan_after_seconds: Annotated[int, Field(gt=0)] = DEFAULT_ORPHAN_AFTER_SECONDS
    """``ELA_TASK_ORPHAN_AFTER_SECONDS``: how long an EXECUTING task may stay silent before
    ``recover()`` fails it as an orphan (ADR 0008 §6)."""

    assignment_ttl_seconds: Annotated[int, Field(gt=0)] = int(
        DEFAULT_ASSIGNMENT_TTL.total_seconds()
    )
    """``ELA_ASSIGNMENT_TTL_SECONDS``: how long the Core waits before deciding a node is gone — for
    the claim of work offered to it, and for a sign of the work it took (ADR 0038 §5).

    No ceiling of its own, because it has three, checked together at start-up by
    :meth:`_the_silence_fits`: the decision's TTL, the orphan threshold, and the cap of a piece of
    work."""

    assignment_max_seconds: Annotated[int, Field(gt=0, le=_SECONDS_IN_ASSIGNMENT_CAP)] = int(
        DEFAULT_ASSIGNMENT_CAP.total_seconds()
    )
    """``ELA_ASSIGNMENT_MAX_SECONDS``: the longest life of work a node took, however often it
    renews (ADR 0038 §13). Capped at a day: no TTL without a cap, and the cap has one too."""

    node_poll_seconds: Annotated[int, Field(gt=0, le=MAX_NODE_POLL_SECONDS)] = (
        DEFAULT_NODE_POLL_SECONDS
    )
    """``ELA_NODE_POLL_SECONDS``: how long ``POST /nodes/work`` holds a request that found nothing.

    Twenty-five seconds, under the thirty of inactivity many intermediaries tolerate — a reason and
    not a measurement (ADR 0038 §11). Capped at a minute: a held connection is the same resource as
    a synchronous ``run``, and what *n* nodes cost a single-process uvicorn is to be measured.
    """

    @property
    def authorization_ttl(self) -> timedelta:
        return timedelta(seconds=self.authorization_ttl_seconds)

    @property
    def approval_ttl(self) -> timedelta:
        return timedelta(seconds=self.approval_ttl_seconds)

    @property
    def orphan_after(self) -> timedelta:
        return timedelta(seconds=self.task_orphan_after_seconds)

    @property
    def decision_ttl(self) -> timedelta:
        return timedelta(seconds=self.decision_ttl_seconds)

    @property
    def assignment_ttl(self) -> timedelta:
        return timedelta(seconds=self.assignment_ttl_seconds)

    @property
    def node_poll(self) -> timedelta:
        return timedelta(seconds=self.node_poll_seconds)

    @property
    def assignment_cap(self) -> timedelta:
        return timedelta(seconds=self.assignment_max_seconds)

    @field_validator("notes_scope")
    @classmethod
    def _a_well_formed_scope(cls, value: str) -> str:
        """A scope ELA cannot compare a path against stops the start-up, it is not repaired.

        The same syntax the catalogue requires of every scope entry (ADR 0010 §5): relative, no
        empty segment, no ``.`` or ``..``, no backslash. A malformed one would either be refused
        later by ``check_capability`` — with a message about a capability, to somebody who wrote
        a variable — or, worse, compared against a path and never match.
        """
        if not is_valid_scope_entry(value):
            raise ValueError(
                f"ELA_NOTES_SCOPE must be a relative path with no empty, '.' or '..' segment "
                f"and no backslash, not {value!r} (spec §29: the scope is what makes "
                "workspace.write_note LOW)"
            )
        return value

    @model_validator(mode="after")
    def _no_retired_setting(self) -> CoreSettings:
        """A retired variable stops ELA at start-up and says why (ADR 0037 §15)."""
        refuse_retired(self, prefix="ELA_")
        return self

    @model_validator(mode="after")
    def _the_silence_fits(self) -> CoreSettings:
        """The TTL of an assignment fits the three durations it answers to (ADR 0038 §5, §9).

        In the form of ADR 0023 §5: what would make a setting lie, or make ``recover()`` fail a
        task whose work is still out, stops the start-up with the reason, naming both variables.
        """
        ttl = self.assignment_ttl_seconds
        if ttl > self.decision_ttl_seconds:
            raise ValueError(
                f"ELA_ASSIGNMENT_TTL_SECONDS ({ttl}) must be at most ELA_DECISION_TTL_SECONDS "
                f"({self.decision_ttl_seconds}): an offer never outlives its decision, so beyond "
                "it the setting would never count — and a setting that does not count lies"
            )
        if ttl >= self.task_orphan_after_seconds:
            raise ValueError(
                f"ELA_ASSIGNMENT_TTL_SECONDS ({ttl}) must be below "
                f"ELA_TASK_ORPHAN_AFTER_SECONDS ({self.task_orphan_after_seconds}): otherwise "
                "recover() could fail as an orphan a task whose work is still out on a node"
            )
        if ttl > self.assignment_max_seconds:
            raise ValueError(
                f"ELA_ASSIGNMENT_TTL_SECONDS ({ttl}) must be at most ELA_ASSIGNMENT_MAX_SECONDS "
                f"({self.assignment_max_seconds}): the cap of a piece of work cannot be shorter "
                "than its first stretch"
            )
        return self


DEFAULT_NODE_CORE_URL: Final = "http://127.0.0.1:8351"
"""Where a node looks for the Core when nobody said otherwise: this machine (M12.3, dec. C).

ADR 0037 §2 gives ELA two addresses — loopback for the command line, the tailnet for the nodes —
and declares that without a tailnet address "a node does not reach ELA". That is about a
**remote** node: the middleware classifies by identity and never by address (``api/security.py``
compares ``(method, path)``, and ``request.client`` does not appear in it), so a node on the same
machine as the Core reaches it on loopback exactly as the command line does. A node on another
machine sets this to the tailnet address, and then the constraint of ADR 0037 §2 is about it.
"""

DEFAULT_NODE_RETRY_SECONDS: Final = 5.0
"""How long a node waits before asking again when nobody answered at the address.

The CLI does not retry — ``Unreachable`` and exit 3 — and that is right for a command and wrong
for a node: a command is a question a person asked and is waiting for, a node is a process whose
whole job is to be there when the Core comes back. To be measured against a real node (dec. K.2).
"""

DEFAULT_NODE_RETRY_CEILING: Final = 60
"""How many refused connections in a row before a node stops instead of waiting forever.

A ceiling and not a flag, for the reason ADR 0023 §3 gives about TTLs: "a TTL without a ceiling is
a door that can be left open forever by writing a big number". A node that never gives up on a
Core that is never coming back is a process nobody will notice is useless.
"""


class NodeSettings(BaseSettings):
    """What a node reads from the environment, from ``ELA_NODE_*`` (M12.3).

    A section like every other, and it lives here rather than beside the node's code for the same
    reason all of them do: ``ela init`` writes ``.env.example`` from one list, and a variable ELA
    reads from somewhere else is a variable nobody documents. **The secret is not here** — it is in
    the node's state file, because an environment variable is visible in ``ps`` and lands in the
    shell's history, which is the reason ADR 0024 §2 gives for refusing ``--token``.
    """

    model_config = SettingsConfigDict(env_prefix="ELA_", env_file=".env", extra="ignore")

    node_core_url: Annotated[str, Field(min_length=1)] = DEFAULT_NODE_CORE_URL
    node_state_dir: Path = Path.home() / ".ela"
    """Where the node keeps its id and its secret: beside the database, never inside the workspace.

    The workspace is what §23 calls synchronised, and a secret in a folder something may one day
    sync leaves the machine without anybody having decided it (ADR 0029 §1, the same reason
    ``ELA_CAPTURE_DIR`` has).
    """
    node_name: Annotated[str, Field(min_length=1)] = Field(default_factory=platform.node)
    """What ``ela device list`` shows. The machine's own name by default, because a name a program
    invented is a name nobody recognises in a list of three."""
    node_performance: PerformanceClass = PerformanceClass.UNKNOWN
    """What the node claims of its own power, and it claims nothing by default.

    ``UNKNOWN`` is the only honest answer a node can give about itself without measuring: the fake
    node says ``HIGH`` because it is built to win on points, which is right for a fake and would be
    a pretension in a real one. A variable rather than a fixed ``UNKNOWN`` because dec. K.3 has to
    make this node win *and* lose to measure the weights of §17.
    """
    node_retry_seconds: Annotated[float, Field(gt=0)] = DEFAULT_NODE_RETRY_SECONDS
    node_retry_ceiling: Annotated[int, Field(gt=0)] = DEFAULT_NODE_RETRY_CEILING

    @property
    def node_retry_wait(self) -> timedelta:
        """How long to wait before asking again."""
        return timedelta(seconds=self.node_retry_seconds)


class Settings(BaseModel):
    """Everything ELA reads from the environment, in one immutable object (ADR 0023 §2).

    Not a ``BaseSettings`` itself: it reads *through* the eight, not instead of them, and each of
    them stays constructible on its own — which is what keeps the tests that know one piece
    working, and keeps every validation next to the code it protects.
    """

    model_config = ConfigDict(frozen=True)

    persistence: PersistenceSettings
    workspace: WorkspaceSettings
    devices: DeviceSettings
    anthropic: AnthropicSettings
    routing: RoutingSettings
    api: ApiSettings
    core: CoreSettings
    perception: PerceptionSettings
    captures: CaptureSettings
    voice: VoiceSettings
    listen: ListenSettings
    """What ELA hears (M11.2). A section of its own and not part of ``perception``: that one
    watches the machine, this one opens a device and holds the fingerprint of what transcribes
    it."""
    elevenlabs: ElevenLabsSettings
    """The online voice (M11.3). A section of its own and not part of ``voice``: one is a switch
    and a helper on this machine, the other is a credential, a supplier and a bill."""
    context: ContextSettings
    node: NodeSettings
    """What a node on this machine reads (M12.3). Held here so that ``.env.example`` and
    ``VARIABLES`` document it with everything else — the Core itself reads none of it."""

    @classmethod
    def load(cls) -> Settings:
        """Read the environment (and ``.env``) once; :class:`ConfigurationError` if it is wrong.

        The eleven are built here and nowhere else. A failure names the variable and what to do
        with it: whoever reads this message wrote the ``.env``, and a ``ValidationError`` dumped
        on a terminal is not an answer to them.

        The ``.env`` it reads is the one in the working directory, as every settings class of
        ELA already does: a test that must not see the developer's own runs from elsewhere.
        """
        try:
            return cls(
                persistence=PersistenceSettings(),
                workspace=WorkspaceSettings(),
                devices=DeviceSettings(),
                anthropic=AnthropicSettings(),
                routing=RoutingSettings(),
                api=ApiSettings(),
                core=CoreSettings(),
                perception=PerceptionSettings(),
                captures=CaptureSettings(),
                voice=VoiceSettings(),
                listen=ListenSettings(),
                elevenlabs=ElevenLabsSettings(),
                context=ContextSettings(),
                node=NodeSettings(),
            )
        except ValidationError as invalid:
            raise ConfigurationError(explain(invalid)) from invalid
        except SettingsError as unreadable:
            raise ConfigurationError(cannot_read(unreadable)) from unreadable


class NodeConfig(BaseModel):
    """What a **node** reads from the environment: five sections, and not the Core's thirteen.

    A node is not a small ELA. It opens no API, so ``ELA_API_TOKEN`` — which :meth:`Settings.load`
    refuses to start without, because "ELA does not open an unauthenticated API" — is not its
    business; it keeps no database, no workspace, no captures, and it places nothing, so none of
    those sections say anything about it. A node that loaded the Core's ``Settings`` would be a
    process stopped by a missing token it never uses, on a machine where nothing of the Core is
    configured, which on a second machine is the normal case and not the exception.

    The precedent is ``cli/client.py``'s, in its own words: *"``ela health`` must not refuse to
    answer because ``ELA_MODEL_ROUTES`` has a typo in it, since that line is not about the question
    being asked."* Here the question being asked is "run as a node", and the five sections below
    are what that needs: its own cycle, and the credentials of the four tools that travel.
    """

    model_config = ConfigDict(frozen=True)

    node: NodeSettings
    anthropic: AnthropicSettings
    """The key is the **node's**: the order carries the call, never the credentials (M12.1 D1).

    A key travelling inside a work order would be a secret of the Core's on a machine that is not
    its own, which is §57 read backwards.
    """
    routing: RoutingSettings
    """And it must agree with the Core's, or the verification of ``model.complete`` fails whatever
    the node answered: the verifier recomputes the route with the **Core's** router and compares
    the provider the node reports (M12.2 dec. L). On one machine the two are the same ``.env`` and
    nobody notices; on two machines it is the first thing that breaks."""
    voice: VoiceSettings
    elevenlabs: ElevenLabsSettings

    @classmethod
    def load(cls) -> NodeConfig:
        """Read the environment (and ``.env``) once; :class:`ConfigurationError` if it is wrong."""
        try:
            return cls(
                node=NodeSettings(),
                anthropic=AnthropicSettings(),
                routing=RoutingSettings(),
                voice=VoiceSettings(),
                elevenlabs=ElevenLabsSettings(),
            )
        except ValidationError as invalid:
            raise ConfigurationError(explain(invalid)) from invalid
        except SettingsError as unreadable:
            raise ConfigurationError(cannot_read(unreadable)) from unreadable


def explain(invalid: ValidationError) -> str:
    """A pydantic failure as one line per problem, each naming its ``ELA_`` variable.

    A whole-model check — the retired ``ELA_ANTHROPIC_MODEL`` is one — has no field to point at,
    and its own message already names what it is about: it is quoted as it stands.
    """
    lines = []
    for error in invalid.errors():
        message = error["msg"].removeprefix("Value error, ")
        location = error["loc"]
        lines.append(f"  {_variable(location)}: {message}" if location else f"  {message}")
    return "ELA is not configured:\n" + "\n".join(lines)


def cannot_read(unreadable: SettingsError) -> str:
    """A variable pydantic-settings could not parse at all — malformed JSON in a complex one.

    It is raised instead of a ``ValidationError`` and it talks about *fields*, so the field is
    turned back into the variable an operator actually set. Same voice as :func:`explain`: a
    configuration problem is a sentence, never a stack trace.
    """
    named = _FIELD.sub(lambda found: f'variable "{_variable((found.group(1),))}"', str(unreadable))
    return f"ELA is not configured:\n  {named.partition(' from source')[0]} (is it valid JSON?)"


def _variable(location: tuple[int | str, ...]) -> str:
    """The environment variable behind a field name: every settings class uses the prefix."""
    return "ELA_" + str(location[0]).upper()
