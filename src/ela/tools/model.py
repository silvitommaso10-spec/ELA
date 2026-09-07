"""``model.complete`` (spec §29, MEDIUM): the capability that sends the user's content out.

The first tool of ELA that talks to something outside this machine, and the first that cannot be
run twice: a second call costs money, sends the user's content across the network a second time
(§57) and answers something else. So ``idempotent = False``, and the executor runs it under the
STARTED protocol of ADR 0021 §1.

The tool is thin on purpose. It validates its arguments again (§28: a tool never trusts its
caller), builds a :class:`~ela.domain.ProviderRequest` — the vendor-independent shape of a
request — hands it to the provider, and turns the :class:`~ela.domain.ProviderResult` back into
an :class:`~ela.tools.base.Outcome`. It chooses **nothing**: which model answers is decided by
the ``model_hint`` in the arguments or, absent one, by the provider's own default (ADR 0020 §5).
Choosing is the Model Router's job and arrives with M7.3.

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

from typing import ClassVar, Final

from ela.domain import (
    CapabilityId,
    JsonMapping,
    JsonValue,
    ProviderRequest,
    ProviderRequestId,
    ProviderResult,
)
from ela.ports import (
    PROVIDER_ERROR_CODES,
    PROVIDER_NO_OUTPUT,
    Clock,
    IdGenerator,
    ModelProvider,
)
from ela.tools.base import ARGUMENTS_INVALID, Outcome, Tool

__all__ = ["MODEL_COMPLETE", "MODEL_TOOL_NAME", "ModelCompleteTool"]

MODEL_COMPLETE: Final = CapabilityId("model.complete")
MODEL_TOOL_NAME: Final = "model-complete"

DEFAULT_PURPOSE: Final = "model.complete"
"""``ProviderRequest.purpose`` when the arguments name none: the domain requires a purpose, the
capability's schema makes it optional, and inventing a description of the *content* would be
worse than naming the capability that asked."""

TEXT_ARGUMENTS: Final = ("input", "purpose", "instructions", "model_hint")
"""The arguments that must be strings when present; ``input`` must also be there."""


class ModelCompleteTool(Tool):
    """Completes ``input`` with a model, through one :class:`~ela.ports.ModelProvider` (§29).

    ``provider`` is held as data, like a clock: the tool does not know which vendor is behind it,
    only the port. It is the sole caller of ``complete`` in ELA (architecture rule 25), which is
    what makes "the user's content leaves this machine only under a decision of the Guardian" a
    property of the code and not of a habit.
    """

    error_codes: ClassVar[frozenset[str]] = frozenset({ARGUMENTS_INVALID}) | PROVIDER_ERROR_CODES
    """Its own argument check, plus the whole shared vocabulary of ``ela.ports`` — including
    :data:`~ela.ports.PROVIDER_NO_OUTPUT`, which lives there and not here (review of M7.2)."""
    output_keys: ClassVar[frozenset[str]] = frozenset(
        {"output", "provider", "model", "finish_reason"}
    )
    idempotent: ClassVar[bool] = False
    """A second call is charged, sends the user's content out again (§57) and answers something
    else. The executor runs this tool under the STARTED protocol of ADR 0021 §1."""

    def __init__(
        self,
        provider: ModelProvider,
        clock: Clock,
        ids: IdGenerator,
        *,
        name: str = MODEL_TOOL_NAME,
    ) -> None:
        super().__init__(MODEL_COMPLETE, clock, ids, name=name)
        self._provider = provider

    @property
    def provider_name(self) -> str:
        """The name of the provider this tool calls; the audit reads it from the result."""
        return self._provider.name

    async def _run(self, arguments: JsonMapping) -> Outcome:
        request = self._request(arguments)
        if request is None:
            return Outcome({}, ARGUMENTS_INVALID, "input must be a string; so must every other")
        answered = await self._provider.complete(request)
        return self._outcome(answered)

    def _request(self, arguments: JsonMapping) -> ProviderRequest | None:
        """The arguments as a :class:`~ela.domain.ProviderRequest`, or ``None`` if they are not.

        Checked here a second time after the Guardian's schema (§28); ``parameters`` travels as
        it came — what a provider accepts in it is the provider's closed list (ADR 0020 §5), not
        this tool's business.
        """
        values: dict[str, str] = {}
        for key in TEXT_ARGUMENTS:
            given = arguments.get(key)
            if given is None:
                continue
            if not isinstance(given, str):
                return None
            values[key] = given
        if "input" not in values:
            return None
        parameters = arguments.get("parameters", {})
        if not isinstance(parameters, dict):
            return None
        return ProviderRequest(
            id=ProviderRequestId(self._ids.new_uuid()),
            created_at=self._clock.now(),
            purpose=values.get("purpose", DEFAULT_PURPOSE),
            input=values["input"],
            instructions=values.get("instructions"),
            model_hint=values.get("model_hint"),
            parameters=parameters,
        )

    @staticmethod
    def _outcome(answered: ProviderResult) -> Outcome:
        """The provider's result as an outcome: its code, its ``retryable``, its usage.

        The usage travels on **both** branches. A failed call still costs latency, and a refusal
        still costs tokens (ADR 0020 §9, outcome 7): an audit trail that recorded the cost only
        of the calls that worked would under-report exactly the calls worth looking at.
        """
        provided: dict[str, JsonValue] = {
            "provider": answered.provider,
            "model": answered.model,
            "finish_reason": answered.finish_reason,
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
