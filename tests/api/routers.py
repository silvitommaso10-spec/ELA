"""The routers of ``ela.api``, found by walking the package instead of listed by hand.

Three tests used to import the router modules one by one and count the routes of whatever they
had imported (``test_v01_surface.py``, ``test_adr_composition.py``, ``test_adr_screen.py``). A list
like that stays green when a module appears next to the ones it names — it simply does not see
it — which is the failure this repository calls decoration: a count that cannot notice it has
become false. Found by walking the package, a new ``api/nodes.py`` is in the set the day it
exists, and every count built on the set has to say what it thinks of it (M12.1, first commit,
before that file exists — so the derivation is proved on today's tree and then discovers it).

``create_app`` keeps its own explicit tuple, on purpose: production code must not mount a module
because a file appeared. ``tests/api/test_security.py`` holds the two to each other.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable
from types import ModuleType

from fastapi import APIRouter

import ela.api

__all__ = ["api_routers", "routes_of"]

IGNORED_METHODS = frozenset({"HEAD", "OPTIONS"})
"""What FastAPI adds on its own: counting them would count the framework, not ELA."""


def api_routers(package: ModuleType = ela.api) -> dict[str, APIRouter]:
    """Module name -> router, for every module of ``package`` that carries one.

    Private modules are skipped, and not for tidiness: ``ela.api.__main__`` starts the server when
    it is imported.
    """
    found: dict[str, APIRouter] = {}
    for info in pkgutil.iter_modules(package.__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        router = getattr(module, "router", None)
        if isinstance(router, APIRouter):
            found[info.name] = router
    return found


def routes_of(routers: Iterable[APIRouter]) -> set[tuple[str, str]]:
    """Every ``(method, path)`` the routers declare, without the methods FastAPI adds itself."""
    return {
        (method, route.path)
        for router in routers
        for route in router.routes
        for method in getattr(route, "methods", set())
        if method not in IGNORED_METHODS
    }
