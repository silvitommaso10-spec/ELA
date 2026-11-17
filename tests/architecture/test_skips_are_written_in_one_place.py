"""**A skip is written in one place**: ``tests/machines.py`` (M9.5, ADR 0069 — ADR 0047 §18 paid).

A test says what of the machine it needs with ``needs(...)``, and the guard of that file decides —
skipped where the machine need not have it, red where it must. A ``skipif`` written anywhere else
is a precondition nobody guards: the form of the ninety that stood until 2026-11-17, and of the
three of M13.9b that kept ubuntu red for a week.

**What «a skip» is, decided by exclusion**: every ``pytest.mark.skipif``, ``pytest.mark.skip`` and
``pytest.mark.xfail``, every ``pytest.skip``, ``pytest.importorskip`` and ``pytest.xfail`` —
whatever it reads —, and the same names imported from ``pytest``. No list of the skips that are
allowed: the exemptions are two, each a condition with its reason, and each **proved necessary** —
taken away, the rule speaks (decision 68 of the review at ``ad1826c``):

* **the stories a kit of the conformance declares it cannot recite** (:func:`from_the_kit`): a
  ``pytest.skip`` whose condition is read from a kit's ``unsupported`` — the kit's data, which
  reads no machine. It names the condition, not the file;
* **the checks of the measure of M13.9, frozen** (:func:`frozen_and_held`):
  ``tests/scripts/misura_m13_9_checks.py`` is out of the collection — ``make misura-m13.9`` runs it
  —, it stands at ``d110bc3``, and its skips read the machine of a measure that is done. The
  exemption holds **while the test that keeps its digest keeps it**
  (``tests/scripts/test_misura_m13_9_frozen.py``): the file changed, or no longer held, and the
  rule speaks.
"""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Iterator
from pathlib import Path

from tests.scripts import test_misura_m13_9_frozen as frozen_checks

ROOT = Path(__file__).resolve().parents[2]
ONE_PLACE = "tests/machines.py"
MARKS = frozenset({"skipif", "skip", "xfail"})
"""What ``pytest.mark`` has that skips a test, or excuses its failure."""
CALLS = frozenset({"skip", "importorskip", "xfail"})
"""What ``pytest`` has that skips a test from inside, or excuses its failure."""


