"""ADR 0066 — the files from the browser, and the browser's own page — held to the code.

The ADR of the branch ``m13.13-i-file-dal-browser`` is written with the implementation, a piece at a
time (M13.9b, M13.9c, M13.10b, M13.13); what this file holds to the code grows with it. Today: the
ADRs it revises say so on their state line and no other does, each mark names a section of it that
is there, what M13.9b put in the port is the port's — and, of M13.13, the four capabilities, the
rows of their tools and verifiers, the members of the port, the fields of the question and the
codes the text names are the code's.
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.ports import AccountBrowser, Browser, Glanced, Landed, tried
from ela.testing.fakes import FakeAccountBrowser, FakeBrowser
from tests.docs.files_additions import TOOL_ROW, VERIFIER_ROW, added_members
from tests.docs.guided_ports import FILE_CAPABILITIES

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0066-browser-files.md"
REVISED_MARK = "**Rivista da ADR 0066 (M13.13)**"
REVISED_ROW = re.compile(r"^- \*\*ADR (\d{4})\b")


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def status_of(text: str) -> str:
    return text.split("- **Stato:**", 1)[1].split("\n- **", 1)[0]


def revised_by_the_list() -> set[str]:
    """The numbers of the ADRs the list «Righe riviste» of this ADR names, one bullet each."""
    block = adr_text().split("## Conseguenze", 1)[1].split("**Righe riviste**", 1)[1]
    rows = block.split("\n\n", 2)[1]
    return {match.group(1) for line in rows.splitlines() if (match := REVISED_ROW.match(line))}


def written() -> dict[str, str]:
    return {
        path.name[:4]: path.read_text(encoding="utf-8")
        for path in ADR_PATH.parent.glob("[0-9]*.md")
        if path != ADR_PATH
    }


def revised_by_their_state(texts: dict[str, str]) -> set[str]:
    return {number for number, text in texts.items() if REVISED_MARK in status_of(text)}


PROOF_FILE = "`~/Downloads/prova-m13.13-20261111-124909.txt`"
PROVEN_AT = "`ead73aa`"


def test_it_is_accepted_by_the_proof_of_its_branch_with_the_file_and_the_commit() -> None:
    """Decision 51 of M13.13: Accettata with a commit of its own once the proof passed on the last
    commit of the branch — the file of the proof and that commit on the state line; what the proof
    saw and who saw it, the verifier for the site's confirmation and Tommaso for the two questions;
    and the mark of the revised rows it carries. Proposta until then, and the line still says so."""
    said = " ".join(status_of(adr_text()).split())

    assert said.startswith("Accettata il **2026-11-11**")
    assert "la sezione 30 di `docs/GETTING_STARTED.md`" in said
    assert PROOF_FILE in said and PROVEN_AT in said
    assert "«Upload successful!»" in said and "il verifier `browser.expect_visible`" in said
    assert "ai passi 2 e 5" in said and "sullo schermo" in said
    assert "**Le «Righe riviste» che questo ADR porta sono già scritte**" in said
    assert "Proposta il **2026-11-03**" in said


def test_the_adrs_it_revises_say_so_on_their_state_line_and_no_other_does() -> None:
    listed = revised_by_the_list()

    assert listed == {"0047", "0052", "0063", "0064"}
    assert listed == revised_by_their_state(written())


def test_a_revised_adr_that_does_not_say_so_is_found() -> None:
    texts, listed = written(), revised_by_the_list()
    silent = min(listed)
    texts[silent] = texts[silent].replace(REVISED_MARK, "", 1)

    assert revised_by_their_state(texts) == listed - {silent}


def test_each_mark_names_a_section_of_this_adr_that_is_there() -> None:
    sections = set(re.findall(r"^### (\d+)\. ", adr_text(), re.MULTILINE))
    for number in revised_by_the_list():
        said = status_of(written()[number]).split(REVISED_MARK, 1)[1]
        named = set(re.findall(r"ADR 0066 §(\d+)", said))
        assert named and named <= sections, number


def test_what_m13_9b_put_in_the_port_is_the_port_s() -> None:
    """§1: the member, the two fields and the one function the ADR names."""
    assert "unanswered" in vars(Browser)
    assert "unanswered" in Landed.__dataclass_fields__
    assert "unanswered" in Glanced.__dataclass_fields__
    assert tried("chrome-error://chromewebdata/", "https://x.example/") == "https://x.example/"
    text = adr_text()
    for named in ("`ela.ports.tried`", "`unanswered`", "`Page.getFrameTree`"):
        assert named in text, named


def test_the_conseguenze_count_the_totals_of_today() -> None:
    """The pin on today's totals, taken over from ADR 0065 (M13.9c adds the seventy-second rule,
    M13.13 the seventy-third and four capabilities): it moves to the ADR that changes them."""
    import tomllib

    from ela.api.security import Kind
    from ela.permissions import production_catalogue
    from tests.architecture.rules import RULES
    from tests.contracts.protocols import port_protocols
    from tests.docs.test_adr_cli import coded_commands
    from tests.docs.test_adr_composition import coded_routes
    from tests.docs.test_adr_placement import _rules_up_to

    text = adr_text().split("## Conseguenze", 1)[1]
    contracts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "importlinter"
    ]["contracts"]

    assert "**settantatré**" in text
    assert "**Regola di architettura 72**" in text and "**Regola di architettura 73**" in text
    assert len(RULES) == 73
    assert set(RULES) - set(_rules_up_to(71)) == {
        "the-vault-s-program-is-its-adapter-s",
        "a-file-is-given-as-bytes-and-a-download-is-named",
    }
    assert "**quindici**" in text and len(contracts) == 15
    assert "**trentasei**" in text and len(tuple(port_protocols())) == 36
    assert "**settantadue**" in text and len(coded_routes()) == 72
    assert "**trentanove**" in text and len(coded_commands()) == 39
    assert "**ventidue**" in text and len(production_catalogue().specs()) == 22
    assert "**sei**" in text and len(Kind) == 6


# ----------------------------------------------------------------------------------------
# M13.13 — the files from the browser
# ----------------------------------------------------------------------------------------


def codes(cell: str) -> frozenset[str]:
    return frozenset(re.findall(r"`([^`]+)`", cell))


def test_the_capabilities_it_adds_are_the_last_four_all_high_and_none_travels() -> None:
    """§4. The table is compared with the catalogue, argument by argument, by
    ``test_adr_catalogue.py``; here what the section says of the four together."""
    from ela.domain import RiskLevel
    from ela.permissions import production_catalogue

    specs = production_catalogue(fs_scope="ELA").specs()

    assert {spec.id for spec in specs[-4:]} == FILE_CAPABILITIES
    for spec in specs[-4:]:
        assert spec.risk is RiskLevel.HIGH and spec.requires_authorization
        assert spec.scope == ("ELA",) and spec.scoped_arguments == ("file",)
        assert spec.policy_terms is None, "no policy covers a HIGH that asks at every use"
        assert "click" not in spec.input_schema["required"]


def test_the_tool_rows_are_the_running_tools() -> None:
    from ela.permissions import (
        BROWSER_DOWNLOAD,
        BROWSER_DOWNLOAD_AS_YOU,
        BROWSER_UPLOAD,
        BROWSER_UPLOAD_AS_YOU,
    )
    from ela.tools.browser_files import (
        AccountDownloadTool,
        AccountUploadTool,
        BrowserDownloadTool,
        BrowserUploadTool,
    )

    rows = {
        match.group(1): match.groups()
        for line in adr_text().splitlines()
        if (match := TOOL_ROW.match(line)) and match.group(1) in FILE_CAPABILITIES
    }
    running = {
        BROWSER_DOWNLOAD: BrowserDownloadTool,
        BROWSER_DOWNLOAD_AS_YOU: AccountDownloadTool,
        BROWSER_UPLOAD: BrowserUploadTool,
        BROWSER_UPLOAD_AS_YOU: AccountUploadTool,
    }

    assert set(rows) == set(running) == FILE_CAPABILITIES
    for capability, tool in running.items():
        _, class_name, name, idempotent, errors, numbers = rows[capability]
        assert class_name == tool.__name__
        assert name == capability.replace(".", "-").replace("_", "-")
        assert (idempotent == "sì") is tool.idempotent
        assert codes(errors) == tool.error_codes, capability
        assert codes(numbers) == tool.audit_numbers, capability
        assert not tool.relocatable and not tool.continuing


def test_the_verifier_rows_are_the_running_verifiers(tmp_path: Path) -> None:
    from ela.tools.browser_files import (
        AccountFileDownloadedVerifier,
        AccountUploadVerifier,
        FileDownloadedVerifier,
        UploadVerifier,
    )

    rows = {
        match.group(1): match.groups()
        for line in adr_text().splitlines()
        if (match := VERIFIER_ROW.match(line)) and match.group(2).endswith("Verifier")
    }
    rows = {capability: row for capability, row in rows.items() if capability in FILE_CAPABILITIES}
    running = (
        FileDownloadedVerifier(tmp_path),
        AccountFileDownloadedVerifier(tmp_path),
        UploadVerifier(FakeBrowser(), 30.0),
        AccountUploadVerifier(FakeAccountBrowser(), 30.0),
    )

    assert set(rows) == {verifier.capability_id for verifier in running} == FILE_CAPABILITIES
    for verifier in running:
        _, class_name, name, conditions, failures = rows[verifier.capability_id]
        assert class_name == type(verifier).__name__
        assert name == verifier.name
        assert codes(conditions) == verifier.conditions
        assert codes(failures) == {
            code for code in verifier.failure_codes if not code.startswith("verification.")
        }
        assert verifier.reads_the_machine, "none of the four travels"


def test_what_m13_13_put_in_the_port_is_the_port_s() -> None:
    """§6, §8: the four members, on both ports, and the table «Port estesi:» names them."""
    members = {"give", "download", "downloaded_from", "refused_download"}

    assert members <= set(vars(Browser))
    assert all(hasattr(AccountBrowser, name) for name in members)
    assert added_members() == {
        "Browser": frozenset({"unanswered", *members}),
        "AccountBrowser": frozenset({"unanswered", *members}),
    }


def test_the_codes_and_the_limit_the_text_names_are_the_code_s() -> None:
    from ela.tools import browser_files
    from ela.tools.browser import DOWNLOAD_REFUSED, _Done

    text = adr_text()
    for code in (
        browser_files.SITE_NOT_DECLARED,
        browser_files.NOT_A_FILE_FIELD,
        browser_files.FILE_CHANGED,
        browser_files.FILE_TOO_LARGE,
        browser_files.DOWNLOAD_NOT_STARTED,
        browser_files.FILE_DOWNLOADED,
        DOWNLOAD_REFUSED,
    ):
        assert f"`{code}`" in text, code
    assert browser_files.UPLOAD_MAX_BYTES == 50 * 1024 * 1024 and "**50 MiB**" in text
    assert browser_files.OCTET_STREAM == "application/octet-stream" and "`mimetypes`" in text
    assert "«may have been made»" in text
    said = browser_files.BrowserDownloadTool._after  # noqa: SLF001 — the sentence the text quotes
    assert said(None, _Done(made=1, total=1)).endswith("may have been made")  # type: ignore[arg-type]
    assert said(None, _Done(made=0, total=1)).endswith("was not made")  # type: ignore[arg-type]


def test_the_fields_of_the_question_it_names_are_the_schema_s_and_the_executor_s() -> None:
    """§5: four fields of their own, on the three surfaces that answer."""
    from ela.api.schemas import ApprovalOut, Asked
    from ela.cli.system import FILE_ROWS, QUESTION_FIELDS

    named = {"site", "visits", "size", "digest"}

    assert named <= set(Asked.model_fields) and named <= set(ApprovalOut.model_fields)
    assert named <= QUESTION_FIELDS
    assert {"site", "on the site", "size", "sha256"} == FILE_ROWS
    for field in named:
        assert f"`{field}`" in adr_text(), field


def test_the_door_says_two_things_and_the_rule_names_them() -> None:
    """§8 and rule 73: closed and telling, or open under a name of the browser's."""
    from tests.architecture.rules import BYTES_KEY, DOOR_BEHAVIOURS, DOOR_COMMAND, FILE_GIVING_CALL

    text = adr_text()

    assert {"allowAndName", "deny"} == DOOR_BEHAVIOURS
    for word in (*DOOR_BEHAVIOURS, DOOR_COMMAND, FILE_GIVING_CALL):
        assert f"`{word}`" in text, word
    assert BYTES_KEY == "buffer"
