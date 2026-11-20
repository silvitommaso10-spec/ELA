"""**Every way a test makes the code of a script run is one the fences recognise** (M13.17b,
decision 3): derived with the AST, as ``importers`` of ``test_generate_stato.py`` derives who loads
the generator, and not listed.

The fences recognise a script by the file of a frame, resolved: a file inside ``scripts/``. So what
a test loads **by a path** — ``spec_from_file_location``, ``SourceFileLoader``, ``run_path`` — must
resolve inside ``scripts/``, and so must the name of the file a test **compiles** code of a script
with (``exec`` of a ``compile`` whose source is not the test's own constant); what it loads **by a
name** reaches a script only through a folder put on ``sys.path``, which must be ``scripts/`` itself
— the siblings of a proof, from the test that loads it or from the script that puts its own folder
there —; and **a copy loaded from another folder, a script launched as a child process** — named
in the text of the launch or in the value of an argument the evaluator reads —, **or the code of a
script written into a file** — an attribute of a module a loader of the tests gives back — are
where the fences do not reach: each is found, and named in :data:`OUT_OF_REACH` with what holds for
it.

**A name built while the test runs** — ``import_module`` of the modules of a package of ela's —
is not read: it is a load of a script only if it says ``scripts`` or the name of one, and then it is
one by name, refused here. A script is reached by name only from a folder of ``scripts/`` on the
path, and the tests put it there only while they load a proof by its path.

**A path the small evaluator below cannot read fails the test**: write it in a form it reads — a
constant, a name bound to ``Path(__file__)``, ``/``, ``.parent``, ``.parents[n]``, ``.resolve()``,
``.with_name()``, a ``glob`` of ``scripts/``, the values of a ``parametrize``, the argument a
function of the tests is called with.
"""

from __future__ import annotations

import ast
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest

ROOT: Final = Path(__file__).resolve().parents[2]
SCRIPTS: Final = Path(os.path.realpath(ROOT / "scripts"))
BY_PATH: Final = frozenset({"spec_from_file_location", "SourceFileLoader", "run_path"})
"""The calls that load a module from a file: the argument that names the file."""
LAUNCHES: Final = frozenset(
    {"run", "Popen", "call", "check_call", "check_output", "create_subprocess_exec", "system"}
)
BY_NAME: Final = frozenset({"import_module", "__import__", "run_module"})
STEMS: Final = frozenset(path.stem for path in SCRIPTS.glob("*.py"))
"""The names a script would be imported by: the files of the folder, read when the test runs."""
OUT_OF_REACH: Final[dict[str, str]] = {
    "tests/scripts/test_misura_m13_11_windows.py:FIRST": (
        "B3's first program — it prints two lines and nothing else — written into the test's "
        "folder and run by PowerShell, whose launch the test names exactly: a grandchild of the "
        "test, which no fence sees"
    ),
    "tests/scripts/test_misura_m13_11_windows.py:SECOND": (
        "B3's second program — it writes the bytes it receives into the file of the test's "
        "folder it is given — written and run as the first"
    ),
}
"""Where the fences do not reach — a copy of a script loaded from another folder, a script
launched as a child, the code of a script written into a file —, by ``file:attribute`` or
``file:line``, with what holds for it. On 2026-11-20 (the re-read of 25afb1e) the programs of B3 of
``scripts/misura_m13_11.py``, which the test of Windows runs through both PowerShells."""


class Unreadable(Exception):
    """A path the evaluator cannot read: written in another form, or named."""


@dataclass(frozen=True)
class Under:
    """Every file a ``glob`` of a folder finds: inside that folder by construction."""

    folder: Path


Value = Path | str | Under | int


@dataclass(frozen=True)
class Module:
    path: Path
    tree: ast.Module

    @property
    def where(self) -> str:
        return self.path.relative_to(ROOT).as_posix()


def modules(roots: Iterable[Path]) -> list[Module]:
    return [
        Module(path, ast.parse(path.read_text(encoding="utf-8")))
        for root in roots
        for path in sorted(root.rglob("*.py"))
    ]


