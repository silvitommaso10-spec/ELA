"""ADR 0065 — the browser in more steps (M13.10) — held to the code.

The ADR is written with the implementation, a section at a time; what this file holds to the code
grows with it. Today: the bag of what a question named, the rule it adds — the seventy-first, and
no other —, and the pin on **today's** totals, taken over from ADR 0064.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from ela.api.security import Kind
from ela.executive import executor
from ela.permissions import production_catalogue
from ela.ports import (
    BROWSER_LOGIN_FORM_GONE,
    CONTINUES,
    LOGIN_FORM,
    LOGIN_FORM_AMBIGUOUS,
    LOGIN_FORM_NOT_FOUND,
    NO_LOGIN_FORM,
    PROFILE_TASK,
    Prospect,
)
from ela.tools.account import (
    ENTRY_NOT_NAMED,
    LOGIN_FORM_STILL_THERE,
    STOP_A_TASK,
    LoginTool,
    LoginVerifier,
)
from ela.tools.browser import (
    LEFT_WHILE_WAITING,
    NO_PAGE_TO_CONTINUE,
    BrowserActTool,
    BrowserReadTool,
)
from ela.tools.guided import LOOKS_OF_A_LOGIN, SENDS_AS_YOU, SESSION_AS_YOU
from tests.architecture.rules import NAMED_CONSTANT, RULES
from tests.contracts.protocols import port_protocols
from tests.docs.guided_ports import STEPS_PORTS
from tests.docs.test_adr_cli import coded_commands
from tests.docs.test_adr_composition import coded_routes
from tests.docs.test_adr_placement import _rules_up_to

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0065-browser-steps.md"
THE_RULE = "named-reaches-the-tool-only"


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def conseguenze() -> str:
    return adr_text().split("## Conseguenze", 1)[1]


# ----------------------------------------------------------------------------------------
# §2 — what the yes named reaches the tool with the yes
# ----------------------------------------------------------------------------------------


def test_the_bag_the_adr_names_is_the_executor_s_and_the_prospect_s() -> None:
    text = adr_text()

    assert executor.NAMED == "named" and "`named`" in text
    assert "named" in Prospect.__dataclass_fields__ and "`Prospect.named`" in text
    assert f"`{ENTRY_NOT_NAMED}`" in text
    assert "`vault.entry_forgotten` è ritirato" in text


def test_the_code_of_the_remembered_entry_is_in_no_file_of_the_product() -> None:
    """Criterion 9 of M13.10: ``vault.entry_forgotten`` went with the entry remembered in memory —
    in no module of ``src/``, and in no page of ``apps/``."""
    gone = "vault." + "entry_forgotten"
    found = [
        path
        for folder in (ROOT / "src", ROOT / "apps")
        for path in folder.rglob("*")
        if path.is_file()
        and path.suffix in {".py", ".html", ".js", ".css", ".json"}
        and gone in path.read_text(encoding="utf-8", errors="replace")
    ]

    assert found == []
    assert ENTRY_NOT_NAMED in (ROOT / "src" / "ela" / "tools" / "account.py").read_text(
        encoding="utf-8"
    ), "the control: the reader reads the module where the code would be"


# ----------------------------------------------------------------------------------------
# §3 — the page between two steps of a task
# ----------------------------------------------------------------------------------------


def test_the_names_of_the_page_between_steps_are_the_code_s() -> None:
    text = adr_text()

    assert f"`{CONTINUES}`" in text and f"`{NO_PAGE_TO_CONTINUE}`" in text
    assert f"`{LEFT_WHILE_WAITING}`" in text and f"**`{PROFILE_TASK}`**" in text
    assert "`ela task cancel`" in text and STOP_A_TASK == "ela task cancel"
    assert NO_PAGE_TO_CONTINUE in BrowserReadTool.error_codes & BrowserActTool.error_codes
    assert NO_PAGE_TO_CONTINUE not in LoginTool.error_codes, "a login never continues"
    assert LEFT_WHILE_WAITING not in BrowserReadTool.audit_numbers | BrowserActTool.audit_numbers


# ----------------------------------------------------------------------------------------
# §4 — the login the model asks for
# ----------------------------------------------------------------------------------------


def test_the_names_of_the_login_of_the_model_are_the_code_s() -> None:
    text = adr_text()

    for name in (LOGIN_FORM, NO_LOGIN_FORM, LOGIN_FORM_NOT_FOUND, LOGIN_FORM_AMBIGUOUS):
        assert f"`{name}`" in text, name
    assert f"**`{BROWSER_LOGIN_FORM_GONE}`**" in text
    assert BROWSER_LOGIN_FORM_GONE in LoginVerifier.conditions
    assert LOGIN_FORM_STILL_THERE in LoginVerifier.failure_codes
    assert [tool.name for tool in SESSION_AS_YOU.tools] == ["read", "act", "login"]
    assert "**conta due gesti**" in text and LOOKS_OF_A_LOGIN == 2


def test_the_sentence_of_what_leaves_is_the_one_of_decision_32() -> None:
    said = (
        "the text of the pages read as you, and of a login where its page ended, its status and "
        "whether its form was still there — never the entry, the username or the password"
    )
    assert said in SENDS_AS_YOU and said in " ".join(adr_text().split())


# ----------------------------------------------------------------------------------------
# The ADRs it revises say so
# ----------------------------------------------------------------------------------------

REVISED_MARK = "**Rivista da ADR 0065 (M13.10)**"
REVISED_ROW = re.compile(r"^- \*\*ADR (\d{4})\b")


def status_of(text: str) -> str:
    return text.split("- **Stato:**", 1)[1].split("\n- **", 1)[0]


def revised_by_the_list() -> set[str]:
    """The numbers of the ADRs the list «Righe riviste» of this ADR names, one bullet each."""
    block = conseguenze().split("**Righe riviste**", 1)[1].split("\n\n", 2)[1]
    return {match.group(1) for line in block.splitlines() if (match := REVISED_ROW.match(line))}


def written() -> dict[str, str]:
    return {
        path.name[:4]: path.read_text(encoding="utf-8")
        for path in ADR_PATH.parent.glob("[0-9]*.md")
        if path != ADR_PATH
    }


def revised_by_their_state(texts: dict[str, str]) -> set[str]:
    return {number for number, text in texts.items() if REVISED_MARK in status_of(text)}


def test_the_adrs_it_revises_say_so_on_their_state_line_and_no_other_does() -> None:
    """X13 and decision 33 of the review of M13.10's SPEC: closed both ways."""
    listed = revised_by_the_list()

    assert listed == {"0045", "0052", "0060", "0063", "0064"}
    assert listed == revised_by_their_state(written())


