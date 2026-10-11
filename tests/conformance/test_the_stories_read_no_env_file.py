"""The stories are told to a Core of the test's own, never to the one this machine is set up for.

``Settings.load()`` reads the ``.env`` of the folder it is called in, for every variable the
test did not set. Until 2026-10-11 the stories built their Core from the folder the suite is
launched in — the repository's, where whoever uses ELA keeps their own ``.env`` —: on the day
that file came to name a folder for the browser's profile and the program of a vault, the suite
was building its Core on them (M13.9, the review at ``1666739``; the family of ADR 0031: a suite
that inherits the machine it runs on).

Like ``tests/api``, ``tests/cli`` and ``tests/composition``, every test here runs in a folder of
its own with no ``.env``, and with no ``ELA_`` variable it did not set.
"""

from __future__ import annotations

import os
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]


def test_a_story_runs_in_a_folder_of_its_own_where_nobody_wrote_an_env_file(
    tmp_path: Path,
) -> None:
    here = Path.cwd().resolve()

    assert here == tmp_path.resolve(), "the folder of this test, and of no other"
    assert here != REPOSITORY and REPOSITORY not in here.parents
    assert not (here / ".env").exists()


def test_a_story_inherits_no_variable_of_ela_s_from_whoever_launched_the_suite() -> None:
    assert [name for name in os.environ if name.startswith("ELA_")] == []
