"""The one place of the skips and its guard (M9.5, ``tests/machines.py``; ADR 0069 pays ADR 0047
§18).

Never skipped: nothing here needs anything of the machine. The decision is a pure function, and
**every declaration of the one place is exercised by it in both values** of its reading, on the
three machines of the CI — the declarations are written by hand, and this is what holds them to what
they say. The calculation of the jobs is a pure function too, on a workflow and a suite built here.
And the hook is proved wired in a pytest of its own (``tests/machines_cases.py``).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from tests import machines

REPO = Path(__file__).resolve().parent.parent
CASES = "tests/machines_cases.py"
LINUX = machines.Machine("Linux", "linux", runner=True)
MAC = machines.Machine("Darwin", "darwin", runner=True)
WINDOWS = machines.Machine("Windows", "win32", runner=True)
A_MAC_OF_SOMEBODY = machines.Machine("Darwin", "darwin", runner=False)
PRETENDED = machines.Machine("Linux", "darwin", runner=False)
"""``make check-linux``: the system pretended, the kernel this Mac's."""


def condition(
    name: str, required: Callable[[machines.Machine], bool], *, nowhere: str | None = None
) -> machines.Condition:
    return machines.Condition(name, lambda: None, required, "somewhere", nowhere=nowhere)


ALWAYS = condition("always", lambda machine: True)
ON_LINUX = condition("on linux", lambda machine: machine.kernel == "linux")


def reading(**absent: str) -> Callable[[machines.Condition], str | None]:
    """A reading of the machine where the conditions named in ``absent`` are missing."""
    return lambda one: absent.get(one.name)


# ----------------------------------------------------------------------------------------
# The decision
# ----------------------------------------------------------------------------------------


def test_what_is_here_runs() -> None:
    assert machines.decision([(ALWAYS, ""), (ON_LINUX, "")], LINUX, reading()).kind == "runs"


def test_what_is_missing_where_it_need_not_be_is_skipped_with_the_why_and_the_reason() -> None:
    decided = machines.decision([(ON_LINUX, "the why")], MAC, reading(**{"on linux": "absent"}))

    assert decided == machines.Decision("skipped", "the why — absent")


def test_what_is_missing_where_it_must_be_is_red_and_says_what_and_where() -> None:
    decided = machines.decision([(ON_LINUX, "the why")], LINUX, reading(**{"on linux": "absent"}))

    assert decided.kind == "red"
    assert "on linux must be here" in decided.said and "absent" in decided.said


def test_a_condition_carried_twice_is_red() -> None:
    decided = machines.decision([(ALWAYS, ""), (ALWAYS, "again")], LINUX, reading())

    assert decided.kind == "red" and "twice" in decided.said


def test_a_test_that_does_not_cover_this_machine_is_skipped_whatever_else_is_missing() -> None:
    """The order the author wrote does not decide: a condition that need not be here and is
    missing skips the test, even beside one that must be here and is missing too — the test does
    not cover this machine. And the second is never read: what costs is read only where the test
    would run."""
    read: list[str] = []

    def missing(one: machines.Condition) -> str | None:
        read.append(one.name)
        return "absent"

    decided = machines.decision([(ALWAYS, ""), (ON_LINUX, "")], MAC, missing)

    assert decided.kind == "skipped"
    assert read == ["on linux"]


def every_condition() -> list[machines.Condition]:
    """Every condition of the one place, found in the module — not listed here."""
    return [one for one in vars(machines).values() if isinstance(one, machines.Condition)]


def test_the_one_place_has_its_conditions_each_once_by_name() -> None:
    found = every_condition()

    assert len(found) >= 20
    assert len({one.name for one in found}) == len(found)


@pytest.mark.parametrize("machine", [LINUX, MAC, WINDOWS], ids=["ubuntu", "macos", "windows"])
@pytest.mark.parametrize("one", every_condition(), ids=lambda one: one.name)
def test_every_declaration_is_exercised_in_both_values_on_the_machines_of_the_ci(
    one: machines.Condition, machine: machines.Machine
) -> None:
    """Held: it runs. Missing: red where it is declared to hold, skipped where it is not. The
    declaration is the only thing that tells the two apart."""
    held = machines.decision([(one, "")], machine, lambda _: None)
    missing = machines.decision([(one, "")], machine, lambda _: "absent")

    assert held.kind == "runs"
    assert missing.kind == ("red" if one.required(machine) else "skipped")


