"""The rows of the Guardian's table, and who admits a policy of §59 (ADR 0011 §3; M13.12, ADR 0062).

:data:`RISK_POLICY` and its predicates lived in ``guardian.py`` until M13.12. They moved here, in a
module that imports nothing but the domain, because two more places read them: the catalogue, which
refuses a declaration of ``policy_terms`` on a row that does not ask unless authorized (decision 2),
and the module of the policies, which says why a capability admits none (decision 6) — and the
catalogue cannot import the Guardian without a cycle, since the Guardian imports the catalogue. The
values did not move, and ``guardian.py`` re-exports every name: it is the same table.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from ela.domain import CapabilitySpec, RiskLevel

__all__ = [
    "ASKING_RULES",
    "RISK_POLICY",
    "Rule",
    "asks_at_every_use",
    "no_policy_for",
]


class Rule(StrEnum):
    """Which check settled a decision; ``metadata["rule"]`` of every decision (ADR 0011 §3).

    The first five are the rows of :data:`RISK_POLICY`, one per risk level; the others are the
    checks that run before or beside the row, or the fail-safe.
    """

    ALLOW = "ALLOW"
    ALLOW_WITHIN_SCOPE = "ALLOW_WITHIN_SCOPE"
    APPROVAL_UNLESS_AUTHORIZED = "APPROVAL_UNLESS_AUTHORIZED"
    APPROVAL_EVERY_USE = "APPROVAL_EVERY_USE"
    """HIGH: a question at every use, and no standing policy of §59 reaches it (M13.1 dec. D, N).

    Not ``APPROVAL_UNLESS_AUTHORIZED``: "unless authorized" would be false for the one row no
    standing authorization can satisfy, and a rule name is what somebody reads in an audit a month
    later (M17.2 dec. K.3, the precedent of a name that lied).
    """
    DENY = "DENY"
    SCOPE = "SCOPE"
    """A target outside the scope the capability declares — on **any** row (M13.1 dec. C).

    A check and not a row: it is bound to the *fact* that a capability declares a scope, never to
    one risk level, so the third row born tomorrow cannot quietly escape it. Until M13.1 this
    denial signed itself ``ALLOW_WITHIN_SCOPE``, which named the row that allows and not the
    boundary that refused: a false diagnosis is false even when the outcome is right.
    """
    CATALOGUE = "CATALOGUE"
    ARGUMENTS = "ARGUMENTS"
    STEP_MISMATCH = "STEP_MISMATCH"
    AUTHORIZATION_MISMATCH = "AUTHORIZATION_MISMATCH"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


RISK_POLICY: Final[Mapping[RiskLevel, Rule]] = MappingProxyType(
    {
        RiskLevel.SAFE: Rule.ALLOW,
        RiskLevel.LOW: Rule.ALLOW_WITHIN_SCOPE,
        RiskLevel.MEDIUM: Rule.APPROVAL_UNLESS_AUTHORIZED,
        RiskLevel.HIGH: Rule.APPROVAL_EVERY_USE,
        RiskLevel.CRITICAL: Rule.DENY,
    }
)
"""Policy by risk level (§29). Data, compared with the table of ADR 0011 and its revision in
ADR 0045 by the tests; a level missing from it is denied.

``HIGH`` stopped being ``DENY`` in M13.1, openly: §29 said HIGH and CRITICAL were not introduced
in production "in the first version", v0.1 was tagged on 2026-09-07 and this work stands outside
it. ``CRITICAL`` is still denied and has no capability: the day it gets one, that row moves the
same way this one did, in the open."""

ASKING_RULES: Final[frozenset[Rule]] = frozenset(
    {Rule.APPROVAL_UNLESS_AUTHORIZED, Rule.APPROVAL_EVERY_USE}
)
"""The rows that end in a question when no usable grant covers the call.

Derived from here and never re-listed: a row added to :data:`RISK_POLICY` that asks must say so
once, and the executor reads the same set to know when a decision rests on its grant."""


def asks_at_every_use(risk: RiskLevel) -> bool:
    """Whether this row asks every time and is covered **only** by a grant born from a yes.

    One definition, read by the Guardian when it judges a grant it was handed and by the executor
    when it chooses which grant to hand over (M13.1 dec. D). Two copies of this rule would be two
    answers to "does this grant cover", which is the thing ADR 0014 §2 exists to prevent — and the
    cheaper of the two mistakes would be a task denied where the user should have been asked.
    """
    return RISK_POLICY.get(risk) is Rule.APPROVAL_EVERY_USE


def no_policy_for(capability: CapabilitySpec) -> str | None:
    """Why a policy of §59 cannot cover ``capability``, or ``None`` if it can (M13.12; decision 6).

    Three reasons, and they are distinct on purpose: **a row that asks at every use** — or a row
    above it — is reached by no policy (ADR 0045 §3); **a row that does not ask** needs none; **a
    row that asks unless authorized** is covered only if the capability declares what a policy must
    bound, and no milestone has done so yet for every ``MEDIUM`` (decision 1). Read by the
    catalogue, which refuses a declaration on the first two, and by the birth of a policy.

    One condition for the levels from ``HIGH`` up: a ``CRITICAL`` never reaches it — the catalogue's
    cap refuses it first —, and a branch of its own would be a branch no test could walk.
    """
    rule = RISK_POLICY.get(capability.risk)
    if rule is Rule.APPROVAL_UNLESS_AUTHORIZED:
        if capability.policy_terms is None:
            return f"no milestone has said what a policy must bound for {capability.id}"
        return None
    if capability.risk >= RiskLevel.HIGH:
        return "no policy reaches a HIGH (ADR 0045 §3)"
    return f"{capability.id} does not ask: it needs no policy"
