"""``ela.permissions.scope``: path-prefix semantics, fail-safe on everything else (ADR 0011 §4)."""

from __future__ import annotations

import pytest

from ela.permissions import scope_covers, targets_of, within_scope
from tests.permissions.support import ECHO, NOTE, NOTE_ARGS

NOTES = ("workspace/notes",)


@pytest.mark.parametrize(
    "target",
    [
        "workspace/notes",
        "workspace/notes/briefing.md",
        "workspace/notes/2026/09/briefing.md",
    ],
)
def test_a_path_under_the_entry_is_within_scope(target: str) -> None:
    assert within_scope(NOTES, target)


@pytest.mark.parametrize(
    "target",
    [
        "workspace/notes-old/x.md",  # a sibling that shares the prefix as text, not as a path
        "workspace",  # the parent
        "workspace/note",
        "../workspace/notes/x.md",
        "workspace/../workspace/notes/x.md",
        "workspace/./notes/x.md",
        "/workspace/notes/x.md",
        "workspace/notes/",
        "workspace//notes/x.md",
        "workspace\\notes\\x.md",
        "",
        "other/notes/x.md",
    ],
)
def test_anything_else_is_outside(target: str) -> None:
    assert not within_scope(NOTES, target)


@pytest.mark.parametrize("target", [None, 42, 1.5, True, ["workspace/notes/x"], {"path": "x"}])
def test_a_non_string_target_is_outside(target: object) -> None:
    assert not within_scope(NOTES, target)


def test_any_entry_of_the_scope_may_cover_the_target() -> None:
    scope = ("workspace/notes", "workspace/drafts")
    assert within_scope(scope, "workspace/drafts/a.md")
    assert within_scope(scope, "workspace/notes/a.md")
    assert not within_scope(scope, "workspace/other/a.md")


def test_a_malformed_entry_protects_nothing() -> None:
    """The fake registry admits ``../x``; such an entry covers no target, not even itself."""
    assert not within_scope(("../x",), "../x/a.md")
    assert not within_scope(("/abs",), "/abs/a.md")
    assert not within_scope(("",), "anything")
    assert within_scope(("../x", "ok"), "ok/a.md")


def test_an_empty_scope_covers_no_target() -> None:
    assert not within_scope((), "workspace/notes/a.md")


# --------------------------------------------------------------------------------------
# scope_covers: the whole call
# --------------------------------------------------------------------------------------


def test_every_target_must_be_inside() -> None:
    assert scope_covers(NOTES, ("workspace/notes/a.md", "workspace/notes/b.md"))
    assert not scope_covers(NOTES, ("workspace/notes/a.md", "elsewhere/b.md"))
    assert not scope_covers(NOTES, ("workspace/notes/a.md", None))


def test_no_scope_and_no_targets_is_covered() -> None:
    assert scope_covers((), ())


def test_a_scope_that_constrains_nothing_is_a_doubt() -> None:
    assert not scope_covers(NOTES, ())


def test_no_scope_with_targets_covers_none() -> None:
    assert not scope_covers((), ("workspace/notes/a.md",))


# --------------------------------------------------------------------------------------
# targets_of
# --------------------------------------------------------------------------------------


def test_targets_are_the_scoped_arguments_in_declaration_order() -> None:
    assert targets_of(NOTE, NOTE_ARGS) == ("workspace/notes/briefing.md",)
    two = NOTE.model_copy(update={"scoped_arguments": ("body", "path")})
    assert targets_of(two, NOTE_ARGS) == ("...", "workspace/notes/briefing.md")


def test_a_missing_scoped_argument_is_a_none_target() -> None:
    assert targets_of(NOTE, {"body": "..."}) == (None,)


def test_a_capability_without_scoped_arguments_has_no_targets() -> None:
    assert targets_of(ECHO, {"message": "hi", "path": "workspace/notes/x"}) == ()
