"""ADR 0053 and the CI say the same thing: the runner has a written version, the debt is paid.

The defence §2 asked for, in the form of ADR 0035 §7, turned round by M6.3c (ADR 0054 §1): until
2026-09-30 ``.github/workflows/ci.yml`` ran ``make check`` on ``ubuntu-latest`` and used the actions
the runner warned about. Now the Linux runner is a written Ubuntu version and none of those actions
is left; the day one of them comes back — a merge, a revert — the debt is owed again, and the test
below says so.

**A run that started always finishes** (``CLAUDE.md``, decision 2 of M14.6b, from decision 26 of
M13.13): ``cancel-in-progress`` is ``false``. Until 2026-11-11 it was ``true``, and on 2026-11-03 a
push cancelled a run that would have been red — a verification nobody saw.

***Since 2026-11-20*** (answer 63 (c) of the branch ``m13.11-il-browser-sul-pc``): **the step ``make
check`` has a limit, and the step of the log still always runs.** On the step, not on the job: a
suite that hangs is cut while the runner is alive, and the next step carries the log away. On that
day the macOS runner of ``a83da54`` lost communication 53 minutes into ``make check``, and no log
was left.

***Since 2026-11-21*** (answer 67 B of the same branch): **the machine's sampler starts before
``make check``, writes in the folder the step of the log carries away, and cannot turn the job
red** — ``continue-on-error`` on its step, in the background with its streams closed, and no exit
of ``.github/sampler.sh`` other than 0. On 2026-11-20 the macOS runner fell a second time, under
the limit of the step, and again said nothing of itself.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0053-ci-runner.md"
PAYMENT_PATH = ROOT / "docs" / "adr" / "0054-stopped-midway.md"
CI = ROOT / ".github" / "workflows" / "ci.yml"
SAMPLER = ROOT / ".github" / "sampler.sh"

OWED = (
    "os: [ubuntu-latest, macos-latest]",
    "actions/checkout@v4",
    "actions/cache/restore@v4",
    "astral-sh/setup-uv@v6",
)
"""What the debt was, as the file spelled it: the moving label, and the actions on Node.js 20."""

WRITTEN_UBUNTU = re.compile(r"os: \[ubuntu-\d{2}\.\d{2}, macos-latest\]")
"""The matrix of ``make check`` with Linux as a version, not a label (ADR 0053 §1)."""

CANCEL_IN_PROGRESS = re.compile(r"^\s*cancel-in-progress:\s*(.*?)\s*$", re.MULTILINE)
"""Every ``cancel-in-progress`` of the workflow, with its value as the file writes it."""


def cancelling(workflow: str) -> list[str]:
    """The values of ``cancel-in-progress`` other than ``false``: each, a run a push cancels."""
    return [value for value in CANCEL_IN_PROGRESS.findall(workflow) if value != "false"]


def owed(workflow: str) -> list[str]:
    """The parts of the debt the workflow still carries."""
    return [line for line in OWED if line in workflow]


def test_the_ci_runs_on_a_written_ubuntu_with_no_node_20_action() -> None:
    workflow = CI.read_text(encoding="utf-8")

    assert owed(workflow) == []
    assert WRITTEN_UBUNTU.search(workflow) is not None


def test_bringing_back_one_part_of_the_debt_owes_it_again() -> None:
    """The negative case: the moving label, or one old action, is the debt again."""
    workflow = CI.read_text(encoding="utf-8")
    moving = WRITTEN_UBUNTU.sub(OWED[0], workflow)
    old_checkout = re.sub(r"actions/checkout@v\d+", OWED[1], workflow)

    assert owed(moving) == [OWED[0]]
    assert WRITTEN_UBUNTU.search(moving) is None
    assert owed(old_checkout) == [OWED[1]]


def test_a_run_that_started_always_finishes() -> None:
    workflow = CI.read_text(encoding="utf-8")

    assert CANCEL_IN_PROGRESS.findall(workflow) == ["false"]
    assert cancelling(workflow) == []


def test_a_push_that_cancels_a_run_is_found() -> None:
    """The negative case: ``true``, or an expression that is ``true`` on some branch, cancels."""
    workflow = CI.read_text(encoding="utf-8")
    written = "cancel-in-progress: false"
    on_branches = "${{ github.ref != 'refs/heads/main' }}"

    assert cancelling(workflow.replace(written, "cancel-in-progress: true")) == ["true"]
    assert cancelling(workflow.replace(written, f"cancel-in-progress: {on_branches}")) == [
        on_branches
    ]


def test_the_adr_charges_the_debt_to_m6_3c_with_its_deadline() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")

    assert "### 2. Un debito datato: il runner della CI, da fissare entro il 2026-10-19" in text
    assert "**Debito a carico di M6.3c**, dichiarato il **2026-09-30**" in text


def test_the_adr_of_m6_3c_writes_the_payment() -> None:
    """The heading ``scripts/generate_stato.py`` reads to call the debt paid."""
    text = PAYMENT_PATH.read_text(encoding="utf-8")

    assert "### 1. Il debito di ADR 0053 §2, saldato" in text


STEP = re.compile(
    r"^(?P<indent> +)- name: (?P<name>[^\n]+)\n(?P<body>(?:(?P=indent)  [^\n]*\n)*)", re.MULTILINE
)
"""A step of the workflow: its name, and the lines of its body, indented under it."""

STEP_LIMIT = re.compile(r"^ +timeout-minutes: *(\d+) *$", re.MULTILINE)
JOB_LIMIT = re.compile(r"^    timeout-minutes:", re.MULTILINE)
"""A limit of a job, which would cut the step of the log with the suite."""
ALWAYS = re.compile(r"^ +if: always\(\) *$", re.MULTILINE)


def steps(workflow: str) -> dict[str, str]:
    return {found["name"]: found["body"] for found in STEP.finditer(workflow)}


def unguarded(workflow: str) -> list[str]:
    """What is missing for a suite that hangs to be cut with its log carried away."""
    named = steps(workflow)
    limits = STEP_LIMIT.findall(named.get("make check", ""))
    missing = []
    if len(limits) != 1 or int(limits[0]) <= 0:
        missing.append("the step make check has no limit")
    if JOB_LIMIT.search(workflow):
        missing.append("a job has a limit")
    if not ALWAYS.search(named.get("The log of the suite", "")):
        missing.append("the step of the log does not always run")
    return missing


def test_the_step_make_check_has_a_limit_and_the_step_of_the_log_always_runs() -> None:
    assert unguarded(CI.read_text(encoding="utf-8")) == []


def test_a_suite_that_could_hang_the_runner_or_lose_its_log_is_found() -> None:
    """The negative cases: no limit; the limit on the job instead of the step; a step of the log
    that does not always run."""
    workflow = CI.read_text(encoding="utf-8")
    limit = STEP_LIMIT.search(steps(workflow)["make check"])
    assert limit is not None
    line = limit.group(0) + "\n"
    without = workflow.replace(line, "", 1)
    on_the_job = without.replace(
        "    runs-on: ${{ matrix.os }}\n",
        "    runs-on: ${{ matrix.os }}\n    timeout-minutes: 40\n",
    )
    log_unguarded = workflow.replace(
        "      - name: The log of the suite\n        if: always()\n",
        "      - name: The log of the suite\n",
    )

    assert unguarded(without) == ["the step make check has no limit"]
    assert unguarded(on_the_job) == ["the step make check has no limit", "a job has a limit"]
    assert unguarded(log_unguarded) == ["the step of the log does not always run"]


SAMPLER_STEP = "The machine's sampler"
SAMPLER_FOLDER = re.compile(r'sampler\.sh "([^"]+)"')
SUITE_LOG = re.compile(r"^ +SUITE_LOG: *(.+?) *$", re.MULTILINE)
UPLOADED = re.compile(r"^ +path: *(.+?) *$", re.MULTILINE)
RUN = re.compile(r"^ +run: *(.+?) *$", re.MULTILINE)
CLOSED = "> /dev/null 2>&1 < /dev/null"
"""The sampler's streams, closed: a child that holds the step's pipes keeps the step from ending."""
SET_E = re.compile(r"^\s*set\s+-\w*e", re.MULTILINE)
EXIT = re.compile(r"\bexit\b(?:\s+(\S+))?")


def code_of(script: str) -> str:
    """The lines of a shell script that are not comments."""
    return "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("#"))


def unsampled(workflow: str, sampler: str) -> list[str]:
    """What is missing for the machine's sampler to write, through ``make check``, where the log
    is carried away from, without ever turning the job red."""
    names = [found["name"] for found in STEP.finditer(workflow)]
    named = steps(workflow)
    body = named.get(SAMPLER_STEP)
    if body is None:
        return ["there is no sampler"]
    missing = []
    if names.index(SAMPLER_STEP) > names.index("make check"):
        missing.append("the sampler starts after make check")
    folder = SAMPLER_FOLDER.search(body)
    log = SUITE_LOG.findall(named.get("make check", ""))
    uploaded = [
        path.rstrip("/") for path in UPLOADED.findall(named.get("The log of the suite", ""))
    ]
    if folder is None or [folder.group(1)] != log or log != uploaded:
        missing.append("the sampler does not write in the folder the log carries away")
    run = RUN.findall(body)
    if len(run) != 1 or not run[0].endswith("&") or CLOSED not in run[0]:
        missing.append("the sampler holds its step")
    code = code_of(sampler)
    exits = EXIT.findall(code)
    if (
        not re.search(r"^ +continue-on-error: *true *$", body, re.MULTILINE)
        or SET_E.search(code)
        or any(value != "0" for value in exits)
    ):
        missing.append("the sampler can turn the job red")
    return missing


def test_the_sampler_runs_before_make_check_into_the_log_and_cannot_fail() -> None:
    workflow = CI.read_text(encoding="utf-8")
    sampler = SAMPLER.read_text(encoding="utf-8")

    assert unsampled(workflow, sampler) == []
    assert EXIT.findall(code_of(sampler)), "the sampler has no exit of its own"


def test_a_sampler_that_is_late_elsewhere_in_the_foreground_or_can_fail_is_found() -> None:
    """The negative cases: no sampler; after ``make check``; another folder; no
    ``continue-on-error``; in the foreground, or with its streams open; a script with ``set -e``
    or an exit that is not 0."""
    workflow = CI.read_text(encoding="utf-8")
    sampler = SAMPLER.read_text(encoding="utf-8")
    start = workflow.index(f"      - name: {SAMPLER_STEP}\n")
    end = workflow.index("\n\n", start) + 2
    block = workflow[start:end]
    without = workflow.replace(block, "")
    log_step = without.index("      - name: The log of the suite\n")
    late = without[:log_step] + block + without[log_step:]
    elsewhere = workflow.replace(
        'sampler.sh "${{ runner.temp }}/suite-log"', 'sampler.sh "${{ runner.temp }}/machine"'
    )
    failing = workflow.replace(block, block.replace("        continue-on-error: true\n", ""))
    foreground = workflow.replace(f"{CLOSED} &\n", f"{CLOSED}\n")
    open_streams = workflow.replace(f" {CLOSED} &\n", " &\n")

    assert unsampled(without, sampler) == ["there is no sampler"]
    assert unsampled(late, sampler) == ["the sampler starts after make check"]
    assert unsampled(elsewhere, sampler) == [
        "the sampler does not write in the folder the log carries away"
    ]
    assert unsampled(failing, sampler) == ["the sampler can turn the job red"]
    assert unsampled(foreground, sampler) == ["the sampler holds its step"]
    assert unsampled(open_streams, sampler) == ["the sampler holds its step"]
    assert unsampled(workflow, "set -e\n" + sampler) == ["the sampler can turn the job red"]
    assert unsampled(workflow, sampler.replace("|| exit 0", "|| exit 1", 1)) == [
        "the sampler can turn the job red"
    ]
