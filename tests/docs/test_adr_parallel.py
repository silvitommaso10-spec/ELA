"""ADR 0041 and the tree say the same thing: the suite runs in parallel, and the debt is paid.

Two claims are checked. The first is §1 — ``-n auto`` in ``addopts``, next to the same coverage
options, and ``pytest-xdist`` among the development dependencies — because a decision the
configuration no longer carries is a decision nobody took back. The second is the defence §5 asked
for, in the form of ADR 0035 §7, **turned round by M9.5** (ADR 0069 §2): the waits the debt listed
are gone from their files, each test waits for an event or says why it does not, and the payment
is written in an ADR.
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


PAYMENT = ROOT / "docs" / "adr" / "0069-suite-discipline.md"
PAID = "### 2. Il debito di ADR 0041 §5, saldato: le cinque attese, e i test di architettura"
STAYS = ("tests/perception/test_core.py", "perception_loop_interval_seconds=1")
"""The one wait of §5 that stays, a cadence the verdict does not depend on — with its reason beside
it, in the test's own words (decision 69 of the review at ``ad1826c``)."""


def still_waiting(sources: dict[str, str]) -> list[tuple[str, str]]:
    """The waits of the list still in their files — but the cadence that stays."""
    return [(path, wait) for path, wait in WAITS if (path, wait) != STAYS and wait in sources[path]]


def sources() -> dict[str, str]:
    return {path: (ROOT / path).read_text(encoding="utf-8") for path, _ in WAITS}


def test_the_tests_that_waited_wait_for_an_event_or_say_why() -> None:
    """ADR 0041 §5, turned round by M9.5 (ADR 0069 §2). The waits it listed are gone, but the
    cadence of the loop of perception, which stays with the reason beside it; and the payment is a
    section of the ADR that paid, which says the cadence stays."""
    payment = " ".join(PAYMENT.read_text(encoding="utf-8").split())
    found = sources()

    assert PAID in payment
    assert "il secondo di tempo vero resta" in payment
    assert still_waiting(found) == []
    assert (
        STAYS[1] in found[STAYS[0]] and "is not the repair of a measured cause" in found[STAYS[0]]
    )


def test_a_wait_that_came_back_is_seen() -> None:
    """The negative case: a duration of the list written again into its file is found."""
    path, wait = WAITS[0]
    found = sources()
    found[path] += f"\n        {wait}\n"

    assert still_waiting(found) == [(path, wait)]
