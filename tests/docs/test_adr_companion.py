"""ADR 0043 against the tree (M12.5): the numbers it states, and the promises it makes.

The shape of ``test_adr_nodes_windows.py``: an ADR is immutable, so the pin on *today's* totals
lives with the ADR that last moved them — and since M12.5 that is this one.

What is checked here is what a reader would otherwise have to take on trust: that the rules it
names exist, that the constraints it declares are the same ones the milestone declares, that the
routes and the ports it counts are the ones the code serves, and that the two ADRs it revises are
named where somebody looking at *them* would find the revision.
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.api.security import COMPANION_CODE_ROUTES, COMPANION_ROUTES
from ela.domain import AuditEventType, DeviceRole
from tests.architecture.rules import RULES
from tests.contracts.protocols import port_protocols
from tests.docs.test_adr_composition import coded_routes

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0043-companion.md"
MILESTONE = ROOT / "docs" / "milestones" / "M12.5.md"
NEW_RULES = ("pages-read-the-routes", "the-bell-rings-a-method", "one-composer-for-a-page")


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def conseguenze() -> str:
    return adr_text().split("## Conseguenze", 1)[1]


def bullets(text: str) -> set[str]:
    """The bold opening of every bullet of a block: what each line claims, without its prose."""
    return {match.group(1).strip() for match in re.finditer(r"^- \*\*(.+?)\*\*", text, re.M)}


def test_the_conseguenze_count_what_the_tree_has_today() -> None:
    """The pin moves to the ADR that moved the totals, as it did from ADR 0039 to ADR 0040."""
    text = conseguenze()

    assert "**cinquantasette**" in text
    assert len(RULES) == 57
    assert "**ventisei**" in text
    assert len(tuple(port_protocols())) == 26
    assert "**trentasette**" in text
    assert len(coded_routes()) == 37


def test_the_three_new_rules_it_names_are_in_the_tree() -> None:
    """A rule an ADR names and the tree does not have is a defence nobody wrote."""
    for rule in NEW_RULES:
        assert rule in RULES, rule
    text = adr_text().replace("**", "")
    assert {"regola 55", "regola 56", "regola 57"} <= set(re.findall(r"regola \d+", text))
    assert "regola 44" in text, "the rule the role extends"


def test_the_declared_constraints_are_the_ones_the_milestone_declares() -> None:
    """Both documents, one list: the ADR is where a constraint is read a year later, and the
    milestone is where it was decided. A constraint in one and not the other is how the two
    start disagreeing — the drift ``docs/STATO.md`` exists to make impossible for the numbers.
    """
    in_the_adr = bullets(adr_text().split("## 10. Vincoli dichiarati", 1)[1].split("\n## ", 1)[0])
    in_the_milestone = bullets(
        MILESTONE.read_text(encoding="utf-8")
        .split("## Vincoli dichiarati previsti per ADR 0043", 1)[1]
        .split("\n## ", 1)[0]
    )

    assert in_the_adr
    assert in_the_adr == in_the_milestone


def test_the_adr_names_the_two_it_revises_and_says_what_changes() -> None:
    """ADR 0023 §7 («whoever has no token does not learn which routes exist») and ADR 0037 §4
    («the same 401, not a 403») are revised by dec. C.3, and an ADR that revised another in
    silence would leave the older text true-looking and false."""
    text = adr_text()

    assert "ADR 0023" in text and "ADR 0037" in text
    assert "404" in text and "401" in text


def test_the_role_and_its_two_members_are_the_ones_the_table_documents() -> None:
    documented = {
        match.group(1)
        for match in re.finditer(
            r"^\| `(WORKER|COMPANION)` \| [^|]+ \| [^|]+ \| [^|]+ \|$", adr_text(), re.M
        )
    }

    assert documented == {member.value for member in DeviceRole}


def test_the_event_the_bell_writes_is_the_one_the_domain_has() -> None:
    assert AuditEventType.BELL_RUNG.value in adr_text()


def test_the_pages_it_documents_are_the_ones_the_middleware_lets_through() -> None:
    """The route table of §5 against the two closed lists of ``api/security.py``: a page added to
    one and not the other answers ``404`` to the iPhone, which is safe and inexplicable."""
    documented = {
        (match.group(1), match.group(2))
        for match in re.finditer(r"^\| `(GET|POST)` \| `(/companion/[\w.]*)` \|", adr_text(), re.M)
    }

    assert documented == COMPANION_ROUTES | COMPANION_CODE_ROUTES
