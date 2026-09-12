"""ADR 0038 against the code: the protocol of the work (M12.2).

What ADR 0038 says that the code can answer is asked here, table by table, and each table joins the
test in the commit that brings the code making it true: an ADR is written whole, before the code it
describes (ADR 0030 §15), and a check that read a table ahead of its code would be red for a reason
nobody could act on. The pin on today's totals is here too, taken over from ADR 0037.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

from ela.permissions import production_catalogue
from ela.testing.fakes import (
    FakeClock,
    FakeIdGenerator,
    FakeListening,
    FakeModelRouter,
    FakeProbe,
    FakeProviderRegistry,
    FakeScreenCapture,
    FakeSpeech,
    FakeTextRecognition,
)
from ela.tools import (
    ECHO_TOOL_NAME,
    CaptureSettings,
    CaptureStore,
    production_tools,
    production_verifiers,
)
from tests.architecture.rules import RULES
from tests.contracts.protocols import port_protocols
from tests.docs.test_adr_nodes import documented_rules
from tests.executive import test_assignment_recovery as recovery

ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "adr"
ADR_PATH = ADR_DIR / "0038-work-protocol.md"
ADR_0037 = ADR_DIR / "0037-node-identity.md"
ADDED_RULES = {
    48: "assignment-port-readers",
    49: "assignments-built-only-by-the-assigner",
    50: "release-step-has-one-caller",
    51: "a-work-order-goes-only-to-its-node",
    52: "results-are-minted-by-the-core",
}
PAID_CONSTRAINT = "**Un nodo remoto non riceve lavoro fino a M12.2**"
ANSWER_ROW = re.compile(r"^\| \*\*(Quale [^*]+|Perché [^*]+)\*\* \| (.+) \|$")
"""§16: the four questions of §57 and their answers — two cells, the first one bold."""
_FAKE_MACHINE: dict[str, object] = {
    "clock": FakeClock(),
    "ids": FakeIdGenerator(),
    "router": FakeModelRouter(),
    "providers": FakeProviderRegistry(),
    "screen": FakeScreenCapture(),
    "probe": FakeProbe(),
    "recognition": FakeTextRecognition(),
    "languages": ("it-IT",),
    "listening": FakeListening(),
    "listen_enabled": True,
    "speech": FakeSpeech(),
    "voice": "Alice",
    "voice_enabled": True,
    "speech_online": FakeSpeech(),
    "voice_id": "VZOd9FMXDnXRZpGn0thg",
    "model": "eleven_flash_v2_5",
}
"""Everything ``production_tools`` needs that is a port, faked: what is under test is which tools
say twice-is-once, and that answer is the tool's own and not its machine's."""
WINDOW_ROW = re.compile(r"^\| (A\d+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \| (.+) \|$")
"""§19: the crash windows, named ``A<n>`` — the only table whose first cell is one."""
REPAIRED_MARK = "**Riparato.**"
"""What the document says of a window the next call gets past. ``Non riparato`` is not this."""
RECOVERY_TESTS = Path(__file__).resolve().parents[1] / "executive" / "test_assignment_recovery.py"
VERIFIER_ROW = re.compile(
    r"^\| `([a-z_]+\.[a-z_]+)` \| [^|]+ \| [^|]+ \| [^|]+ \| `(True|False)` \|$"
)
"""§14: a capability, three cells of prose, and what its verifier declares."""


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def conseguenze() -> str:
    return adr_text().split("## Conseguenze", 1)[1]


# ----------------------------------------------------------------------------------------
# The rules, and the pin on today's number of them
# ----------------------------------------------------------------------------------------


def test_the_rules_this_adr_adds_are_registered_under_the_names_it_gives_them() -> None:
    """`Regole aggiunte:` names five rules that exist, each declaring its number."""
    documented = documented_rules(adr_text())

    assert {number: documented.get(number) for number in ADDED_RULES} == ADDED_RULES
    for number, name in ADDED_RULES.items():
        assert name in RULES
        assert f"Rule {number}:" in (inspect.getdoc(RULES[name]) or ""), name


def test_the_conseguenze_count_the_rules_and_the_capabilities_of_today() -> None:
    """The pin on today's totals, taken over from ADR 0037 by the ADR that changed them.

    The rules moved with the two commits that wrote rules 48 to 52 before their code, the ports
    with the commit that wrote the twenty-fifth; the capabilities do not move — in M12.2 four of
    the eight travel and none is added.
    """
    assert "**cinquantadue**" in conseguenze()
    assert len(RULES) == 52
    assert "**venticinque**" in conseguenze()
    assert len(tuple(port_protocols())) == 25
    assert "**restano otto**" in conseguenze()
    assert len(production_catalogue().specs()) == 8


# ----------------------------------------------------------------------------------------
# The guarantee of M12.1 that stops holding
# ----------------------------------------------------------------------------------------


def test_the_verifier_table_says_what_each_verifier_declares(tmp_path: Path) -> None:
    """§14: one row per capability, and its last cell is the ``reads_the_machine`` the verifier of
    the Core declares — the table the orchestrator's filter F7 is built on."""
    captures = CaptureStore(CaptureSettings(capture_dir=tmp_path / "captures"))
    verifiers = production_verifiers(root=tmp_path, router=FakeModelRouter(), captures=captures)
    documented = {
        match.group(1): match.group(2) == "True"
        for line in adr_text().splitlines()
        if (match := VERIFIER_ROW.match(line))
    }

    assert documented == {
        verifier.capability_id: verifier.reads_the_machine for verifier in verifiers.verifiers()
    }
    assert "**Quattro capability viaggiano, quattro no.**" in adr_text()
    assert sorted(documented.values()) == [False] * 4 + [True] * 4


