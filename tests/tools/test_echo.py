"""``EchoTool`` (§29, SAFE): returns its message, refuses what the contract refuses."""

from __future__ import annotations

from datetime import timedelta

import pytest

from ela.domain import ExecutionStatus, PermissionOutcome
from ela.ports import NotAllowedError
from ela.testing.fakes import FakeClock, FakeIdGenerator
from ela.tools import ARGUMENTS_INVALID, CORE_ECHO, ECHO_TOOL_NAME, EchoTool
from tests.tools.support import allowed


@pytest.fixture
def tool() -> EchoTool:
    return EchoTool(FakeClock(), FakeIdGenerator())


async def test_echoes_the_message(tool: EchoTool) -> None:
    decision = allowed(CORE_ECHO)
    result = await tool.execute(decision, {"message": "hello"})
    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.output == {"message": "hello"}
    assert result.error is None
    assert result.capability_id == CORE_ECHO
    assert result.tool_name == ECHO_TOOL_NAME == tool.name
    assert (result.task_id, result.step_id) == (decision.task_id, decision.step_id)
    assert result.duration_ms == 0


async def test_duration_is_measured_on_the_tools_clock() -> None:
    clock = FakeClock()

    class SlowClock:
        def now(self):  # type: ignore[no-untyped-def]
            instant = clock.now()
            clock.advance(timedelta(milliseconds=250))
            return instant

    tool = EchoTool(SlowClock(), FakeIdGenerator())
    result = await tool.execute(allowed(CORE_ECHO), {"message": "hi"})
    assert result.duration_ms == 250


@pytest.mark.parametrize("arguments", [{}, {"message": 42}, {"message": None}], ids=repr)
async def test_a_message_that_is_not_a_string_fails_with_a_code(
    tool: EchoTool, arguments: dict[str, object]
) -> None:
    result = await tool.execute(allowed(CORE_ECHO), arguments)
    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert result.error.code == ARGUMENTS_INVALID
    assert result.error.tool_name == tool.name
    assert result.output == {}


async def test_the_contract_is_checked_before_anything(tool: EchoTool) -> None:
    with pytest.raises(NotAllowedError, match="outcome is DENIED"):
        await tool.execute(allowed(CORE_ECHO, outcome=PermissionOutcome.DENIED), {"message": "x"})
    with pytest.raises(NotAllowedError, match="is about workspace.write_note"):
        await tool.execute(
            allowed(tool.capability_id).model_copy(
                update={"capability_id": "workspace.write_note"}
            ),
            {"message": "x"},
        )
    with pytest.raises(NotAllowedError, match="expired"):
        await tool.execute(allowed(CORE_ECHO, expires_at=FakeClock().now()), {"message": "x"})


def test_declares_its_output_and_error_codes() -> None:
    assert EchoTool.output_keys == {"message"}
    assert EchoTool.error_codes == {ARGUMENTS_INVALID}
