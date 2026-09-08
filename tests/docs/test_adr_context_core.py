"""ADR 0032 and the code say the same thing about the context (M10.4).

This document owns **today's** totals — the rules, the contracts, the ports, the capabilities,
the critical packages — because it is the one that last changed them. ADR 0028 to ADR 0031 keep
the numbers they wrote, as history about the tree each left behind; the next ADR to add a rule
takes the pin from here. That arrangement is what lets an ADR stay immutable while the tree keeps
growing, and it is the same shape ``test_adr_ports.py`` already uses for the port tables.

The decisions that are *properties* are asserted rather than believed: the composer holds no
writing member, no module names a snapshot beside an audit event, the five absences are the
sources with no field, and the criteria that generalise beyond this milestone are written down
and not only applied.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from ela.context import ContextCore
from ela.domain import SOURCE_FIELDS, ContextSnapshot, ContextSource
from ela.permissions import catalogue_v01, production_catalogue
from tests.architecture.rules import CONTEXT_NOT_RECORDED, CONTEXT_WRITE_MEMBERS, RULES
from tests.contracts.protocols import port_protocols

REPO_ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = REPO_ROOT / "docs" / "adr" / "0032-context-core.md"
PYPROJECT = REPO_ROOT / "pyproject.toml"
MAKEFILE = REPO_ROOT / "Makefile"
RULE_ROW = re.compile(r"^\| (\d+) `([a-z-]+)` \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \|$")


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def documented_rules() -> dict[int, str]:
    return {
        int(match.group(1)): match.group(2)
        for line in adr_text().splitlines()
        if (match := RULE_ROW.match(line))
    }


# ----------------------------------------------------------------------------------------
# The two rules the ADR introduces
# ----------------------------------------------------------------------------------------


def test_the_two_rules_of_the_adr_are_rules_the_code_has() -> None:
    documented = documented_rules()

    assert documented == {38: "context-writes-nothing", 39: "context-is-not-recorded"}
    for name in documented.values():
        assert name in RULES, name


def test_the_rules_are_silent_on_the_tree_they_guard() -> None:
    """A door nobody has walked through yet, which is the only moment it can still be shut."""
    package = REPO_ROOT / "src" / "ela"

    assert RULES["context-writes-nothing"](package) == []
    assert RULES["context-is-not-recorded"](package) == []


def test_rule_38_names_every_writing_member_of_the_ports() -> None:
    """The vocabulary is closed because the ports are: these are the names ELA changes state by."""
    members = {
        name for protocol in port_protocols() for name in dir(protocol) if not name.startswith("_")
    }
    writing = members & {
        "add",
        "add_plan",
        "append",
        "append_event",
        "authorize",
        "consume",
        "decide",
        "execute",
        "grant",
        "register",
        "respond",
        "save",
        "update",
        "verify",
    }
    assert writing <= CONTEXT_WRITE_MEMBERS


def test_the_composer_holds_no_writing_member_of_its_own() -> None:
    """Whatever ``ContextCore`` offers a caller, none of it changes anything."""
    public = {name for name in dir(ContextCore) if not name.startswith("_")}

    assert public == {"assemble"}
    assert not public & CONTEXT_WRITE_MEMBERS


def test_rule_39_guards_both_directions() -> None:
    assert {"AuditEvent", "ProviderRequest"} == CONTEXT_NOT_RECORDED


# ----------------------------------------------------------------------------------------
# The contract, the gate, the port
# ----------------------------------------------------------------------------------------


def test_the_fourteenth_contract_exists_and_forbids_what_the_adr_says() -> None:
    contracts = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["importlinter"][
        "contracts"
    ]
    ours = [one for one in contracts if one["source_modules"] == ["ela.context"]]

    assert len(contracts) == 14
    assert len(ours) == 1
    assert set(ours[0]["forbidden_modules"]) == {
        "ela.api",
        "ela.cli",
        "ela.composition",
        "ela.executive",
        "ela.infrastructure",
        "ela.permissions",
        "ela.providers",
        "ela.routing",
        "ela.tools",
    }


def test_perception_and_devices_are_deliberately_not_forbidden() -> None:
    """Observing is not acting (ADR 0029 §5), and only the registry may derive availability."""
    text = adr_text()

    assert "`ela.perception` **non** è vietata" in text
    assert "regola\n20" in text or "regola 20" in text


def test_the_context_package_joined_the_gate_in_this_milestone() -> None:
    """CLAUDE.md: a package joins ``CRITICAL_PACKAGES`` in the milestone it receives code."""
    assignment = MAKEFILE.read_text(encoding="utf-8").split("CRITICAL_PACKAGES = ", 1)[1]
    packages = assignment.split("\n\n", 1)[0].replace("\\\n", " ").split()

    assert "ela.context" in packages
    assert len(packages) == 14


def test_the_port_gained_two_members_and_no_port_was_added() -> None:
    """M10.4 added no port. Monotonic since: M11.1 adds the twenty-second (dec. G)."""
    assert len(tuple(port_protocols())) >= 21


# ----------------------------------------------------------------------------------------
# The five absences, and that they are derived
# ----------------------------------------------------------------------------------------


def test_the_absences_of_the_adr_are_the_absences_of_the_code() -> None:
    """The table of §3 and the model, held to each other."""
    missing = {
        source
        for source in ContextSource
        if SOURCE_FIELDS[source] not in ContextSnapshot.model_fields
    }

    assert {source.value for source in missing} == {
        "CALENDAR",
        "MAIL",
        "DOCUMENTS",
        "PROJECTS",
        "RELEVANCE",
    }
    for source in missing:
        assert f"| `{source.value}` | `{SOURCE_FIELDS[source]}` | **no** |" in adr_text()
    for source in set(ContextSource) - missing:
        assert f"| `{source.value}` | `{SOURCE_FIELDS[source]}` | sì |" in adr_text()


# ----------------------------------------------------------------------------------------
# The criteria that outlive this milestone
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sentence",
    [
        "Se il fatto si ricalcola, è contesto. Se perderlo perde informazione, è memoria.",
        "Un elenco troncato dichiara il proprio troncamento.",
        "Una regola che costringe il codice corretto a contorcersi insegna ad aggirare le regole.",
        "la memoria sarà una fonte del contesto, mai il contrario",
        "Non è il riuso a essere concesso, è il riuso *più* il test sulle chiavi.",
        (
            "Un test di una milestone chiusa che asserisce un totale del repository non sta "
            "verificando quella milestone: sta verificando il repository."
        ),
    ],
)
def test_the_general_criteria_are_written_and_not_only_applied(sentence: str) -> None:
    """A criterion nobody can read is one the next milestone re-derives or contradicts (M9.2)."""
    assert sentence in " ".join(adr_text().replace("\n> ", "\n").split())


def test_the_rule_38_formulation_is_in_the_adr_verbatim() -> None:
    """Approved wording, and it is the wording that has to be there."""
    flowed = " ".join(adr_text().replace("\n> ", "\n").split())

    assert (
        "Se rispondere a una domanda di contesto richiede una capability, quella risposta non è "
        "contesto: è un'azione" in flowed
    )


# ----------------------------------------------------------------------------------------
# §Conseguenze: today's totals, pinned here until the next ADR changes them
# ----------------------------------------------------------------------------------------


def test_the_conseguenze_count_the_rules_the_contracts_and_the_capabilities() -> None:
    conseguenze = adr_text().split("## Conseguenze", 1)[1]

    assert "**trentanove**" in conseguenze
    # Monotonic, for the reason ADR 0026's test gives (``test_adr_placement.py``): an
    # immutable document cannot keep counting a growing collection, and today's totals are
    # pinned by the newest ADR that moved them — since M11.1, ``test_adr_voice.py``.
    assert len(RULES) >= 39
    assert "**quattordici**" in conseguenze
    assert "**ventuno**" in conseguenze
    assert len(tuple(port_protocols())) >= 21
    assert "**cinque**" in conseguenze
    assert len(production_catalogue().specs()) >= 5
    assert "**tre**" in conseguenze
    assert len(catalogue_v01().specs()) == 3


def test_the_measurement_carries_its_date_and_its_machine() -> None:
    """A number without a date is a number nobody can re-take (ADR 0030 §14)."""
    text = adr_text()

    assert "2026-09-08" in text
    assert "macOS 26.6" in text
    assert "21,5 ms" in text
