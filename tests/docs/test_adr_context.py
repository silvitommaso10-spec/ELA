"""ADR 0030 and the code say the same thing about the context and the text (M10.3).

This document owns **today's** totals — the rules, the ports, the capabilities, the perception
families — because it is the one that last changed them. ADR 0028 and ADR 0029 keep the numbers
they wrote, as history about the tree each left behind; the next ADR to add a rule takes the pin
from here. That arrangement is what lets an ADR stay immutable while the tree keeps growing, and
it is the same shape ``test_adr_ports.py`` already uses for the port tables.

The decisions that are *properties* are asserted rather than believed: no window title is read
anywhere, a derived artefact has no lifetime of its own, the text never reaches an ``output``, and
the criterion that came out of the language measurement is written down and not only applied.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ela.domain import FAMILY_FIELDS, ProbeFamily, RawObservation
from ela.permissions import catalogue_v01, production_catalogue
from ela.tools import PERCEPTION_READ_SCREEN_TEXT, ReadScreenTextTool
from tests.architecture.rules import RULES, perception_children
from tests.architecture.violations import PACKAGE_ROOT
from tests.contracts.protocols import port_protocols

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0030-screen-text.md"
RULE_ROW = re.compile(r"^\| (\d+) `([a-z-]+)` \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \|$")
EXTENDED_ROW = re.compile(r"^\| (\d+) `([a-z-]+)` \| ([^|]+?) \| ([^|]+?) \|$")


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def flowed() -> str:
    """The document with its line breaks collapsed, for searching a sentence that wraps.

    A criterion is a sentence, not a line: asserting on the raw text would make a reflow of the
    paragraph, a block quote marker or a pair of asterisks look like a criterion somebody deleted.
    """
    plain = adr_text().replace("**", "").replace("\n> ", "\n")
    return " ".join(plain.split())


# ----------------------------------------------------------------------------------------
# §15: the rules, added and extended
# ----------------------------------------------------------------------------------------


def test_the_rule_this_adr_adds_is_registered_under_the_name_it_gives_it() -> None:
    documented = [
        match.groups() for line in adr_text().splitlines() if (match := RULE_ROW.match(line))
    ]

    assert [number for number, *_ in documented] == ["36"]
    assert documented[0][1] in RULES


def test_the_rules_this_adr_extends_are_registered_under_their_new_names() -> None:
    """``Regole estese:`` is how a rule changes without an older ADR being edited."""
    extended = adr_text().split("`Regole estese:`", 1)[1].split("\n\n**", 1)[0]
    documented = [
        match.groups() for line in extended.splitlines() if (match := EXTENDED_ROW.match(line))
    ]

    assert [number for number, *_ in documented] == ["33", "35"]
    for _, name, *_ in documented:
        assert name in RULES, name


@pytest.mark.parametrize(
    "key",
    [
        "perception-reads-no-window-titles",
        "perception-children-import-only-stdlib",
        "capture-stays-on-the-machine",
    ],
)
def test_each_rule_holds_on_the_real_tree(key: str) -> None:
    assert RULES[key](PACKAGE_ROOT) == []


def test_the_subject_of_rule_33_is_derived_and_finds_both_children() -> None:
    """§6: the subject stopped being a named file, so a child added later cannot escape the rule.

    Asserted on what the derivation *finds*, not on a list: a test that named the two files would
    be the hand-written list the decision exists to avoid.
    """
    found = {path.name for path in perception_children(PACKAGE_ROOT)}

    assert found == {"probe.py", "vision.py"}
    assert all(
        "__main__" in path.read_text(encoding="utf-8") for path in perception_children(PACKAGE_ROOT)
    )


def test_no_window_title_is_named_anywhere_in_the_source() -> None:
    """§2, §3 as a property of the whole tree and not only of the package the rule reads.

    The rule is scoped to the perception adapter because that is where ``ctypes`` may live, so
    this is the wider claim it stands for: nowhere in ELA is that key written down.
    """
    sources = [path for path in PACKAGE_ROOT.rglob("*.py")]

    assert sources
    assert not [path for path in sources if "kCGWindowName" in path.read_text(encoding="utf-8")]


# ----------------------------------------------------------------------------------------
# The criteria that must survive this document, written down and not only applied
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sentence",
    [
        "va spezzata prima di essere consegnata",
        "eredita i vincoli della cattura senza che nessuno debba ricordarsene",
        "dipende da chi fa il lavoro",
        "lista è una cosa che qualcuno dimentica di aggiornare",
    ],
)
def test_the_general_criteria_are_written_and_not_only_applied(sentence: str) -> None:
    """A criterion nobody can read is one the next milestone re-derives or contradicts (M9.2)."""
    assert sentence in flowed()


def test_the_new_criterion_names_the_one_it_is_the_twin_of() -> None:
    """§8 is only half a rule without ADR 0026 §7 beside it: one forbids a branch that cannot
    fire, the other a branch that fires for two opposite reasons."""
    section = adr_text().split("## 8.", 1)[1].split("\n## ", 1)[0]

    assert "ADR 0026 §7" in section
    assert "SensorCause" in section  # and where ELA had already applied it without a name


# ----------------------------------------------------------------------------------------
# The properties, asserted rather than believed
# ----------------------------------------------------------------------------------------


def test_the_applications_family_carries_state_and_never_a_title() -> None:
    """§2: three fields, and a partition of ``RawObservation`` that leaves nothing homeless."""
    fields = FAMILY_FIELDS[ProbeFamily.APPLICATIONS]

    assert set(fields) == {"running_bundle_ids", "frontmost_bundle_id", "window_count"}
    assert not [name for name in RawObservation.model_fields if "title" in name]
    partition = [name for family in ProbeFamily for name in FAMILY_FIELDS[family]]
    assert sorted(partition) == sorted(RawObservation.model_fields)


def test_the_reading_reports_what_the_artefact_is_and_never_what_it_says() -> None:
    """§13: ``output`` is insert-only and has no expiry, so no character of the screen enters it."""
    keys = ReadScreenTextTool.output_keys

    assert "text" not in keys
    assert "lines" in keys and "characters" in keys  # how much, never what


def test_the_capability_is_medium_and_asks_for_authorization_with_a_purpose() -> None:
    spec = production_catalogue().get(PERCEPTION_READ_SCREEN_TEXT)

    assert spec.risk.value == "MEDIUM"
    assert spec.requires_authorization
    assert spec.prompt_arguments == ("purpose",)
    assert "capture_id" not in spec.prompt_arguments  # a UUID says nothing to whoever answers


def test_the_reading_module_reaches_no_router_no_registry_and_no_client() -> None:
    """§15, as the property rather than as the rule: the module that holds the text of a screen
    has no way to send it anywhere, and the defence was written a commit before the module."""
    source = (PACKAGE_ROOT / "tools" / "screen_text.py").read_text(encoding="utf-8")

    assert "ModelRouter" not in source
    assert "ProviderRegistry" not in source
    assert "httpx" not in source


# ----------------------------------------------------------------------------------------
# §Conseguenze: today's totals, pinned here until the next ADR changes them
# ----------------------------------------------------------------------------------------


def test_the_conseguenze_count_the_rules_the_ports_the_capabilities_and_the_families() -> None:
    conseguenze = adr_text().split("## Conseguenze", 1)[1]

    assert "**trentasei**" in conseguenze
    assert len(RULES) == 36
    assert "**ventuno**" in conseguenze
    assert len(tuple(port_protocols())) == 21
    assert "**tredici**" in conseguenze
    assert "**cinque**" in conseguenze
    assert len(production_catalogue().specs()) == 5
    assert "**tre**" in conseguenze
    assert len(catalogue_v01().specs()) == 3
    assert "**quattro**" in conseguenze
    assert len(tuple(ProbeFamily)) == 4
    assert "**due**" in conseguenze
    assert len(perception_children(PACKAGE_ROOT)) == 2
