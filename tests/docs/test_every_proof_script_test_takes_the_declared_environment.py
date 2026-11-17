"""**Every test of a script of a proof takes the declared environment** (M9.5, ADR 0069; annotated
on 2026-10-12 by the review of M13.9, decision 113).

The scripts of the proofs by hand (``scripts/prova_*.py``) read ELA's settings, and a ``.env`` in
the folder the suite runs in, or an ``ELA_`` variable of whoever launches it, would change what
their tests see: a variable left empty does not hide the line of a file. The fixture that takes both
away is ``_only_the_declared_environment`` (``tests/composition/support.py``): autouse, it deletes
every ``ELA_`` variable and moves the test into its own folder.

**Found from the source, not from a list**: a module of the suite that names a script of a proof —
the path it loads, the glob it walks, the import of the module that holds its path — takes the
fixture where pytest gives it: bound in the module,
or in a ``conftest.py`` of its folder or of one above it, up to ``tests/``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = "_only_the_declared_environment"
A_PROOF = re.compile(r"(?:^|/)prova_[\w*]+\.py$")
"""How a module names a script of a proof: its file, or the glob of all of them."""


def bound(tree: ast.Module) -> set[str]:
    """The names a module binds at its top: what it imports, defines and assigns."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def names_a_proof(tree: ast.Module) -> bool:
    """Whether a module names a script of a proof: a path or a glob of one, or an import from a
    module of one — the script, or the test that holds its path."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found = A_PROOF.search(node.value) is not None
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            found = node.module.split(".")[-1].startswith(("prova_", "test_prova_"))
        elif isinstance(node, ast.Import):
            found = any(one.name.split(".")[-1].startswith("prova_") for one in node.names)
        else:
            found = False
        if found:
            return True
    return False


def without_the_environment(root: Path) -> list[str]:
    """The modules of ``root / "tests"`` that name a script of a proof and do not take the
    fixture."""
    tests = root / "tests"
    missing = []
    for path in sorted(tests.rglob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if not names_a_proof(tree):
            continue
        given = FIXTURE in bound(tree)
        folder = path.parent
        while not given and folder.is_relative_to(tests):
            conftest = folder / "conftest.py"
            if conftest.is_file():
                given = FIXTURE in bound(ast.parse(conftest.read_text(encoding="utf-8")))
            folder = folder.parent
        if not given:
            missing.append(path.relative_to(root).as_posix())
    return missing


def test_every_test_of_a_script_of_a_proof_takes_the_declared_environment() -> None:
    assert without_the_environment(ROOT) == []


def test_a_module_that_names_a_proof_without_the_fixture_is_seen(tmp_path: Path) -> None:
    """The negative case, on a suite built here: a module that loads a script by its path, one that
    walks the glob, one that takes the fixture itself, one that has it from the ``conftest.py`` of
    its folder, and one that names no proof."""
    files = {
        "tests/docs/test_a.py": 'SCRIPT = "scripts/prova_m1.py"\n',
        "tests/docs/test_b.py": 'FOUND = sorted(Path("scripts").glob("prova_*.py"))\n',
        "tests/docs/test_c.py": (
            "from tests.composition.support import _only_the_declared_environment\n"
            'SCRIPT = "prova_m2.py"\n'
        ),
        "tests/cli/conftest.py": (
            "from tests.composition.support import _only_the_declared_environment\n"
        ),
        "tests/cli/test_d.py": 'SCRIPT = "scripts/prova_m3.py"\n',
        "tests/cli/test_e.py": 'SCRIPT = "scripts/other.py"\n',
        "tests/scripts/test_f.py": "from tests.docs.test_prova_m1 import SCRIPT\n",
    }
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text, encoding="utf-8")

    assert without_the_environment(tmp_path) == [
        "tests/docs/test_a.py",
        "tests/docs/test_b.py",
        "tests/scripts/test_f.py",
    ]