def bound_at_top(module: Module) -> dict[str, ast.expr]:
    found: dict[str, ast.expr] = {}
    for node in module.tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else []
        if isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                found[target.id] = node.value  # type: ignore[assignment]
    return found


def functions(module: Module) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in ast.walk(module.tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)  # type: ignore[misc]
    }


def parents(module: Module) -> dict[ast.AST, ast.AST]:
    return {child: node for node in ast.walk(module.tree) for child in ast.iter_child_nodes(node)}


class Evaluator:
    """What a path of the tests is, read and never run."""

    def __init__(self, everything: list[Module], *, callers: bool = True) -> None:
        self.callers = callers
        """Whether a parameter is read at the calls of its function — not for the arguments of a
        launch, which are many and mostly the test's own programs."""
        self.modules = {module.path: module for module in everything}
        self.owners: dict[Path, dict[ast.AST, ast.AST]] = {}
        self.by_dotted = {
            ".".join(module.path.relative_to(ROOT).with_suffix("").parts): module
            for module in everything
        }

    def owner(self, module: Module) -> dict[ast.AST, ast.AST]:
        if module.path not in self.owners:
            self.owners[module.path] = parents(module)
        return self.owners[module.path]

    def values(self, node: ast.expr, module: Module, scope: ast.AST | None) -> set[Value]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str | int):
            return {node.value}
        if isinstance(node, ast.Name):
            return self.name(node.id, module, scope)
        if isinstance(node, ast.JoinedStr):
            return self.joined(node, module, scope)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return {
                Path(left) / str(right) if not isinstance(left, Under) else left
                for left in self.values(node.left, module, scope)
                for right in self.values(node.right, module, scope)
                if isinstance(left, Path | Under)
            }
        if isinstance(node, ast.Attribute) and node.attr == "parent":
            return {Path(one).parent for one in self.paths(node.value, module, scope)}
        if isinstance(node, ast.Attribute) and node.attr == "stem":
            return {Path(one).stem for one in self.paths(node.value, module, scope)}
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "parents"
            and isinstance(node.slice, ast.Constant)
        ):
            index = node.slice.value
            return {Path(one).parents[index] for one in self.paths(node.value.value, module, scope)}
        if isinstance(node, ast.Call):
            return self.called(node, module, scope)
        if (
            isinstance(node, ast.ListComp | ast.GeneratorExp | ast.SetComp)
            and len(node.generators) == 1
            and isinstance(node.generators[0].target, ast.Name)
            and isinstance(node.elt, ast.Name)
            and node.elt.id == node.generators[0].target.id
        ):
            return self.values(node.generators[0].iter, module, scope)
        raise Unreadable(f"{module.where}:{node.lineno}: {ast.unparse(node)}")

    def paths(self, node: ast.expr, module: Module, scope: ast.AST | None) -> set[Path]:
        found = self.values(node, module, scope)
        return {one for one in found if isinstance(one, Path)} | {
            Path(one) for one in found if isinstance(one, str)
        }

    def joined(self, node: ast.JoinedStr, module: Module, scope: ast.AST | None) -> set[Value]:
        texts = {""}
        for part in node.values:
            if isinstance(part, ast.Constant):
                texts = {text + str(part.value) for text in texts}
            elif isinstance(part, ast.FormattedValue):
                texts = {
                    text + str(value)
                    for text in texts
                    for value in self.values(part.value, module, scope)
                }
        return set(texts)

    def called(self, node: ast.Call, module: Module, scope: ast.AST | None) -> set[Value]:
        func = node.func
        if isinstance(func, ast.Name) and func.id == "Path":
            argument = node.args[0]
            if isinstance(argument, ast.Name) and argument.id == "__file__":
                return {module.path}
            return {Path(str(one)) for one in self.values(argument, module, scope)}
        if isinstance(func, ast.Attribute) and func.attr in ("resolve", "absolute"):
            return {Path(os.path.realpath(one)) for one in self.paths(func.value, module, scope)}
        if isinstance(func, ast.Attribute) and func.attr == "with_name":
            names = self.values(node.args[0], module, scope)
            return {
                Path(one).with_name(str(name))
                for one in self.paths(func.value, module, scope)
                for name in names
            }
        if isinstance(func, ast.Attribute) and func.attr == "glob":
            return {Under(Path(one)) for one in self.paths(func.value, module, scope)}
        if isinstance(func, ast.Name) and func.id in ("sorted", "str", "list", "tuple"):
            return self.values(node.args[0], module, scope)
        if ast.unparse(func) in ("os.fspath", "os.path.realpath"):
            return self.values(node.args[0], module, scope)
        if isinstance(func, ast.Name):
            target = self.function(func.id, module)
            if target is not None:
                owner, defined = target
                returns = [one for one in ast.walk(defined) if isinstance(one, ast.Return)]
                if returns and all(one.value is not None for one in returns):
                    return set().union(
                        *(self.values(one.value, owner, defined) for one in returns if one.value)
                    )
        raise Unreadable(f"{module.where}:{node.lineno}: {ast.unparse(node)}")

    def function(self, name: str, module: Module) -> tuple[Module, ast.FunctionDef] | None:
        here = functions(module)
        if name in here:
            return module, here[name]
        for node in module.tree.body:
            if isinstance(node, ast.ImportFrom) and node.module in self.by_dotted:
                for alias in node.names:
                    if (alias.asname or alias.name) == name:
                        other = self.by_dotted[node.module]
                        found = functions(other).get(alias.name)
                        return (other, found) if found is not None else None
        return None

    def name(self, name: str, module: Module, scope: ast.AST | None) -> set[Value]:
        while scope is not None:
            if isinstance(scope, COMPREHENSIONS):
                for generator in scope.generators:
                    if isinstance(generator.target, ast.Name) and generator.target.id == name:
                        return self.values(
                            generator.iter, module, enclosing(scope, self.owner(module))
                        )
            else:
                parameter = self.parameter(name, module, scope)
                if parameter is not None:
                    return parameter
                local = self.local(name, module, scope)
                if local is not None:
                    return local
            scope = enclosing(scope, self.owner(module))
        top = bound_at_top(module)
        if name in top:
            return self.values(top[name], module, None)
        for node in module.tree.body:
            if isinstance(node, ast.ImportFrom) and node.module in self.by_dotted:
                for alias in node.names:
                    if (alias.asname or alias.name) == name:
                        other = self.by_dotted[node.module]
                        return self.name(alias.name, other, None)
        raise Unreadable(f"{module.where}: the name {name}")

    def local(self, name: str, module: Module, scope: ast.AST) -> set[Value] | None:
        for node in ast.walk(scope):
            if (
                isinstance(node, ast.For)
                and isinstance(node.target, ast.Name)
                and node.target.id == name
            ):
                return self.values(node.iter, module, scope)
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == name for target in node.targets
            ):
                return self.values(node.value, module, scope)
        return None

    def parameter(self, name: str, module: Module, scope: ast.AST) -> set[Value] | None:
        if not isinstance(scope, ast.FunctionDef | ast.AsyncFunctionDef):  # type: ignore[misc]
            return None
        names = [argument.arg for argument in scope.args.args]
        if name not in names:
            return None
        if not self.callers:
            raise Unreadable(f"{module.where}:{scope.lineno}: the parameter {name}")
        index = names.index(name)
        found = self.parametrized(name, scope, module)
        if found is not None:
            return found
        values: set[Value] = set()
        for caller, call, within in self.calls_of(scope.name, module):
            given = call.args[index] if index < len(call.args) else None
            if given is None:
                raise Unreadable(f"{caller.where}:{call.lineno}: {scope.name} without {name}")
            values |= self.values(given, caller, within)
        if not values:
            raise Unreadable(f"{module.where}:{scope.lineno}: nobody calls {scope.name}")
        return values

    def parametrized(self, name: str, scope: ast.FunctionDef, module: Module) -> set[Value] | None:
        for decorator in scope.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and ast.unparse(decorator.func).endswith("parametrize")
                and isinstance(decorator.args[0], ast.Constant)
                and decorator.args[0].value == name
            ):
                given = decorator.args[1]
                if not isinstance(given, ast.List | ast.Tuple):
                    return self.values(given, module, None)
                found: set[Value] = set()
                for one in given.elts:
                    if isinstance(one, ast.Call) and ast.unparse(one.func).endswith("param"):
                        one = one.args[0]
                    found |= self.values(one, module, None)
                return found
        return None

    def calls_of(self, name: str, defined_in: Module) -> Iterator[tuple[Module, ast.Call, ast.AST]]:
        dotted = ".".join(defined_in.path.relative_to(ROOT).with_suffix("").parts)
        for module in self.modules.values():
            local = {name} if module is defined_in else set()
            for node in module.tree.body:
                if isinstance(node, ast.ImportFrom) and node.module == dotted:
                    local |= {
                        alias.asname or alias.name for alias in node.names if alias.name == name
                    }
            for node in ast.walk(module.tree):
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):  # type: ignore[misc]
                    for inner in ast.walk(node):
                        if (
                            isinstance(inner, ast.ImportFrom)
                            and inner.module == dotted
                            and any(alias.name == name for alias in inner.names)
                        ):
                            local |= {
                                alias.asname or alias.name
                                for alias in inner.names
                                if alias.name == name
                            }
            if not local:
                continue
            owner = parents(module)
            for node in ast.walk(module.tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in local
                ):
                    yield module, node, enclosing(node, owner)


