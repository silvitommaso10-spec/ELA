"""The vault as ELA's tools and routes reach it (M13.9, ADR 0063; decisions 15, 16, 28, 33, 42).

The passwords stay in the vault, and the vault's adapter is the only thing that launches its
program. Between the two stands :class:`VaultDoor`, in the gate, and it is what a tool and a route
hold:

* **the identity of the program** — the file the declared path leads to and the digest of what it
  holds (:class:`~ela.tools.programs.Identity`) — is fixed at the start and compared again
  **before every use**: it is the program that receives the key and gives back the passwords, and
  an update ELA did not see start does not receive them. A program that begins as a script is
  refused: what would be fixed is a launcher of a few lines (decision 42);
* **the key is kept for an hour from the opening**, never from its last use (decision 33): at
  that time it is forgotten and the vault is asked to lock — and a use that comes later finds it
  closed, whoever did or did not close it;
* **every refusal has a code of its own**, and a sentence that names the program to run and never
  an entry of the vault;
* **an entry is bound to a site by the equality of the host, compared here** — not by the vault's
  own match, which is by domain and does not look at the port (measured). The comparison runs
  before the question, on the listing, and again after the yes **on the very reading the password
  comes from** (decision 64).
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final
from urllib.parse import urlsplit

from ela.ports import (
    VAULT_UNAUTHENTICATED,
    VAULT_UNLOCKED,
    Clock,
    Secret,
    Vault,
    VaultEntry,
    VaultError,
    VaultNotOpen,
    VaultTaken,
    VaultTimeout,
)
from ela.tools.programs import Identity, identity_of

__all__ = [
    "ENTRY_AMBIGUOUS",
    "ENTRY_NOT_FOR_SITE",
    "FAILED",
    "KEY_REFUSED",
    "LOCKED",
    "NO_ENTRY",
    "NO_PASSWORD",
    "NO_PROGRAM",
    "PROGRAM_CHANGED",
    "PROGRAM_GONE",
    "PROGRAM_IS_A_SCRIPT",
    "TIMEOUT",
    "UNAUTHENTICATED",
    "UNDECLARED",
    "VAULT_CODES",
    "VAULT_OPEN_SECONDS",
    "VAULT_TIMEOUT_SECONDS",
    "VaultDoor",
    "VaultProblem",
    "VaultState",
    "host_of",
]

VAULT_TIMEOUT_SECONDS: Final = 15
"""How long one launch of the vault's program may take — a decision, against 2.5–3.1 s measured
with an account (decision 64): about five times the slowest."""
VAULT_OPEN_SECONDS: Final = 3600
"""How long ELA keeps the key, **from the opening**: an hour (decision 33). Logins are rare, and
«for as short as possible» is not eight hours."""

UNDECLARED: Final = "vault.undeclared"
"""``ELA_VAULT_PROGRAM`` is not set: ELA does not look for the vault's program in the ``PATH``."""
NO_PROGRAM: Final = "vault.no_program"
PROGRAM_CHANGED: Final = "vault.program_changed"
PROGRAM_GONE: Final = "vault.program_gone"
PROGRAM_IS_A_SCRIPT: Final = "vault.program_is_a_script"
"""The declared program begins with ``#!``: a launcher, not the code that receives the key."""
UNAUTHENTICATED: Final = "vault.unauthenticated"
LOCKED: Final = "vault.locked"
TIMEOUT: Final = "vault.timeout"
"""The vault's program did not answer within :data:`VAULT_TIMEOUT_SECONDS`."""
FAILED: Final = "vault.failed"
"""The vault's program could not be started, failed, or answered in a form ELA does not read."""
KEY_REFUSED: Final = "vault.key_refused"
"""The key handed to ELA does not open the vault: it is forgotten."""
NO_ENTRY: Final = "vault.no_entry"
ENTRY_AMBIGUOUS: Final = "vault.entry_ambiguous"
ENTRY_NOT_FOR_SITE: Final = "vault.entry_not_for_site"
NO_PASSWORD: Final = "vault.no_password"  # noqa: S105 — a code, not a password
VAULT_CODES: Final[frozenset[str]] = frozenset(
    {
        UNDECLARED,
        NO_PROGRAM,
        PROGRAM_CHANGED,
        PROGRAM_GONE,
        PROGRAM_IS_A_SCRIPT,
        UNAUTHENTICATED,
        LOCKED,
        TIMEOUT,
        FAILED,
        KEY_REFUSED,
        NO_ENTRY,
        ENTRY_AMBIGUOUS,
        ENTRY_NOT_FOR_SITE,
        NO_PASSWORD,
    }
)

SCRIPT: Final = b"#!"
HOST: Final = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*")
"""What a host is once it is plain: labels of letters, digits and hyphens, joined by dots."""
HTTPS: Final = "https"
HTTPS_PORT: Final = 443
_STATES: Final = {
    UNDECLARED: "undeclared",
    NO_PROGRAM: "no_program",
    PROGRAM_CHANGED: "changed",
    PROGRAM_GONE: "gone",
    PROGRAM_IS_A_SCRIPT: "is_a_script",
    TIMEOUT: "timeout",
    FAILED: "failed",
}


