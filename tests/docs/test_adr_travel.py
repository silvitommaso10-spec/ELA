"""ADR 0048 and the running code describe the same travelling action, the same beat, the same lock.

This is where the **pin on today's totals** lives since M13.3 (the precedent of M13.1 dec. K and of
M13.2): an ADR is immutable, so each older one keeps saying the number it saw, and the ADR that
last changed a number carries the assertion about the tree as it is now. ADR 0048 is written one
piece per commit, in the order of the SPEC; the pins grow with it.
"""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

from ela.composition import CoreSettings
from ela.devices import BEATS_PER_TTL, DeviceOrchestrator, DeviceRegistry, LocalHeartbeat
from ela.domain import CapabilityId
from ela.executive import VERIFICATION_MISSING, Executor
from ela.permissions import CORE_ECHO, MODEL_COMPLETE, TERMINAL_RUN
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
    FS_READ,
    FS_WRITE,
    RESERVED_ON_WINDOWS,
    VERIFIED_ON_THE_NODE,
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
from tests.windows import OUTSIDE_THE_WINDOWS_JOB

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
    """§5 as the first run measured it: the grammar's tests in the job, the two smokes in the map
    with the reason the run gave, and the defect of the product that reason reveals, declared."""
    text = section(5)
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert text.startswith("### 5. Il debito di ADR 0047 §17, saldato")
    assert "tests/tools/test_paths_windows.py" in text
    assert "tests/tools/test_paths_windows.py" in workflow
    for smoke in ("test_acl_smoke.py", "test_power_smoke.py"):
        assert f"tests/infrastructure/machine/{smoke}" in workflow, smoke
        assert f"tests/infrastructure/machine/{smoke}" not in OUTSIDE_THE_WINDOWS_JOB, smoke
    assert "`36151577468`" in text and "`PSModulePath`" in text
    assert "**Riparato da M12.3d**" in text and "`36164151413`" in text
    assert "`tests/windows.py`" in text and "`test_sapi_smoke.py`" in text
    assert "test_every_test_of_windows_is_in_the_job_or_says_why_not" in text


# ----------------------------------------------------------------------------------------
# §6: relocatable, and the guard of ADR 0038 §8 in its new home
# ----------------------------------------------------------------------------------------


def travelling(
    tools: ToolRegistryPort,
    verifiers: VerifierRegistryPort,
    carried: frozenset[CapabilityId] = VERIFIED_ON_THE_NODE,
) -> set[str]:
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
        carried=carried,
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


# ----------------------------------------------------------------------------------------
# §7: the verifier where the effect happens
# ----------------------------------------------------------------------------------------


def test_the_section_of_the_verifier_on_the_node_names_what_the_code_holds() -> None:
    text = section(7)

    assert {FS_READ, FS_WRITE} == VERIFIED_ON_THE_NODE
    for named in (
        "`VERIFIED_ON_THE_NODE`",
        "`verification.missing`",
        "`verified_on`",
        "`VerifierPort.failure_codes`",
        "`refuse_the_root`",
        "`carried`",
        "`success_conditions`",
    ):
        assert named in text, named
    assert VERIFICATION_MISSING == "verification.missing"


def test_the_section_of_the_question_says_what_is_lost_and_what_is_not() -> None:
    text = " ".join(section(8).split())

    assert "`asserted`" in text and "`UNSEEN`" in text
    assert "ADR 0011 §3 e ADR 0045 §6 e §6-bis si leggono con questa sezione accanto" in text
    assert "il costo è un sì speso, mai un effetto diverso da quello approvato" in text
    assert "byte per byte" in text
    assert "**Lo sguardo sul nodo prima della domanda**" in adr_text()
    assert "non è un debito" in " ".join(adr_text().split())


# ----------------------------------------------------------------------------------------
# §9 to §14: the debts re-declared, the answers of §57, what is lost, the weights, the clock
# ----------------------------------------------------------------------------------------

