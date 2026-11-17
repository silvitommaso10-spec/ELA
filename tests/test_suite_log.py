"""The log of the suite writes with its variable and nothing without it (M9.5, decision 75 of the
review at ``ad1826c``) — in a pytest of its own, with the hook of this suite —, and the two jobs of
``make check`` set the variable and carry the log away in a step that never turns a job red.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from tests import suite_log

REPO = Path(__file__).resolve().parent.parent
CASES = "tests/suite_log_cases.py"
CI = REPO / ".github" / "workflows" / "ci.yml"


def cases(log: Path, variable: str = suite_log.VARIABLE) -> list[dict[str, object]]:
    """The lines the pytest of the cases wrote in ``log``, run with ``variable`` naming it."""
    environment = {name: value for name, value in os.environ.items() if name != suite_log.VARIABLE}
    environment[variable] = str(log)
    subprocess.run(
        [sys.executable, "-m", "pytest", CASES, "-p", "no:cacheprovider", "--no-cov", "-n0", "-q"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env=environment,
    )
    del environment
    written = sorted(log.glob("*.jsonl")) if log.exists() else []
    return [json.loads(one) for file in written for one in file.read_text().splitlines()]


def test_with_the_variable_each_test_is_a_line_and_without_it_nothing_is_written(
    tmp_path: Path,
) -> None:
    lines = cases(tmp_path / "log")
    elsewhere = cases(tmp_path / "another", "ELA_SUITE_LOG")

    assert [(one["id"], one["outcome"], one["failed_in"]) for one in lines] == [
        (f"{CASES}::test_passes", "passed", []),
        (f"{CASES}::test_fails", "failed", ["call"]),
    ]
    assert all(one["worker"] == "main" and isinstance(one["started"], float) for one in lines)
    assert all(isinstance(one[phase], float) for one in lines for phase in ("setup", "call"))
    assert elsewhere == [] and not (tmp_path / "another").exists(), "another name turns nothing on"


STEP = re.compile(
    r"- name: The log of the suite\n\s+if: always\(\)\n\s+continue-on-error: true\n"
    r"\s+uses: actions/upload-artifact@v\d+\n"
)


def carried_away(workflow: str) -> bool:
    """Whether the job of ``make check`` sets the variable on its step and uploads the folder in a
    step that always runs and never turns the job red."""
    return (
        "env:\n          SUITE_LOG: ${{ runner.temp }}/suite-log\n        run: make check"
        in workflow
        and STEP.search(workflow) is not None
    )


def test_the_jobs_of_make_check_write_the_log_and_carry_it_away() -> None:
    """One job, the matrix of the two runners (``ubuntu-24.04``, ``macos-latest``)."""
    assert carried_away(CI.read_text(encoding="utf-8"))


def test_a_step_that_can_turn_a_job_red_or_does_not_always_run_is_seen() -> None:
    workflow = CI.read_text(encoding="utf-8")

    assert not carried_away(workflow.replace("continue-on-error: true", "continue-on-error: false"))
    assert not carried_away(
        workflow.replace(
            "        if: always()\n        continue-on-error", "        continue-on-error"
        )
    )
    assert not carried_away(
        workflow.replace("SUITE_LOG: ${{ runner.temp }}", "ELA_LOG: ${{ runner.temp }}")
    )
