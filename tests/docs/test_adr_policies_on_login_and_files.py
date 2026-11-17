"""ADR 0071 against the tree (M13.15): the tables it writes — the declarations, the second
dimension and the Core, the words, the checks and the gaps of today, the codes the tools add, the
refusals before a spend —, the version, the marks on the ADRs it revises, and what it declares in
plain words.

The shape of ``test_adr_policies_on_high.py``: since M13.15 the gaps and the checks of today are
this ADR's, and ADR 0068 keeps the tables of its day.
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.permissions import (
    GAPS,
    LAUNCHES_A_PROGRAM,
    POLICY_CHECKS,
    POLICY_VERSION,
    production_catalogue,
)
from tests.docs.test_adr_policies import documented_checks, documented_gaps, documented_terms

ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = ROOT / "docs" / "adr"
ADR_PATH = ADR_DIR / "0071-policies-on-login-and-files.md"
INDEX_ROW = re.compile(
    r"^\| \[0071\]\(0071-policies-on-login-and-files\.md\) \| (.+?) \| (.+?) \|$", re.M
)
VALUE_ROW = re.compile(r"^\| `([\w.]+)` \| `(\w+)` \| (sì|no) \|$", re.M)
WORDS_ROW = re.compile(r"^\| `([\w.]+)` \| «([^»]+)» \| «([^»]+)» \| «([^»]+)» \|$", re.M)
ADDED_ROW = re.compile(r"^\| `([\w.]+)` \| ((?:`[\w.]+`(?:, )?)+) \|$", re.M)
REVISED_ROW = re.compile(r"^- \*\*ADR (\d{4})\b")
REVISED_MARK = "**Rivista da ADR 0071 (M13.15)**"
FIVE = (
    "browser.login",
    "browser.download",
    "browser.download_as_you",
    "browser.upload",
    "browser.upload_as_you",
)


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def prose() -> str:
    return " ".join(adr_text().split())


def status_of(text: str) -> str:
    return text.split("- **Stato:**", 1)[1].split("\n- **", 1)[0]


def added_codes() -> dict[str, frozenset[str]]:
    """The codes a tool adds to those the ADRs before wrote (§4), by capability: read by the tests
    of those ADRs, whose rows stay as they were."""
    return {
        name: frozenset(re.findall(r"`([\w.]+)`", cells))
        for name, cells in ADDED_ROW.findall(adr_text())
    }


def test_the_five_declarations_are_the_catalogue_s() -> None:
    catalogue = production_catalogue()
    declared = documented_terms(adr_text())

    assert set(declared) == set(FIVE)
    for capability, (limits, uncovered, free, route) in declared.items():
        terms = catalogue.get(capability).policy_terms  # type: ignore[arg-type]
        assert terms is not None
        assert (limits, uncovered, free, route) == (
            terms.limits,
            terms.uncovered,
            terms.free,
            (terms.route or "",),
        )


def test_the_second_dimension_the_core_and_the_words_are_the_catalogue_s() -> None:
    catalogue = production_catalogue()
    values = {name: (by, core == "sì") for name, by, core in VALUE_ROW.findall(adr_text())}
    words = {name: rest for name, *rest in WORDS_ROW.findall(adr_text())}

    assert set(values) == set(words) == set(FIVE)
    for name in FIVE:
        spec = catalogue.get(name)  # type: ignore[arg-type]
        assert spec.policy_terms is not None and spec.policy_words is not None
        assert values[name] == (spec.policy_terms.by_value, spec.policy_terms.on_the_core), name
        assert tuple(words[name]) == (
            spec.policy_words.does,
            spec.policy_words.goes,
            spec.policy_words.together,
        ), name


def test_the_gaps_and_the_checks_of_today_are_the_code_s_in_their_order() -> None:
    assert documented_gaps(adr_text()) == [gap.value for gap in GAPS]
    assert documented_checks(adr_text()) == [check.value for check in POLICY_CHECKS]


def test_every_high_declares_terms_but_the_ones_that_launch_a_program() -> None:
    """The closed world ADR 0068 kept until M13.15: every ``HIGH`` declares terms, but the ones
    that launch a program the plan chooses — ``terminal.run``, until M13.16."""
    specs = production_catalogue().specs()
    highs = {spec.id for spec in specs if spec.risk.value == "HIGH"}
    declaring = {spec.id for spec in specs if spec.policy_terms is not None}

    assert set(FIVE) <= highs & declaring
    assert highs - declaring == LAUNCHES_A_PROGRAM


def test_the_added_codes_are_the_tools_and_a_read_refuses_with_them() -> None:
    from ela.tools.browser_files import AccountUploadTool, BrowserUploadTool
    from ela.tools.fs import ELA_S_OWN, HARD_LINK, FsReadTool

    assert added_codes() == {
        "browser.upload": frozenset({ELA_S_OWN, HARD_LINK}),
        "browser.upload_as_you": frozenset({ELA_S_OWN, HARD_LINK}),
        "fs.read": frozenset({ELA_S_OWN, HARD_LINK}),
    }
    for tool in (BrowserUploadTool, AccountUploadTool, FsReadTool):
        assert {ELA_S_OWN, HARD_LINK} <= tool.error_codes, tool.__name__


def test_the_refusals_before_a_spend_are_codes_of_the_tools() -> None:
    """The table of §7: every code it names is one a tool of the five gives."""
    from ela.tools.account import LoginTool
    from ela.tools.browser_files import AccountDownloadTool, AccountUploadTool

    section = adr_text().split("### 7. La spesa di ciò che riuscirebbe", 1)[1].split("### 8.", 1)[0]
    named = set(re.findall(r"`([a-z_]+\.[a-z_]+)`", section)) - {"browser.login"}
    given = AccountDownloadTool.error_codes | AccountUploadTool.error_codes | LoginTool.error_codes

    assert named and named <= given, named - given


def test_the_version_is_the_code_s() -> None:
    assert POLICY_VERSION == "v0.5"
    assert f"`POLICY_VERSION` passa da `v0.4` a `{POLICY_VERSION}`" in adr_text()


def test_what_it_declares_is_said_in_plain_words() -> None:
    """Decisions 3, 4 and 29: what a yes guaranteed and a policy has not, said aloud."""
    text = prose()

    for said in (
        "**Sotto una policy niente di questo c'è: nessuno guarda il file prima che esca",
        "la frase «chi approva è presente» di ADR 0063 §5 è falsa su questo cammino",
        "**Un login sotto una policy entra in un account senza che chi usa ELA sia davanti**",
        "spostano un contenuto fra due siti senza che nessuno lo guardi",
        "**Lo schermo bloccato — NON MISURATO.**",
        "l'istante più vicino che i dati danno",
        "**Il difetto C, con la data.** *Trovato il 2026-11-17",
        "non è una credenziale",
    ):
        assert said in text, said


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

    assert listed == {"0062", "0063", "0066", "0068"}
    assert listed == revised_by_their_state(written())


def test_a_revised_adr_that_does_not_say_so_is_found() -> None:
    texts, listed = written(), revised_by_the_list()
    silent = min(listed)
    texts[silent] = texts[silent].replace(REVISED_MARK, "", 1)

    assert revised_by_their_state(texts) == listed - {silent}


def test_it_is_proposed_until_the_proof_and_the_index_says_so() -> None:
    said = " ".join(status_of(adr_text()).split())
    index = (ADR_DIR / "README.md").read_text(encoding="utf-8")
    found = INDEX_ROW.findall(index)

    assert said.startswith("**Proposta** il **2026-11-17**")
    assert "la sezione 34 di `docs/GETTING_STARTED.md`" in said
    assert "`scripts/prova_m13_15.py`" in said
    assert len(found) == 1 and found[0][1] == "Proposta"
