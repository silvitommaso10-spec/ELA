"""ADR 0068 against the tree (M13.14): the tables it writes — the gaps, the checks, the
declarations, the words, the reasons —, the version, the constant, the marks on the ADRs it
revises, and the limit it declares in plain words.

The shape of ``test_adr_policies.py``: since M13.14 the predicate and the birth are this ADR's, and
ADR 0062 keeps the tables of its day.
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.api.policies import ON_THE_CORE, RECENT_MAX
from ela.permissions import (
    GAPS,
    LAUNCHES_A_PROGRAM,
    POLICY_CHECKS,
    POLICY_VERSION,
    PolicyCheck,
    no_policy_for,
    production_catalogue,
)
from tests.docs.test_adr_policies import documented_checks, documented_gaps, documented_terms

ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = ROOT / "docs" / "adr"
ADR_PATH = ADR_DIR / "0068-policies-on-high.md"
INDEX_ROW = re.compile(r"^\| \[0068\]\(0068-policies-on-high\.md\) \| (.+?) \| (.+?) \|$", re.M)
CORE_ROW = re.compile(r"^\| `(\w+\.[\w.]+)` \| (sì|no) \|$", re.M)
WORDS_ROW = re.compile(r"^\| `([\w.]+)` \| «([^»]+)» \| «([^»]+)» \|$", re.M)
REASON_ROW = re.compile(r"^\| [^|]+ \| «([^»]+)» \|$", re.M)
REVISED_ROW = re.compile(r"^- \*\*ADR (\d{4})\b")
ADDED_ROW = re.compile(r"^\| `([\w.]+)` \| ((?:`[\w.]+`(?:, )?)+) \|$", re.M)
REVISED_MARK = "**Rivista da ADR 0068 (M13.14)**"
OPENED = ("fs.write", "browser.act", "browser.act_as_you")


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def prose() -> str:
    """The text with its line breaks as spaces: a sentence wrapped at the margin is one sentence."""
    return " ".join(adr_text().split())


def status_of(text: str) -> str:
    return text.split("- **Stato:**", 1)[1].split("\n- **", 1)[0]


def specs() -> dict[str, object]:
    return {spec.id: spec for spec in production_catalogue().specs()}


def added_codes() -> dict[str, frozenset[str]]:
    """The codes a tool adds to those the ADRs before wrote (§7), by capability: read by the tests
    of those ADRs, whose rows stay as they were."""
    return {
        name: frozenset(re.findall(r"`([\w.]+)`", cells))
        for name, cells in ADDED_ROW.findall(adr_text())
    }


def test_the_added_codes_are_the_tools_and_a_write_refuses_with_them() -> None:
    from ela.tools.browser_files import AccountDownloadTool, BrowserDownloadTool
    from ela.tools.fs import ELA_S_OWN, HARD_LINK, FsWriteTool

    added = added_codes()

    assert added == {
        "fs.write": frozenset({ELA_S_OWN, HARD_LINK}),
        "browser.download": frozenset({ELA_S_OWN, HARD_LINK}),
        "browser.download_as_you": frozenset({ELA_S_OWN, HARD_LINK}),
    }
    for tool in (FsWriteTool, BrowserDownloadTool, AccountDownloadTool):
        assert {ELA_S_OWN, HARD_LINK} <= tool.error_codes, tool.__name__


def test_the_gaps_and_the_checks_are_the_code_s_in_their_order() -> None:
    assert documented_gaps(adr_text()) == [gap.value for gap in GAPS]
    assert documented_checks(adr_text()) == [check.value for check in POLICY_CHECKS]
    assert set(documented_checks(adr_text())) == {check.value for check in PolicyCheck}


def test_the_three_declarations_are_the_catalogue_s() -> None:
    catalogue = production_catalogue()
    declared = documented_terms(adr_text())

    assert set(declared) == set(OPENED)
    for capability, (limits, uncovered, free, route) in declared.items():
        terms = catalogue.get(capability).policy_terms  # type: ignore[arg-type]
        assert terms is not None
        assert (limits, uncovered, free, route) == (
            terms.limits,
            terms.uncovered,
            terms.free,
            (terms.route or "",),
        )


def test_on_the_core_and_the_words_are_the_catalogue_s() -> None:
    catalogue = production_catalogue()
    core = {name: said == "sì" for name, said in CORE_ROW.findall(adr_text())}
    words = {name: (does, goes) for name, does, goes in WORDS_ROW.findall(adr_text())}

    assert set(core) == set(words) == set(OPENED)
    for name in OPENED:
        spec = catalogue.get(name)  # type: ignore[arg-type]
        assert spec.policy_terms is not None and spec.policy_words is not None
        assert core[name] is spec.policy_terms.on_the_core, name
        assert words[name] == (spec.policy_words.does, spec.policy_words.goes), name


def test_the_capabilities_that_declare_terms_are_these_and_no_other_high() -> None:
    """Every ``HIGH`` of the catalogue that declares terms is one of the three, and the rest ask at
    every use — the login and the four of the files until M13.15, the terminal until M13.16."""
    highs = {spec.id for spec in production_catalogue().specs() if spec.risk.value == "HIGH"}
    declaring = {
        spec.id for spec in production_catalogue().specs() if spec.policy_terms is not None
    }

    assert highs & declaring == set(OPENED)
    assert highs - declaring >= LAUNCHES_A_PROGRAM


def test_the_reasons_the_adr_quotes_are_the_ones_no_policy_for_gives() -> None:
    catalogue = production_catalogue()
    quoted = set(REASON_ROW.findall(adr_text()))

    assert no_policy_for(catalogue.get("terminal.run")) in quoted  # type: ignore[arg-type]
    assert no_policy_for(catalogue.get("browser.login")) in quoted  # type: ignore[arg-type]
    assert "and only you create one" in no_policy_for(catalogue.get("terminal.run"))  # type: ignore[arg-type,operator]


def test_the_version_and_the_constants_are_the_code_s() -> None:
    text = adr_text()

    assert POLICY_VERSION == "v0.4"
    assert f"`POLICY_VERSION` passa da `v0.3` a `{POLICY_VERSION}`" in text
    assert f"RECENT_MAX = {RECENT_MAX}" in text
    assert f"«{ON_THE_CORE}»" in prose()


def test_the_limit_is_declared_in_plain_words() -> None:
    """Answer 20 of the review of the SPEC: the sentence of decision 12 was false, the three roads
    stay, and the ADR says so with the user's own words for the limit."""
    text = prose()

    assert "**il limite è vero quanto le cartelle e i siti scelti**" in text
    assert "Nessuna lista dei posti che il sistema lancia" in text
    assert "**Togliere al gettone del Core la creazione di una policy**" in text


