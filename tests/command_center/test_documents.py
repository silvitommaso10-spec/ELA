"""The documents of ``apps/command-center/`` say what is there (M17.2 dec. E; ADR 0044).

``CLAUDE.md``: the rules of what lives in ``apps/`` do not walk Python — they live in the tests of
their folder, *and the README of the folder names every rule with the test that defends it*. So
the README and this folder of tests are a closed world, in both directions; and the folder §48
does not foresee is named where a reader of ``apps/`` would look for it.
"""

from __future__ import annotations

import re
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parents[1]
COMMAND_CENTER = ROOT / "apps" / "command-center"
NAMED = re.compile(r"`tests/command_center/(test_[a-z_]+\.py)`")


def files_of_the_folder() -> set[str]:
    found = {path.name for path in TESTS.glob("test_*.py")}
    assert found, "there must be tests, or this test is vacuous"
    return found


def readme() -> str:
    return (COMMAND_CENTER / "README.md").read_text(encoding="utf-8")


def test_the_readme_names_every_test_of_the_folder_and_no_other() -> None:
    assert set(NAMED.findall(readme())) == files_of_the_folder()


def test_a_test_nobody_named_would_be_reported() -> None:
    """The negative case of the closed world, on strings: a file with no row fails."""
    named = set(NAMED.findall("| Regola | `tests/command_center/test_templates.py` |"))

    assert named == {"test_templates.py"}
    assert named != {"test_templates.py", "test_nobody_named.py"}


def test_the_readme_names_the_defence_that_does_not_live_in_this_folder() -> None:
    """The second half of «niente JavaScript» is the policy, and it is proved through the app:
    a README that named only the folder's own tests would hide the defence that matters most."""
    assert "`tests/api/test_console.py`" in readme()


def test_the_folder_the_spec_does_not_foresee_is_named_in_apps() -> None:
    assert "`command-center/`" in (ROOT / "apps" / "README.md").read_text(encoding="utf-8")


def test_the_readme_says_where_the_ceiling_comes_from() -> None:
    """Dec. J and dec. 17 of the review: whoever opens the Command Center from the tailnet must
    find written why they see an id where the Mac sees a goal."""
    text = readme()

    assert "dec. J" in text
    assert "loopback" in text
    assert "ela node enroll --privacy TRUSTED --role console" in text
