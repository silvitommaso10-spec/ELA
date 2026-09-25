"""ADR 0048 and the running code describe the same travelling action, the same beat, the same lock.

This is where the **pin on today's totals** lives since M13.3 (the precedent of M13.1 dec. K and of
M13.2): an ADR is immutable, so each older one keeps saying the number it saw, and the ADR that
last changed a number carries the assertion about the tree as it is now. ADR 0048 is written one
piece per commit, in the order of the SPEC; the pins grow with it.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from ela.devices import BEATS_PER_TTL, DeviceOrchestrator, DeviceRegistry, LocalHeartbeat
from ela.permissions import CORE_ECHO, MODEL_COMPLETE
from ela.ports import LocalBeat, ToolRegistryPort, VerifierRegistryPort
from ela.testing.fakes import (
    FakeAuditLog,
    FakeCapabilityRegistry,
    FakeClock,
    FakeDeviceRegistry,
    FakeIdGenerator,
    FakeTool,
    FakeVerifier,
)
from ela.tools import (
    ECHO_TOOL_NAME,
    RESERVED_ON_WINDOWS,
    EchoTool,
    EchoVerifier,
    ToolRegistry,
    VerifierRegistry,
)
from tests.architecture.rules import RULES
from tests.contracts.protocols import port_protocols
from tests.devices.nodes import step
from tests.docs.test_adr_composition import coded_routes
from tests.tools.test_registry import _production

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0048-travelling-action.md"
WORK_ADR_PATH = ROOT / "docs" / "adr" / "0038-work-protocol.md"
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


# ----------------------------------------------------------------------------------------
# §6: relocatable, and the guard of ADR 0038 §8 in its new home
# ----------------------------------------------------------------------------------------


def travelling(tools: ToolRegistryPort, verifiers: VerifierRegistryPort) -> set[str]:
    """The names of the tools whose capability F7 lets go to a node: asked of the orchestrator's
    own ``requirements``, not restated — the day a node carries a verifier, this grows by itself."""
    clock, audit = FakeClock(), FakeAuditLog()
    orchestrator = DeviceOrchestrator(
        DeviceRegistry(
            FakeDeviceRegistry(), clock, audit, FakeIdGenerator(), heartbeat_ttl=timedelta(60)
        ),
        tools,
        audit,
        FakeIdGenerator(),
        clock,
        verifiers=verifiers,
        capabilities=FakeCapabilityRegistry(),
    )
    return {
        tool.name
        for tool in tools.tools()
        if not orchestrator.requirements(
            step(capabilities=(tool.capability_id,), goal=tool.name)
        ).verified_here
    }


def moving(tools: ToolRegistryPort, verifiers: VerifierRegistryPort) -> set[str]:
    """Travels ∩ relocatable: the tools whose claimed and silent work is placed again."""
    names = travelling(tools, verifiers)
    return {tool.name for tool in tools.tools() if tool.name in names and tool.relocatable}


def test_the_work_that_moves_when_a_node_goes_silent_is_the_echo_s_alone(tmp_path: Path) -> None:
    """ADR 0038 §8's guard, rewritten and not loosened (M13.3, form E). It computed «travels» from
    ``reads_the_machine``, and with ``fs.*`` travelling it would have seen nothing. Now «travels» is
    what F7 lets go, and the predicate is ``relocatable``: the set is ``{core-echo}``, and the entry
    condition of M13.6 — more than one relocatable tool that travels — is still not met."""
    tools, verifiers, _ = _production(tmp_path)

    assert moving(tools, verifiers) == {ECHO_TOOL_NAME}
    assert "§15 oggi è onorato da un tool su otto" in WORK_ADR_PATH.read_text(encoding="utf-8")
    assert "«viaggia ∩ ripiazzabile» è `{core-echo}`" in section(6)


def test_the_guard_sees_one_relocatable_tool_more() -> None:
    """The negative case: a second tool that travels and declares itself relocatable is seen."""
    clock, ids = FakeClock(), FakeIdGenerator()
    tools = ToolRegistry(
        (
            EchoTool(clock, ids),
            FakeTool(MODEL_COMPLETE, clock, ids, name="another", relocatable=True),
        )
    )
    verifiers = VerifierRegistry(
        (EchoVerifier(), FakeVerifier(MODEL_COMPLETE, reads_the_machine=False))
    )

    assert moving(tools, verifiers) == {ECHO_TOOL_NAME, "another"}
    assert CORE_ECHO in {tool.capability_id for tool in tools.tools()}
