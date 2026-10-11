"""The vault of the passwords, as the Core reaches it (M13.9, ADR 0063; decisions 16 and 32).

Three routes, the Core's. ``GET /vault`` says what the vault is — **asked of its program at every
request, never remembered** — and, for a locked one, the whole line to paste in a terminal.
``POST /vault/session`` receives the session key that ``bw unlock --raw`` printed into a pipe:
**from this machine only** — both ends of the socket loopback, the tailnet does not deliver a key
—, kept only if the vault's program says it opens, and never said back. ``POST /vault/lock``
forgets it and asks the vault to lock.

**The master password has no route**: nothing here has a field it could travel in. And the key
goes from the request into a :class:`~ela.ports.Secret` and to the door, and nowhere else — not
into an answer, a refusal, the audit or a log.

**The audit**: an opening is written here, by the route that receives it, signed by who handed
the key. A closing is written by the keeper of the key — the door —, because it is who sees every
one of them: this route's, the hour's, the stop of ELA.
"""

from __future__ import annotations

from typing import Final

from fastapi import APIRouter, Request

from ela.api.deps import ElaDep, IdentityDep
from ela.api.errors import ApiError
from ela.api.schemas import VaultKeyIn, VaultLockedOut, VaultOpenedOut, VaultOut
from ela.api.security import Identity, from_this_machine
from ela.composition import Ela
from ela.domain import AuditEvent, AuditEventId, AuditEventType
from ela.ports import Secret

__all__ = [
    "NOT_LOCAL",
    "VaultKeyNotLocalError",
    "VaultRefusedError",
    "router",
    "vault_locked",
    "vault_of",
]

router = APIRouter(tags=["vault"])

NOT_LOCAL: Final = "vault.not_local"
"""A key that arrived on a socket whose two ends are not both loopback: refused, and never
tried. The one code of the vault that is this route's and not the door's."""
FORGOTTEN: Final = "ELA forgot the key, and the vault was not asked to lock"


class VaultRefusedError(ApiError):
    """The vault did not take the key, or did not lock: the vault's own code is the first word,
    and the sentence after it names what to run — never an entry, and never the key."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class VaultKeyNotLocalError(ApiError):
    """The key of the vault from anywhere but this machine. Not a subclass of the refusal above:
    the vault was never asked."""

    def __init__(self) -> None:
        super().__init__(
            f"{NOT_LOCAL}: the key of the vault is taken only from this machine. Run "
            "`ela vault open` on the machine ELA runs on"
        )


async def vault_of(ela: Ela) -> VaultOut:
    """What the vault is now, asked of its program — what the route answers, and what a page
    reads (architecture rule 55)."""
    state = await ela.vault.state()
    return VaultOut(
        state=state.name,
        forgets_at=state.forgets_at,
        program=ela.vault.program,
        opens_with=state.opens_with,
        message=state.message,
    )


async def vault_locked(ela: Ela, identity: Identity) -> VaultLockedOut:
    """Forget the key and ask the vault to lock, for whoever asked: the route's whole work, and a
    page's. Whatever this answers, ELA holds no key."""
    problem = await ela.vault.close(identity.actor)
    if problem is not None:
        raise VaultRefusedError(problem.code, f"{problem.message}. {FORGOTTEN}")
    return VaultLockedOut(locked=True)


@router.get("/vault")
async def vault(ela: ElaDep) -> VaultOut:
    """What the vault is now, and for a locked one the line that opens it."""
    return await vault_of(ela)


@router.post("/vault/session")
async def opened(
    body: VaultKeyIn, request: Request, ela: ElaDep, identity: IdentityDep
) -> VaultOpenedOut:
    """Hand ELA the session key. Refused before anything is tried unless both ends of the socket
    are loopback; kept only if the vault's program says it opens."""
    if not from_this_machine(request):
        raise VaultKeyNotLocalError
    problem = await ela.vault.open(Secret(body.key.get_secret_value()))
    if problem is not None:
        raise VaultRefusedError(problem.code, problem.message)
    forgets_at = ela.vault.forgets_at
    assert forgets_at is not None  # noqa: S101 — the door has just set it
    await ela.audit.append(
        AuditEvent(
            id=AuditEventId(ela.ids.new_uuid()),
            created_at=ela.clock.now(),
            event_type=AuditEventType.VAULT_OPENED,
            actor=identity.actor,
            summary="vault: opened",
            payload={"forgets_at": forgets_at.isoformat()},
        )
    )
    return VaultOpenedOut(forgets_at=forgets_at)


@router.post("/vault/lock")
async def locked(ela: ElaDep, identity: IdentityDep) -> VaultLockedOut:
    """Forget the key and ask the vault to lock. Whatever this answers, ELA holds no key: a lock
    that could not be asked — a program that changed — is a refusal that says so."""
    return await vault_locked(ela, identity)
