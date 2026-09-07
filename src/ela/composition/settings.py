"""All of ELA's configuration, read in one place (spec §54 "Configuration"; ADR 0023 §2, §3).

Until M8.1 five ``BaseSettings`` classes shared the ``ELA_`` prefix and nobody read them together:
:class:`~ela.infrastructure.persistence.PersistenceSettings`,
:class:`~ela.tools.settings.WorkspaceSettings`, :class:`~ela.devices.settings.DeviceSettings`,
:class:`~ela.providers.anthropic.AnthropicSettings` and
:class:`~ela.routing.RoutingSettings`. What was scattered was never the *validation* — each piece
is checked next to the code that uses it, by the ADR that decided it — but the **point of
reading**. :meth:`Settings.load` is now that point, and the only one.

Two classes are new here, and hold what only a running ELA needs: :class:`ApiSettings` (the
token, the address) and :class:`CoreSettings` (who the user is, and the three durations the
Executive Core runs on). Both keep the ``ELA_`` prefix: one namespace, one ``.env``.
"""

from __future__ import annotations

import ipaddress
import re
from datetime import timedelta
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.exceptions import SettingsError

from ela.composition.errors import ConfigurationError
from ela.devices.settings import DeviceSettings
from ela.domain import NAME_MAX_LENGTH
from ela.executive import DEFAULT_APPROVAL_TTL, MAX_APPROVAL_TTL
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
from ela.routing import RoutingSettings
from ela.tools.settings import WorkspaceSettings

__all__ = [
    "DEFAULT_API_HOST",
    "DEFAULT_API_PORT",
    "DEFAULT_ORPHAN_AFTER_SECONDS",
    "DEFAULT_USER_NAME",
    "MIN_TOKEN_LENGTH",
    "ApiSettings",
    "CoreSettings",
    "Settings",
]

DEFAULT_API_HOST: Final = "127.0.0.1"
"""Loopback, and only loopback (ADR 0023 §7): ELA on the network is the story of the nodes."""
DEFAULT_API_PORT: Final = 8351
"""An uncommon port collides less with whatever else runs on a developer's machine."""
MIN_TOKEN_LENGTH: Final = 32
"""Short enough to type, long enough not to be guessed by whatever else runs on this machine."""
DEFAULT_USER_NAME: Final = "user"
DEFAULT_ORPHAN_AFTER_SECONDS: Final = 900
"""Fifteen minutes, and the reason is ``run`` being synchronous inside an HTTP request
(ADR 0023 §9): an EXECUTING task may legitimately stay silent for as long as a model call takes,
and a shorter default would fail a live task as an orphan on every restart."""

_FIELD = re.compile(r'field "(\w+)"')
"""How pydantic-settings names what it could not read: as a field, not as a variable."""

_SECONDS_IN_AUTHORIZATION_TTL: Final = int(MAX_AUTHORIZATION_TTL.total_seconds())
_SECONDS_IN_APPROVAL_TTL: Final = int(MAX_APPROVAL_TTL.total_seconds())
_SECONDS_IN_DECISION_TTL: Final = int(MAX_DECISION_TTL.total_seconds())


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

    @property
    def token(self) -> str:
        """The token as a string, for the one comparison that needs it."""
        assert self.api_token is not None  # the validator refuses anything else
        return self.api_token.get_secret_value()


class CoreSettings(BaseSettings):
    """Who the user is, the durations ELA runs on, and where a note may be written.

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

    user_name: Annotated[str, Field(min_length=1, max_length=NAME_MAX_LENGTH)] = DEFAULT_USER_NAME
    """``ELA_USER_NAME``: who signs an answer to a request for approval (§30, §62).

    One token, one identity (§2.1). It does **not** come from the request: a caller that named
    itself would write that name into the audit trail, which is what "who said yes" is read from
    later (§32). It goes away the day the nodes bring an authenticated identity (ADR 0023 §4)."""

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

    @classmethod
    def load(cls) -> Settings:
        """Read the environment (and ``.env``) once; :class:`ConfigurationError` if it is wrong.

        The eight are built here and nowhere else. A failure names the variable and what to do
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
