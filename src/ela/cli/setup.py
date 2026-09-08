"""``ela init``: the file ELA needs before it can start (ADR 0024 §8).

The second command that is not a client — there is no ELA to talk to yet — and the only one that
writes on this machine. What it writes is one file, ``.env``, with a token generated here and
**never printed**: a secret echoed to a terminal is a secret in the scrollback and in the shell
history. The mode is ``0600``.

It never overwrites an existing ``.env``. Overwriting one is losing a token and leaving an ELA
that does not restart, and "when in doubt, no" (§33) applies to a file as much as to an action:
on a file that is already there it *reports* — which variables ELA knows and this file does not
set — and touches nothing.

The directories are not created here. ``build`` already creates the database directory and the
workspace when ELA starts (ADR 0006 §3, ADR 0013 §12), and creating them here would mean naming
``ela.infrastructure`` from the CLI, which architecture rule 27 forbids and rule 28 would forbid
again. Two places that create the same directory is one place too many.
"""

from __future__ import annotations

import re
import secrets
from pathlib import Path
from typing import Final

import typer

from ela.cli.errors import CONFIGURATION, fail, handled

__all__ = ["ENV_FILE", "GENERATE_TOKEN", "TOKEN_BYTES", "TOKEN_VARIABLE", "VARIABLES", "init"]

ENV_FILE: Final = ".env"
TOKEN_VARIABLE: Final = "ELA_API_TOKEN"
TOKEN_BYTES: Final = 32
"""``secrets.token_urlsafe(32)`` is 43 characters: over the 32 the settings require."""
GENERATE_TOKEN: Final = 'python -c "import secrets; print(secrets.token_urlsafe(32))"'
"""What to run to make one by hand, for whoever has an ``.env`` already."""

ASSIGNED = re.compile(r"^\s*(ELA_\w+)\s*=", re.MULTILINE)
"""A variable a file actually sets. A commented line sets nothing."""

VARIABLES: tuple[tuple[str, str], ...] = (
    ("ELA_API_HOST", "127.0.0.1"),
    ("ELA_API_PORT", "8351"),
    ("ELA_USER_NAME", "user"),
    ("ELA_DB_URL", "sqlite:///<home>/.ela/ela.db"),
    ("ELA_WORKSPACE_DIR", "<home>/.ela/workspace"),
    ("ELA_DEVICE_HEARTBEAT_TTL_SECONDS", "60"),
    ("ELA_ANTHROPIC_API_KEY", ""),
    ("ELA_ANTHROPIC_TIMEOUT_SECONDS", "60"),
    ("ELA_ANTHROPIC_MAX_RETRIES", "2"),
    ("ELA_ANTHROPIC_MAX_OUTPUT_TOKENS", "4096"),
    ("ELA_MODEL_ROUTES", "the table of spec §25"),
    ("ELA_MODEL_DEFAULT_ROUTE", "the default route of spec §25"),
    ("ELA_AUTHORIZATION_TTL_SECONDS", "3600"),
    ("ELA_APPROVAL_TTL_SECONDS", "86400"),
    ("ELA_TASK_ORPHAN_AFTER_SECONDS", "900"),
    ("ELA_DECISION_TTL_SECONDS", "300"),
    ("ELA_NOTES_SCOPE", "workspace/notes"),
    ("ELA_PERCEPTION_ENABLED", "true"),
    ("ELA_PERCEPTION_LOOP_INTERVAL_SECONDS", "0"),
    ("ELA_PERCEPTION_SENSORS_INTERVAL_SECONDS", "2"),
    ("ELA_PERCEPTION_SESSION_INTERVAL_SECONDS", "5"),
    ("ELA_PERCEPTION_PERMISSIONS_INTERVAL_SECONDS", "30"),
    ("ELA_PERCEPTION_PROBE_TIMEOUT_SECONDS", "2.0"),
    ("ELA_CAPTURE_DIR", "<home>/.ela/captures"),
    ("ELA_CAPTURE_TTL_SECONDS", "300"),
    ("ELA_CAPTURE_MAX_COUNT", "20"),
    ("ELA_CAPTURE_MAX_BYTES", "209715200"),
    ("ELA_CAPTURE_TIMEOUT_SECONDS", "10.0"),
)
"""Every optional variable, with ELA's own default beside it.

The same list as ``.env.example``, and a documentation test keeps the two the same: a variable
added to ELA and not to both is a variable nobody discovers.
"""

HEADER = f"""\
# ELA — local configuration, written by `ela init`. Never commit this file.
#
# The token is the only variable ELA requires: without it the local API does not open.
{TOKEN_VARIABLE}=%s

# Everything below is optional, and shows the default ELA uses when it is not set.
"""


def template(token: str) -> str:
    """The whole ``.env`` as it is written the first time."""
    lines = [HEADER % token]
    lines.extend(f"# {name}={default}" for name, default in VARIABLES)
    return "\n".join(lines) + "\n"


def assigned(text: str) -> frozenset[str]:
    """The ``ELA_`` variables a file sets. What is commented out is not set."""
    return frozenset(ASSIGNED.findall(text))


@handled
def init() -> None:
    """Write the ``.env`` ELA needs, with a token of its own, in this directory."""
    env = Path(ENV_FILE)
    if env.exists():
        _report(env)
        return
    env.write_text(template(secrets.token_urlsafe(TOKEN_BYTES)), encoding="utf-8")
    env.chmod(0o600)
    typer.echo(
        f"wrote {ENV_FILE} (mode 600) with a fresh {TOKEN_VARIABLE}. It is not printed here: "
        f"read it from the file.\n"
        "next:\n"
        "  uv run alembic upgrade head   # ELA does not migrate on start-up (ADR 0006)\n"
        "  ela serve                     # ELA creates its database directory and workspace"
    )


def _report(env: Path) -> None:
    """Say what this ``.env`` does not set, and change nothing (the user's note on 6a)."""
    present = assigned(env.read_text(encoding="utf-8"))
    unset = [name for name, _ in VARIABLES if name not in present]
    typer.echo(f"{ENV_FILE} is already here: left untouched.")
    if unset:
        typer.echo(f"not set, so ELA uses its own default: {', '.join(unset)}")
    if TOKEN_VARIABLE not in present:
        fail(
            CONFIGURATION,
            f"{ENV_FILE} does not set {TOKEN_VARIABLE}, and ELA does not open an "
            f"unauthenticated API. Add one: {GENERATE_TOKEN}",
        )
    typer.echo(f"{TOKEN_VARIABLE} is set: nothing required is missing.")