def revised_by_the_list() -> set[str]:
    block = adr_text().split("## Conseguenze", 1)[1].split("**Righe riviste**", 1)[1]
    rows = block.split("\n\n", 2)[1]
    return {match.group(1) for line in rows.splitlines() if (match := REVISED_ROW.match(line))}


def written() -> dict[str, str]:
    return {
        path.name[:4]: path.read_text(encoding="utf-8")
        for path in ADR_DIR.glob("[0-9]*.md")
        if path != ADR_PATH
    }


def revised_by_their_state(texts: dict[str, str]) -> set[str]:
    return {number for number, text in texts.items() if REVISED_MARK in status_of(text)}


def test_the_adrs_it_revises_say_so_on_their_state_line_and_no_other_does() -> None:
    listed = revised_by_the_list()

    assert listed == {"0019", "0045", "0047", "0048", "0060", "0062", "0063", "0066"}
    assert listed == revised_by_their_state(written())


def test_a_revised_adr_that_does_not_say_so_is_found() -> None:
    texts, listed = written(), revised_by_the_list()
    silent = min(listed)
    texts[silent] = texts[silent].replace(REVISED_MARK, "", 1)

    assert revised_by_their_state(texts) == listed - {silent}


def test_the_index_names_it_with_its_state() -> None:
    index = (ADR_DIR / "README.md").read_text(encoding="utf-8")
    found = INDEX_ROW.findall(index)
    state = status_of(adr_text()).split("**", 1)[0].strip().split()[0]

    assert len(found) == 1
    assert found[0][1] == state


def test_the_conseguenze_count_the_totals_of_today() -> None:
    """The pin on today's totals, taken over from ADR 0066 (M13.14 adds the seventy-fourth rule and
    the sixteenth contract): it moves to the ADR that changes them."""
    import tomllib

    from ela.api.security import Kind
    from tests.architecture.rules import RULES
    from tests.contracts.protocols import port_protocols
    from tests.docs.test_adr_cli import coded_commands
    from tests.docs.test_adr_composition import coded_routes
    from tests.docs.test_adr_placement import _rules_up_to

    text = prose().split("## Conseguenze", 1)[1]
    contracts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "importlinter"
    ]["contracts"]

    assert "**settantaquattro**" in text and "**Regola di architettura 74**" in text
    assert len(RULES) == 74
    assert set(RULES) - set(_rules_up_to(73)) == {"a-program-is-launched-by-the-terminal"}
    assert "**Contratto di import-linter 16**" in text and "**sedici**" in text
    assert len(contracts) == 16
    assert len([one for one in contracts if str(one["name"]).startswith("16. ")]) == 1
    assert "**trentasei**" in text and len(tuple(port_protocols())) == 36
    assert "**settantadue**" in text and len(coded_routes()) == 72
    assert "**trentanove**" in text and len(coded_commands()) == 39
    assert "**ventidue**" in text and len(production_catalogue().specs()) == 22
    assert "**sei**" in text and len(Kind) == 6
