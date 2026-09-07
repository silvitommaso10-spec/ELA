"""``model.complete`` (spec §29, MEDIUM): the capability that sends the user's content out.

The first tool of ELA that talks to something outside this machine, and the first that cannot be
run twice: a second call costs money, sends the user's content across the network a second time
(§57) and answers something else. So ``idempotent = False``, and the executor runs it under the
STARTED protocol of ADR 0021 §1.

The tool is thin on purpose. It validates its arguments again (§28: a tool never trusts its
caller), **asks the router where the call goes** (§25, ADR 0022), builds a
:class:`~ela.domain.ProviderRequest` — the vendor-independent shape of a request — hands it to
the provider the route named, and turns the :class:`~ela.domain.ProviderResult` back into an
:class:`~ela.tools.base.Outcome`. It still chooses **nothing**: the choice is the router's, and
what the tool adds is that the choice is now made by a policy instead of by whoever typed the
arguments (M7.3; until M7.2 it was the ``model_hint`` or the provider's own default).

Everything the tool does before the call is done **without touching the network**: a task type
the policy does not know, or a route whose providers are all unusable, is a failed outcome and
not a request — which is the whole reason the router reads a declared ``ProviderStatus`` instead
of trying (ADR 0020 §2, ADR 0022 §7).

A provider failure is a failed :class:`~ela.tools.base.Outcome` carrying the provider's **own**
code and its **own** ``retryable`` (ADR 0020 §7): a rate limit reaches the audit trail as
temporary and a rejected argument as final, because that distinction is the one §64 needs and
the tool is not entitled to flatten it. An answer with no text is the one failure this module
*names* rather than relays — :data:`~ela.ports.PROVIDER_NO_OUTPUT` — and it is named from the
shared vocabulary in ``ela.ports``, never from a constant of its own: a code outside the closed
vocabulary is what the vocabulary exists to forbid (review of M7.2).

What comes back from the model is the user's content. It goes in ``output["output"]``, which
lives in the execution result and in the private database, and in no audit event (§57, rule 23).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar, Final

from ela.domain import (
    CapabilityId,
    JsonMapping,
    JsonValue,
    ModelRoute,
    ProviderRequest,
    ProviderRequestId,
    ProviderResult,
)
from ela.ports import (
    PROVIDER_ERROR_CODES,
    PROVIDER_NO_OUTPUT,
    PROVIDER_UNAVAILABLE,
    ROUTING_ERROR_CODES,
    Clock,
    IdGenerator,
    ModelRouterPort,
    NotFoundError,
    ProviderRegistryPort,
    RoutingError,
)
from ela.tools.base import ARGUMENTS_INVALID, Outcome, Tool

__all__ = [
    "MODEL_COMPLETE",
    "MODEL_TOOL_NAME",
    "ROUTING_ARGUMENTS",
    "ModelCompleteTool",
    "routing_arguments",
]

MODEL_COMPLETE: Final = CapabilityId("model.complete")
MODEL_TOOL_NAME: Final = "model-complete"

DEFAULT_PURPOSE: Final = "model.complete"
"""``ProviderRequest.purpose`` when the arguments name none: the domain requires a purpose, the
capability's schema makes it optional, and inventing a description of the *content* would be
worse than naming the capability that asked."""

TEXT_ARGUMENTS: Final = ("input", "purpose", "instructions", "task_type", "model_hint")
"""The arguments that must be strings when present; ``input`` must also be there."""

ROUTING_ARGUMENTS: Final = ("task_type", "model_hint")
"""The two arguments the route is computed from, and nothing else (ADR 0022 §2).

Named here, once, because two modules read them the same way: this tool before the call, and
``ModelCompleteVerifier`` afterwards when it recomputes the route it was supposed to take. Two
readings of "what did the caller ask for" that could drift apart would make
``model.routed_as_asked`` verify the verifier's opinion instead of the policy.
"""


def _text_arguments(arguments: JsonMapping) -> dict[str, str] | None:
    """The string arguments that are there, or ``None`` if one is not a string or ``input`` is
    missing. Checked here a second time after the Guardian's schema (§28)."""
    values: dict[str, str] = {}
    for key in TEXT_ARGUMENTS:
        given = arguments.get(key)
        if given is None:
            continue
        if not isinstance(given, str):
            return None
        values[key] = given
    return values if "input" in values else None


def routing_arguments(arguments: JsonMapping) -> tuple[str | None, str | None] | None:
    """``(task_type, model_hint)`` as strings, or ``None`` if either is present and not one.

    Absent is not invalid: both arguments are optional in the schema (ADR 0010 §5). Present and
    of the wrong type is invalid, and is refused here rather than passed to the router, which
    would then have to have an opinion about a type the Guardian already excluded (§28).
    """
    values: list[str | None] = []
    for key in ROUTING_ARGUMENTS:
        given = arguments.get(key)
        if given is not None and not isinstance(given, str):
            return None
        values.append(given)
    task_type, model_hint = values
    return task_type, model_hint