def test_the_declarations_say_the_machines_the_census_found() -> None:
    """Where a condition must hold, for the conditions whose answer is not their own name: the
    programs of POSIX on Darwin and Linux, the user that chmod binds and the permission of the
    screen on the runners, the volume that ignores case on Darwin's kernel."""
    for program in (machines.MAKE, machines.LSOF, machines.USR_BIN_TRUE, machines.CLAUDE_CODE):
        assert [program.required(one) for one in (LINUX, MAC, WINDOWS)] == [True, True, False]
    assert [machines.PERMISSIONS_BITE.required(one) for one in (MAC, A_MAC_OF_SOMEBODY)] == [
        True,
        False,
    ]
    assert machines.SCREEN_RECORDING.required(MAC) and not machines.SCREEN_RECORDING.required(LINUX)
    assert machines.IGNORES_CASE.required(PRETENDED), "a Mac pretending: the volume is the Mac's"
    assert not machines.DARWIN.required(PRETENDED), "the system pretended is not Darwin"
    assert not machines.PROC.required(PRETENDED), "the kernel is not pretended"


def test_a_test_of_a_binary_is_known_by_its_marks() -> None:
    """Decision 79 (a): the conditions that name a real binary a test launches say so, and a test
    is of a binary by what it needs — the browser of the profile, the binary of Claude Code —, never
    by the file it is in."""
    named = {one.name for one in every_condition() if one.binary}

    assert named == {machines.PROFILE_BROWSER.name, machines.CLAUDE_CODE.name}
    assert machines.of_a_binary(
        Item(machines.needs(machines.POSIX), machines.needs(machines.CLAUDE_CODE))
    )
    assert not machines.of_a_binary(Item(machines.needs(machines.POSIX, machines.MAKE)))
    assert not machines.of_a_binary(Item())


def test_needs_takes_conditions_of_the_one_place_and_at_least_one() -> None:
    with pytest.raises(TypeError):
        machines.needs()
    with pytest.raises(TypeError):
        machines.needs("Darwin")  # type: ignore[arg-type]
    assert machines.needs(machines.DARWIN, why="w").mark.kwargs == {"why": "w"}


# ----------------------------------------------------------------------------------------
# The jobs of the CI
# ----------------------------------------------------------------------------------------

WORKFLOW = """
jobs:
  node-windows:
    steps:
      - run: uv run pytest -p no:cacheprovider --no-cov tests/node tests/x/test_on_the_line.py
"""


def test_the_windows_job_collects_what_its_line_names() -> None:
    (_, _, windows) = machines.jobs(WORKFLOW)

    assert machines.windows_line(WORKFLOW) == ["tests/node", "tests/x/test_on_the_line.py"]
    assert windows.takes("tests/node/test_a.py") and windows.takes("tests/x/test_on_the_line.py")
    assert not windows.takes("tests/nodes/test_a.py") and not windows.takes("tests/x/test_b.py")


def test_a_test_runs_on_the_jobs_that_collect_it_and_have_all_it_needs() -> None:
    among = machines.jobs(WORKFLOW)
    on_windows = [machines.WINDOWS]

    assert machines.runs_on([], "tests/x/test_b.py", among) == [
        "make check (ubuntu-24.04)",
        "make check (macos-latest)",
    ]
    assert machines.runs_on(on_windows, "tests/x/test_on_the_line.py", among) == [
        "node suite (windows-latest)"
    ]
    assert machines.runs_on(on_windows, "tests/x/test_b.py", among) == []
    assert machines.runs_on([machines.DARWIN, machines.PROC], "tests/x/test_b.py", among) == []


