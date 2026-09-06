"""``core.echo`` (spec §29): the tool that proves the pipeline works end to end."""

from __future__ import annotations

from typing import ClassVar, Final

from ela.domain import CapabilityId, JsonMapping
from ela.ports import Clock, IdGenerator
from ela.tools.base import ARGUMENTS_INVALID, Outcome, Tool

__all__ = ["CORE_ECHO", "ECHO_TOOL_NAME", "EchoTool"]

CORE_ECHO: Final = CapabilityId("core.echo")
ECHO_TOOL_NAME: Final = "core-echo"


class EchoTool(Tool):
    """Returns the ``message`` it receives, as ``output["message"]`` (§29, SAFE).

    Nothing leaves the process and nothing is written: the tool exists so that a decision, a
    tool call and a ``TOOL_EXECUTED`` event can be followed through the system with no side
    effect to clean up.
    """

    output_keys: ClassVar[frozenset[str]] = frozenset({"message"})
    idempotent: ClassVar[bool] = True
    """Nothing is written and nothing leaves the process: a second run is the first one."""

    def __init__(self, clock: Clock, ids: IdGenerator, *, name: str = ECHO_TOOL_NAME) -> None:
        super().__init__(CORE_ECHO, clock, ids, name=name)

    async def _run(self, arguments: JsonMapping) -> Outcome:
        message = arguments.get("message")
        if not isinstance(message, str):
            return Outcome({}, ARGUMENTS_INVALID, "message must be a string")
        return Outcome({"message": message})
