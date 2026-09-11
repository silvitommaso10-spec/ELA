"""ADR 0036 and the code say the same thing about the listening (M11.2).

Two things live here rather than beside the feature they describe. The first is the dated debt of
§12 — a value in the audit's enum that nobody writes — kept honest by the smallest defence a debt
can have: an assertion that it is *still* unpaid, so that paying it takes this section out with it.

The second is the pin on today's totals, which this ADR takes over because it is the one that last
changed them.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from ela.domain import AuditEventType
from ela.permissions import production_catalogue
from tests.architecture.rules import RULES
from tests.architecture.violations import PACKAGE_ROOT
from tests.contracts.protocols import port_protocols
from tests.docs.test_adr_placement import _rules_up_to

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0036-listening.md"
UNWRITTEN = AuditEventType.PROVIDER_CALLED


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def writers_of(event: AuditEventType) -> list[str]:
    """Every module of ``src/ela`` that names ``event`` other than where the enum is declared.

    Read from the AST rather than by grep so that the answer is about code and not about prose: a
    docstring that mentions the member is not a writer, and this debt is precisely about the
    difference between naming a thing and doing it.
    """
    found = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        if path.name == "domain.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == event.name:
                found.append(str(path.relative_to(PACKAGE_ROOT)))
                break
    return found


def test_the_debt_of_paragraph_12_is_still_open_and_says_who_owns_it() -> None:
    """The form ADR 0035 §7 used, and the device that made it get paid: a date and an owner.

    Asserted in the direction that makes the declaration expire. The day ``PROVIDER_CALLED`` gets
    a writer — or leaves the enum — this fails, and §12 comes out with it.
    """
    text = adr_text()

    assert writers_of(UNWRITTEN) == [], "the debt of ADR 0036 §12 is paid: remove the section"
    assert UNWRITTEN.name in text
    assert "2026-09-10" in text
    assert "a carico di chi aggiungerà il prossimo `AuditEventType`" in text


def test_the_event_this_milestone_added_does_have_a_writer() -> None:
    """The other half of the debt: a type added here is a type something writes."""
    assert writers_of(AuditEventType.SENSOR_ACTIVATED) == ["executive/executor.py"]


def test_the_conseguenze_count_the_rules_and_the_ports_of_today() -> None:
    """The pin on today's totals, which moves to the ADR that last changed them.

    The rules have moved on: M12.1 adds rules 46 and 47 before ADR 0037 is written (ADR 0030 §15,
    the defence before the room). So ADR 0036's «quarantacinque» is read the way ADR 0026's
    «trentuno» is (``test_adr_placement.py``): as a claim about the rules numbered up to 45, which
    each rule declares in its own docstring — history that stays checkable, not a total. The pin on
    today's number of rules moves to ADR 0037's test when that document exists. Ports and
    capabilities have not moved yet, and stay pinned here until they do.
    """
    conseguenze = adr_text().split("## Conseguenze", 1)[1]

    assert "**quarantacinque**" in conseguenze
    assert len(_rules_up_to(45)) == 45
    assert "**ventitré**" in conseguenze
    assert len(tuple(port_protocols())) == 23
    assert len(production_catalogue().specs()) == 8


def test_the_adr_names_the_rules_it_renamed_and_they_resolve() -> None:
    """``Regole rinominate:`` is how a rule changes without an older ADR being edited."""
    block = adr_text().split("`Regole rinominate:`", 1)[1].split("\n\n", 3)[1]
    rows = re.findall(r"^\| (\d+) \| `([a-z-]+)` \| `([a-z-]+)` \|", block, re.MULTILINE)

    assert {number for number, *_ in rows} == {"34", "35"}
    for _, old, new in rows:
        assert old not in RULES
        assert new in RULES
