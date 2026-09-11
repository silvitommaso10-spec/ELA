"""The derivation of ``tests/api/routers.py`` finds what nobody listed.

Proved on a package built for the purpose, so the test says something about the walk and not
about today's shape of ``ela.api``: a module with a router that no list names is found, a module
without one is not a router, and a private module is never imported.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest

from tests.api.routers import api_routers, routes_of

ROUTER = """from fastapi import APIRouter

router = APIRouter()


@router.{method}("{path}")
async def endpoint() -> None:
    return None
"""


@pytest.fixture
def package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A router module, a module without one, and a private one that must not run.

    **A name of its own for every test, and the modules forgotten afterwards.** With one shared
    name, ``sys.modules`` kept the first test's package — and its ``__path__``, which points at
    the first test's temporary directory — so the second test wrote ``nodes.py`` into a folder
    nobody was reading any more, and the walk correctly found nothing new. The test was polluted
    by its neighbour, not the derivation wrong.
    """
    name = f"fakeapi_{uuid4().hex}"
    root = tmp_path / name
    root.mkdir()
    (root / "__init__.py").write_text("", encoding="utf-8")
    (root / "system.py").write_text(ROUTER.format(method="get", path="/health"), encoding="utf-8")
    (root / "problems.py").write_text("CODE = 'x'\n", encoding="utf-8")
    (root / "__main__.py").write_text("raise SystemExit('imported')\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield name
    for module in [key for key in sys.modules if key == name or key.startswith(f"{name}.")]:
        del sys.modules[module]


def test_only_the_modules_that_carry_a_router_are_routers(package: str) -> None:
    found = api_routers(importlib.import_module(package))

    assert set(found) == {"system"}
    assert routes_of(found.values()) == {("GET", "/health")}


def test_a_router_module_nobody_listed_is_found_the_day_it_exists(
    package: str, tmp_path: Path
) -> None:
    """The negative case the three hand-written lists could not have: a file appears, and the
    set grows — so every count built on the set fails until somebody says what the file is."""
    before = set(api_routers(importlib.import_module(package)))
    (tmp_path / package / "nodes.py").write_text(
        ROUTER.format(method="post", path="/nodes"), encoding="utf-8"
    )
    importlib.invalidate_caches()

    after = api_routers(importlib.import_module(package))

    assert set(after) - before == {"nodes"}
    assert ("POST", "/nodes") in routes_of(after.values())


def test_the_real_package_is_walked_and_the_server_is_not_started() -> None:
    """``ela.api.__main__`` raises ``SystemExit`` on import: reaching this line is the proof."""
    assert "system" in api_routers()
