"""ADR 0041 and the tree say the same thing: the suite runs in parallel, and the debt is still owed.

Two claims are checked. The first is §1 — ``-n auto`` in ``addopts``, next to the same coverage
options, and ``pytest-xdist`` among the development dependencies — because a decision the
configuration no longer carries is a decision nobody took back. The second is the defence §5 asked
for, in the form of ADR 0035 §7: the waits the debt lists are still in their files. The day somebody
repairs one, the test below fails, the payment is written in an ADR, and this test is turned round.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0041-parallel-suite.md"
PYPROJECT = ROOT / "pyproject.toml"

WAITS = (
    ("tests/infrastructure/machine/test_spawn.py", "await asyncio.sleep(0.9)"),
    ("tests/infrastructure/machine/test_microphone_smoke.py", "await asyncio.sleep(1.5)"),
    ("tests/infrastructure/machine/test_microphone_smoke.py", "time.sleep(0.2)"),
    ("tests/perception/test_core.py", "perception_loop_interval_seconds=1"),
    ("tests/api/test_server.py", "await asyncio.sleep(0.05)"),
)
"""What each test of §5 waits for, as the file spells it: a duration, or a cadence of real time."""


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def configuration() -> dict[str, object]:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_the_suite_runs_on_every_core_with_the_same_measurement() -> None:
    """§1: the parallel run is in ``addopts``, so ``make check`` and the CI get it without asking,
    and the coverage options beside it are the ones the gates were measured with."""
    pytest_options = configuration()["tool"]["pytest"]["ini_options"]  # type: ignore[index]
    options = pytest_options["addopts"].split()
    development = configuration()["dependency-groups"]["dev"]  # type: ignore[index]

    assert options[options.index("-n") + 1] == "auto"
    assert {"--cov=ela", "--cov-branch"} <= set(options)
    assert any(package.startswith("pytest-xdist") for package in development)


def test_the_debt_declares_its_owner_the_day_and_the_caution() -> None:
    """The form of ADR 0035 §7, and the one line the user asked to travel with it."""
    text = adr_text()

    assert "**Debito a carico della milestone sulla disciplina della suite**" in text
    assert "dichiarato il **2026-09-18**" in text
    assert "la riparazione non toglie un caso" in text


def test_the_tests_that_wait_still_wait() -> None:
    """The smallest defence of §5: each wait is still where the debt says it is.

    Failing here is not a regression. It means the debt is being paid — write the payment in an
    ADR, and turn this test round, as ``test_adr_devices.py`` was turned for ADR 0035 §7.
    """
    text = adr_text()
    for path, wait in WAITS:
        assert f"`{path}" in text, f"ADR 0041 §5 does not name {path}"
        assert wait in (ROOT / path).read_text(encoding="utf-8"), f"{path}: {wait} is gone"
