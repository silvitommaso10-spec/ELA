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

import os
import re
import secrets
from pathlib import Path
from typing import Final

import typer

from ela.cli.errors import CONFIGURATION, fail, handled

__all__ = [
    "ENV_FILE",
    "GENERATE_TOKEN",
    "REQUIRED",
    "TOKEN_BYTES",
    "TOKEN_VARIABLE",
    "VARIABLES",
    "init",
]

ENV_FILE: Final = ".env"
TOKEN_VARIABLE: Final = "ELA_API_TOKEN"
TOKEN_BYTES: Final = 32
"""``secrets.token_urlsafe(32)`` is 43 characters: over the 32 the settings require."""
GENERATE_TOKEN: Final = 'python -c "import secrets; print(secrets.token_urlsafe(32))"'
"""What to run to make one by hand, for whoever has an ``.env`` already."""

ASSIGNED = re.compile(r"^\s*(ELA_\w+)\s*=", re.MULTILINE)
"""A variable a file actually sets. A commented line sets nothing."""

REQUIRED: tuple[tuple[str, str], ...] = (
    ("ELA_FS_ROOT", "/Users/you/Documents"),
    ("ELA_FS_SCOPE", "ELA"),
    ("ELA_TERMINAL_PROGRAMS", "[]"),
)
"""The variables ELA cannot start without, beside the token, each with an **example** — not a
default: ELA has none for them, and it does not choose the user's folder (M13.1, ADR 0045) nor what
may run on the user's machine (M13.2, ADR 0047). The example of ``ELA_TERMINAL_PROGRAMS`` is ``[]``,
which is an admitted answer — «no program» — and not a program ELA picked.

Until M13.1b they sat among the optional ones, and ``init`` said the token was «the only variable
ELA requires» about an ``.env`` ELA would refuse. The list is not compared with another list:
``tests/cli/test_init.py`` writes what ``init`` writes plus these lines and asks
``Settings.load()`` whether ELA would start, and without each one of them whether it would not
(ADR 0046). A variable that becomes required and is not here makes that test fail.
"""

VARIABLES: tuple[tuple[str, str], ...] = (
    ("ELA_API_HOST", "127.0.0.1"),
    ("ELA_API_PORT", "8351"),
    ("ELA_API_TAILNET_HOST", ""),
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
    ("ELA_ASSIGNMENT_TTL_SECONDS", "120"),
    ("ELA_ASSIGNMENT_MAX_SECONDS", "3600"),
    ("ELA_NODE_POLL_SECONDS", "25"),
    ("ELA_NOTES_SCOPE", "workspace/notes"),
    ("ELA_PERCEPTION_ENABLED", "true"),
    ("ELA_PERCEPTION_LOOP_INTERVAL_SECONDS", "0"),
    ("ELA_PERCEPTION_SENSORS_INTERVAL_SECONDS", "2"),
    ("ELA_PERCEPTION_APPLICATIONS_INTERVAL_SECONDS", "2"),
    ("ELA_PERCEPTION_SESSION_INTERVAL_SECONDS", "5"),
    ("ELA_PERCEPTION_PERMISSIONS_INTERVAL_SECONDS", "30"),
    ("ELA_PERCEPTION_PROBE_TIMEOUT_SECONDS", "2.0"),
    ("ELA_CAPTURE_DIR", "<home>/.ela/captures"),
    ("ELA_CAPTURE_TTL_SECONDS", "300"),
    ("ELA_CAPTURE_MAX_COUNT", "20"),
    ("ELA_CAPTURE_MAX_BYTES", "209715200"),
    ("ELA_CAPTURE_TIMEOUT_SECONDS", "5.0"),
    ("ELA_OCR_TIMEOUT_SECONDS", "10.0"),
    ("ELA_OCR_LANGUAGES", "it-IT,en-US"),
    ("ELA_VOICE_ENABLED", "true"),
    ("ELA_VOICE_NAME", "Alice"),
    ("ELA_VOICE_TIMEOUT_SECONDS", "60.0"),
    ("ELA_LISTEN_ENABLED", "true"),
    ("ELA_LISTEN_LANGUAGE", "it"),
    ("ELA_STT_BINARY", ""),
    ("ELA_STT_MODEL", ""),
    ("ELA_STT_BINARY_SHA256", ""),
    ("ELA_STT_MODEL_SHA256", ""),
    ("ELA_STT_TIMEOUT_SECONDS", "30.0"),
    ("ELA_ELEVENLABS_API_KEY", ""),
    ("ELA_ELEVENLABS_VOICE_ID", ""),
    ("ELA_ELEVENLABS_MODEL", "eleven_flash_v2_5"),
    ("ELA_ELEVENLABS_TIMEOUT_SECONDS", "15.0"),
    ("ELA_ELEVENLABS_MAX_RETRIES", "1"),
    ("ELA_NTFY_TOPIC", ""),
    ("ELA_NTFY_URL", "https://ntfy.sh"),
    ("ELA_NTFY_TIMEOUT_SECONDS", "5.0"),
    ("ELA_CONTEXT_TASKS_LIMIT", "20"),
    ("ELA_CONTEXT_DEADLINES_LIMIT", "10"),
    ("ELA_CONTEXT_EVENTS_LIMIT", "10"),
    ("ELA_TERMINAL_TIMEOUT_SECONDS", "120"),
    ("ELA_TERMINAL_OUTPUT_MAX_BYTES", "65536"),
    ("ELA_NODE_CORE_URL", "http://127.0.0.1:8351"),
    ("ELA_NODE_STATE_DIR", "<home>/.ela"),
    ("ELA_NODE_NAME", "the machine's own name"),
    ("ELA_NODE_PERFORMANCE", "UNKNOWN"),
    ("ELA_NODE_RETRY_SECONDS", "5.0"),
    ("ELA_NODE_RETRY_CEILING", "60"),
)
"""Every optional variable, with ELA's own default beside it — the required ones are in
:data:`REQUIRED`.

The same list as ``.env.example``, and a documentation test keeps the two the same: a variable
added to ELA and not to both is a variable nobody discovers.
"""