class ModelCompleteTool(Tool):
    """Completes ``input`` with a model, through the router and one provider (§25, §29).

    ``router`` and ``providers`` are held as data, like a clock: the tool does not know which
    vendor is behind a name, only the ports. It is the sole caller of ``complete`` in ELA
    (architecture rule 25), which is what makes "the user's content leaves this machine only
    under a decision of the Guardian" a property of the code and not of a habit.

    The registry is here and not inside the router because a :class:`~ela.domain.ModelRoute`
    names a provider rather than holding one: a decision that is data can be written into a
    result and recomputed by a verifier, which is what ``model.routed_as_asked`` needs.
    """

    error_codes: ClassVar[frozenset[str]] = (
        frozenset({ARGUMENTS_INVALID}) | PROVIDER_ERROR_CODES | ROUTING_ERROR_CODES
    )
    """Its own argument check, the whole shared vocabulary of ``ela.ports`` — including
    :data:`~ela.ports.PROVIDER_NO_OUTPUT`, which lives there and not here (review of M7.2) — and
    the routing codes, which are reported with the code the router raised."""
    output_keys: ClassVar[frozenset[str]] = frozenset(
        {"output", "provider", "model", "finish_reason", "profile", "skipped"}
    )
    """``profile`` and ``skipped`` are the route the call took: which profile was asked for, and
    which providers were passed over because they were not usable. They live in the execution
    result — never in an audit event (§57, rule 23) — and they are what makes a fallback a thing
    somebody can see afterwards instead of a silent substitution (§33)."""
    idempotent: ClassVar[bool] = False
    """A second call is charged, sends the user's content out again (§57) and answers something
    else. The executor runs this tool under the STARTED protocol of ADR 0021 §1."""

    def __init__(
        self,
        router: ModelRouterPort,
        providers: ProviderRegistryPort,
        clock: Clock,
        ids: IdGenerator,
        *,
        name: str = MODEL_TOOL_NAME,
    ) -> None:
        super().__init__(MODEL_COMPLETE, clock, ids, name=name)
        self._router = router
        self._providers = providers

    async def _run(self, arguments: JsonMapping) -> Outcome:
        """Validate, route, call. Only the last step leaves this machine.

        The order is not incidental: arguments that do not typecheck are refused before the
        router is asked anything, so a routing failure always means the arguments were fine and
        the *policy* said no.
        """
        routing = routing_arguments(arguments)
        texts = _text_arguments(arguments)
        parameters = arguments.get("parameters", {})
        if routing is None or texts is None or not isinstance(parameters, dict):
            return Outcome({}, ARGUMENTS_INVALID, "input must be a string; so must every other")
        try:
            route = self._router.route(*routing)
        except RoutingError as error:
            return Outcome({}, error.code, error.message)
        try:
            provider = self._providers.get(route.provider)
        except NotFoundError:
            return Outcome({}, PROVIDER_UNAVAILABLE, f"no provider named {route.provider!r}")
        answered = await provider.complete(self._request(texts, parameters, route))
        return self._outcome(answered, route)

    def _request(
        self, texts: Mapping[str, str], parameters: JsonMapping, route: ModelRoute
    ) -> ProviderRequest:
        """The arguments and the route as a :class:`~ela.domain.ProviderRequest`.

        ``parameters`` travels as it came — what a provider accepts in it is the provider's
        closed list (ADR 0020 §5), not this tool's business. ``model_hint`` is the **route's**
        profile: what goes out is what the router chose, which is the caller's hint when there
        was one and the table's profile when there was not (ADR 0022 §3).
        """
        return ProviderRequest(
            id=ProviderRequestId(self._ids.new_uuid()),
            created_at=self._clock.now(),
            purpose=texts.get("purpose", DEFAULT_PURPOSE),
            input=texts["input"],
            instructions=texts.get("instructions"),
            model_hint=route.profile,
            parameters=parameters,
        )

    @staticmethod
    def _outcome(answered: ProviderResult, route: ModelRoute) -> Outcome:
        """The provider's result as an outcome: its code, its ``retryable``, its usage, its route.

        The usage travels on **both** branches. A failed call still costs latency, and a refusal
        still costs tokens (ADR 0020 §9, outcome 7): an audit trail that recorded the cost only
        of the calls that worked would under-report exactly the calls worth looking at. So does
        the route: a fallback that ended in a failure is the fallback worth seeing.
        """
        provided: dict[str, JsonValue] = {
            "provider": answered.provider,
            "model": answered.model,
            "finish_reason": answered.finish_reason,
            "profile": route.profile,
            "skipped": list(route.skipped),
        }
        if answered.error is not None:
            return Outcome(
                provided,
                answered.error.code,
                answered.error.message,
                retryable=answered.error.retryable,
                usage=answered.usage,
            )
        if not answered.output:
            return Outcome(
                provided,
                PROVIDER_NO_OUTPUT,
                f"{answered.provider} answered {answered.model!r} with no text",
                usage=answered.usage,
            )
        return Outcome({**provided, "output": answered.output}, usage=answered.usage)