def test_fifteen_is_honoured_by_one_tool_of_eight(tmp_path: Path) -> None:
    """Criterion 12, the user's own sentence pinned: «§15 oggi è onorato da un tool su otto.»

    Among the capabilities that may travel (§14), the tools that can be **run again** are exactly
    ``{core-echo}`` — so today the predicate of the STARTED record and the predicate of D6 coincide,
    and they coincide for a reason that is not D6: D15 keeps ``workspace.write_note`` on this
    machine. The day its verifier runs on the node, a repeatable note claimed and silent would be
    released and written a second time on another machine, and D6 would have to become a second
    predicate in the code. This test is what forces that paragraph to be re-read: it fails if a tool
    changes its idempotency, or if a fourth capability starts travelling.
    """
    captures = CaptureStore(CaptureSettings(capture_dir=tmp_path / "captures"))
    verifiers = production_verifiers(root=tmp_path, router=FakeModelRouter(), captures=captures)
    travels = {v.capability_id for v in verifiers.verifiers() if not v.reads_the_machine}
    tools = production_tools(root=tmp_path, **_FAKE_MACHINE, captures=captures)

    repeatable = {
        tool.name
        for tool in tools.tools()
        if tool.capability_id in travels and tool.idempotent  # type: ignore[attr-defined]
    }

    assert repeatable == {ECHO_TOOL_NAME}
    assert len(tuple(production_catalogue().specs())) == 8
    assert "§15 oggi è onorato da un tool su otto" in adr_text()


# ----------------------------------------------------------------------------------------
# §16 — the four answers of §57
# ----------------------------------------------------------------------------------------


