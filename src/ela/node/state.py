"""What a node keeps on disk: the id the Core minted and the secret it presents (M12.3 dec. B).

Two fields, and the choice of which two is the decision. The Core minted both, once, and neither
ever changes; everything about a node that *does* change — its revision above all — is a fact of
the Core's row, and the node asks for it (``GET /nodes/me``, dec. L). A copy of a changing fact on
a second machine is a cache nobody resynchronises, and a node that believes a stale revision is a
node in ``412`` with nothing able to take it out of there.

**Not the Keychain**, and that was measured rather than argued (2026-09-12, macOS 26.6). Six probes:
the same interpreter reads its own entry with no dialog even from a path it has never been at, while
``/usr/bin/security`` and a freshly ad-hoc-signed binary are stopped by one. What the ACL recognises
is the *code identity* — the ``cdhash`` — so every update of the interpreter would make the secret
unreadable, behind a dialog a background process has nobody to show it to. It is the same wall
ADR 0029 §16 already found for TCC, reached by another road, and it comes down once: with a signed
executable of ELA's own, together with ``launchd``.

**Not an environment variable** either, for the reason ADR 0024 §2 gives about ``--token``: it would
be visible in ``ps`` and land in the shell's history.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

__all__ = [
    "DIRECTORY_MODE",
    "STATE_FILE",
    "STATE_MODE",
    "NodeIdentity",
    "read_identity",
    "write_identity",
]

STATE_FILE: Final = "node.json"
"""Beside the database and never inside the workspace (ADR 0029 §1, the reason ``ELA_CAPTURE_DIR``
has): the workspace is what §23 calls synchronised, and a secret in a folder something may one day
sync leaves the machine without anybody having decided it."""

STATE_MODE: Final = 0o600
DIRECTORY_MODE: Final = 0o700

SECRET_HIDDEN: Final = "<hidden>"
"""What ``repr`` shows instead of the secret, so a traceback cannot print it (ADR 0024 §8)."""


@dataclass(frozen=True, slots=True)
class NodeIdentity:
    """Who this node is. The secret is never in ``repr``, because tracebacks are printed."""

    device_id: str
    secret: str

    def __repr__(self) -> str:
        return f"NodeIdentity(device_id={self.device_id!r}, secret={SECRET_HIDDEN!r})"

    @property
    def bearer(self) -> str:
        """``<id>.<secret>``: the credential of a node, as ``api/security.py`` splits it."""
        return f"{self.device_id}.{self.secret}"


def state_path(directory: Path) -> Path:
    return directory / STATE_FILE


def read_identity(directory: Path) -> NodeIdentity | None:
    """The identity this machine enrolled with, or ``None`` if it never did.

    ``None`` and not an exception: "this node has not enrolled yet" is the normal first run, and it
    is the caller — the command — that knows whether a ``--join`` was offered to fix it.
    """
    path = state_path(directory)
    if not path.is_file():
        return None
    kept: Any = json.loads(path.read_text(encoding="utf-8"))
    return NodeIdentity(device_id=str(kept["device_id"]), secret=str(kept["secret"]))


def write_identity(directory: Path, identity: NodeIdentity) -> None:
    """Write the identity once, ``0o600`` from the first byte, and refuse to overwrite one.

    ``O_EXCL`` is the whole point and not a precaution: a second enrollment over a file that is
    already there would throw away an identity the Core still has a row for, leaving a node nobody
    can revoke because nobody can name it. It fails with :class:`FileExistsError` instead.

    The mode is exact **before a byte is written**, which is why the ``fchmod`` is there and not a
    ``chmod`` afterwards: the creation mode can only be narrowed by the process umask, so a file
    written and then narrowed carries that umask for an instant — which is the bug ADR 0037 §7
    records ``ela init`` having had ("``ela init`` wrote ``.env`` and then changed its mode"). And
    ``O_NOFOLLOW`` so the path cannot be pointed somewhere else by a symlink planted first.
    """
    directory.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(state_path(directory), flags, STATE_MODE)
    os.fchmod(descriptor, STATE_MODE)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump({"device_id": identity.device_id, "secret": identity.secret}, handle)
        handle.write("\n")
