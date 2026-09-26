"""ADR 0044 against the tree (M17.2): the numbers it states, and the promises it makes.

The shape of ``test_adr_companion.py``: an ADR is immutable, so the pin on *today's* totals lives
with the ADR that last moved them — and since M17.2 that is this one.

What is checked here is what a reader would otherwise have to take on trust: that the role it
names exists, that the rules it says it extends are in the tree and that it adds none, that the
routes it documents are the ones the code serves, and that the constraints it declares are the
ones the milestone declares.
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.api.security import CONSOLE_CODE_ROUTES, CONSOLE_ROUTES, Kind
from ela.domain import DeviceRole
from tests.architecture.rules import RULES
from tests.contracts.protocols import port_protocols
from tests.docs.test_adr_composition import coded_routes

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0044-command-center.md"
MILESTONE = ROOT / "docs" / "milestones" / "M17.2.md"
EXTENDED = ("pages-read-the-routes", "identity-resolved-in-one-place")


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def conseguenze() -> str:
    return adr_text().split("## Conseguenze", 1)[1]


def bullets(text: str) -> set[str]:
    """The bold opening of every bullet of a block: what each line claims, without its prose."""
    return {match.group(1).strip() for match in re.finditer(r"^- \*\*(.+?)\*\*", text, re.M)}


def test_the_conseguenze_count_what_the_tree_had_when_it_was_written() -> None:
    """The pin on *today's* totals moved on to ADR 0047, as it did from ADR 0043 to this one.

    An ADR is immutable: what stays here is that the numbers ADR 0044 wrote are still true **of what
    it saw**. The rules and the routes have not moved since; the ports have — M13.2 added the
    launcher of the terminal —, so that one is counted without it.
    """
    text = conseguenze()

    assert "**cinquantasette**" in text
    assert len(RULES) == 57
    assert "**ventisei**" in text
    assert (
        len(
            tuple(p for p in port_protocols() if p.__name__ not in {"CommandLauncher", "LocalBeat"})
        )
        == 26
    )
    assert "**quarantotto**" in text
    assert len(coded_routes()) == 48


def test_it_adds_no_rule_and_the_two_it_extends_exist() -> None:
    """«Nessuna regola di architettura nuova»: a claim that is only worth what the tree says."""
    assert "Nessuna regola di architettura nuova" in conseguenze()
    for rule in EXTENDED:
        assert rule in RULES, rule
    text = adr_text().replace("**", "")
    assert {"regola 55", "regola 47"} <= set(re.findall(r"regola \d+", text))


def test_the_third_role_and_the_fifth_kind_are_in_the_tree() -> None:
    """A role an ADR names and the domain does not have is a decision nobody wrote."""
    assert "CONSOLE" in {member.value for member in DeviceRole}
    assert len(DeviceRole) == 3
    assert Kind.CONSOLE.value == "console"
    assert len(Kind) == 5


def test_the_routes_it_documents_are_the_ones_the_console_serves() -> None:
    """Eleven, and the two sheets among them: what ``ela.api`` serves of ``apps/`` is a route like
    the others, behind the identity like the others."""
    documented = {
        (match.group(1), match.group(2))
        for line in adr_text().splitlines()
        if (match := re.match(r"^\| `(GET|POST)` \| `(/[\w.{}/-]*)` \| ([^|]+) \|$", line))
    }

    assert documented == CONSOLE_ROUTES | CONSOLE_CODE_ROUTES
    assert len(documented) == 11


def test_the_constraints_it_declares_are_the_ones_the_milestone_declares() -> None:
    """A constraint in one document and not the other is a promise with one reader."""
    declared = bullets(
        adr_text().split("## 7. Vincoli dichiarati", 1)[1].split("## Conseguenze")[0]
    )
    milestone = bullets(
        MILESTONE.read_text(encoding="utf-8")
        .split("## Vincoli dichiarati previsti per ADR 0044", 1)[1]
        .split("## La prova a mano")[0]
    )

    assert declared, "the ADR must declare its constraints"
    assert milestone <= declared, milestone - declared


def test_it_says_the_old_name_of_the_counter_is_superseded() -> None:
    """An ADR is not rewritten: M12.5 keeps naming ``core_on_a_companion_route`` three times, and
    this is the line that is read beside it (dec. K.3)."""
    text = adr_text()

    assert "core_on_a_companion_route" in text and "core_on_a_page" in text
    assert "superato" in text


def test_it_says_why_no_migration_was_written() -> None:
    """The reason is a fact of the schema, and a reader must not have to go and look."""
    text = adr_text()

    assert "Nessuna migrazione" in text
    assert "String(32)" in text and "server_default='WORKER'" in text