COMPREHENSIONS: Final = (ast.ListComp, ast.GeneratorExp, ast.SetComp, ast.DictComp)
SCOPES: Final = (ast.FunctionDef, ast.AsyncFunctionDef, *COMPREHENSIONS)


def enclosing(node: ast.AST, owner: dict[ast.AST, ast.AST]) -> ast.AST | None:
    """The nearest function or comprehension around ``node``: where its names are bound."""
    while node in owner:
        node = owner[node]
        if isinstance(node, SCOPES):
            return node
    return None


def called_name(node: ast.Call) -> str:
    return getattr(node.func, "attr", getattr(node.func, "id", ""))


def inside_the_scripts(value: Value) -> bool:
    if isinstance(value, Under):
        return Path(os.path.realpath(value.folder)) == SCRIPTS
    return isinstance(value, Path) and Path(os.path.realpath(value)).is_relative_to(SCRIPTS)


@dataclass(frozen=True)
class Way:
    where: str
    how: str
    loads: frozenset[Value]


def loaders(everything: Iterable[Module]) -> frozenset[str]:
    """The functions of the tests that load a module by a path: what they give back is a script's
    module, whose attributes are the script's code."""
    return frozenset(
        function.name
        for module in everything
        for function in ast.walk(module.tree)
        if isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef)
        and any(
            isinstance(call, ast.Call) and called_name(call) in BY_PATH
            for call in ast.walk(function)
        )
    )


