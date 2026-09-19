"""The lists are not copied: each is read from its source (M17.1, criteri 7, 8 e 9; dec. 3).

The states of ELA are the titles of section 6 of ``docs/spec/ELA_design.md``; the levels of
attention are the block of its section 13; the levels of risk are ``ela.domain.RiskLevel``,
which a second test compares with section 29 of the same document. In order, in both
directions, and no reader accepts a document in which its section is missing or empty — so
none of these can become vacuous.

The names of attention are a **decision** of ADR 0042 (review of 2026-09-18, point 14): the day
the domain gets an enum, this file changes source and not values.
"""

from __future__ import annotations

import enum
import inspect
import re
from collections.abc import Iterable

import pytest

import ela.domain
from ela.domain import RiskLevel
from tests.design.tree import DESIGN_DOCUMENT, generator, tokens

SECTION = re.compile(r"^# (\d+)\. ")
STATE = re.compile(r"^### (.+?)\s*$")
RISK = re.compile(r"^Quando (?:un'azione )?è ([A-Z][A-Z ]*):\s*$")
FENCE = "```"


def section(document: str, number: int) -> list[str]:
    """The lines of section ``number`` of the design document, without its title."""
    lines = document.splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if (m := SECTION.match(line)) and int(m.group(1)) == number
    ]
    if len(starts) != 1:
        raise ValueError(f"the design document has {len(starts)} sections numbered {number}")
    rest = lines[starts[0] + 1 :]
    end = next((index for index, line in enumerate(rest) if SECTION.match(line)), len(rest))
    return rest[:end]


def listed(found: list[str], what: str) -> list[str]:
    if not found:
        raise ValueError(f"the design document lists no {what}")
    return found


def design_states(document: str) -> list[str]:
    return listed(
        [m.group(1) for line in section(document, 6) if (m := STATE.match(line))], "state"
    )


def design_attention(document: str) -> list[str]:
    lines = section(document, 13)
    fences = [index for index, line in enumerate(lines) if line.startswith(FENCE)]
    if len(fences) != 2:
        raise ValueError("section 13 of the design document has no single fenced block")
    return listed(
        [line.strip() for line in lines[fences[0] + 1 : fences[1]] if line.strip()], "level"
    )


def design_risk(document: str) -> list[str]:
    return listed([m.group(1) for line in section(document, 29) if (m := RISK.match(line))], "risk")


def document() -> str:
    return DESIGN_DOCUMENT.read_text(encoding="utf-8")


def keys(group: str) -> list[str]:
    return list(generator().entries(tokens()[group]))


# ----------------------------------------------------------------------------------------
# The three lists
# ----------------------------------------------------------------------------------------


def test_the_states_are_the_titles_of_section_6_of_the_design_in_order() -> None:
    assert keys("state") == design_states(document())


def test_the_levels_of_attention_are_the_block_of_section_13_of_the_design_in_order() -> None:
    assert keys("attention") == design_attention(document())
    assert keys("attention") == ["SILENT", "NOTIFICATION", "PRIORITY", "PHONE CALL", "EMERGENCY"], (
        "ADR 0042 decides these names: a change here is a change of that decision"
    )


def test_the_levels_of_risk_are_the_enum_of_the_domain_in_order() -> None:
    assert keys("risk") == [level.value for level in RiskLevel]


def test_the_enum_of_the_domain_and_section_29_of_the_design_agree() -> None:
    """If they ever part, the tokens would follow the enum against the document: ask the user."""
    assert [level.value for level in RiskLevel] == design_risk(document())


# ----------------------------------------------------------------------------------------
# The readers cannot become vacuous, and they see a change
# ----------------------------------------------------------------------------------------

SYNTHETIC = """# 5. Before

### NOT A STATE

# 6. Stati di ELA

### OFFLINE

Prose.

### WAITING APPROVAL

# 7. After

### NOT A STATE EITHER

# 13. Attention Center

```text
SILENT
PHONE CALL
```

# 29. Design e sicurezza

Quando un'azione è SAFE:

Quando è CRITICAL:

# 30. End
"""


def test_a_reader_reads_its_section_and_only_that() -> None:
    assert design_states(SYNTHETIC) == ["OFFLINE", "WAITING APPROVAL"]
    assert design_attention(SYNTHETIC) == ["SILENT", "PHONE CALL"]
    assert design_risk(SYNTHETIC) == ["SAFE", "CRITICAL"]


