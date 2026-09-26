"""The channel of numbers into ``TOOL_EXECUTED``: keys the tool declares, integers by type (M13.2).

Decision 10, confirmed at the resumption (Domanda 2; ADR 0047): the first door through which a
tool writes facts of its own into a log that is never redacted, and so it is built narrow. A tool
declares — **without a default**, like ``idempotent`` — the closed set of the keys of its result
that go into the audit; the registry refuses a tool that declares nothing and a key that is not in
its result; and the one function that reads the values lets through integers and ``None`` and
refuses anything else **by type**: a string, a float, a boolean, a list.
"""

from __future__ import annotations

import pytest

from ela.domain import CapabilityId
from ela.ports import audited_numbers
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeTool
from ela.tools import EchoTool, Tool, ToolRegistry
from ela.tools.errors import UndeclaredNumbersError

ECHO = CapabilityId("core.echo")


def test_the_values_of_the_declared_keys_are_read_through_the_result() -> None:
    output = {"count": 2, "stream": {"total": 10, "head": "not asked"}, "free": "text"}

    assert audited_numbers(frozenset({"count", "stream.total", "absent"}), output) == {
        "absent": None,
        "count": 2,
        "stream.total": 10,
    }


def test_nothing_declared_is_nothing_read() -> None:
    assert audited_numbers(frozenset(), {"count": "whatever"}) == {}


@pytest.mark.parametrize("value", ["3", 3.0, True, [3], {"n": 3}])
def test_a_value_that_is_not_an_integer_is_refused_by_its_type(value: object) -> None:
    """The negative case: a string cannot pass, and neither can what is almost a number."""
    with pytest.raises(ValueError) as caught:
        audited_numbers(frozenset({"count"}), {"count": value})

    assert "count" in str(caught.value)
    assert type(value).__name__ in str(caught.value)
    assert repr(value) not in str(caught.value), "the key and the type, never the value"


def test_a_path_through_something_that_is_not_an_object_is_refused() -> None:
    with pytest.raises(ValueError):
        audited_numbers(frozenset({"stream.total"}), {"stream": "10 bytes"})


def test_every_tool_declares_its_numbers_and_none_inherits_them() -> None:
    assert not hasattr(Tool, "audit_numbers"), "the base gives no default to inherit by mistake"
    assert EchoTool.audit_numbers == frozenset()


def test_a_tool_that_declares_no_numbers_is_refused_at_registration() -> None:
    class _Silent:
        capability_id = ECHO
        name = "silent"
        idempotent = True
        relocatable = True

    with pytest.raises(UndeclaredNumbersError) as caught:
        ToolRegistry((_Silent(),))  # type: ignore[arg-type]

    assert "audit_numbers" in str(caught.value)


def test_a_declared_key_that_is_not_in_the_result_is_refused_at_registration() -> None:
    tool = FakeTool(ECHO, FakeClock(), FakeIdGenerator(), audit_numbers=frozenset({"elsewhere"}))
    tool.output_keys = frozenset({"message"})

    with pytest.raises(UndeclaredNumbersError) as caught:
        ToolRegistry((tool,))

    assert "elsewhere" in str(caught.value)


def test_a_key_through_a_declared_result_key_is_accepted() -> None:
    tool = FakeTool(ECHO, FakeClock(), FakeIdGenerator(), audit_numbers=frozenset({"out.total"}))
    tool.output_keys = frozenset({"out"})

    assert ToolRegistry((tool,)).get(ECHO) is tool
