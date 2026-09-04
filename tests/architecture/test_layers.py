"""Architecture tests for the layering rules (CLAUDE.md "Architettura", spec §49, §52)."""

import ast
import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOMAIN_PATH = REPO_ROOT / "src" / "ela" / "domain.py"
ALLOWED_TOP_LEVEL = set(sys.stdlib_module_names) | {"pydantic"}


def _imported_top_level_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import: stays inside the ela package
                modules.add("ela")
            elif node.module:
                modules.add(node.module.split(".")[0])
    return modules


def test_domain_imports_only_stdlib_and_pydantic() -> None:
    assert DOMAIN_PATH.is_file(), f"{DOMAIN_PATH} must exist"

    forbidden = _imported_top_level_modules(DOMAIN_PATH) - ALLOWED_TOP_LEVEL
    assert not forbidden, f"ela.domain imports outside stdlib/pydantic: {sorted(forbidden)}"
    importlib.import_module("ela.domain")
