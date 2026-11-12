"""ADR 0067 (M14.6b): the price list without Haiku 4.5, held to the code.

The price list, the profiles, the date and the column ``effort`` are read by ``test_adr_provider``,
which reads them from this ADR since M14.6b; the day the re-reading is due by is derived by
``tests/composition/test_policy_wiring.py``. This file holds what is only this ADR's: the table of
today's worst cases — one row for every model of the list and for each of the two outputs, and the
numbers the function gives —, the ADRs it revises and their marks, the dated notes where a row of
theirs is no longer the one read, and the sentences it quotes of the code.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import pytest

from ela.composition import ConfigurationError
from ela.composition.routes import every_route_names_a_model
from ela.domain import ErrorMetadata
from ela.ports import PROVIDER_UNKNOWN_MODEL_HINT
from ela.providers.anthropic.models import MODELS
from ela.providers.anthropic.pricing import worst_cost
from ela.routing import DEFAULT_ROUTES, Route, RoutePolicy
from ela.tools.model import placed
from tests.domain.examples import HAIKU_4_5_ID

ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = ROOT / "docs" / "adr"
ADR_PATH = ADR_DIR / "0067-three-models.md"
INDEX_ROW = re.compile(r"^\| \[0067\]\(0067-three-models\.md\) \| (.+?) \| (.+?) \|$", re.MULTILINE)
WORST_ROW = re.compile(r"^\| `([\w.-]+)` \| (\d+) \| ([\d,]+) \$ \|$", re.MULTILINE)
"""A row of §2: the model as its id — no dictionary of names by hand —, an output, a cost."""
OUTPUTS = (4096, 8192)
"""The default output, and the output of the long plan of the guide's section 23."""
REVISED_MARK = "**Rivista da ADR 0067 (M14.6b)**"
REVISED_ROW = re.compile(r"^- \*\*ADR (\d{4})\b")
NOTE = "*Dal 2026-11-11 (M14.6b"


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def status_of(text: str) -> str:
    return text.split("- **Stato:**", 1)[1].split("\n- **", 1)[0]


def section(text: str, number: int) -> str:
    return text.split(f"\n### {number}.", 1)[1].split("\n### ", 1)[0].split("\n## ", 1)[0]


def worst_rows(text: str) -> set[tuple[str, int]]:
    return {(model, int(output)) for model, output, _ in WORST_ROW.findall(section(text, 2))}


def every_model_at_both_outputs() -> set[tuple[str, int]]:
    return {(model, output) for model in MODELS for output in OUTPUTS}


# ----------------------------------------------------------------------------------------
# §2 — today's worst cases
# ----------------------------------------------------------------------------------------


def test_today_s_worst_cases_have_a_row_for_every_model_and_both_outputs() -> None:
    """Decision 4: no filter «if the model is still there» — a row of a model that is not in the
    list is a red, and so is a model without its row."""
    assert worst_rows(adr_text()) == every_model_at_both_outputs()


def test_a_row_of_a_model_that_left_or_a_model_without_its_row_is_found() -> None:
    text = adr_text()
    gone = text.replace(
        "| `claude-haiku-5-5` | 8192 | 0,516384 $ |",
        f"| `claude-haiku-5-5` | 8192 | 0,516384 $ |\n| `{HAIKU_4_5_ID}` | 4096 | 0,216384 $ |",
        1,
    )
    missing = text.replace("| `claude-sonnet-5-5` | 8192 | 2,065536 $ |\n", "", 1)

    assert worst_rows(gone) - every_model_at_both_outputs() == {(HAIKU_4_5_ID, 4096)}
    assert every_model_at_both_outputs() - worst_rows(missing) == {("claude-sonnet-5-5", 8192)}


def test_each_worst_case_is_the_function_s() -> None:
    """The numbers are computed by ``worst_cost``, never by hand."""
    for model, output, amount in WORST_ROW.findall(section(adr_text(), 2)):
        expected = Decimal(amount.replace(",", "."))
        assert worst_cost(MODELS[model], output_tokens=int(output)) == expected, (model, output)


# ----------------------------------------------------------------------------------------
# §3, §4 — the sentences it quotes are the code's
# ----------------------------------------------------------------------------------------