@dataclass(frozen=True, slots=True)
class VaultProblem:
    """Why the vault did not give what it was asked for: a code, and a sentence that names the
    program to run when there is something to do — never an entry, its id or its name."""

    code: str
    message: str


@dataclass(frozen=True, slots=True)
class VaultState:
    """What the vault is now, asked and never remembered: ``name`` is one of ``undeclared``,
    ``no_program``, ``changed``, ``gone``, ``is_a_script``, ``unauthenticated``, ``locked``,
    ``unlocked`` — or ``timeout`` and ``failed`` for a program that did not say —, and
    ``forgets_at`` the instant ELA forgets the key, when it holds one that opens."""

    name: str
    forgets_at: datetime | None = None


def host_of(address: str) -> str | None:
    """The host an entry's address is for, or ``None`` if the address does not count.

    It counts only if it is ``https``, with no user and no password before the host, on the
    default port; the host is compared in lower case, in the ASCII form of an international name,
    without a final dot. **What does not read as an address matches nothing.** Stricter than the
    vault itself on purpose (decision 15c).
    """
    try:
        parts = urlsplit(address)
        port = parts.port
        host = parts.hostname
    except ValueError:
        return None
    if parts.scheme != HTTPS or parts.username is not None or parts.password is not None:
        return None
    if port not in (None, HTTPS_PORT) or not host:
        return None
    try:
        plain = host.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None
    return plain if HOST.fullmatch(plain) else None


def _hosts(addresses: tuple[str, ...]) -> frozenset[str]:
    return frozenset(host for host in map(host_of, addresses) if host is not None)


