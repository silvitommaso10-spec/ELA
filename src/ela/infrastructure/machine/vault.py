"""The vault: the CLI of Bitwarden as a child process, and the one session key ELA holds (M13.9,
ADR 0063; decisions 16, 28, 31 and 64).

Implements :class:`~ela.ports.Vault`. The passwords stay in the vault: this adapter launches the
vault's own program — ``bw``, at the path the user declared and whose identity the tools fixed —
for **a closed list of commands**, :data:`COMMANDS`, and reads what it prints.

**What a child receives**: the closed environment the composition hands this adapter, plus
``BW_NOINTERACTION`` — ``bw`` never asks anything inside ELA — and, when there is one, the session
key in ``BW_SESSION``. Never in ``argv``: ``--session`` is not an argument this module composes.
Its stdin is the end of a file; its stderr goes nowhere. It is the leader of a group of its own,
and is killed with it when it does not answer in time or when nobody waits for it any more.

**What leaves this module.** Before a yes, :meth:`BitwardenVault.find`: the id of an entry, its
name, its addresses, its username **masked**, and whether it has a password — every value is
dropped here, with the rest of what ``bw`` printed. After a yes, :meth:`BitwardenVault.take`: the
addresses, and the username and the password inside a :class:`~ela.ports.Secret`. **The output of
``bw`` never enters an exception**, its own or one it would be chained to: an error names the
command, and is raised once nothing that was read is in scope.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
from collections.abc import Mapping
from typing import Any, Final

from ela.ports import (
    VAULT_LOCKED,
    VAULT_UNAUTHENTICATED,
    VAULT_UNLOCKED,
    Secret,
    VaultEntry,
    VaultFailed,
    VaultNotOpen,
    VaultTaken,
    VaultTimeout,
)

__all__ = ["COMMANDS", "BitwardenVault", "masked"]

STATUS: Final = ("status",)
LIST: Final = ("list", "items", "--url")
ITEM: Final = ("get", "item")
LOCK: Final = ("lock",)
COMMANDS: Final = (STATUS, LIST, ITEM, LOCK)
"""Every command this adapter composes, each followed at most by one value: the address of a site
for the listing, the id of an entry for the reading (decision 64 — one reading, in place of ``get
username`` and ``get password``). Never ``unlock``, ``login``, ``export``, ``get totp``, ``get
uri``, ``serve`` or ``sync``: ELA reads the copy of the vault this machine has."""

NO_INTERACTION: Final = "BW_NOINTERACTION"
SESSION: Final = "BW_SESSION"
NEVER: Final = 5
"""How Bitwarden marks an address its owner said never to match: such an address is not one of
the entry's, for ELA either."""
STATES: Final = frozenset({VAULT_UNAUTHENTICATED, VAULT_LOCKED, VAULT_UNLOCKED})
_UNREADABLE: Final = object()


def masked(username: str) -> str:
    """A username as a question may show it (decision 31): its first character, and for an address
    what follows the at sign. A name of one character does not show even that.

    **A name that begins with the at sign is a handle, not an address**: what follows the sign
    is the whole of it, and is not shown (re-read of 2026-10-11)."""
    if not username:
        return ""
    local, at, domain = username.rpartition("@")
    if not at or not local:
        local, at, domain = username, "", ""
    shown = local[0] if len(local) > 1 else ""
    return f"{shown}…{at}{domain}"


