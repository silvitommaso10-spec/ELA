"""**The log of the suite**: which test ran on which worker, when, for how long, and how it ended
(M9.5, decision 75 of the review at ``ad1826c``).

What the log of the CI did not say on 2026-11-12, when M13.4g looked for the cause of two reds: a
red names its worker (``[gw1]``) and nothing else — not which tests that worker ran before, nor how
long each took. **Turned on by one variable**, :data:`VARIABLE`, which the two jobs of ``make
check`` set and a run on this Mac does not: **without it nothing is written**, and what ``make
check`` prints does not change. Not ``ELA_``: that is the product's space, and the fixture of the
declared environment empties it.

Each process writes its own file in the folder the variable names — ``<worker>-<pid>.jsonl``, one
JSON line per test, at its teardown: its id, the worker, the instant its set-up began (the clock of
the system), the durations of set-up, call and teardown, and how it ended. ***Since 2026-11-20***
(answer 63 (b) of the branch ``m13.11-il-browser-sul-pc``) **a test has a line at the beginning of
its set-up too** — its id, the worker and ``begun``, the clock of the system, and no ``outcome`` —:
a test in flight when the suite is cut, which never reaches its teardown, is the one whose first
line has no second. On that day a macOS runner fell 53 minutes into ``make check``, and a log that
wrote only at the teardown could not have named a test that hung. A pytest a test launches
inherits the variable and writes a file of its own beside, ``main-<pid>.jsonl``: a worker knows it
is one from its configuration, not from an environment a child inherits; the workers of the suite
are the files named ``gw*``. A report the controller of ``xdist`` receives from a worker is
the worker's, and is written there, once.

The upload of the folder is a step of each job with ``if: always()`` and ``continue-on-error:
true``: **an instrument, not a defence** — its failure turns no job red.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Final

import pytest

VARIABLE: Final = "SUITE_LOG"
"""The folder the log is written in, when it is set."""

_open: dict[str, dict[str, Any]] = {}
_worker: list[str] = ["main"]


def configured(config: pytest.Config) -> None:
    """Who this process is: a worker of ``xdist`` says its id in its configuration — not in its
    environment, which a pytest that a test launches would inherit."""
    workerinput = getattr(config, "workerinput", None)
    _worker[0] = str(workerinput["workerid"]) if workerinput else "main"


def folder() -> Path | None:
    """Where the log goes, or ``None``: off."""
    named = os.environ.get(VARIABLE, "")
    return Path(named) if named else None


def line(nodeid: str, phases: dict[str, Any], worker: str) -> dict[str, Any]:
    """The line of a test, from the reports of its phases."""
    failed = [
        when for when in ("setup", "call", "teardown") if phases.get(f"{when}_outcome") == "failed"
    ]
    skipped = phases.get("setup_outcome") == "skipped" or phases.get("call_outcome") == "skipped"
    return {
        "id": nodeid,
        "worker": worker,
        "started": phases.get("started"),
        "setup": phases.get("setup"),
        "call": phases.get("call"),
        "teardown": phases.get("teardown"),
        "outcome": "failed" if failed else ("skipped" if skipped else "passed"),
        "failed_in": failed,
    }


def reported(report: pytest.TestReport) -> None:
    """Take one report of a phase; at the teardown, write the line of its test. Off without the
    variable, and silent for a report a controller received from a worker."""
    where = folder()
    if where is None or getattr(report, "node", None) is not None:
        return
    phases = _open.setdefault(report.nodeid, {})
    if report.when == "setup":
        phases["started"] = round(report.start, 3)
    phases[report.when] = round(report.duration, 4)
    phases[f"{report.when}_outcome"] = report.outcome
    if report.when != "teardown":
        return
    written(where, line(report.nodeid, _open.pop(report.nodeid), _worker[0]))


def begun(nodeid: str) -> None:
    """The line of a test whose set-up begins: its id, the worker, the clock of the system — and no
    ``outcome``. Off without the variable. Called by the process that runs the test, never by a
    controller: a test in flight is the one whose line has no second."""
    where = folder()
    if where is None:
        return
    written(where, {"id": nodeid, "worker": _worker[0], "begun": round(time.time(), 3)})


def written(where: Path, one: dict[str, Any]) -> None:
    """One line in the file of this process, written and closed at once: a process that is cut
    leaves every line it wrote."""
    where.mkdir(parents=True, exist_ok=True)
    with (where / f"{_worker[0]}-{os.getpid()}.jsonl").open("a", encoding="utf-8") as sink:
        sink.write(json.dumps(one) + "\n")