class VaultDoor:
    """The vault, behind the identity of its program and the hour of its key."""

    def __init__(
        self,
        vault: Vault | None,
        program: str | None,
        at_start: Identity | None,
        *,
        clock: Clock,
        seconds: int = VAULT_OPEN_SECONDS,
    ) -> None:
        self._vault = vault
        self._program = program
        self._at_start = at_start
        self._clock = clock
        self._seconds = seconds
        self._opened_at: datetime | None = None

    @classmethod
    async def fixed(
        cls,
        vault: Vault | None,
        program: str | None,
        *,
        clock: Clock,
        seconds: int = VAULT_OPEN_SECONDS,
    ) -> VaultDoor:
        """The door, with the identity of ``program`` read **now**, once, in a thread: the start
        of ELA, and nothing later."""
        at_start = None if program is None else await asyncio.to_thread(identity_of, program[1:])
        return cls(vault, program, at_start, clock=clock, seconds=seconds)

    # The program ----------------------------------------------------------------------------

    def _looked(self) -> VaultProblem | None:
        """Why the program is not the one to launch now, or ``None`` if it is. Read from the disk
        at every call: this is the «before every use»."""
        program, start = self._program, self._at_start
        if program is None or start is None:
            return VaultProblem(
                UNDECLARED,
                "ELA_VAULT_PROGRAM is not set: write in the .env the absolute path of the "
                "vault's program (bw), and restart ELA",
            )
        now = identity_of(program[1:])
        if now.runs is None and start.executable:
            return VaultProblem(
                PROGRAM_GONE, f"{program!r} was there when ELA started and is not there now"
            )
        if not now.executable:
            return VaultProblem(
                NO_PROGRAM, f"{program!r} is not there, does not execute, or cannot be read"
            )
        if now != start:
            return VaultProblem(
                PROGRAM_CHANGED,
                f"{program!r} changed after ELA started (an update, for instance): restart ELA "
                "to accept it",
            )
        if _begins_as_a_script(start.runs):
            return VaultProblem(
                PROGRAM_IS_A_SCRIPT,
                f"{program!r} begins with #!: it is a launcher, not the program that receives "
                "the key. Declare the native program of the vault",
            )
        return None

    async def _problem(self) -> VaultProblem | None:
        return await asyncio.to_thread(self._looked)

    def _said(self, error: VaultError) -> VaultProblem:
        """A failure of the vault's adapter, with its code and what to do about it."""
        if isinstance(error, VaultNotOpen):
            if error.state == VAULT_UNAUTHENTICATED:
                return VaultProblem(
                    UNAUTHENTICATED,
                    "no account is signed in to the vault on this machine: run "
                    f"`{self._program} login` in your terminal",
                )
            return VaultProblem(
                LOCKED,
                f"the vault is locked: run `{self._program} unlock --raw | ela vault open` in "
                "your terminal",
            )
        return VaultProblem(TIMEOUT if isinstance(error, VaultTimeout) else FAILED, str(error))

    # The key --------------------------------------------------------------------------------

    def _forgets_at(self) -> datetime | None:
        opened = self._opened_at
        return None if opened is None else opened + timedelta(seconds=self._seconds)

    async def open(self, key: Secret) -> VaultProblem | None:
        """Hand ELA the session key. It is kept only if the vault's program — the one of the
        start — says it opens the vault; otherwise it is forgotten, and the reason is said."""
        problem = await self._problem()
        if problem is not None:
            return problem
        assert self._vault is not None
        try:
            opens = await self._vault.unlock(key)
        except VaultError as error:
            return self._said(error)
        if not opens:
            return VaultProblem(KEY_REFUSED, "that key does not open the vault: it was forgotten")
        self._opened_at = self._clock.now()
        return None

    async def close(self) -> VaultProblem | None:
        """Forget the key and ask the vault to lock. **With a program that changed or is gone the
        key is forgotten and nothing is run**: what would be launched is not the program ELA
        vouched for. Whatever is returned, the key is not held any more."""
        self._opened_at = None
        vault = self._vault
        problem = await self._problem()
        if vault is None:
            return problem
        if problem is not None:
            await vault.forget()
            return problem
        try:
            await vault.lock()
        except VaultError as error:
            await vault.forget()
            return self._said(error)
        return None

    async def expire(self) -> bool:
        """Close the vault if the hour of the key is over; whether it was closed here."""
        forgets_at = self._forgets_at()
        if forgets_at is None or self._clock.now() < forgets_at:
            return False
        await self.close()
        return True

    async def state(self) -> VaultState:
        """What the vault is now: asked of the program, never remembered."""
        problem = await self._problem()
        if problem is not None:
            return VaultState(_STATES[problem.code])
        assert self._vault is not None
        await self.expire()
        try:
            said = await self._vault.status()
        except VaultError as error:
            return VaultState(_STATES[self._said(error).code])
        if said != VAULT_UNLOCKED and self._opened_at is not None:
            # The key ELA held was ended elsewhere — another unlock, a lock —: it opens nothing.
            self._opened_at = None
            await self._vault.forget()
        return VaultState(said, self._forgets_at() if said == VAULT_UNLOCKED else None)

    # The entry ------------------------------------------------------------------------------

    async def find(self, site: str, wanted: str | None = None) -> VaultEntry | VaultProblem:
        """**Before the question**: the entry of the vault for ``site`` — the one ``wanted`` names
        by its id, or the only one whose host is the site —, without any value; or why not."""
        problem = await self._problem()
        if problem is not None:
            return problem
        assert self._vault is not None
        await self.expire()
        try:
            listed = await self._vault.find(f"{HTTPS}://{site}")
        except VaultError as error:
            return self._said(error)
        return _chosen(site, listed, wanted)

    async def take(self, site: str, entry: str) -> VaultTaken | VaultProblem:
        """**After the yes**: read ``entry`` once, compare it again with ``site`` on that very
        reading, and give what is typed; or why not — and then nothing was given."""
        problem = await self._problem()
        if problem is not None:
            return problem
        assert self._vault is not None
        await self.expire()
        try:
            taken = await self._vault.take(entry)
        except VaultError as error:
            return self._said(error)
        if site not in _hosts(taken.addresses):
            return VaultProblem(
                ENTRY_NOT_FOR_SITE,
                f"the entry of the vault is not for {site} any more: nothing was typed",
            )
        return taken


def _chosen(
    site: str, listed: tuple[VaultEntry, ...], wanted: str | None
) -> VaultEntry | VaultProblem:
    """The entry for ``site`` among ``listed``, by the equality of the host. A refusal names the
    site and never an entry."""
    if wanted is not None:
        named = [entry for entry in listed if entry.id == wanted]
        if not named:
            return VaultProblem(NO_ENTRY, f"the vault has no such entry for {site}")
        if site not in _hosts(named[0].addresses):
            return VaultProblem(
                ENTRY_NOT_FOR_SITE, f"that entry of the vault is not for {site}: it is not used"
            )
        chosen = named[0]
    else:
        matching = [entry for entry in listed if site in _hosts(entry.addresses)]
        if not matching:
            return VaultProblem(NO_ENTRY, f"the vault has no entry whose address is https://{site}")
        if len(matching) > 1:
            return VaultProblem(
                ENTRY_AMBIGUOUS,
                f"the vault has more than one entry for {site}: name one with `entry`",
            )
        chosen = matching[0]
    if not chosen.has_password:
        return VaultProblem(NO_PASSWORD, f"the entry of the vault for {site} has no password")
    return chosen


def _begins_as_a_script(path: str | None) -> bool:
    """Whether the file at ``path`` begins with ``#!``. One that cannot be read now is not said
    to be a script: the launch itself will say what became of it."""
    try:
        with open(path or "", "rb") as handle:  # noqa: PTH123 — a read of two bytes
            return handle.read(len(SCRIPT)) == SCRIPT
    except OSError:
        return False
