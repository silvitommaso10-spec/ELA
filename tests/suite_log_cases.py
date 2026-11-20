"""Two tests the test of the log runs **in a pytest of their own** (M9.5, ``tests/suite_log.py``) —
never collected by the suite: the name of this file is not a test module's."""

from __future__ import annotations

import os


def test_passes() -> None:
    pass


def test_fails() -> None:
    raise AssertionError("the failure of the case")


def test_is_cut_in_flight() -> None:
    """A suite cut while this test runs, as a limit of the step cuts it: the process ends here,
    with no teardown and no report — the last of the cases."""
    os._exit(0)