class BitwardenVault:
    """``bw`` at ``program``, launched with ``environment`` and never for longer than
    ``timeout_seconds`` — and the session key, kept in memory inside a ``Secret``, nowhere else."""

    def __init__(
        self, program: str, *, environment: Mapping[str, str], timeout_seconds: float = 15.0
    ) -> None:
        self._program = program
        self._environment = dict(environment)
        self._timeout = timeout_seconds
        self._key: Secret | None = None

    # The key -------------------------------------------------------------------------------

    async def status(self) -> str:
        return await self._status(self._key)

    async def unlock(self, key: Secret) -> bool:
        if await self._status(key) != VAULT_UNLOCKED:
            return False
        self._key = key
        return True

    async def lock(self) -> None:
        key, self._key = self._key, None
        code, _ = await self._run(LOCK, key=key)
        if code != 0:
            raise VaultFailed("bw lock failed")

    async def forget(self) -> None:
        self._key = None

    # Before a yes ---------------------------------------------------------------------------

    async def find(self, address: str) -> tuple[VaultEntry, ...]:
        state = await self._status(self._key)
        if state != VAULT_UNLOCKED:
            raise VaultNotOpen(state)
        code, printed = await self._run(LIST, address, key=self._key)
        if code != 0:
            raise VaultFailed("bw list items failed")
        found = _entries(_read(printed, "list items"))
        del printed  # every password of the listing was in there
        if found is None:
            raise VaultFailed("bw list items did not print a list of entries")
        return found

    # After a yes ----------------------------------------------------------------------------

    async def take(self, entry: str) -> VaultTaken:
        code, printed = await self._run(ITEM, entry, key=self._key)
        if code != 0:
            del printed
            # Asked only now, when the reading failed: why — a vault that was locked in between
            # is «locked», anything else is that the entry could not be read.
            state = await self._status(self._key)
            if state != VAULT_UNLOCKED:
                raise VaultNotOpen(state)
            raise VaultFailed("bw get item failed: no such entry, or it could not be read")
        taken = _taken(_read(printed, "get item"))
        del printed
        if taken is None:
            raise VaultFailed("bw get item printed an entry with no password to take")
        return taken

    # The process ----------------------------------------------------------------------------

    async def _status(self, key: Secret | None) -> str:
        code, printed = await self._run(STATUS, key=key)
        if code != 0:
            raise VaultFailed("bw status failed")
        said = _read(printed, "status")
        state = said.get("status") if isinstance(said, dict) else None
        del said, printed  # the account's address was in there: it goes no further
        if not isinstance(state, str) or state not in STATES:
            raise VaultFailed("bw status did not say whether the vault is open")
        return state

    async def _run(
        self, command: tuple[str, ...], *value: str, key: Secret | None
    ) -> tuple[int, bytes]:
        environment = {**self._environment, NO_INTERACTION: "true"}
        if key is not None:
            environment[SESSION] = key.reveal()
        said = " ".join(command)
        refused: str | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                self._program,
                *command,
                *value,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=environment,
                start_new_session=True,
            )
        except (OSError, ValueError) as error:
            # A ``ValueError`` is Python's, before any process exists: a NUL in the key or in the
            # value, which no environment and no argument can carry. Its name, and never its text.
            refused = type(error).__name__
        finally:
            del environment
        if refused is not None:
            raise VaultFailed(f"bw could not be started ({refused})")
        answered = False
        printed = b""
        try:
            printed, _ = await asyncio.wait_for(process.communicate(), self._timeout)
            answered = True
        except TimeoutError:
            pass
        finally:
            if process.returncode is None:
                # Nobody waits for it any more — its time is over, or whoever asked was
                # cancelled —: its whole group goes, and it is collected. «Not permitted» is what
                # macOS answers for a group whose only process has ended and is not collected yet
                # (measured): a group with nothing left to kill, like one that is not there.
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
        if not answered:
            raise VaultTimeout(f"bw {said} did not answer within {self._timeout:g} s")
        return int(process.returncode or 0), printed


def _read(printed: bytes, what: str) -> Any:
    """What ``bw`` printed, as JSON. An output that is not JSON is an error that says which
    command and **carries nothing of the output** — it is raised after the reading failed and
    outside its handler, so that it is chained to nothing that holds the text."""
    try:
        parsed = json.loads(printed)
    except ValueError:
        parsed = _UNREADABLE
    if parsed is _UNREADABLE:
        raise VaultFailed(f"bw {what} did not answer in a form ELA reads")
    return parsed


def _addresses(login: Mapping[str, Any]) -> tuple[str, ...]:
    listed = login.get("uris")
    if not isinstance(listed, list):
        return ()
    return tuple(
        one["uri"]
        for one in listed
        if isinstance(one, dict) and isinstance(one.get("uri"), str) and one.get("match") != NEVER
    )


def _entries(listed: Any) -> tuple[VaultEntry, ...] | None:
    """The entries of a listing that have a login, each without any value; ``None`` if what was
    printed is not a list of entries."""
    if not isinstance(listed, list) or not all(isinstance(item, dict) for item in listed):
        return None
    found: list[VaultEntry] = []
    for item in listed:
        login = item.get("login")
        if not isinstance(login, dict) or not isinstance(item.get("id"), str):
            continue
        username = login.get("username")
        found.append(
            VaultEntry(
                id=item["id"],
                name=item["name"] if isinstance(item.get("name"), str) else "",
                addresses=_addresses(login),
                username=masked(username) if isinstance(username, str) else "",
                has_password=isinstance(login.get("password"), str) and bool(login["password"]),
            )
        )
    return tuple(found)


def _taken(item: Any) -> VaultTaken | None:
    """What is kept of one entry: **what is named here, and nothing else** — a field a later
    version of ``bw`` adds does not pass. ``None`` for an entry with no password to take."""
    login = item.get("login") if isinstance(item, dict) else None
    if not isinstance(login, dict):
        return None
    password = login.get("password")
    if not isinstance(password, str) or not password:
        return None
    username = login.get("username")
    return VaultTaken(
        addresses=_addresses(login),
        username=Secret(username if isinstance(username, str) else ""),
        password=Secret(password),
    )
