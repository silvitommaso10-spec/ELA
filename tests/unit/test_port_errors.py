"""What a port says when a key is not there (ADR 0005; review of M8.2).

The message of a miss is not decoration: it crosses the API in the body of a 404 and reaches a
person through ``ela task show``. What it must carry is the identifier they typed and can paste
into the next command.
"""

from __future__ import annotations

import uuid

import pytest

from ela.ports import AlreadyExistsError, NotFoundError, named

TASK_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


def test_a_uuid_is_named_in_its_canonical_form() -> None:
    """``repr`` would give ``UUID('…')``: Python's syntax for building one, not an identifier."""
    assert named(TASK_ID) == "11111111-1111-4111-8111-111111111111"
    assert "UUID(" not in named(TASK_ID)


@pytest.mark.parametrize(
    ("key", "expected"),
    [("core.echo", "'core.echo'"), ("", "''"), (" padded ", "' padded '")],
    ids=["name", "empty", "padded"],
)
def test_a_string_key_keeps_its_quotes(key: str, expected: str) -> None:
    """An empty or space-padded key has to stay visible: that is what the quotes are for."""
    assert named(key) == expected


def test_the_miss_names_the_kind_and_the_key() -> None:
    error = NotFoundError("task", TASK_ID)

    assert str(error) == f"task {TASK_ID} not found"
    assert (error.kind, error.key) == ("task", TASK_ID)


def test_the_duplicate_names_them_too() -> None:
    error = AlreadyExistsError("audit event", TASK_ID)

    assert str(error) == f"audit event {TASK_ID} already exists"
    assert (error.kind, error.key) == ("audit event", TASK_ID)
