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
  that time it is forgotten and the vault is asked to lock — by a task of the door's own, because
  nobody may be calling —, and a use that comes later finds it closed, whoever did or did not
  close it;
* **every closing is told, with why** — a command, the hour, the stop of ELA, a key ended
  elsewhere — to whoever the composition names: in ELA, the audit. The key is forgotten first;
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
import shlex
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final
from urllib.parse import urlsplit

from ela.domain import Actor
from ela.ports import (
    VAULT_LOCKED,
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
    "BY_COMMAND",
    "BY_STOP",
    "BY_TIME",
    "CLOSING_REASONS",
    "ELSEWHERE",
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
    "VaultClosing",
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

BY_COMMAND: Final = "command"
"""Somebody asked: ``ela vault close``, or the console."""
BY_TIME: Final = "expired"
"""The hour of the key ran out."""
BY_STOP: Final = "stopped"
"""ELA stopped: the key is forgotten, and nothing is launched."""
ELSEWHERE: Final = "ended_elsewhere"
"""The vault said the key ELA held opens nothing any more: another unlock, a lock (K2)."""
CLOSING_REASONS: Final[frozenset[str]] = frozenset({BY_COMMAND, BY_TIME, BY_STOP, ELSEWHERE})

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
    ``forgets_at`` the instant ELA forgets the key, when it holds one that opens.

    ``message`` is what there is to do about it, empty for a vault that is open; ``opens_with``
    **the whole line to paste** in a terminal, for a vault that is locked and for no other
    (decision 32): composed with the declared program, never with a placeholder."""

    name: str
    forgets_at: datetime | None = None
    message: str = ""
    opens_with: str | None = None


@dataclass(frozen=True, slots=True)
class VaultClosing:
    """ELA stopped holding the key of the vault, or locked it on a command: ``reason`` is one of
    :data:`CLOSING_REASONS`; ``by`` who asked, ``None`` when nobody did; ``locked`` whether the
    vault's program was asked to lock and did; ``code`` why it was not, when a lock was due.
    Nothing of the vault is in here."""

    reason: str
    by: Actor | None
    locked: bool
    code: str | None


Closed = Callable[[VaultClosing], Awaitable[None]]
Wait = Callable[[float], Awaitable[None]]


async def _nobody_is_told(closing: VaultClosing) -> None:
    """Whoever builds a door without saying who is told of a closing: a test of something else."""


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
    """The vault, behind the identity of its program and the hour of its key.

    ``closed`` is told of every closing (:class:`VaultClosing`), after the key is forgotten;
    ``wait`` is how the hour is waited for — a sleep, and an event in a test."""

    def __init__(
        self,
        vault: Vault | None,
        program: str | None,
        at_start: Identity | None,
        *,
        clock: Clock,
        seconds: int = VAULT_OPEN_SECONDS,
        closed: Closed = _nobody_is_told,
        wait: Wait = asyncio.sleep,
    ) -> None:
        self._vault = vault
        self._program = program
        self._at_start = at_start
        self._clock = clock
        self._seconds = seconds
        self._closed = closed
        self._wait = wait
        self._opened_at: datetime | None = None
        self._watching: asyncio.Future[None] | None = None

    @classmethod
    async def fixed(
        cls,
        vault: Vault | None,
        program: str | None,
        *,
        clock: Clock,
        seconds: int = VAULT_OPEN_SECONDS,
        closed: Closed = _nobody_is_told,
        wait: Wait = asyncio.sleep,
    ) -> VaultDoor:
        """The door, with the identity of ``program`` read **now**, once, in a thread: the start
        of ELA, and nothing later."""
        at_start = None if program is None else await asyncio.to_thread(identity_of, program[1:])
        return cls(vault, program, at_start, clock=clock, seconds=seconds, closed=closed, wait=wait)

    @property
    def program(self) -> str | None:
        """The declared program, as it was written; ``None`` when nobody declared one."""
        return self._program

    @property
    def forgets_at(self) -> datetime | None:
        """When ELA forgets the key it holds; ``None`` when it holds none."""
        opened = self._opened_at
        return None if opened is None else opened + timedelta(seconds=self._seconds)

    def _opens_with(self) -> str:
        """The whole line to paste in a terminal (decision 32): the declared program, quoted as
        a shell wants a path with a space in it, and never a placeholder."""
        return f"{shlex.quote(self._program or '')} unlock --raw | ela vault open"

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
                LOCKED, f"the vault is locked: run `{self._opens_with()}` in your terminal"
            )
        return VaultProblem(TIMEOUT if isinstance(error, VaultTimeout) else FAILED, str(error))

    # The key --------------------------------------------------------------------------------

    async def open(self, key: Secret) -> VaultProblem | None:
        """Hand ELA the session key. It is kept only if the vault's program — the one of the
        start — says it opens the vault; otherwise it is forgotten, and the reason is said.
        **The hour starts here**, and the wait for its end with it."""
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
        self._unwatch()
        self._watching = asyncio.ensure_future(self._expiring())
        return None

    async def close(self, by: Actor | None = None) -> VaultProblem | None:
        """Forget the key and ask the vault to lock, on the command of ``by``. **With a program
        that changed or is gone the key is forgotten and nothing is run**: what would be launched
        is not the program ELA vouched for. Whatever is returned, the key is not held any more."""
        self._unwatch()
        return await self._close(BY_COMMAND, by)

    async def expire(self) -> bool:
        """Close the vault if the hour of the key is over; whether it was closed here. Asked at
        every use, on the clock: the wait below is not the only thing that ends the hour."""
        forgets_at = self.forgets_at
        if forgets_at is None or self._clock.now() < forgets_at:
            return False
        self._unwatch()
        await self._close(BY_TIME, None)
        return True

    async def stopped(self) -> None:
        """ELA is stopping: the key is forgotten **and nothing is launched** — a process started
        while ELA closes is one more thing to wait for. The wait of the hour is ended, and a
        closing of the keeper's own that was in flight is over when this returns: the loop is
        never torn down with a launch of the vault's program in flight."""
        watching = self._unwatch()
        if watching is not None:
            await asyncio.wait({watching})
        await self._forgotten(BY_STOP)

    def _unwatch(self) -> asyncio.Future[None] | None:
        watching, self._watching = self._watching, None
        if watching is not None:
            watching.cancel()
        return watching

    async def _expiring(self) -> None:
        """The keeper's own task (decision 33): at the end of the hour nobody may be calling.
        It does not end itself: whoever closes first ends this wait."""
        await self._wait(float(self._seconds))
        await self._close(BY_TIME, None)

    async def _close(self, reason: str, by: Actor | None) -> VaultProblem | None:
        held, self._opened_at = self._opened_at is not None, None
        vault = self._vault
        problem = await self._problem()
        locked = False
        if vault is not None:
            if problem is None:
                try:
                    await vault.lock()
                    locked = True
                except VaultError as error:
                    problem = self._said(error)
            if not locked:
                await vault.forget()
        if held or locked:
            code = None if problem is None else problem.code
            await self._closed(VaultClosing(reason, by, locked, code))
        return problem

    async def _forgotten(self, reason: str) -> None:
        """The key dropped without asking the vault anything, and told if one was held."""
        held, self._opened_at = self._opened_at is not None, None
        if self._vault is not None:
            await self._vault.forget()
        if held:
            await self._closed(VaultClosing(reason, None, False, None))

    async def state(self) -> VaultState:
        """What the vault is now: asked of the program, never remembered."""
        problem = await self._problem()
        if problem is not None:
            return VaultState(_STATES[problem.code], message=problem.message)
        assert self._vault is not None
        await self.expire()
        try:
            said = await self._vault.status()
        except VaultError as error:
            failed = self._said(error)
            return VaultState(_STATES[failed.code], message=failed.message)
        if said == VAULT_UNLOCKED:
            return VaultState(said, self.forgets_at)
        if self._opened_at is not None:
            # The key ELA held was ended elsewhere — another unlock, a lock —: it opens nothing.
            self._unwatch()
            await self._forgotten(ELSEWHERE)
        return VaultState(
            said,
            message=self._said(VaultNotOpen(said)).message,
            opens_with=self._opens_with() if said == VAULT_LOCKED else None,
        )

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