def a_script_s_module(node: ast.expr, given: frozenset[str], bound: set[str]) -> bool:
    """Whether ``node`` is the module of a script: a call of a loader, or a name bound to one."""
    if isinstance(node, ast.Call):
        return called_name(node) in given
    return isinstance(node, ast.Name) and node.id in bound


def launched(node: ast.Call, evaluator: Evaluator, module: Module, scope: ast.AST | None) -> bool:
    """Whether a launch names a file of ``scripts/``: in its text, or in the value of one of its
    arguments the evaluator reads — what it cannot read is a program of the test's."""
    if "scripts/" in ast.unparse(node):
        return True
    arguments: list[ast.expr] = []
    for argument in node.args:
        arguments.extend(
            argument.elts if isinstance(argument, ast.List | ast.Tuple) else [argument]
        )
    for argument in arguments:
        try:
            values = evaluator.values(argument, module, scope)
        except Unreadable:
            continue
        if any(inside_the_scripts(one) for one in values if not isinstance(one, str | int)):
            return True
    return False


def ways(everything: list[Module], tests: Iterable[Module]) -> list[Way]:
    """Every way a module of ``tests`` makes the code of a script run: the loads by a path, the
    code compiled with a file's name, the folders put on ``sys.path``, the launches that name a
    file of ``scripts/``, and the code of a script written into a file."""
    evaluator = Evaluator(everything)
    of_a_launch = Evaluator(everything, callers=False)
    given = loaders(everything)
    found: list[Way] = []
    for module in tests:
        owner = parents(module)
        bound = {
            target.id
            for assign in ast.walk(module.tree)
            if isinstance(assign, ast.Assign) and a_script_s_module(assign.value, given, set())
            for target in assign.targets
            if isinstance(target, ast.Name)
        }
        for node in ast.walk(module.tree):
            if not isinstance(node, ast.Call):
                continue
            name = called_name(node)
            scope = enclosing(node, owner)
            if isinstance(node.func, ast.Name) and name == "compile" and len(node.args) >= 2:
                if isinstance(node.args[0], ast.Constant):
                    continue  # the test's own code, under a name it chooses
                values = evaluator.values(node.args[1], module, scope)
                found.append(Way(f"{module.where}:{node.lineno}", "compilato", frozenset(values)))
            elif (
                name in ("write_text", "write_bytes")
                and node.args
                and isinstance(node.args[0], ast.Attribute)
                and a_script_s_module(node.args[0].value, given, bound)
            ):
                written = f"{module.where}:{node.args[0].attr}"
                found.append(Way(written, "scritto", frozenset()))
            elif name in BY_PATH and node.args:
                argument = node.args[-1] if name != "run_path" else node.args[0]
                values = evaluator.values(argument, module, scope)
                found.append(
                    Way(f"{module.where}:{node.lineno}", "per percorso", frozenset(values))
                )
            elif name in BY_NAME and node.args:
                try:
                    names = {str(one) for one in evaluator.values(node.args[0], module, scope)}
                except Unreadable:
                    # A name built while the test runs: of a module of ela's, unless it says
                    # otherwise (the module docstring, «a name»).
                    names = {word for word in STEMS | {"scripts"} if word in ast.unparse(node)}
                if {one.split(".")[0] for one in names} & (STEMS | {"scripts"}):
                    found.append(Way(f"{module.where}:{node.lineno}", "per nome", frozenset()))
            elif name in LAUNCHES and launched(node, of_a_launch, module, scope):
                found.append(Way(f"{module.where}:{node.lineno}", "figlio", frozenset()))
        for node in ast.walk(module.tree):
            named = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            if {one.split(".")[0] for one in named} & STEMS:
                found.append(Way(f"{module.where}:{node.lineno}", "per nome", frozenset()))
    return found


