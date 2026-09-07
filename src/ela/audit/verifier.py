"""Who can say whether the trail was tampered with (spec §32, §58; ADR 0024 §4).

:mod:`ela.audit.chain` defines what "tampered" *means*; this is the one member the Core needs in
order to ask the question of a real log. The implementation is the SQL adapter, because only the
adapter sees what the answer is made of — ``seq``, ``prev_hash``, ``row_hash`` — none of which an
:class:`~ela.domain.AuditEvent` carries.

**Why it is not in :mod:`ela.ports`.** It returns a :class:`~ela.audit.chain.ChainSummary`, and
contract 2 forbids the ports to import :mod:`ela.audit`: a port that returned it would drag the
chain into the one module that is allowed to know only the domain. The same reason put the
``Database`` protocol in :mod:`ela.composition.root` instead of in the ports (ADR 0023 §5).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ela.audit.chain import ChainSummary

__all__ = ["AuditVerifier"]


@runtime_checkable
class AuditVerifier(Protocol):
    """Reads the whole log and says whether its links still hold."""

    async def verify(self) -> ChainSummary:
        """The log as two numbers — how long it is, the hash at its head — if it verifies.

        :raises ela.audit.chain.AuditChainError: at the first entry that does not fit the chain,
            with the position and which fault it is. A failure is raised and never returned as a
            ``False`` somebody can forget to look at (§33).
        """
