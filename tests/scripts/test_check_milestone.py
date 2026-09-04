"""Behaviour of scripts/check_milestone.py on synthetic milestone directories."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_milestone.py"

VALID = (
    "# M9.9 — Test\n\n## Obiettivo\n\nx\n\n## Criteri di accettazione\n\n- `make check` passa.\n"
)
MISSING = "# M9.9 — Test\n\n## Obiettivo\n\nx\n"
EMPTY = "# M9.9 — Test\n\n## Criteri di accettazione\n\n\n## Rischi\n\n- r\n"
PLACEHOLDER_ONLY = "# M9.9 — Test\n\n## Criteri di accettazione\n\n- <Condizione verificabile.>\n"


@pytest.fixture(scope="module")
def check_milestone() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_milestone", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(directory: Path, name: str, content: str) -> None:
    (directory / name).write_text(content, encoding="utf-8")


def test_valid_milestone_passes_and_template_is_ignored(
    tmp_path: Path, check_milestone: ModuleType
) -> None:
    _write(tmp_path, "M9.9.md", VALID)
    _write(tmp_path, "TEMPLATE.md", PLACEHOLDER_ONLY)
    assert check_milestone.check_milestones(tmp_path) == []
    assert check_milestone.main([str(SCRIPT), str(tmp_path)]) == 0


@pytest.mark.parametrize(
    ("content", "reason"),
    [(MISSING, "missing section"), (EMPTY, "not filled in"), (PLACEHOLDER_ONLY, "not filled in")],
)
def test_invalid_milestone_fails(
    tmp_path: Path, check_milestone: ModuleType, content: str, reason: str
) -> None:
    _write(tmp_path, "M9.9.md", content)
    problems = check_milestone.check_milestones(tmp_path)
    assert len(problems) == 1 and reason in problems[0]
    assert check_milestone.main([str(SCRIPT), str(tmp_path)]) == 1


def test_repository_milestones_are_valid(check_milestone: ModuleType) -> None:
    assert check_milestone.check_milestones(SCRIPT.parents[1] / "docs" / "milestones") == []
