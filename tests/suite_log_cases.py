"""Two tests the test of the log runs **in a pytest of their own** (M9.5, ``tests/suite_log.py``) —
never collected by the suite: the name of this file is not a test module's."""

from __future__ import annotations


def test_passes() -> None:
    pass


def test_fails() -> None:
    raise AssertionError("the failure of the case")
