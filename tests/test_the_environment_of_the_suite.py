"""**No test reaches the configuration of whoever runs the suite** (M13.17b, answers 39 and 54):
the third fence of ``tests/script_fences.py``. The configuration reaches the real world by three
roads — the ``.env`` of the folder a load starts from, the ``ELA_`` variables of the process, and
the defaults under the real home when nothing is declared —, and the suite says the same thing on
the Mac of whoever uses ELA and on a runner.

**Nothing here reads a real ``.env``**: the one the negative case finds is written by the test, in
a folder of its own outside pytest's temporary folder — the place a ``.env`` of somebody's would
be.
"""

from __future__ import annotations

import ast
import importlib
import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic_settings import BaseSettings

from tests.composition import support

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
LINE = "ELA_DB_URL=sqlite:////una-riga-del-env-finto-del-rosso.db"


# ----------------------------------------------------------------------------------------
# Answer 39 (d): a fixture of a module that loads the settings beside somebody's .env
# ----------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def settings_loaded_beside_a_dotenv_outside(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[Any, Any]]:
    """Set up before any fixture of a function: a folder outside ``getbasetemp()`` with a ``.env``
    the test wrote, and the settings loaded there, as the fixtures ``real`` load them in the folder
    pytest started from."""
    from ela.infrastructure.persistence.settings import PersistenceSettings

    folder = Path(tempfile.mkdtemp(prefix="ela-env-finto-"))
    base = tmp_path_factory.getbasetemp().resolve()
    assert not folder.resolve().is_relative_to(base), "outside pytest's folder, said"
    (folder / ".env").write_text(LINE + "\n", encoding="utf-8")
    before = Path.cwd()
    os.chdir(folder)
    try:
        try:
            found: Any = PersistenceSettings().db_url
            refusal: Any = None
        except BaseException as raised:  # noqa: BLE001 — the refusal is one on purpose
            found, refusal = None, raised
        yield found, refusal
    finally:
        os.chdir(before)
        shutil.rmtree(folder, ignore_errors=True)


def test_a_dotenv_outside_the_test_s_folders_is_never_read_in_a_module_fixture(
    settings_loaded_beside_a_dotenv_outside: tuple[Any, Any],
) -> None:
    found, refusal = settings_loaded_beside_a_dotenv_outside

    assert found != LINE.partition("=")[2], "a .env outside the test's folders was read"
    assert type(refusal).__name__ == "DotenvOutsideTheTest"


# ----------------------------------------------------------------------------------------
# Answer 54 (b): every default under the home is moved by the declared environment
# ----------------------------------------------------------------------------------------


def settings_classes() -> list[type[BaseSettings]]:
    """Every class of settings of ELA, derived from the source and not listed: a class whose bases
    reach ``BaseSettings``, imported by the name of its module — never a ``__main__``, which
    starts ELA when it is imported (decision 52)."""
    defined: dict[tuple[str, str], list[str]] = {}
    for path in sorted((SOURCE / "ela").rglob("*.py")):
        if path.name == "__main__.py":
            continue
        dotted = ".".join(path.relative_to(SOURCE).with_suffix("").parts)
        module = dotted.removesuffix(".__init__")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef):
                defined[(module, node.name)] = [
                    base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
                    for base in node.bases
                ]
    found: set[tuple[str, str]] = set()
    grew = True
    while grew:
        names = {name for _, name in found}
        new = {
            key for key, bases in defined.items() if "BaseSettings" in bases or names & set(bases)
        } - found
        found |= new
        grew = bool(new)
    return [getattr(importlib.import_module(module), name) for module, name in sorted(found)]


class Recorded:
    """A ``MonkeyPatch`` that only remembers what it was asked to set."""

    def __init__(self) -> None:
        self.names: set[str] = set()

    def setenv(self, name: str, value: str, prepend: str | None = None) -> None:
        self.names.add(name)

    def delenv(self, name: str, raising: bool = True) -> None:
        pass


def test_every_default_under_the_home_is_moved_by_the_declared_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from ela.infrastructure.persistence.settings import PersistenceSettings

    house = tmp_path / "casa"
    monkeypatch.setenv("HOME", str(house))
    declared = Recorded()
    support.declare(declared, tmp_path / "declared")  # type: ignore[arg-type]
    classes = settings_classes()
    under: dict[str, str] = {}
    for cls in classes:
        prefix = (cls.model_config.get("env_prefix") or "").upper()
        for name, field in cls.model_fields.items():
            factory: Any = field.default_factory
            default = factory() if factory is not None else field.default
            if str(house) in str(default):
                under[f"{cls.__module__}.{cls.__name__}.{name}"] = prefix + name.upper()

    assert PersistenceSettings in classes and under, "the classes found, and a default under home"
    left = {where: variable for where, variable in under.items() if variable not in declared.names}
    assert left == {}, "a default under the home that the declared environment does not move"
