"""ADR 0074 against the tree (M13.17): the tables it writes — the codes the tools and the verifiers
add, the constants of the guard and of a read, the places ELA's list gains —, its sentences that
quote the code, the marks on the ADRs it revises, the index, and what it declares in plain words.

The shape of ``test_adr_policies_on_login_and_files.py``: the rows of the ADRs before stay as they
were, and their tests read the codes this one adds through :func:`added_codes` and
:func:`added_failure_codes`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from ela.composition.settings import DATABASE_JOURNAL, THE_ENV
from ela.tools.disk import ABANDONED_MOST, DISK_LIMIT_SECONDS
from ela.tools.fs import FS_READ_MAX_BYTES

ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = ROOT / "docs" / "adr"
ADR_PATH = ADR_DIR / "0074-filesystem-up-to-the-home.md"
INDEX_ROW = re.compile(
    r"^\| \[0074\]\(0074-filesystem-up-to-the-home\.md\) \| (.+?) \| (.+?) \|$", re.M
)
ADDED_ROW = re.compile(r"^\| `([\w.]+)` \| ((?:`[\w.]+`(?:, )?)+) \|$", re.M)
CONSTANT_ROW = re.compile(r"^\| `([A-Z_]+)` \| (\d+) \|$", re.M)
PLACE_ROW = re.compile(r"^\| `([^`]+)` \| .+ \|$", re.M)
REVISED_ROW = re.compile(r"^- \*\*ADR (\d{4})\b")
REVISED_MARK = "**Rivista da ADR 0074 (M13.17)**"
TOOLS_TABLE = "I codici che i tool aggiungono a quelli che gli ADR di prima scrivono:"
VERIFIERS_TABLE = "I codici di fallimento che i verifier aggiungono (ADR 0014 §2):"


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def prose() -> str:
    return " ".join(adr_text().split())


def status_of(text: str) -> str:
    """The state line: up to the next head entry, **or to the first blank line** — an ADR without a
    «Data:» entry would otherwise give its whole body (the consistency reading, R1)."""
    return text.split("- **Stato:**", 1)[1].split("\n- **", 1)[0].split("\n\n", 1)[0]


def _table(after: str) -> str:
    return adr_text().split(after, 1)[1].split("\n\n", 2)[1]


def added_codes() -> dict[str, frozenset[str]]:
    """The codes a tool adds to those the ADRs before wrote (§12), by capability: read by the tests
    of those ADRs, whose rows stay as they were."""
    return {
        name: frozenset(re.findall(r"`([\w.]+)`", cells))
        for name, cells in ADDED_ROW.findall(_table(TOOLS_TABLE))
    }


def added_failure_codes() -> dict[str, frozenset[str]]:
    """The failure codes a verifier adds (§12), by capability."""
    return {
        name: frozenset(re.findall(r"`([\w.]+)`", cells))
        for name, cells in ADDED_ROW.findall(_table(VERIFIERS_TABLE))
    }


def test_the_codes_the_tools_add_are_the_tools() -> None:
    """Every row names codes its tool declares, and every tool under the root that gives one of the
    codes of this ADR has a row."""
    from ela.tools import FsReadTool, FsWriteTool
    from ela.tools.browser_files import (
        AccountDownloadTool,
        AccountUploadTool,
        BrowserDownloadTool,
        BrowserUploadTool,
    )
    from ela.tools.terminal import TerminalRunTool

    tools = {
        "fs.read": FsReadTool,
        "fs.write": FsWriteTool,
        "terminal.run": TerminalRunTool,
        "browser.download": BrowserDownloadTool,
        "browser.download_as_you": AccountDownloadTool,
        "browser.upload": BrowserUploadTool,
        "browser.upload_as_you": AccountUploadTool,
    }

    assert set(added_codes()) == set(tools)
    for capability, codes in added_codes().items():
        assert codes <= tools[capability].error_codes, capability
        assert "fs.no_answer" in codes, capability


def test_the_codes_the_verifiers_add_are_the_verifiers(tmp_path: Path) -> None:
    from ela.tools.browser_files import AccountFileDownloadedVerifier, FileDownloadedVerifier
    from ela.tools.verifiers import FsReadVerifier, FsWriteVerifier

    running = (
        FsReadVerifier(tmp_path, protected={}),
        FsWriteVerifier(tmp_path, protected={}),
        FileDownloadedVerifier(tmp_path, protected={}),
        AccountFileDownloadedVerifier(tmp_path, protected={}),
    )

    assert set(added_failure_codes()) == {str(one.capability_id) for one in running}
    for verifier in running:
        assert added_failure_codes()[str(verifier.capability_id)] <= verifier.failure_codes


def test_the_constants_are_the_code_s() -> None:
    assert dict(CONSTANT_ROW.findall(adr_text())) == {
        "DISK_LIMIT_SECONDS": str(int(DISK_LIMIT_SECONDS)),
        "ABANDONED_MOST": str(ABANDONED_MOST),
        "FS_READ_MAX_BYTES": str(FS_READ_MAX_BYTES),
    }
    assert int(DISK_LIMIT_SECONDS) == DISK_LIMIT_SECONDS


def test_the_places_the_list_gains_are_the_names_the_settings_give() -> None:
    section = adr_text().split("**La lista guadagna**", 1)[1].split("### 6.", 1)[0]
    named = set(PLACE_ROW.findall(section)) - {"Posto"}

    assert named == {
        *(f"the journal of the database ({suffix})" for suffix in DATABASE_JOURNAL),
        "the folders of the guided sessions",
        THE_ENV,
    }


def test_the_sentences_it_quotes_are_the_ones_the_settings_give(tmp_path: Path) -> None:
    """A message quoted in a document and nowhere else drifts the first time somebody edits it:
    each one is asked of the function that gives it."""
    from ela.composition.settings import FilesystemSettings, refuse_the_folders, refuse_the_root

    said = prose()
    with pytest.raises(ValidationError) as bare:
        FilesystemSettings(fs_root=tmp_path, fs_scope="ELA")
    with pytest.raises(ValueError) as above:
        refuse_the_root(tmp_path, {}, home=tmp_path / "you")
    (tmp_path / ".ela").mkdir()
    with pytest.raises(ValueError) as inside:
        refuse_the_folders(tmp_path, (".ela",), {"ELA's home": tmp_path / ".ela"}, limit=10.0)

    rewritten = " ".join(str(bare.value).split())
    assert "since M13.17 the scope is a list of folders, one line of JSON. Write" in rewritten
    assert 'ELA_FS_SCOPE=["ELA"] for the folder this line named until now' in rewritten
    assert "since M13.17 the scope is a list of folders, one line of JSON. Write" in said
    assert "the folders ELA may touch reach at most up to your home" in str(above.value)
    assert "holds your home" in str(above.value) and "holds your home" in said
    sentence = "it would open nothing — every read and write there is refused as ELA's own"
    assert sentence in str(inside.value) and sentence in said


def test_the_words_of_answer_49_are_written_as_given() -> None:
    assert (
        "**Il sì a una lettura approva il percorso; la dimensione nella domanda è quella che il "
        "disco diceva alla domanda, e il tetto chiude il caso peggiore. Un confronto della sola "
        "dimensione sarebbe mezza difesa con il nome di una intera — un file cambiato con la "
        "stessa dimensione passerebbe — e rifiuterebbe ogni file che cresce fra la domanda e il "
        "sì. Per un "
        "caricamento è diverso: lì i byte escono dalla macchina, e la domanda ne porta lo sha256. "
        "Il risultato dice già i byte letti.**"
    ) in prose()


def test_what_it_declares_is_said_in_plain_words() -> None:
    text = prose()

    for said in (
        "**Nessuna lista dei posti pericolosi.**",
        "**Un programma che `terminal.run` lancia arriva ai posti di ELA**",
        "**Una scrittura di ELA li raggiunge solo se chi usa ELA apre la cartella che li "
        "contiene.**",
        "[M13.20](../ROADMAP.md), riservata",
        "**Che cosa macOS fa quando chiede o nega**",
        "**Un file che iCloud tiene altrove**: NON MISURATO",
        "**Il tetto è di una lettura**",
        "**Su un nodo la domanda non dice la dimensione**",
        "**Una cartella il cui nome è esso stesso una lista di JSON**",
        "**Gli eventi già nell'audit tengono la frase di prima**",
        "`POLICY_VERSION` non si muove",
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

    assert listed == {"0014", "0045", "0047", "0048", "0066", "0068", "0071"}
    assert listed == revised_by_their_state(written())
    assert all(
        f"ADR {one}" in status_of(adr_text()) or one in status_of(adr_text()) for one in listed
    )


def test_a_revised_adr_that_does_not_say_so_is_found() -> None:
    texts, listed = written(), revised_by_the_list()
    silent = min(listed)
    texts[silent] = texts[silent].replace(REVISED_MARK, "", 1)

    assert revised_by_their_state(texts) == listed - {silent}


def test_it_is_accepted_after_the_proof_and_the_index_says_so() -> None:
    """Decisions 64–66 of the last block of M13.17: accepted with a commit of its own once the proof
    passed, and its state line says what the hand saw, what only the tests prove, and what is not
    measured."""
    said = " ".join(status_of(adr_text()).split())
    found = INDEX_ROW.findall((ADR_DIR / "README.md").read_text(encoding="utf-8"))

    assert said.startswith("**Accettata** il **2026-11-19**")
    assert "la sezione 35 di `docs/GETTING_STARTED.md`" in said
    assert "`scripts/prova_m13_17.py`" in said
    assert "`~/Downloads/prova-m13.17-20261119-133951.txt`: 45 PASSATI al primo giro" in said
    for part in ("**Che cosa ha visto la mano**", "**Che cosa prova solo il test**"):
        assert part in said, part
    assert "**Che cosa resta NON MISURATO**" in said
    assert len(found) == 1 and found[0][1] == "Accettata"
    assert adr_text().startswith(f"# 0074. {found[0][0]}\n")
