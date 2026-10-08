"""Whether a step can be acted on: one function for the executor, the Planner and the hand route.

M14.2, ADR 0058 (decision B, decision 8 of the review). Until M14.2 these checks lived inline in
``Executor._prepared``: **exactly one capability** (ADR 0013 §2), **at least one success
condition** (ADR 0014 §3), the capability **in the catalogue**, **a tool** and **a verifier** for
it, and every condition **in the verifier's vocabulary**. ADR 0014 asked for the same to be
checkable when a plan is validated, and nobody had made it so: a plan with two capabilities in a
step came in, and left its task ``EXECUTING`` at the first run.

Now there is one answer, :func:`readiness`, and each caller words it: the executor raises what it
always raised — the registry's own ``NotFoundError``, or an ``ExecutorError`` with the same
sentence —; the Planner and the hand route refuse the plan before it comes in, naming the step by
position. What decides whether a step runs is what decides whether a plan enters.

Pure: three registry reads, no I/O, nothing written.
"""

from __future__ import annotations

from typing import NamedTuple

from ela.domain import CapabilitySpec, TaskStep
from ela.ports import (
    CapabilityRegistryPort,
    NotFoundError,
    ToolPort,
    ToolRegistryPort,
    VerifierPort,
    VerifierRegistryPort,
)

__all__ = ["Ready", "Unready", "readiness"]


class Ready(NamedTuple):
    """A step the executor can act on: the registries' answers about its one capability."""

    spec: CapabilitySpec
    tool: ToolPort
    verifier: VerifierPort


class Unready(NamedTuple):
    """Why a step cannot be acted on.

    ``code`` names the constraint: ``capabilities``, ``no_condition``, ``unknown_capability``,
    ``no_tool``, ``no_verifier``, ``outside``. ``said`` is the sentence **without the step's id and
    without the words the plan wrote** — a capability outside the catalogue is not named, the
    conditions outside the vocabulary are counted —, because the Planner's reason goes to the audit
    and the route's to whoever sent the plan (§57). ``error`` is the registry's own error, for the
    three that a registry answers; ``outside`` the conditions the verifier cannot check, which only
    the executor quotes, as it always did.
    """

    code: str
    said: str
    error: NotFoundError | None = None
    outside: tuple[str, ...] = ()


def readiness(
    step: TaskStep,
    *,
    capabilities: CapabilityRegistryPort,
    tools: ToolRegistryPort,
    verifiers: VerifierRegistryPort,
) -> Ready | Unready:
    """The executor's preconditions of ``step``, in the executor's order; never raises for one."""
    declared = len(step.required_capabilities)
    if declared != 1:
        return Unready(
            "capabilities",
            f"declares {declared} capabilities; an executable step declares exactly one",
        )
    if not step.success_conditions:
        return Unready(
            "no_condition",
            "declares no success condition; an action that cannot be verified is not executed",
        )
    try:
        spec = capabilities.get(step.required_capabilities[0])
    except NotFoundError as error:
        return Unready(
            "unknown_capability", "requires a capability that is not in the catalogue", error
        )
    try:
        tool = tools.get(spec.id)
    except NotFoundError as error:
        return Unready("no_tool", f"requires {spec.id}, which has no tool", error)
    try:
        verifier = verifiers.get(spec.id)
    except NotFoundError as error:
        return Unready("no_verifier", f"requires {spec.id}, which has no verifier", error)
    outside = tuple(c for c in step.success_conditions if c not in verifier.conditions)
    if outside:
        count = len(outside)
        return Unready(
            "outside",
            f"names {count} success condition{'' if count == 1 else 's'} {verifier.name} cannot "
            "check; an action that cannot be verified is not executed",
            outside=outside,
        )
    return Ready(spec, tool, verifier)