def test_a_test_that_runs_on_no_job_has_a_reason_only_in_a_declared_place() -> None:
    said = condition("said", lambda machine: False, nowhere="no runner has it")
    silent = condition("silent", lambda machine: False)

    assert machines.nowhere_said([silent], "tests/x/test_b.py", {}) is None
    assert machines.nowhere_said([silent, said], "tests/x/test_b.py", {}) == "no runner has it"
    assert machines.nowhere_said([silent], "tests/x/test_b.py", {"tests/x/test_b.py": "why"}) == (
        "why"
    )


def test_every_test_of_the_suite_runs_on_a_job_or_says_why_and_the_sapi_smoke_says_why() -> None:
    """The one test that runs on no job today, from the declarations: its reason is in
    ``tests/windows.py``."""
    among = machines.jobs(machines.WORKFLOW.read_text(encoding="utf-8"))
    sapi = "tests/infrastructure/machine/test_sapi_smoke.py"

    assert machines.runs_on([machines.WINDOWS], sapi, among) == []
    assert machines.nowhere_said([machines.WINDOWS], sapi) == "a CI runner has no speakers"


# ----------------------------------------------------------------------------------------
# The guard, on an item, and wired into the suite
# ----------------------------------------------------------------------------------------


class Item:
    """What the hook hands to the guard, as far as the guard reads it."""

    def __init__(self, *needs: pytest.MarkDecorator) -> None:
        self.nodeid = "tests/x/test_a.py::test_a"
        self.marks = [one.mark for one in needs]
        self.added: list[pytest.MarkDecorator] = []

    def iter_markers(self, name: str) -> list[pytest.Mark]:
        return [one for one in self.marks if one.name == name]

    def add_marker(self, mark: pytest.MarkDecorator) -> None:
        self.added.append(mark)


def test_the_guard_leaves_alone_a_test_that_needs_nothing() -> None:
    item = Item()

    machines.guard(item)  # type: ignore[arg-type]

    assert item.added == []


def test_the_guard_skips_with_the_reason_or_turns_red() -> None:
    absent = machines.Condition("absent", lambda: "not here", lambda machine: machine.runner, "r")
    must = machines.Condition("must", lambda: "not here", lambda machine: True, "everywhere")
    skipped, red = Item(machines.needs(absent, why="w")), Item(machines.needs(must))
    runner = os.environ.pop("GITHUB_ACTIONS", None)
    try:
        machines.guard(skipped)  # type: ignore[arg-type]
        with pytest.raises(pytest.fail.Exception, match="must must be here"):
            machines.guard(red)  # type: ignore[arg-type]
    finally:
        if runner is not None:
            os.environ["GITHUB_ACTIONS"] = runner

    assert [(one.mark.args, one.mark.kwargs) for one in skipped.added] == [
        ((True,), {"reason": "w — not here"})
    ]


SHAPES_THE_OUTPUT = (
    "CI",
    "BUILD_NUMBER",
    "COLUMNS",
    "PYTEST_ADDOPTS",
    "PYTEST_PLUGINS",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
    "PY_COLORS",
    "NO_COLOR",
    "FORCE_COLOR",
    "GITHUB_ACTIONS",
)
"""What in the environment changes what the pytest of the cases writes or decides — the form of
``tests/test_profile_browser.py``, and ``GITHUB_ACTIONS``: the cases are about a machine that is no
runner, and the runner sets it."""


def cases_said() -> str:
    environment = {
        name: value for name, value in os.environ.items() if name not in SHAPES_THE_OUTPUT
    }
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", CASES, "-p", "no:cacheprovider", "--no-cov", "-n0", "-rA"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env=environment,
    )
    del environment
    return ran.stdout


def test_the_hook_of_the_suite_is_the_guard() -> None:
    """In a pytest of its own, with the hook of this suite: each case is what its condition says."""
    said = cases_said()

    assert f"PASSED {CASES}::test_runs_where_what_it_needs_is_here" in said, said
    assert "the reason of the case — it is not on this machine" in said, said
    assert f"ERROR {CASES}::test_is_red_where_what_it_needs_must_be" in said, said
    assert "something that must be here must be here" in said, said
    assert f"ERROR {CASES}::test_is_red_because_no_job_runs_it" in said, said
    assert "this test runs on no job of the CI" in said, said
    assert "1 passed, 2 skipped, 2 errors" in said, said