def _is(node: ast.expr, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _imported_from_pytest(tree: ast.Module) -> dict[str, str]:
    """The names a module binds from ``pytest``: what each local name is there."""
    return {
        alias.asname or alias.name: alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "pytest"
        for alias in node.names
    }


def _caught(tree: ast.Module) -> set[int]:
    """The ``pytest.skip`` of every ``pytest.raises(pytest.skip.Exception)``: a test **of** a skip —
    the kit's door, in ``tests/conformance/test_unsupported.py`` —, which skips nothing."""
    return {
        id(node.args[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "raises"
        and _is(node.func.value, "pytest")
        and node.args
        and isinstance(node.args[0], ast.Attribute)
        and node.args[0].attr == "Exception"
    }


def skips(tree: ast.Module) -> Iterator[ast.AST]:
    """Every skip written in ``tree``, as the node that writes it."""
    imported = _imported_from_pytest(tree)
    marks = {local for local, name in imported.items() if name == "mark"}
    caught = _caught(tree)
    for node in ast.walk(tree):
        if id(node) in caught:
            continue
        if isinstance(node, ast.Attribute):
            on_pytest = _is(node.value, "pytest") and node.attr in CALLS
            on_mark = node.attr in MARKS and (
                (
                    isinstance(node.value, ast.Attribute)
                    and node.value.attr == "mark"
                    and _is(node.value.value, "pytest")
                )
                or any(_is(node.value, local) for local in marks)
            )
            if on_pytest or on_mark:
                yield node
        elif isinstance(node, ast.Name) and imported.get(node.id) in CALLS:
            yield node


def from_the_kit(tree: ast.Module, skip: ast.AST) -> bool:
    """Whether ``skip`` is a ``pytest.skip`` **whose condition is a kit's declaration**: it is
    called under an ``if`` that tests a name, and that name is bound, in the same function, from
    something's ``unsupported`` — the stories a kit of the conformance says it cannot recite."""
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        declared = {
            target.id
            for node in ast.walk(function)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(part, ast.Attribute) and part.attr == "unsupported"
                for part in ast.walk(node.value)
            )
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        for branch in ast.walk(function):
            if not isinstance(branch, ast.If):
                continue
            tested = {part.id for part in ast.walk(branch.test) if isinstance(part, ast.Name)}
            inside = {id(part) for statement in branch.body for part in ast.walk(statement)}
            if tested & declared and id(skip) in inside:
                return True
    return False


def frozen_and_held(path: Path, root: Path = ROOT) -> bool:
    """Whether ``path`` is the file of the frozen checks of M13.9 **and** the test that keeps its
    digest keeps it: listed among the frozen files, with the digest written beside it equal to the
    file's own."""
    if path.resolve() != frozen_checks.CHECKS.resolve():
        return False
    if path.resolve() not in {one.resolve() for one in frozen_checks.frozen()}:
        return False
    written = frozen_checks.WRITTEN.read_text(encoding="utf-8")
    name = path.resolve().relative_to(root).as_posix()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"{digest}  {name}" in written.splitlines()


def written_outside(root: Path, *, kit: bool = True, frozen: bool = True) -> list[str]:
    """Every skip written under ``root / "tests"`` outside the one place — ``path:line: what`` —
    with the two exemptions, each of which can be taken away."""
    found = []
    for path in sorted((root / "tests").rglob("*.py")):
        name = path.relative_to(root).as_posix()
        if name == ONE_PLACE or (frozen and frozen_and_held(path, root)):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=name)
        for node in skips(tree):
            if kit and from_the_kit(tree, node):
                continue
            found.append(f"{name}:{getattr(node, 'lineno', 0)}: {ast.unparse(node)}")
    return found


def test_no_skip_is_written_outside_the_one_place() -> None:
    assert written_outside(ROOT) == []


def test_each_exemption_is_necessary_taken_away_the_rule_speaks() -> None:
    """The form of ``test_exemptions.py``: a door that nobody stands behind is found."""
    without_the_kit = written_outside(ROOT, kit=False)
    without_the_frozen = written_outside(ROOT, frozen=False)

    assert without_the_kit and all(
        one.startswith("tests/conformance/driver.py:") for one in without_the_kit
    ), without_the_kit
    assert without_the_frozen and all(
        one.startswith("tests/scripts/misura_m13_9_checks.py:") for one in without_the_frozen
    ), without_the_frozen


def a_suite(tmp_path: Path, **files: str) -> Path:
    """A suite built here: ``a__test_x`` is ``tests/a/test_x.py``."""
    for name, text in files.items():
        path = tmp_path / "tests" / (name.replace("__", "/") + ".py")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def test_a_skip_written_anywhere_else_is_seen_whatever_it_reads(tmp_path: Path) -> None:
    """The negative case, on a suite built here: every form, in a file of any name."""
    root = a_suite(
        tmp_path,
        machines=(
            "import pytest\n"
            "def needs(*c):\n"
            "    return pytest.mark.skipif(True, reason='the one place')\n"
        ),
        a__test_a="import pytest\n@pytest.mark.skipif(True, reason='r')\ndef test_x(): pass\n",
        a__test_b=(
            "import pytest\ndef test_y(flag):\n    if flag:\n        pytest.skip('inside')\n"
        ),
        a__helper="import pytest\nNEEDS = pytest.importorskip('nowhere')\n",
        a__test_c="import pytest\npytestmark = [pytest.mark.xfail(reason='x')]\n",
        a__test_d="from pytest import mark, skip\nM = mark.skip\ndef f(): skip('s')\n",
        a__test_e="import pytest\ndef test_z():\n    raise pytest.skip.Exception('raised')\n",
        a__test_f=(
            "import pytest\n"
            "def test_w():\n"
            "    with pytest.raises(pytest.skip.Exception):\n"
            "        pass\n"
        ),
    )
    found = written_outside(root)

    assert [one.split(":")[0] for one in found] == [
        "tests/a/helper.py",
        "tests/a/test_a.py",
        "tests/a/test_b.py",
        "tests/a/test_c.py",
        "tests/a/test_d.py",
        "tests/a/test_d.py",
        "tests/a/test_e.py",
    ], found
    assert "machines" not in " ".join(found), "the one place writes its own"


def test_the_kit_s_declaration_is_exempt_and_another_condition_beside_it_is_not(
    tmp_path: Path,
) -> None:
    kit = (
        "import pytest\n"
        "def needs(kit, story):\n"
        "    reason = kit.unsupported.get(story)\n"
        "    if reason is not None:\n"
        "        pytest.skip(reason)\n"
    )
    machine = (
        "import os, pytest\n"
        "def needs(kit, story):\n"
        "    reason = kit.unsupported.get(story)\n"
        "    if os.name == 'nt':\n"
        "        pytest.skip('not here')\n"
    )
    root = a_suite(tmp_path, k__driver=kit, m__driver=machine)

    assert written_outside(root) == ["tests/m/driver.py:5: pytest.skip"]


def test_the_frozen_checks_are_exempt_only_while_their_digest_is_held(tmp_path: Path) -> None:
    """The exemption is the test that keeps the digest: the file as it is, held — exempt; the same
    path with one byte more — not held, and the rule speaks."""
    held = frozen_checks.CHECKS

    assert frozen_and_held(held)
    assert not frozen_and_held(tmp_path / held.name)
    changed = tmp_path / "tests" / "scripts" / held.name
    changed.parent.mkdir(parents=True)
    changed.write_bytes(held.read_bytes() + b"\n")
    assert not frozen_and_held(changed, tmp_path)