ANSWER_ROW = re.compile(r"^\| \*\*(Quale [^*]+|Perché [^*]+)\*\* \| (.+) \|$")
LOSS_ROW = re.compile(
    r"^\| `(fs\.[a-z]+)` \| [^|]+ \| [^|]+ \| [^|]+ \| `(True|False)`, del nodo \|$"
)
TRAVELLING_TODAY = frozenset(
    {"core.echo", "model.complete", "voice.speak", "voice.speak_online", "fs.read", "fs.write"}
)
"""The capabilities F7 lets go to a node, as M13.3 left them — pinned, because the weights of §17
were chosen for these and for no other (ADR 0048 §13)."""


def test_the_terminal_and_its_linux_residue_are_re_declared_to_m13_7() -> None:
    """Criterion 18: ADR 0047 §13 and §5 have a registered owner, and the terminal does not
    travel — it is not among the capabilities a node verifies."""
    owner = (ROOT / "docs" / "milestones" / "M13.7.md").read_text(encoding="utf-8")

    for number in (9, 10):
        text = " ".join(section(number).split())
        assert "**Debito a carico di M13.7**, dichiarato il **2026-09-25**" in text, number
    assert "ADR 0047 §13" in section(9) and "ADR 0047 §5" in section(10)
    assert TERMINAL_RUN not in VERIFIED_ON_THE_NODE
    assert "ADR 0047 §13" in owner and "ADR 0047 §5" in owner


def test_the_four_answers_of_fifty_seven_are_given_for_a_file_on_a_node() -> None:
    rows = [ANSWER_ROW.match(line) for line in section(11).splitlines()]
    asked = [row.group(1) for row in rows if row is not None]

    assert asked == [
        "Quale nodo",
        "Quale tipo di dati",
        "Perché viene inviato",
        "Quale policy lo consente",
    ]
    assert "M13.8" in section(11)


def test_what_stops_being_proven_is_written_for_the_two_that_travel_with_their_verifier(
    tmp_path: Path,
) -> None:
    """The table of §12 names exactly the capabilities a node verifies, and says their verifier
    reads the machine — the node's — which is what the code declares."""
    _, verifiers, _ = _production(tmp_path)
    rows = {
        match.group(1): match.group(2) == "True"
        for line in section(12).splitlines()
        if (match := LOSS_ROW.match(line))
    }

    assert set(rows) == {str(cid) for cid in VERIFIED_ON_THE_NODE}
    assert all(rows.values())
    assert all(verifiers.get(cid).reads_the_machine for cid in VERIFIED_ON_THE_NODE)


def test_the_tripwire_of_the_weights(tmp_path: Path) -> None:
    """Decision 12: the magnitudes of §17 are a choice, and computing power, workload and status
    are stubs no travelling work puts to the test. The day the set of what travels changes, this
    fails — go and read ADR 0048 §13 again before the new capability is weighed like the old."""
    tools, verifiers, _ = _production(tmp_path)
    names = travelling(tools, verifiers)
    travels = {str(tool.capability_id) for tool in tools.tools() if tool.name in names}

    assert travels == TRAVELLING_TODAY, (
        "the capabilities that travel changed: the weights of §17 were chosen for the old set — "
        "read ADR 0048 §13 ('I pesi di §17') and say whether they still hold"
    )
    assert "### 13. I pesi di §17" in adr_text()


def test_the_status_of_local_is_the_executor_s_and_a_question_occupies_nothing() -> None:
    """The user's correction of decision 2 (2026-09-26): ``BUSY`` while a tool runs here, from its
    start to its result stored — the first form, a step ``RUNNING`` on ``local``, is gone from the
    code and says so in the ADR only as what was corrected."""
    text = " ".join(section(13).split())

    assert callable(Executor.running_here)
    assert "`Executor.running_here`" in text
    assert "dall'avvio del tool al risultato registrato" in text
    assert "**Una domanda non occupa il Mac**" in text
    assert "tests/executive/test_local_status.py" in text
    assert "running_on" not in adr_text() and "STARTED_ON" not in adr_text()


