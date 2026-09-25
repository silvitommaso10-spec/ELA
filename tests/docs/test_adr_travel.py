"""ADR 0048 and the running code describe the same travelling action, the same beat, the same lock.

This is where the **pin on today's totals** lives since M13.3 (the precedent of M13.1 dec. K and of
M13.2): an ADR is immutable, so each older one keeps saying the number it saw, and the ADR that
last changed a number carries the assertion about the tree as it is now. ADR 0048 is written one
piece per commit, in the order of the SPEC; the pins grow with it.
"""

from __future__ import annotations

from pathlib import Path

from ela.devices import BEATS_PER_TTL, LocalHeartbeat
from ela.ports import LocalBeat
from ela.tools import RESERVED_ON_WINDOWS
from tests.architecture.rules import RULES
from tests.contracts.protocols import port_protocols
from tests.docs.test_adr_composition import coded_routes

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0048-travelling-action.md"
MILESTONE = ROOT / "docs" / "milestones" / "M13.3.md"


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def section(number: int) -> str:
    """The text of ``### <number>.`` up to the next section of the same level."""
    text = adr_text()
    start = text.index(f"### {number}. ")
    end = text.find("\n### ", start + 1)
    return text[start : end if end != -1 else None]


def conseguenze() -> str:
    return adr_text().split("## Conseguenze", 1)[1]


# ----------------------------------------------------------------------------------------
# The totals of today, pinned here because this ADR is the one that changed them
# ----------------------------------------------------------------------------------------


def test_the_conseguenze_count_the_rules_the_ports_and_the_routes_of_today() -> None:
    text = conseguenze()

    assert "**cinquantasette**" in text
    assert len(RULES) == 57
    assert "**ventotto**" in text
    assert len(tuple(port_protocols())) == 28
    assert "**quarantotto**" in text
    assert len(coded_routes()) == 48


# ----------------------------------------------------------------------------------------
# §1 and §2: the lock, and the beat
# ----------------------------------------------------------------------------------------


def test_the_lock_section_names_the_test_and_the_rule_that_keep_it() -> None:
    text = section(1)

    assert "tests/api/test_task_lock.py" in text
    assert "tests/architecture/test_travel_rules.py" in text
    assert "ADR 0023 §9" in text


def test_the_beat_section_says_the_period_the_code_derives() -> None:
    text = section(2)

    assert BEATS_PER_TTL == 3
    assert "un terzo del TTL" in text
    assert "20 s col default" in text
    assert "`LocalHeartbeat`" in text and "`LocalBeat`" in text
    assert issubclass(LocalHeartbeat, object) and LocalBeat.__name__ == "LocalBeat"
    assert "tests/executive/test_runner_heartbeat.py" in text


# ----------------------------------------------------------------------------------------
# §4 and §5: the grammar of every system, and the tests of Windows in the job
# ----------------------------------------------------------------------------------------


def test_the_grammar_section_names_the_table_and_its_tripwire() -> None:
    text = section(4)

    assert "`RESERVED_ON_WINDOWS`" in text and "COM0" in text and "LPT0" in text
    assert {"COM0", "LPT0"} <= RESERVED_ON_WINDOWS
    assert "`ntpath.isreserved`" in text and "tests/tools/test_paths.py" in text
    assert "`is_junction()`" in text
    assert "**Il Mac si stringe, e lo si scrive**" in text
    assert "tests/tools/test_paths_windows.py" in text


def test_the_payment_of_adr_0047_17_names_the_job_the_map_and_the_turned_defence() -> None:
    text = section(5)
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert text.startswith("### 5. Il debito di ADR 0047 §17, saldato")
    for named in (
        "tests/infrastructure/machine/test_acl_smoke.py",
        "tests/infrastructure/machine/test_power_smoke.py",
        "tests/tools/test_paths_windows.py",
    ):
        assert named in text and named in workflow, named
    assert "`tests/windows.py`" in text and "`test_sapi_smoke.py`" in text
    assert "test_every_test_of_windows_is_in_the_job_or_says_why_not" in text
