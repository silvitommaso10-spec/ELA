"""The hash chain that makes the audit trail tamper-evident (spec §32, §58, §65; ADR 0007).

Every entry of the log carries the hash of the entry before it: change one entry in place, take
one out of the middle, slip one in, or reorder them, and the links no longer match. This module
is the *meaning* of "tampered": pure functions over records, standard library only. Where the
records come from — a SQLite table, in :mod:`ela.infrastructure.persistence.audit_log` — is the
adapter's business, which is the capability/implementation split of §28 applied to the audit.

A record is what the storage holds for one entry, as JSON-compatible values. The canonical form
is fixed here and nowhere else: JSON with sorted keys, compact separators, ASCII only. A hash is
the SHA-256 of the canonical form of ``{"previous_hash": …, "record": …}``, in lowercase hex.

What the chain does *not* prove: that the tail is complete (removing the last entries leaves a
valid chain) or that nobody with write access rewrote the whole chain from one entry on. Both
need an anchor kept outside the log; :class:`ChainSummary` carries the two values to anchor.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

__all__ = [
    "EMPTY_CHAIN",
    "GENESIS_HASH",
    "AuditChainError",
    "ChainFault",
    "ChainSummary",
    "Link",
    "Record",
    "canonical_bytes",
    "link_hash",
    "verify_links",
]

GENESIS_HASH: Final = "0" * 64
"""The ``previous_hash`` of the first entry: no entry came before it."""

Record = Mapping[str, object]
"""One entry as JSON-compatible values, keyed by field name."""


class ChainFault(StrEnum):
    """Why a chain failed to verify."""

    BROKEN_LINK = "BROKEN_LINK"
    """The entry's ``previous_hash`` is not the hash of the entry before it (or the genesis)."""
    ALTERED_ROW = "ALTERED_ROW"
    """The entry's hash is not the hash of its own content: the content changed after hashing."""


@dataclass(frozen=True)
class Link:
    """One entry as the verifier sees it: where it is, what it claims, what it holds."""

    position: int
    previous_hash: str
    hash: str
    record: Record


@dataclass(frozen=True)
class ChainSummary:
    """A verified chain in two numbers: how long it is and the hash at its head.

    An empty chain has ``length == 0`` and ``head_hash == GENESIS_HASH``. Keep both somewhere the
    log cannot reach and a truncated tail becomes detectable too.
    """

    length: int
    head_hash: str


class AuditChainError(Exception):
    """The chain does not verify at ``position`` (§33: raised, never returned as ``False``)."""

    def __init__(self, position: int, fault: ChainFault) -> None:
        self.position = position
        self.fault = fault
        super().__init__(f"audit chain {fault.value} at position {position}")


def canonical_bytes(previous_hash: str, record: Record) -> bytes:
    """The bytes that get hashed: one JSON document, sorted keys, compact, ASCII."""
    document = {"previous_hash": previous_hash, "record": record}
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def link_hash(previous_hash: str, record: Record) -> str:
    """The hash of an entry: SHA-256 of :func:`canonical_bytes`, lowercase hex."""
    return hashlib.sha256(canonical_bytes(previous_hash, record)).hexdigest()


EMPTY_CHAIN: Final = ChainSummary(length=0, head_hash=GENESIS_HASH)


def verify_links(links: Iterable[Link], *, after: ChainSummary = EMPTY_CHAIN) -> ChainSummary:
    """Verify ``links`` in order, continuing the chain summarised by ``after``.

    Each link must point at the current head (``previous_hash``) and hash to what it claims. The
    first link that does not raises :class:`AuditChainError` with its position and the fault.
    Returns the summary of the chain so far, to pass as ``after`` for the next window.
    """
    head = after.head_hash
    length = after.length
    for link in links:
        if link.previous_hash != head:
            raise AuditChainError(link.position, ChainFault.BROKEN_LINK)
        if link_hash(link.previous_hash, link.record) != link.hash:
            raise AuditChainError(link.position, ChainFault.ALTERED_ROW)
        head = link.hash
        length += 1
    return ChainSummary(length=length, head_hash=head)