def test_a_revised_adr_that_does_not_say_so_is_found() -> None:
    texts, listed = written(), revised_by_the_list()
    silent = min(listed)
    texts[silent] = texts[silent].replace(REVISED_MARK, "", 1)

    assert revised_by_their_state(texts) == listed - {silent}


def test_each_mark_names_a_section_of_this_adr_that_is_there() -> None:
    sections = set(re.findall(r"^### (\d+)\. ", adr_text(), re.MULTILINE))
    for number in revised_by_the_list():
        state = status_of(written()[number])
        said = state.split(REVISED_MARK, 1)[1]
        named = set(re.findall(r"ADR 0065 §(\d+)", said))
        assert named and named <= sections, number


def test_the_registration_of_m13_10_for_the_files_is_among_the_revised_rows() -> None:
    """Decision 48: the files went to M13.13, and the rows say so."""
    assert "**La registrazione di M13.10**, per i file" in conseguenze()
    assert "M13.13" in conseguenze()


def test_what_it_declares_and_does_not_solve_is_a_numbered_section() -> None:
    """X14 (i): a section of its own, numbered, as from ADR 0043 on — not a heading of
    «Vincoli dichiarati», which the census of the constraints would count."""
    assert "### 5. Ciò che questo ADR dichiara e non risolve" in adr_text()
    assert "### Vincoli dichiarati" not in adr_text()
    assert "**Ciò che non è misurato, per nome**" in conseguenze()


THE_DEBT = (
    "### 6. Un debito datato: "
    "un processo del browser lasciato su ubuntu da un test non identificato"
)
CHARGED_TO = (
    "**Debito a carico di M13.13, la milestone dei file dal browser**, dichiarato il **2026-10-14**"
)


def test_the_debt_of_the_process_left_on_ubuntu_is_dated_charged_and_named_by_who_pays_it() -> None:
    """Decision 56 (b) of the review of M13.10's implementation. A process of the browser was left
    on ubuntu by a test nobody could name, and the merge does not wait for it: the section has the
    form STATO reads, it names the defence — the fixture that names the process whole —, and the
    milestone it is charged to names it among what it inherits. The day it is paid, the payment is
    written in an ADR, and this test is turned."""
    text = adr_text()

    assert THE_DEBT in text
    section = text.split(THE_DEBT, 1)[1].split("\n## ", 1)[0]
    assert CHARGED_TO in section
    assert "`/proc/<pid>/cmdline`" in section
    assert "tests/infrastructure/machine/test_nothing_left_behind.py" in section
    files = (ROOT / "docs" / "milestones" / "M13.13.md").read_text(encoding="utf-8")
    assert "ADR 0065 §6" in files.split("## Che cosa eredita", 1)[1].split("\n## ", 1)[0]


# ----------------------------------------------------------------------------------------
# The rule it adds, and the totals of today
# ----------------------------------------------------------------------------------------


def test_the_rule_it_adds_is_the_seventy_first_and_is_anchored_to_the_constant() -> None:
    assert "**Regola di architettura 71**" in conseguenze()
    assert set(_rules_up_to(71)) - set(_rules_up_to(70)) == {THE_RULE}
    assert f"`{NAMED_CONSTANT}`" in conseguenze()
    assert getattr(executor, NAMED_CONSTANT) == executor.NAMED


def test_the_conseguenze_count_the_totals_of_today() -> None:
    """The pin on today's totals, taken over from ADR 0064: it moves to the ADR that changes
    them."""
    text = conseguenze()
    contracts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "importlinter"
    ]["contracts"]

    assert "**settantuno**" in text
    assert len(RULES) == 71
    assert set(RULES) - set(_rules_up_to(70)) == {THE_RULE}
    assert "**quindici**" in text and len(contracts) == 15
    assert "**trentasei**" in text and len(tuple(port_protocols())) == 36
    assert {port.__name__ for port in port_protocols()} >= STEPS_PORTS == {"TaskPages"}
    assert "**settantadue**" in text and len(coded_routes()) == 72
    assert "**trentanove**" in text and len(coded_commands()) == 39
    assert "**diciotto**" in text and len(production_catalogue().specs()) == 18
    assert "**sei**" in text and len(Kind) == 6
