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
from tests.docs.guided_ports import GUIDED_PORTS
from tests.docs.test_adr_composition import coded_routes, routes_after_0048
from tests.docs.test_adr_placement import _rules_up_to

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
    assert len(_rules_up_to(57)) == 57  # rules 58 and 59 are ADR 0054's
    assert "**ventisei**" in text
    assert (
        len(
            tuple(
                p
                for p in port_protocols()
                if p.__name__
                not in {"CommandLauncher", "LocalBeat", "Browser", "TaskStop", *GUIDED_PORTS}
            )
        )
        == 26
    )
    assert "**quarantotto**" in text
    assert len(coded_routes() - routes_after_0048()) == 48


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
    assert len([kind for kind in Kind if kind is not Kind.SESSION]) == 5  # ADR 0060's sixth


CONSOLE_ROW = re.compile(r"^\| `(GET|POST)` \| `(/console[\w.{}/-]*)` \| ([^|]+) \|$")
"""A row of a table of the console's routes: a method, a path under ``/console``, what it does."""
LATER_CONSOLE_ADRS = (ROOT / "docs" / "adr" / "0062-policies.md",)
"""The ADRs after this one that add routes to the console (M13.12, decision 23 of the review)."""


def console_rows(text: str) -> set[tuple[str, str]]:
    return {
        (match.group(1), match.group(2))
        for line in text.splitlines()
        if (match := CONSOLE_ROW.match(line))
    }


def documented_console_routes(texts: tuple[str, ...]) -> set[tuple[str, str]]:
    """The union of the tables of the console's routes, in the form of ADR 0046 §5."""
    return set().union(*(console_rows(text) for text in texts))


def console_texts() -> tuple[str, ...]:
    return (adr_text(), *(path.read_text(encoding="utf-8") for path in LATER_CONSOLE_ADRS))


def test_the_routes_the_adrs_document_are_the_ones_the_console_serves() -> None:
    """Eleven from ADR 0044 — the two sheets among them —, and four more from ADR 0062, the view
    of the policies (M13.12, decision 23): what ``ela.api`` serves under ``/console`` is the union
    of the tables, and no single ADR is held to the whole count any more."""
    assert len(console_rows(adr_text())) == 11
    assert documented_console_routes(console_texts()) == CONSOLE_ROUTES | CONSOLE_CODE_ROUTES


def test_a_table_that_forgets_a_route_is_found_on_the_union() -> None:
    """The negative case, measured on the union: drop one row from either table."""
    texts = console_texts()
    for which, text in enumerate(texts):
        row = next(line for line in text.splitlines() if CONSOLE_ROW.match(line))
        forgotten = list(texts)
        forgotten[which] = text.replace(row + "\n", "", 1)
        assert documented_console_routes(tuple(forgotten)) != CONSOLE_ROUTES | CONSOLE_CODE_ROUTES


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
