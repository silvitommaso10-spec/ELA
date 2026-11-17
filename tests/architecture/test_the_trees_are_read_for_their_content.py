"""The rules read a tree **once for its content**, never for its path (M9.5, decision 77 of the
review at ``ad1826c``; :func:`tests.architecture.rules.parsed`).

The cache is what makes the architecture tests cheaper, and it is also how a rule could stop seeing
a file a case changed: a tree kept for its path would be the file as it was. The negative case is
that one — **the same path, the content changed, and the rule sees the change** —, on a copy of
``src/ela`` that is clean and then is not.
"""

from __future__ import annotations

from pathlib import Path

from tests.architecture import rules
from tests.architecture.rules import RULES
from tests.architecture.violations import VIOLATIONS, apply


def test_a_file_changed_at_the_same_path_is_seen_by_the_rule(package_copy: Path) -> None:
    case = next(one for one in VIOLATIONS if one.id == "domain-third-party")
    before = rules.parsed(package_copy / case.path)

    clean = RULES[case.rule](package_copy)
    apply(case, package_copy)
    changed = RULES[case.rule](package_copy)

    assert clean == []
    assert [(one.module, one.imported) for one in changed] == [(case.module, case.imported)]
    assert rules.parsed(package_copy / case.path) is not before, "a text of its own, a tree too"


def test_the_same_text_at_two_paths_is_one_tree(tmp_path: Path) -> None:
    """What the cache is for: the copies a case makes are, file by file, the same text."""
    one, other = tmp_path / "one.py", tmp_path / "other.py"
    one.write_text("x = 1\n", encoding="utf-8")
    other.write_text("x = 1\n", encoding="utf-8")

    assert rules.parsed(one) is rules.parsed(other)
    assert rules.walked(rules.parsed(one)) is rules.walked(rules.parsed(other))