def the_tests() -> tuple[list[Module], list[Module]]:
    everything = modules([ROOT / "tests"])
    return everything, everything


def test_every_way_a_test_runs_a_script_loads_a_file_the_fences_recognise() -> None:
    everything, tests = the_tests()
    found = ways(everything, tests)
    by_path = [way for way in found if way.how == "per percorso"]

    assert any(way.where.startswith("tests/docs/test_prova_eyes.py") for way in by_path)
    for way in found:
        if way.where in OUT_OF_REACH:
            continue
        assert way.how != "figlio", f"{way.where}: a script launched as a child, where no fence is"
        assert way.how != "scritto", (
            f"{way.where}: the code of a script written into a file, to run where no fence is"
        )
        assert way.how != "per nome", (
            f"{way.where}: a script imported by its name — from whatever folder sys.path holds "
            "first: load it by its path in scripts/, as tests/docs/test_prova_eyes.py does"
        )
        loads = {one for one in way.loads if not isinstance(one, str | int)} or set(way.loads)
        assert loads and all(inside_the_scripts(one) for one in loads), (
            f"{way.where} ({way.how}) loads {sorted(map(str, way.loads))}: outside scripts/, where "
            "the fences do not recognise it — load it from scripts/, or name it in OUT_OF_REACH"
        )
    assert set(OUT_OF_REACH) <= {way.where for way in found}, "a named way that is not there"


OWN_FOLDER: Final = frozenset(
    {"str(Path(__file__).resolve().parent)", "Path(__file__).resolve().parent"}
)
"""How a script writes its own folder: exactly, so that a parent of it is not taken for it."""


