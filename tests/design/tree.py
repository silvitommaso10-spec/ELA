"""Where the design system is, and the generator that derives half of it.

Everything in ``tests/design`` reads files and writes none: the checks run in parallel
(ADR 0041 §3), and every negative case lives in ``tmp_path`` or in a string.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DESIGN_SYSTEM = ROOT / "apps" / "design-system"
SCRIPT = ROOT / "scripts" / "generate_design_system.py"
DESIGN_DOCUMENT = ROOT / "docs" / "spec" / "ELA_design.md"


@cache
def generator() -> ModuleType:
    """The script, loaded by path: ``scripts/`` is not a package (as ``test_stato.py`` does)."""
    spec = importlib.util.spec_from_file_location("generate_design_system", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@cache
def _tokens() -> dict[str, Any]:
    return json.loads((DESIGN_SYSTEM / "tokens.json").read_text(encoding="utf-8"))


def tokens() -> dict[str, Any]:
    """A copy every time: a negative case mutates it, and the next test must not see that."""
    return copy.deepcopy(_tokens())


def read(name: str) -> str:
    return (DESIGN_SYSTEM / name).read_text(encoding="utf-8")


def handwritten_stylesheets() -> dict[str, str]:
    return {name: read(name) for name in generator().HANDWRITTEN_STYLESHEETS}


def fragments() -> dict[str, str]:
    folder = DESIGN_SYSTEM / generator().FRAGMENTS
    found = {path.name: path.read_text(encoding="utf-8") for path in sorted(folder.glob("*.html"))}
    assert found, "the design system must have fragments, or these tests are vacuous"
    return found


def token_paths() -> dict[str, tuple[str, ...]]:
    """Custom property name -> the path of its token, for the mechanical names."""
    module = generator()
    source = _tokens()
    found: dict[str, tuple[str, ...]] = {}
    for group in module.PLAIN:
        for path, _ in module.leaves(source.get(group, {}), (group,)):
            found[module.css_name(path)] = path
    for path, _ in module.leaves(source[module.THEMES[0]]):
        found[module.css_name(path)] = path
    return found
