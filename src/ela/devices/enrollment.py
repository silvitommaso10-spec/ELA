"""How a node gets an identity: a one-shot code, then a secret (M12.1 dec. D, E; ADR 0037 §5, §6).

The user issues a code with the ``privacy`` the node will have (``ela node enroll --privacy …``);
the node presents it once, with the half it declares of itself; the Core mints the node's id and
its secret, keeps the SHA-256 of the code and of the secret and never either, and the row is born
with the level the code carries. The secret is returned once, by :meth:`NodeEnrollment.enroll`:
it is the only answer of ELA that contains a node's secret.

Both are ``secrets.token_urlsafe(32)``, 256 bits, the entropy of ``ela init``'s token: the SHA-256
of such a value cannot be inverted by a dictionary, and the speed of the hash does not matter,
because the space to walk is 2^256 (dec. E; ADR 0014, alternativa F). A random secret is not a
password.
"""

from __future__ import annotations

import hashlib
import secrets
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from ela.devices.local import LOCAL_USER
from ela.devices.registry import DeviceRegistry, Rejection
from ela.domain import (
    Device,
    DeviceCapability,
    DeviceId,
    Enrollment,
    OperatingSystem,
    PerformanceClass,
    PrivacyLevel,
)
from ela.ports import Clock, EnrollmentConsumedError, EnrollmentStore, IdGenerator, NotFoundError

__all__ = [
    "ENROLLMENT_CODE_TTL",
    "RANDOM_BYTES",
    "EnrolledNode",
    "IssuedCode",
    "NodeEnrollment",
    "fingerprint",
]

ENROLLMENT_CODE_TTL: Final = timedelta(minutes=10)
"""How long a code can be presented. A constant with a ceiling and not a setting (dec. D §4): «un
TTL senza tetto è una porta che si può lasciare aperta per sempre scrivendo un numero grande»
(ADR 0023 §3)."""

RANDOM_BYTES: Final = 32
"""The bytes of randomness in a code and in a secret, as in ``ela init``'s token (dec. E)."""


def fingerprint(value: str) -> str:
    """The SHA-256, in lowercase hex, that ELA keeps instead of a code or a secret (dec. E)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class IssuedCode:
    """A code, handed out once to whoever asked for it, with what it will impose and until when."""

    code: str
    privacy: PrivacyLevel
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class EnrolledNode:
    """The node a code gave birth to, and its secret — the one time the secret exists in clear."""

    device: Device
    secret: str


class NodeEnrollment:
    """Issues codes and turns a presented code into a node (ADR 0037 §5).

    It mints and hashes; the row and the audit are the registry's, which writes every fact of an
    identity (ADR 0037 §13). Issuing a code writes nothing: a code that expires unused changes
    nothing in ELA's world, and the admission is one fact, written when it happens.
    """

    __slots__ = ("_clock", "_codes", "_ids", "_registry")

    def __init__(
        self, codes: EnrollmentStore, registry: DeviceRegistry, clock: Clock, ids: IdGenerator
    ) -> None:
        self._codes = codes
        self._registry = registry
        self._clock = clock
        self._ids = ids

    async def issue(self, privacy: PrivacyLevel) -> IssuedCode:
        """A new code that will impose ``privacy``, valid for :data:`ENROLLMENT_CODE_TTL`.

        :raises ValueError: for ``LOCAL_ONLY``, which is this machine's level (D18) — refused by
            the type, before anything is kept.
        """
        now = self._clock.now()
        code = secrets.token_urlsafe(RANDOM_BYTES)
        enrollment = Enrollment(
            code_hash=fingerprint(code),
            created_at=now,
            expires_at=now + ENROLLMENT_CODE_TTL,
            privacy=privacy,
        )
        await self._codes.offer(enrollment)
        return IssuedCode(code=code, privacy=privacy, expires_at=enrollment.expires_at)

    async def enroll(
        self,
        code: str,
        *,
        name: str,
        os: OperatingSystem,
        capabilities: tuple[DeviceCapability, ...],
        available_tools: tuple[str, ...],
        performance: PerformanceClass,
    ) -> EnrolledNode:
        """Spend ``code`` for a new node with the half it declares; return the node and its secret.

        The id is minted before the code is spent, because the code is spent *by* a node: the
        conditional ``UPDATE`` writes both at once (ADR 0037 §5). If the row is then born and the
        answer lost, the node has no secret and the code is spent: presenting it again is refused,
        the row stays, never seen, and the user revokes it (dec. D §6).

        A code already spent names the node it gave birth to: ``DEVICE_REJECTED`` ``code_reused``,
        if that node exists — in the crash window it does not, and there is nothing to name.

        :raises NotFoundError: for a code nobody issued.
        :raises EnrollmentConsumedError: for a code already spent.
        :raises EnrollmentExpiredError: for a code past its expiry.
        """
        now = self._clock.now()
        device_id = DeviceId(self._ids.new_uuid())
        try:
            spent = await self._codes.consume(fingerprint(code), device_id=device_id, now=now)
        except EnrollmentConsumedError as reused:
            with suppress(NotFoundError):
                await self._registry.reject(reused.device_id, Rejection.CODE_REUSED)
            raise
        secret = secrets.token_urlsafe(RANDOM_BYTES)
        device = await self._registry.enroll(
            device_id,
            name=name,
            os=os,
            capabilities=capabilities,
            available_tools=available_tools,
            performance=performance,
            privacy=spent.privacy,
            secret_hash=fingerprint(secret),
            by=LOCAL_USER,
            issued_at=spent.created_at,
        )
        return EnrolledNode(device=device, secret=secret)
