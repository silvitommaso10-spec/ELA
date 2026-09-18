"""The vocabulary of the wire, held honest in both directions (M12.4).

``error.code`` is what a client branches on (ADR 0023 §10), and a node branches on it exactly where
a status cannot tell two answers apart. Until M12.4 the code was a string written wherever it was
needed — the API's table, a node's constants, a node's tests — and nothing compared the three. The
node's tests scripted ``renewal.capped``, ``too_late`` and ``code_reused``, which no Core has ever
sent, and passed: three invented codes in one place are not three slips, they are a list that does
not know it is false.

So there is one list, :class:`~ela.ports.WireCode`, and two directions to hold:

* **every code the API emits is a member** — :func:`~ela.api.problems.problem` takes nothing else,
  and it is called from exactly the two places whose codes :func:`emitted` reads;
* **every member is emitted by someone** — a code in the vocabulary that nothing sends is a branch a
  client can write and no answer can ever take.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Iterable
from pathlib import Path
from typing import get_type_hints

import pytest

import ela.api
from ela.api.app import FAILURES
from ela.api.problems import problem
from ela.api.security import unauthorized
from ela.ports import WireCode

API = Path(ela.api.__file__).parent

EMITTERS = frozenset({("app.py", "handle"), ("security.py", "unauthorized")})
"""Where the API builds a refusal: the handler of the table, and the middleware's one answer.

A third place fails :func:`test_the_api_builds_a_refusal_in_two_places_only` until :func:`emitted`
reads its codes too — otherwise it could send a member that nobody here counted."""


FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def callers_of_problem(root: Path) -> set[tuple[str, str]]:
    """``(file, innermost enclosing function)`` for every call to ``problem`` under ``root``."""
    found: set[tuple[str, str]] = set()
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for call in ast.walk(tree):
            if not (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "problem"
            ):
                continue
            scope = parents.get(call)
            while scope is not None and not isinstance(scope, FUNCTIONS):
                scope = parents.get(scope)
            name = "<module>" if scope is None else scope.name
            found.add((path.relative_to(root).as_posix(), name))
    return found


def emitted() -> set[str]:
    """The codes the API sends: every row of the table, and the middleware's refusal — read off a
    real answer rather than off the constant it is built from."""
    refusal = json.loads(unauthorized().body)["error"]["code"]
    return {failure.code.value for failure in FAILURES} | {refusal}


def unmatched(vocabulary: Iterable[str], sent: Iterable[str]) -> tuple[set[str], set[str]]:
    """``(sent but not in the vocabulary, in the vocabulary but never sent)``."""
    words, codes = set(vocabulary), set(sent)
    return codes - words, words - codes


def test_the_api_builds_a_refusal_in_two_places_only() -> None:
    assert callers_of_problem(API) == EMITTERS


def test_every_code_the_api_emits_is_in_the_vocabulary() -> None:
    """The first direction. ``problem`` takes a member, the table holds members, and what goes out
    on the wire — read back as JSON — is in the vocabulary."""
    assert get_type_hints(problem)["code"] is WireCode
    assert all(isinstance(failure.code, WireCode) for failure in FAILURES)

    sent_but_unknown, _ = unmatched((code.value for code in WireCode), emitted())

    assert sent_but_unknown == set()


def test_every_member_of_the_vocabulary_is_emitted_by_someone() -> None:
    """The second direction: a member nothing sends would be a branch nobody can reach."""
    _, never_sent = unmatched((code.value for code in WireCode), emitted())

    assert never_sent == set()


# ----------------------------------------------------------------------------------------
# Negative cases: what each check catches
# ----------------------------------------------------------------------------------------


def test_a_code_outside_the_vocabulary_and_a_member_nobody_sends_are_both_caught() -> None:
    assert unmatched({"not_found", "conflict"}, {"not_found", "too_late"}) == (
        {"too_late"},
        {"conflict"},
    )


def test_a_third_place_that_builds_a_refusal_is_caught(tmp_path: Path) -> None:
    (tmp_path / "route.py").write_text(
        "def answer(code):\n    return problem(code, 'x')\n", encoding="utf-8"
    )
    (tmp_path / "nested.py").write_text(
        "def outer():\n    def inner(code):\n        return problem(code, 'x')\n    return inner\n",
        encoding="utf-8",
    )

    assert callers_of_problem(tmp_path) == {("route.py", "answer"), ("nested.py", "inner")}


def test_a_string_is_not_a_code() -> None:
    """What ``mypy --strict`` refuses in ``src/``, refused at run time too: a string has no
    ``.value``, so an invented code cannot become a body."""
    with pytest.raises(AttributeError):
        problem("too_late", "a code no Core sends")  # type: ignore[arg-type]