HEADER = f"""\
# ELA — local configuration, written by `ela init`. Never commit this file.
#
# The token: without it the local API does not open.
{TOKEN_VARIABLE}=%s

# Required, with no default: ELA does not start until these lines are written. The values are
# examples — write your own, and remove the `#`. ELA_TERMINAL_PROGRAMS is one line of JSON, each
# program relative to / (usr/bin/git is /usr/bin/git), and [] means no program at all.
"""

OPTIONAL_HEADER = """
# Everything below is optional, and shows the default ELA uses when it is not set.
"""


def template(token: str) -> str:
    """The whole ``.env`` as it is written the first time."""
    lines = [HEADER % token]
    lines.extend(f"# {name}={example}" for name, example in REQUIRED)
    lines.append(OPTIONAL_HEADER)
    lines.extend(f"# {name}={default}" for name, default in VARIABLES)
    return "\n".join(lines) + "\n"


def assigned(text: str) -> frozenset[str]:
    """The ``ELA_`` variables a file sets. What is commented out is not set."""
    return frozenset(ASSIGNED.findall(text))


ENV_MODE: Final = 0o600
"""The only mode ``.env`` ever has — from its first byte, not after a ``chmod``.

Created with this mode, the file can only be *narrower* than it (the umask removes bits, never
adds them); ``fchmod`` on the descriptor then makes it exactly this, before a byte is written. The
shape is ``tools/notes.py``'s. Written and then narrowed, the file would carry the process umask
for an instant, with the token already inside (M12.1, criterio 16).
"""

ENV_FLAGS: Final = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
"""``O_EXCL`` closes the gap between the ``exists()`` check and the creation: a file that
appeared in between is refused instead of overwritten."""


@handled
def init() -> None:
    """Write the ``.env`` ELA needs, with a token of its own, in this directory."""
    env = Path(ENV_FILE)
    if env.exists():
        _report(env)
        return
    descriptor = os.open(env, ENV_FLAGS, ENV_MODE)
    os.fchmod(descriptor, ENV_MODE)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(template(secrets.token_urlsafe(TOKEN_BYTES)))
    typer.echo(
        f"wrote {ENV_FILE} (mode 600) with a fresh {TOKEN_VARIABLE}. It is not printed here: "
        f"read it from the file.\n"
        "next:\n"
        f"  write {_names(REQUIRED)} in {ENV_FILE}   # no default, and no start without\n"
        "  uv run alembic upgrade head   # ELA does not migrate on start-up (ADR 0006)\n"
        "  ela serve                     # ELA creates its database directory and workspace"
    )


NOTES: Final = {
    "ELA_FS_ROOT": "\nThe folder is yours: ELA does not create it and does not choose it.",
    "ELA_TERMINAL_PROGRAMS": (
        "\nThe programs are one line of JSON, each relative to / — usr/bin/git is /usr/bin/git —, "
        "and [] is an answer: no program at all."
    ),
}
"""What a missing required line needs said beside its example, once (M13.2)."""


def _names(variables: tuple[tuple[str, str], ...] | list[tuple[str, str]]) -> str:
    """``A``, ``A and B``, ``A, B and C``: names a person reads, not a chain of «and»."""
    names = [name for name, _ in variables]
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def _report(env: Path) -> None:
    """Say what this ``.env`` does not set, and change nothing (the user's note on 6a).

    What ELA cannot start without is a configuration failure, exit ``2``: the token, and since
    M13.1b the lines of :data:`REQUIRED` too — a file ELA would refuse is not a file with
    «nothing required missing», and they have no default to be listed beside.
    """
    present = assigned(env.read_text(encoding="utf-8"))
    unset = [name for name, _ in VARIABLES if name not in present]
    missing = [(name, example) for name, example in REQUIRED if name not in present]
    typer.echo(f"{ENV_FILE} is already here: left untouched.")
    if unset:
        typer.echo(f"not set, so ELA uses its own default: {', '.join(unset)}")
    if TOKEN_VARIABLE not in present:
        fail(
            CONFIGURATION,
            f"{ENV_FILE} does not set {TOKEN_VARIABLE}, and ELA does not open an "
            f"unauthenticated API. Add one: {GENERATE_TOKEN}",
        )
    if missing:
        lines = "".join(f"\n    {name}={example}" for name, example in missing)
        notes = "".join(NOTES[name] for name, _ in missing if name in NOTES)
        one = len(missing) == 1
        fail(
            CONFIGURATION,
            f"{ENV_FILE} does not set {_names(missing)}, and ELA does not start without "
            f"{'it' if one else 'them'}: {'it has' if one else 'they have'} no default. Write "
            f"{'it' if one else 'them'}, for example:{lines}{notes}",
        )
    typer.echo(f"{TOKEN_VARIABLE} and {_names(REQUIRED)} are set: nothing required is missing.")
