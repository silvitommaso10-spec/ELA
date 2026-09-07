"""What belongs to the fakes and not to the contracts: the knobs a test turns.

The contract tests in ``tests/contracts/`` say what every implementation must do; these say what
the fakes offer on top — a clock that advances, predictable ids, a Guardian table, a canned reply.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from ela.domain import (
    CapabilityId,
    ErrorMetadata,
    ExecutionStatus,
    PermissionOutcome,
    ProviderRequest,
    ProviderStatus,
    RiskLevel,
)
from ela.ports import (
    PROVIDER_UNAVAILABLE,
    ROUTING_UNKNOWN_TASK_TYPE,
    VERIFICATION_NOT_SUCCEEDED,
    AlreadyExistsError,
    NotAllowedError,
    RoutingError,
)
from ela.testing.fakes import (
    DEFAULT_START,
    FAKE_CONDITION,
    FakeCapabilityRegistry,
    FakeClock,
    FakeIdGenerator,
    FakeModelProvider,
    FakeModelRouter,
    FakePermissionGuardian,
    FakeTool,
    FakeVerifier,
    GuardianCall,
    ToolCall,
    VerifierCall,
)
from tests.domain.examples import (
    CAPABILITY_SPEC,
    ERROR_METADATA,
    EXECUTION_RESULT,
    PERMISSION_DECISION,
    PROVIDER_REQUEST,
    TASK,
    WRITE_NOTE,
)

ARGUMENTS = {"path": "workspace/notes/briefing.md", "body": "..."}

# --------------------------------------------------------------------------------------
# FakeClock
# --------------------------------------------------------------------------------------


def test_clock_starts_where_told_and_advances() -> None:
    clock = FakeClock()
    assert clock.now() == DEFAULT_START
    clock.advance(timedelta(seconds=1))
    assert clock.now() == DEFAULT_START + timedelta(seconds=1)


def test_clock_normalises_to_utc() -> None:
    start = datetime(2026, 9, 4, 12, 0, tzinfo=timezone(timedelta(hours=2)))
    clock = FakeClock(start)
    assert clock.now() == start
    assert clock.now().tzinfo == UTC


def test_clock_refuses_a_naive_start() -> None:
    with pytest.raises(ValueError, match="aware"):
        FakeClock(datetime(2026, 9, 4, 12, 0))


def test_clock_only_moves_forward() -> None:
    clock = FakeClock()
    with pytest.raises(ValueError, match="forward"):
        clock.advance(timedelta(seconds=-1))
    assert clock.now() == DEFAULT_START
    clock.advance(timedelta(0))
    assert clock.now() == DEFAULT_START


# --------------------------------------------------------------------------------------
# FakeIdGenerator
# --------------------------------------------------------------------------------------


def test_ids_are_sequential_and_predictable() -> None:
    ids = FakeIdGenerator()
    assert ids.new_uuid() == UUID("00000000-0000-4000-8000-000000000001")
    assert ids.new_uuid() == UUID("00000000-0000-4000-8000-000000000002")
    assert [FakeIdGenerator().new_uuid() for _ in range(3)] == [
        FakeIdGenerator().new_uuid() for _ in range(3)
    ]


# --------------------------------------------------------------------------------------
# FakePermissionGuardian
# --------------------------------------------------------------------------------------


def test_registry_is_empty_by_default_and_fixed_at_construction() -> None:
    assert FakeCapabilityRegistry().specs() == ()
    other = CAPABILITY_SPEC.model_copy(update={"id": CapabilityId("core.echo")})
    registry = FakeCapabilityRegistry([other, CAPABILITY_SPEC])
    assert registry.specs() == (other, CAPABILITY_SPEC)
    assert not hasattr(registry, "register")


def test_registry_refuses_a_duplicate_id_at_construction() -> None:
    with pytest.raises(AlreadyExistsError):
        FakeCapabilityRegistry([CAPABILITY_SPEC, CAPABILITY_SPEC])


def test_registry_validates_nothing_else() -> None:
    """A test may hold a HIGH capability to see the Guardian deny it (ADR 0010 §1)."""
    high = CAPABILITY_SPEC.model_copy(update={"risk": RiskLevel.HIGH, "scope": ("../x",)})
    assert FakeCapabilityRegistry([high]).get(high.id) is high


def test_guardian_returns_the_configured_outcome() -> None:
    guardian = FakePermissionGuardian(
        FakeClock(), FakeIdGenerator(), outcomes={WRITE_NOTE: PermissionOutcome.ALLOWED}
    )
    decision = guardian.decide(CAPABILITY_SPEC, ARGUMENTS, task=TASK)
    assert decision.outcome is PermissionOutcome.ALLOWED
    assert decision.created_at == DEFAULT_START
    assert decision.id == UUID("00000000-0000-4000-8000-000000000001")


def test_guardian_denies_what_is_not_in_the_table() -> None:
    guardian = FakePermissionGuardian(
        FakeClock(), FakeIdGenerator(), outcomes={WRITE_NOTE: PermissionOutcome.ALLOWED}
    )
    unknown = CAPABILITY_SPEC.model_copy(update={"id": CapabilityId("model.complete")})
    decision = guardian.decide(unknown, ARGUMENTS)
    assert decision.outcome is PermissionOutcome.DENIED
    assert "§33" in decision.reason


def test_guardian_records_every_call() -> None:
    guardian = FakePermissionGuardian(FakeClock(), FakeIdGenerator())
    guardian.decide(CAPABILITY_SPEC, ARGUMENTS, task=TASK)
    assert guardian.calls == (GuardianCall(CAPABILITY_SPEC, ARGUMENTS, TASK, None, None, 0),)


# --------------------------------------------------------------------------------------
# FakeTool
# --------------------------------------------------------------------------------------


def allowed_decision(**update: object) -> object:
    base = {"outcome": PermissionOutcome.ALLOWED, "expires_at": None}
    return PERMISSION_DECISION.model_copy(update={**base, **update})


async def test_tool_records_accepted_calls_and_returns_its_output() -> None:
    tool = FakeTool(
        WRITE_NOTE,
        FakeClock(),
        FakeIdGenerator(),
        name="notes",
        output={"written": True},
        status=ExecutionStatus.SUCCEEDED,
    )
    decision = allowed_decision()
    result = await tool.execute(decision, ARGUMENTS)  # type: ignore[arg-type]
    assert tool.calls == (ToolCall(decision, ARGUMENTS),)  # type: ignore[arg-type]
    assert result.output == {"written": True}
    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.tool_name == "notes"
    assert result.created_at == DEFAULT_START
    assert result.duration_ms == 0


async def test_tool_leaves_no_trace_of_a_refused_call() -> None:
    tool = FakeTool(WRITE_NOTE, FakeClock(), FakeIdGenerator())
    with pytest.raises(NotAllowedError) as info:
        await tool.execute(PERMISSION_DECISION, ARGUMENTS)  # REQUIRES_APPROVAL
    assert info.value.capability_id == WRITE_NOTE
    assert "REQUIRES_APPROVAL" in info.value.reason
    assert tool.calls == ()


async def test_tool_expiry_is_measured_on_its_own_clock() -> None:
    clock = FakeClock()
    tool = FakeTool(WRITE_NOTE, clock, FakeIdGenerator())
    decision = allowed_decision(expires_at=DEFAULT_START + timedelta(minutes=1))
    await tool.execute(decision, ARGUMENTS)  # type: ignore[arg-type]
    clock.advance(timedelta(minutes=1))  # expiring right now is already expired
    with pytest.raises(NotAllowedError, match="expired"):
        await tool.execute(decision, ARGUMENTS)  # type: ignore[arg-type]
    assert len(tool.calls) == 1


def test_tool_default_output_is_empty() -> None:
    tool = FakeTool(WRITE_NOTE, FakeClock(), FakeIdGenerator())
    assert tool.name == "fake-tool"
    assert tool.capability_id == WRITE_NOTE


# --------------------------------------------------------------------------------------
# FakeVerifier
# --------------------------------------------------------------------------------------


SUCCEEDED = EXECUTION_RESULT.model_copy(update={"status": ExecutionStatus.SUCCEEDED, "error": None})
MISMATCH = ErrorMetadata(code="fake.mismatch", message="differs", details={"actual_bytes": 0})


def test_verifier_defaults_to_one_condition_that_holds() -> None:
    verifier = FakeVerifier(WRITE_NOTE)
    assert verifier.name == "fake-verifier"
    assert verifier.capability_id == WRITE_NOTE
    assert verifier.conditions == {FAKE_CONDITION}


async def test_verifier_answers_from_its_table_and_names_the_condition() -> None:
    verifier = FakeVerifier(WRITE_NOTE, conditions=("a.ok", "b.bad"), failures={"b.bad": MISMATCH})
    failures = await verifier.verify(("a.ok", "b.bad", "a.ok"), ARGUMENTS, SUCCEEDED)
    assert [f.code for f in failures] == ["fake.mismatch"]
    assert failures[0].details == {"actual_bytes": 0, "condition": "b.bad"}
    assert failures[0].message == MISMATCH.message
    assert await verifier.verify(("a.ok",), ARGUMENTS, SUCCEEDED) == ()


async def test_verifier_records_every_call_even_a_refused_one() -> None:
    verifier = FakeVerifier(WRITE_NOTE)
    refused = await verifier.verify((FAKE_CONDITION,), ARGUMENTS, EXECUTION_RESULT)  # FAILED
    assert [f.code for f in refused] == [VERIFICATION_NOT_SUCCEEDED]
    await verifier.verify((FAKE_CONDITION,), ARGUMENTS, SUCCEEDED)
    assert verifier.calls == (
        VerifierCall((FAKE_CONDITION,), ARGUMENTS, EXECUTION_RESULT),  # type: ignore[arg-type]
        VerifierCall((FAKE_CONDITION,), ARGUMENTS, SUCCEEDED),  # type: ignore[arg-type]
    )


def test_verifier_refuses_a_failure_for_a_condition_it_does_not_know() -> None:
    with pytest.raises(ValueError, match="outside the vocabulary"):
        FakeVerifier(WRITE_NOTE, failures={"x.unknown": MISMATCH})


# --------------------------------------------------------------------------------------
# FakeModelProvider
# --------------------------------------------------------------------------------------


async def test_provider_fixed_reply_and_word_usage() -> None:
    provider = FakeModelProvider(FakeClock(), FakeIdGenerator(), reply="tre punti principali")
    result = await provider.complete(PROVIDER_REQUEST)
    assert result.output == "tre punti principali"
    assert result.model == "fake-model"
    assert result.finish_reason == "end_turn"
    assert result.error is None
    prompt = f"{PROVIDER_REQUEST.input} {PROVIDER_REQUEST.instructions}"
    assert result.usage.input_tokens == len(prompt.split())
    assert result.usage.output_tokens == 3
    assert provider.requests == (PROVIDER_REQUEST,)


async def test_provider_reply_can_depend_on_the_request() -> None:
    def echo(request: ProviderRequest) -> str:
        return request.input.upper()

    provider = FakeModelProvider(FakeClock(), FakeIdGenerator(), name="echo", reply=echo)
    result = await provider.complete(PROVIDER_REQUEST)
    assert result.output == PROVIDER_REQUEST.input.upper()
    assert result.provider == "echo"


async def test_provider_error_is_a_result_not_an_exception() -> None:
    provider = FakeModelProvider(FakeClock(), FakeIdGenerator(), error=ERROR_METADATA)
    request = PROVIDER_REQUEST.model_copy(update={"instructions": None})
    result = await provider.complete(request)
    assert result.error == ERROR_METADATA
    assert result.output == ""
    assert result.finish_reason == "error"
    assert result.usage.output_tokens == 0


async def test_a_provider_with_no_credentials_answers_without_working() -> None:
    """ADR 0020 §2: an UNAVAILABLE provider says so — a result, not an exception — and records
    no request, because nothing was ever asked of anyone."""
    provider = FakeModelProvider(
        FakeClock(), FakeIdGenerator(), name="dry", status=ProviderStatus.UNAVAILABLE
    )

    result = await provider.complete(PROVIDER_REQUEST)

    assert result.error is not None and result.error.code == PROVIDER_UNAVAILABLE
    assert result.error.retryable is False
    assert result.output == "" and result.model == ""
    assert result.provider == "dry"
    assert result.request_id == PROVIDER_REQUEST.id
    assert result.usage.input_tokens == result.usage.output_tokens == 0
    assert provider.requests == ()


# ----------------------------------------------------------------------------------------
# FakeModelRouter
# ----------------------------------------------------------------------------------------


def test_the_router_answers_with_the_route_it_was_given() -> None:
    router = FakeModelRouter(provider="second", profile="cheap", skipped=("first",))

    route = router.route("coding", None)

    assert (route.provider, route.profile, route.skipped) == ("second", "cheap", ("first",))
    assert router.calls == (("coding", None),)


def test_an_explicit_hint_wins_over_the_profile_of_the_route() -> None:
    """ADR 0022 §3, the way the real router does it: whoever wrote a hint has chosen."""
    assert FakeModelRouter(profile="cheap").route("coding", "quality").profile == "quality"


def test_a_router_that_cannot_route_raises_what_it_was_given() -> None:
    """How a test reaches the branches where nothing is sent: the call is still recorded, so a
    test can prove the tool asked before it gave up."""
    refused = RoutingError(ROUTING_UNKNOWN_TASK_TYPE, "no route for 'dancing'")
    router = FakeModelRouter(error=refused)

    with pytest.raises(RoutingError) as raised:
        router.route("dancing", None)

    assert raised.value is refused
    assert router.calls == (("dancing", None),)
