"""The documents say what is there (M17.1, criterio 18).

``CLAUDE.md``: the rules of what lives in ``apps/`` do not walk Python — they live in the tests
of their folder, *and the README of the folder names every rule with the test that defends it*.
So the README and the folder of tests are a closed world, in both directions; and the folder
§48 does not foresee is named where a reader of ``apps/`` would look for it.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.design.tree import DESIGN_SYSTEM, ROOT, generator

TESTS = Path(__file__).resolve().parent
NAMED = re.compile(r"`tests/design/(test_[a-z_]+\.py)`")


def files_of_the_folder() -> set[str]:
    found = {path.name for path in TESTS.glob("test_*.py")}
    assert found, "there must be tests, or this test is vacuous"
    return found


def named_by(readme: str) -> set[str]:
    return set(NAMED.findall(readme))


def readme() -> str:
    return (DESIGN_SYSTEM / "README.md").read_text(encoding="utf-8")


def test_the_readme_names_every_test_of_the_design_system_and_no_other() -> None:
    assert named_by(readme()) == files_of_the_folder()


def test_the_readme_names_every_derived_file_as_derived() -> None:
    for name in generator().DERIVED:
        assert f"| `{name}` | **derivato** |" in readme(), name
    assert "scripts/generate_design_system.py" in readme()


def test_the_folder_the_spec_does_not_foresee_is_named_in_apps() -> None:
    assert "`design-system/`" in (ROOT / "apps" / "README.md").read_text(encoding="utf-8")


def test_claude_md_says_where_the_rules_of_apps_live() -> None:
    text = " ".join((ROOT / "CLAUDE.md").read_text(encoding="utf-8").split())
    assert "Le regole di ciò che sta in `apps/` non camminano Python" in text
    assert "`tests/design/` per il design system" in text


def test_a_test_the_readme_forgets_and_one_it_invents_are_seen() -> None:
    text = "| a | `tests/design/test_generated.py` |\n| b | `tests/design/test_imaginary.py` |"
    assert named_by(text) == {"test_generated.py", "test_imaginary.py"}
    assert named_by(text) - files_of_the_folder() == {"test_imaginary.py"}
    assert "test_contrast.py" in files_of_the_folder() - named_by(text)
