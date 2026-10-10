"""``Secret``: a value that is not printed, not serialised and not compared (M13.9, ADR 0063).

A password taken from the vault travels from one adapter to another through the tool that asked
for it, and the tool must not be able to leave it anywhere by accident: not in an outcome, a
message, an event or a log line. So the type that carries it shows nothing of itself to anything
that would write it down, and opens with one method — which architecture rule 68 lets only the
adapters, and the fakes that stand in for them, call.
"""

from __future__ import annotations

import copy
import json
import logging
import pickle
from typing import Any

import pytest

SENTINEL = "the-password-of-the-test-0f3a"


def secret(value: str = SENTINEL) -> Any:
    from ela.ports import Secret

    return Secret(value)


def test_it_opens_with_one_method_and_gives_back_what_it_was_given() -> None:
    assert secret().reveal() == SENTINEL


@pytest.mark.parametrize(
    "written",
    [
        lambda s: repr(s),
        lambda s: str(s),
        lambda s: f"{s}",
        lambda s: f"{s!r:>20}",
        lambda s: "%s and %r" % (s, s),  # noqa: UP031 — the form a log line uses
        lambda s: repr([s, {"k": s}, (s,)]),
        lambda s: format(s, ""),
    ],
    ids=["repr", "str", "f-string", "format spec", "percent", "inside a container", "format"],
)
def test_nothing_that_writes_it_down_writes_its_value(written: Any) -> None:
    said = written(secret())

    assert SENTINEL not in said
    assert "<secret>" in said


def test_a_log_line_that_is_handed_one_says_secret(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        logging.getLogger("ela.test").info("took %s for %r", secret(), secret())

    assert SENTINEL not in caplog.text
    assert "took <secret> for <secret>" in caplog.text


@pytest.mark.parametrize(
    "serialise",
    [json.dumps, pickle.dumps, copy.copy, copy.deepcopy],
    ids=["json", "pickle", "copy", "deepcopy"],
)
def test_it_is_not_serialised_and_not_copied(serialise: Any) -> None:
    with pytest.raises(TypeError):
        serialise(secret())


def test_a_secret_inside_what_is_serialised_stops_the_serialisation() -> None:
    with pytest.raises(TypeError):
        json.dumps({"password": secret()})


def test_it_is_not_compared_and_not_hashed() -> None:
    one, other = secret(), secret()

    with pytest.raises(TypeError, match="not compared"):
        _ = one == other
    with pytest.raises(TypeError, match="not compared"):
        _ = one != SENTINEL
    with pytest.raises(TypeError):
        hash(one)
    with pytest.raises(TypeError):
        _ = {one}


def test_it_has_no_length_no_items_and_no_attribute_to_read_it_from() -> None:
    one = secret()

    with pytest.raises(TypeError):
        len(one)
    with pytest.raises(TypeError):
        iter(one)
    with pytest.raises(TypeError):
        vars(one)
    assert "__dict__" not in dir(one), "no dictionary of attributes for a debugger to print"


def test_it_refuses_what_is_not_text() -> None:
    from ela.ports import Secret

    with pytest.raises(TypeError):
        Secret(b"bytes")  # type: ignore[arg-type]


def test_an_exception_that_carries_one_does_not_carry_its_value() -> None:
    try:
        raise RuntimeError("could not use", secret())
    except RuntimeError as error:
        assert SENTINEL not in repr(error) and SENTINEL not in str(error)