def test_the_four_questions_of_57_are_answered_about_a_node(tmp_path: Path) -> None:
    """§16, in the form ADR 0030 §17 fixed for rule 35 — the provider, here, being a node.

    The table is read rather than admired: each answer names the artefact the code actually
    provides, and the last one is the one that matters most, because it says the two policies are
    **the user's** and are compared in one place. A table that said "two policies" while the code
    compared one would be the kind of claim §57 exists to prevent.
    """
    documented = {
        match.group(1): match.group(2)
        for line in adr_text().splitlines()
        if (match := ANSWER_ROW.match(line))
    }

    assert set(documented) == {
        "Quale nodo",
        "Quale tipo di dati",
        "Perché viene inviato",
        "Quale policy lo consente",
    }
    # one node, named by the assignment, and the order composed in one place (rule 51)
    assert "assegnazione nomina" in documented["Quale nodo"]
    assert "regola 51" in documented["Quale nodo"]
    # one step's arguments, for one capability: no other step, no earlier result, no artefact
    assert "argomenti di uno step" in documented["Quale tipo di dati"]
    # the reason is a recorded choice
    assert "DEVICE_SELECTED" in documented["Perché viene inviato"]
    assert "max_privacy" in documented["Perché viene inviato"]
    # and both policies are the user's, compared where the filter lives
    policy = documented["Quale policy lo consente"]
    assert "tetto del nodo" in policy and "sensibilità del task" in policy
    assert "nessuna la scrive il nodo" in policy or "nessuna delle due la scrive il nodo" in policy


# ----------------------------------------------------------------------------------------
# §19 — the crash windows, and the tests that make them facts
# ----------------------------------------------------------------------------------------


def documented_windows() -> dict[str, str]:
    """``A<n>`` → what the ADR says a retry does there. Anchored on the name, so the table of the
    filters — five cells too — cannot be mistaken for this one."""
    rows = {
        match.group(1): match.group(5)
        for line in adr_text().splitlines()
        if (match := WINDOW_ROW.match(line))
    }
    assert rows, "ADR 0038 §19 must contain the table of the crash windows"
    return rows


def repaired_windows(rows: dict[str, str]) -> frozenset[str]:
    return frozenset(window for window, retry in rows.items() if REPAIRED_MARK in retry)


def test_the_windows_are_numbered_without_gaps() -> None:
    """A gap would mean a window was removed from the table and not from the order of the writes."""
    documented = list(documented_windows())

    assert documented == [f"A{number}" for number in range(1, len(documented) + 1)]
    assert len(documented) == 15


def test_every_window_is_either_repaired_or_declared() -> None:
    """One or the other, never neither: a row that said nothing about a retry would be a window
    nobody has thought about, which is the thing this table exists to prevent."""
    for window, retry in documented_windows().items():
        assert (REPAIRED_MARK in retry) != ("Non riparato" in retry or "Dichiarato" in retry), (
            window
        )


def test_the_repaired_rows_are_the_ones_with_a_retry_test() -> None:
    """``**Riparato.**`` in the document and ``REPAIRED`` in the tests are two names for one fact
    (criterion 28, the rule of ADR 0015 §8 applied to this ADR)."""
    rows = documented_windows()

    assert repaired_windows(rows) == recovery.REPAIRED
    assert set(rows) - repaired_windows(rows) == recovery.DECLARED


def test_every_window_has_a_test_named_after_it() -> None:
    """Repaired or declared, each one is a test: what a retry does in a window nobody repairs is a
    fact too, and a fact that lives only in prose is one the code can stop honouring in silence."""
    source = RECOVERY_TESTS.read_text(encoding="utf-8")

    for window in sorted(documented_windows()):
        assert f"async def test_window_{window.lower()}_" in source, window


def test_a_row_promoted_without_a_test_is_detected() -> None:
    """The negative: a declared row re-labelled ``**Riparato.**`` in the document, with no test
    behind it, must stop agreeing with the code."""
    rows = documented_windows()
    promoted = {**rows, "A12": rows["A12"].replace("Non riparato.", REPAIRED_MARK)}

    assert repaired_windows(promoted) != recovery.REPAIRED
    assert "A12" in repaired_windows(promoted)


def test_the_constraint_adr_0037_declared_is_paid_here_and_stays_there() -> None:
    """Dec. O: ADR 0037 declared that a remote node receives no work until M12.2; ADR 0038 records
    it as paid, in the form ADR 0029 used for ADR 0028 §9, and ADR 0037 is not rewritten."""
    assert PAID_CONSTRAINT in ADR_0037.read_text(encoding="utf-8")
    assert PAID_CONSTRAINT in adr_text()
    assert "**saldato**" in adr_text()