def test_the_three_places_of_a_hint_are_the_tool_s_words() -> None:
    flat = " ".join(section(adr_text(), 3).split())
    refused = ErrorMetadata(code=PROVIDER_UNKNOWN_MODEL_HINT, message="no model for hint 'x'")
    for task_type, model_hint in ((None, "x"), ("routine", None), (None, None)):
        said = placed(refused, task_type, model_hint).message or ""
        assert f"«…{said.removeprefix(refused.message or '')}»" in flat, said


def test_the_reason_it_quotes_is_the_gate_s_with_the_tool_s_place() -> None:
    flat = " ".join(section(adr_text(), 3).split())
    refused = ErrorMetadata(
        code=PROVIDER_UNKNOWN_MODEL_HINT, message=f"no model for hint {HAIKU_4_5_ID!r}"
    )
    said = placed(refused, None, HAIKU_4_5_ID).message

    assert f"«this call cannot be bounded: {PROVIDER_UNKNOWN_MODEL_HINT}: {said}»" in flat


def test_the_startup_refusal_it_quotes_is_the_composition_s() -> None:
    pinned = Route(providers=("anthropic",), profile=HAIKU_4_5_ID)
    quoted = "\n".join(
        line.removeprefix("> ")
        for line in section(adr_text(), 4).splitlines()
        if line.startswith("> ")
    )

    with pytest.raises(ConfigurationError) as stopped:
        every_route_names_a_model(RoutePolicy({**DEFAULT_ROUTES, "routine": pinned}))

    assert " ".join(quoted.split()) == str(stopped.value)


# ----------------------------------------------------------------------------------------
# The state, the revised rows, the dated notes
# ----------------------------------------------------------------------------------------


PROOF_FILE = "`~/Downloads/prova-m14.6b-20261112-021100.txt`"
PROVEN_AT = "`e41b8a8`"


def test_it_is_accepted_by_the_proof_of_its_branch_with_the_file_and_the_commit() -> None:
    """Decision 14 and answers 31 and 33: Accettata with a commit of its own once the proof of
    section 31 passed on the last commit of the branch — the file of the proof and that commit on
    the state line, and who saw what. Proposta until then, and the line still says so."""
    (row,) = INDEX_ROW.findall((ADR_DIR / "README.md").read_text(encoding="utf-8"))
    said = " ".join(status_of(adr_text()).split())

    assert row[1] == "Accettata"
    assert said.startswith("Accettata il **2026-11-12**")
    assert "la sezione 31 di `docs/GETTING_STARTED.md`" in said
    assert PROOF_FILE in said and PROVEN_AT in said
    assert "l'`occhio` del passo 3 Tommaso, e la risposta è stata sì" in said
    assert "il rifiuto all'avvio solo la suite" in said
    assert "Proposta il **2026-11-11**" in said


def test_what_the_proof_saw_and_did_not_is_written_with_who_saw_it() -> None:
    """Answers 28, 31 and 32: §7 says what the proof saw — the task of October was there —,
    what only the suite proves, the ``.env`` of the Mac, and that the PC has not been looked at."""
    said = " ".join(section(adr_text(), 7).split())

    assert "***Com'è andata, il 2026-11-12***" in said
    assert "**il task di ottobre c'era**: `3a4d7002`, del 2026-10-07" in said
    assert "hanno stampato 0 e 0" in said
    assert "**Il PC non è ancora stato guardato**" in said


def revised_by_the_list() -> set[str]:
    """The numbers of the ADRs the list «Righe riviste» of this ADR names, one bullet each."""
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
    """ADR 0063 is not among them: its note is a re-reading's, which leaves no mark."""
    listed = revised_by_the_list()

    assert listed == {"0020", "0057", "0061"}
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
        named = set(re.findall(r"ADR 0067 §(\d+)", said))
        assert named and named <= sections, number


def test_a_dated_note_stands_where_a_row_is_no_longer_the_one_read() -> None:
    """Decision 3: ADR 0061 and ADR 0057 are not rewritten — a dated note in italics where a row of
    theirs is no longer the one read; and ADR 0020 §3 and §5, which ADR 0067 revises openly."""
    texts = written()
    adr_0061, adr_0057, adr_0020 = texts["0061"], texts["0057"], texts["0020"]

    assert NOTE in section(adr_0061, 1)
    assert NOTE in section(adr_0061, 4)
    assert "Dal 2026-11-11 il listino e la sua scadenza" in adr_0061.split("## Conseguenze", 1)[1]
    assert NOTE in section(adr_0057, 2)
    assert NOTE in section(adr_0020, 3)
    assert NOTE in section(adr_0020, 5)
