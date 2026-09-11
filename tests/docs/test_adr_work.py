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
from ela.testing.fakes import FakeModelRouter
from ela.tools import CaptureSettings, CaptureStore, production_verifiers
from tests.architecture.rules import RULES
from tests.contracts.protocols import port_protocols
from tests.docs.test_adr_nodes import documented_rules

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


def test_the_constraint_adr_0037_declared_is_paid_here_and_stays_there() -> None:
    """Dec. O: ADR 0037 declared that a remote node receives no work until M12.2; ADR 0038 records
    it as paid, in the form ADR 0029 used for ADR 0028 §9, and ADR 0037 is not rewritten."""
    assert PAID_CONSTRAINT in ADR_0037.read_text(encoding="utf-8")
    assert PAID_CONSTRAINT in adr_text()
    assert "**saldato**" in adr_text()