def test_a_state_added_renamed_or_removed_in_the_document_is_seen() -> None:
    assert design_states(SYNTHETIC.replace("### OFFLINE", "### OFFLINE\n\n### DREAMING")) == [
        "OFFLINE",
        "DREAMING",
        "WAITING APPROVAL",
    ]
    assert design_states(SYNTHETIC.replace("### OFFLINE", "### UNREACHABLE"))[0] == "UNREACHABLE"
    assert design_states(SYNTHETIC.replace("### OFFLINE\n", "")) == ["WAITING APPROVAL"]


@pytest.mark.parametrize(
    ("reader", "broken", "sentence"),
    [
        (
            design_states,
            SYNTHETIC.replace("# 6. Stati di ELA", "# 60. Stati"),
            "0 sections numbered 6",
        ),
        (
            design_states,
            SYNTHETIC.replace("### OFFLINE", "OFFLINE").replace("### WAITING", "WAITING"),
            "no state",
        ),
        (design_states, SYNTHETIC + "\n# 6. Again\n", "2 sections numbered 6"),
        (
            design_attention,
            SYNTHETIC.replace("# 13. Attention Center", "# 130. Attention"),
            "0 sections",
        ),
        (
            design_attention,
            SYNTHETIC.replace("```text\nSILENT\nPHONE CALL\n```", "SILENT"),
            "no single fenced",
        ),
        (design_attention, SYNTHETIC.replace("SILENT\nPHONE CALL\n", ""), "no level"),
        (design_risk, SYNTHETIC.replace("Quando", "Se"), "no risk"),
    ],
    ids=["no-6", "empty-6", "two-6", "no-13", "no-fence", "empty-13", "empty-29"],
)
def test_a_document_without_the_section_is_refused(
    reader: object, broken: str, sentence: str
) -> None:
    assert callable(reader)
    with pytest.raises(ValueError, match=sentence):
        reader(broken)


# ----------------------------------------------------------------------------------------
# The domain does not move (criterio 9)
# ----------------------------------------------------------------------------------------

ALREADY_THERE = {
    "DeviceAvailability": {"OFFLINE"},
    "DeviceStatus": {"IDLE"},
    "NetworkKind": {"OFFLINE"},
    "TaskState": {"PLANNING", "WAITING APPROVAL"},
}
"""Names of section 6 of the design that an enum of the domain held on 2026-09-18, each
meaning something else: the state of a task, of a node, of a network. Pinned so that «it was
already there» can be told from «it came in»."""


def same_name(name: str) -> str:
    """The one normalisation this file needs, and it is written: a space is an underscore.

    Without it ``ATTENTION_REQUIRED`` would never be «ATTENTION REQUIRED», and the defence
    below would not fire.
    """
    return name.upper().replace("_", " ").replace("-", " ")


def borrowed(enums: Iterable[type[enum.Enum]], states: list[str]) -> dict[str, set[str]]:
    """Enum name -> the states of ELA it names, by member name or by value."""
    wanted = {same_name(state) for state in states}
    found: dict[str, set[str]] = {}
    for candidate in enums:
        held = {same_name(member.name) for member in candidate}
        held |= {same_name(str(member.value)) for member in candidate}
        if held & wanted:
            found[candidate.__name__] = held & wanted
    return found


def domain_enums() -> list[type[enum.Enum]]:
    found = [
        candidate
        for _, candidate in inspect.getmembers(ela.domain, inspect.isclass)
        if issubclass(candidate, enum.Enum) and candidate.__module__ == ela.domain.__name__
    ]
    assert found, "the domain must have enums, or this test is vacuous"
    return found


def test_no_enum_of_the_domain_gains_a_state_of_ela() -> None:
    """``docs/STATO.md``, voce 5.10: the states are a projection, never a value of the domain."""
    assert borrowed(domain_enums(), design_states(document())) == ALREADY_THERE


def test_an_enum_that_brings_a_state_in_is_seen() -> None:
    class Presence(enum.StrEnum):
        ATTENTION_REQUIRED = "ATTENTION_REQUIRED"
        EVOLVING = "evolving"
        SOMETHING_ELSE = "SOMETHING_ELSE"

    found = borrowed([Presence], design_states(document()))
    assert found == {"Presence": {"ATTENTION REQUIRED", "EVOLVING"}}