def test_the_scripts_that_put_a_folder_on_the_path_put_their_own() -> None:
    """The siblings of a proof are imported by name, from the folder the script puts on
    ``sys.path``: its own — so what they load is inside ``scripts/``."""
    scripts = modules([SCRIPTS])
    for module in scripts:
        for node in ast.walk(module.tree):
            if (
                isinstance(node, ast.Call)
                and called_name(node) in ("insert", "append")
                and ast.unparse(node.func).startswith("sys.path.")
            ):
                put = ast.unparse(node.args[-1])
                assert put in OWN_FOLDER, f"{module.where}: {put}"


# ----------------------------------------------------------------------------------------
# The negative cases, on sources of the test's
# ----------------------------------------------------------------------------------------


LOADER = (
    "import importlib.util\nfrom pathlib import Path\n"
    "SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'prova_m6_3c.py'\n"
    "def script():\n"
    "    return importlib.util.spec_from_file_location('x', SCRIPT)\n"
    "\n"
)
"""A loader of the tests: what it gives back is a script's module (its load is on line 5)."""


def synthetic(tmp_path: Path, source: str) -> list[Module]:
    folder = ROOT / "tests"
    path = folder / "a_test_that_is_not_there.py"
    return [Module(path, ast.parse(source))]


@pytest.mark.parametrize(
    ("source", "found"),
    [
        (
            "from pathlib import Path\nimport importlib.util\n"
            "SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'prova_m6_3c.py'\n"
            "importlib.util.spec_from_file_location('x', SCRIPT)\n",
            "inside",
        ),
        (
            "import importlib.util\nfrom pathlib import Path\n"
            "def copy(tmp_path):\n"
            "    importlib.util.spec_from_file_location('x', tmp_path / 'p.py')\n",
            "unreadable",
        ),
        (
            "import importlib.util\nfrom pathlib import Path\n"
            "OTHER = Path(__file__).resolve().parent / 'prova_m6_3c.py'\n"
            "importlib.util.spec_from_file_location('x', OTHER)\n",
            "outside",
        ),
        ("import subprocess\nsubprocess.run(['python', 'scripts/prova_m6_3c.py'])\n", "child"),
        (
            "import subprocess, sys\nfrom pathlib import Path\n"
            "SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'\n"
            "subprocess.run([sys.executable, str(SCRIPTS / 'prova_m6_3c.py')])\n",
            "child",
        ),
        ("import prova_m6_3c\n", "by name"),
        ("import importlib\nimportlib.import_module('misura_m14_3')\n", "by name"),
        ("import runpy\nrunpy.run_module('prova_m6_3c')\n", "by name"),
        ("import runpy\nrunpy.run_path('/una/copia/prova_m6_3c.py')\n", "outside"),
        (
            LOADER + "exec(compile(script().FAKE, str(SCRIPT), 'exec'), {})\n",
            "inside",
        ),
        (LOADER + "exec(compile(script().FAKE, 'altrove', 'exec'), {})\n", "outside"),
        (LOADER + "exec(compile('pass', 'altrove', 'exec'), {})\n", "nothing"),
        (LOADER + "measure = script()\nPath('p.py').write_text(measure.FIRST)\n", "written"),
    ],
)
def test_a_copy_a_child_and_an_unreadable_path_are_found(
    tmp_path: Path, source: str, found: str
) -> None:
    those = synthetic(tmp_path, source)
    if found == "unreadable":
        with pytest.raises(Unreadable):
            ways(those, those)
        return
    if found == "nothing":
        assert [way.how for way in ways(those, those)] == ["per percorso"], "the loader alone"
        return
    (way, *rest) = [way for way in ways(those, those) if way.where.split(":")[-1] != "5"]
    assert rest == []
    if found == "written":
        assert way.how == "scritto" and way.where.endswith(":FIRST")
    elif found == "child":
        assert way.how == "figlio"
    elif found == "by name":
        assert way.how == "per nome"
    else:
        loads = {one for one in way.loads if not isinstance(one, str | int)} or set(way.loads)
        assert all(inside_the_scripts(one) for one in loads) is (found == "inside")