def test_the_order_of_the_network_is_written_measured_with_its_day_and_its_files() -> None:
    """Rule 2 and rule 6 of the SPEC: the order confirmed for both kinds of work, with the medians,
    the maxima, the day and the files — for the one pair measured."""
    text = " ".join(section(13).split())

    assert "**L'esito: l'ordine è misurato**, il **2026-09-26**" in text
    assert "| `core.echo` | 0,9 ms | 1,0 ms | 463 ms | 1010 ms | 93,5 ms |" in section(13)
    assert "| `fs.read` | 1,7 ms | 1,9 ms | 559 ms | 1092 ms | 144 ms |" in section(13)
    assert "**l'eco e la lettura danno lo stesso ordine**" in text
    assert "**L'ordine vale per la sola coppia misurata**" in text
    for measured in ("A-eco", "A-lettura", "B-eco", "B-lettura"):
        assert f"`m13.3-pesi-{measured}.jsonl`" in text


WORST_AHEAD_SECONDS = 38.332
"""The worst drift of the PC in the thirty days before the manual test: the time service took the
clock back by 38 332 ms on 2026-09-03 (ADR 0048 §14)."""


def test_the_clock_section_says_the_premise_was_wrong_with_the_measures_and_the_history() -> None:
    """The user's correction after the measure (2026-09-26): the wake-up is not the worst case —
    the error grows with the time since the last synchronisation, and the history of the
    corrections is where the worst case lives."""
    text = " ".join(section(14).split())

    assert "**La premessa era sbagliata**" in text
    assert "**L'errore cresce con il tempo passato dall'ultima sincronizzazione**" in text
    assert "**0,83 s al giorno in avanti**" in text
    evening = "01:01–01:03, il PC otto giorni dopo l'ultima sincronizzazione | +0,0698 ± 0,030 s |"
    assert evening in section(14)
    assert "| +0,0362 ± 0,031 s | da −0,3833 a −0,3862 s | **+0,42 s** |" in section(14)
    assert "**La misura del risveglio vale**" in text
    assert "**Il peggio osservato è 38,3 s avanti**" in text
    assert "**In trenta giorni il PC non è mai stato indietro.**" in text
    assert "si scrive qui quando c'è" not in text
    for measured in ("mac", "mac-2", "pc", "pc-sveglio", "pc-sveglio-eventi", "pc-correzioni"):
        assert f"`m13.3-orologio-{measured}.txt`" in text


def test_the_worst_drift_observed_fits_the_margin_the_settings_give() -> None:
    """The comparison is with the margin of today's settings: if the TTLs move, the ADR's
    arithmetic goes stale here and not silently."""
    core = CoreSettings.model_construct()
    margin = core.decision_ttl_seconds - core.assignment_ttl_seconds
    left = f"{margin - WORST_AHEAD_SECONDS:.1f}".replace(".", ",")
    text = " ".join(section(14).split())

    assert margin > WORST_AHEAD_SECONDS
    assert f"ne lascia {left}" in text
    assert (
        "**La deriva ci sta dentro con margine, e i cinque minuti di ADR 0011 §9 restano.**" in text
    )


def test_the_guide_and_the_spec_no_longer_call_the_wake_up_the_worst_case() -> None:
    guide = (ROOT / "docs" / "GETTING_STARTED.md").read_text(encoding="utf-8")
    spec = MILESTONE.read_text(encoding="utf-8")

    assert "**Il risveglio non è il caso peggiore.**" in guide
    assert "la lettura non è il caso peggiore" not in " ".join(guide.split())
    assert "**Il vincolo 3 era sbagliato: il risveglio non è il caso peggiore.**" in spec
    assert "La lettura è il caso peggiore" not in " ".join(spec.split())


def test_the_margin_of_the_clock_is_the_difference_of_the_two_settings() -> None:
    core = CoreSettings.model_construct()
    margin = core.decision_ttl_seconds - core.assignment_ttl_seconds

    assert margin == 180
    assert "**180 s con i default**" in section(14)
