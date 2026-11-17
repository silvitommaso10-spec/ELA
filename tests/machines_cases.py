"""Five tests the test of the guard runs **in a pytest of their own** (M9.5, ``tests/machines.py``)
— never collected by the suite: the name of this file is not a test module's, and
``tests/test_machines.py`` runs it by its path, with no ``GITHUB_ACTIONS`` in its environment.

Each needs a condition built here, with a reading and a declaration that say what the case is:

* one needs what **is here**: it runs;
* one needs what is missing and **need not be here** — it must hold on the runners only: skipped,
  with the reason;
* one needs what is missing and **must be here**: red, before it is set up;
* one needs what **no job has**, and nothing says why: red, wherever it is;
* one needs what no job has, **with the reason declared**: the calculation lets it be, and here it
  is skipped like any other.
"""

from __future__ import annotations

from tests import machines

HERE = machines.Condition("something here", lambda: None, lambda machine: True, "everywhere")
ON_RUNNERS = machines.Condition(
    "something of the runners",
    lambda: "it is not on this machine",
    lambda machine: machine.runner,
    "on a runner",
)
MUST = machines.Condition(
    "something that must be here",
    lambda: "it is not on this machine",
    lambda machine: True,
    "everywhere",
)
NOWHERE = machines.Condition(
    "something no job has",
    lambda: "it is not on this machine",
    lambda machine: False,
    "nowhere",
)
SAID = machines.Condition(
    "something no job has, and why",
    lambda: "it is not on this machine",
    lambda machine: False,
    "nowhere",
    nowhere="no runner has it, measured",
)
SKIPPED_BECAUSE = "the reason of the case"


@machines.needs(HERE)
def test_runs_where_what_it_needs_is_here() -> None:
    pass


@machines.needs(ON_RUNNERS, why=SKIPPED_BECAUSE)
def test_is_skipped_where_what_it_needs_need_not_be() -> None:
    raise AssertionError("never run: skipped")


@machines.needs(MUST)
def test_is_red_where_what_it_needs_must_be() -> None:
    raise AssertionError("never run: red before its set-up")


@machines.needs(NOWHERE)
def test_is_red_because_no_job_runs_it() -> None:
    raise AssertionError("never run: red before its set-up")


@machines.needs(SAID)
def test_runs_on_no_job_and_says_why() -> None:
    raise AssertionError("never run: skipped here")
