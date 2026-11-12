"""ADR 0061 (M14.6): Haiku 5.5 in the price list, and what it names is what the code has.

The price list, the profiles, the date and the shares of the cache were read by
``test_adr_provider`` from this ADR from M14.6 to M14.6b, and are ADR 0067's since; this file holds
what is only this ADR's: its worst cases held to the function — today's, which are ADR 0067's since
M14.6b —, the revisions it writes on ADR 0057 and on M14.1, the state it is in — «Proposta» until
the proof of M14.3, which has the step that checks it, and Accettata since it passed —, and the
field it adds to the usage.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from ela.domain import ProviderUsage
from ela.providers.anthropic.models import HAIKU_5_5, MODELS, PROFILES
from ela.providers.anthropic.pricing import worst_cost
from tests.docs.test_adr_three_models import ADR_PATH as TODAY_PATH
from tests.docs.test_adr_three_models import WORST_ROW

ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = ROOT / "docs" / "adr"
ADR_PATH = ADR_DIR / "0061-haiku-5-5.md"
INDEX_ROW = re.compile(r"^\| \[0061\]\(0061-haiku-5-5\.md\) \| (.+?) \| (.+?) \|$", re.MULTILINE)


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def status_of(text: str) -> str:
    return text.split("- **Stato:**", 1)[1].split("\n- **", 1)[0]


def test_the_table_of_the_worst_cases_is_the_function_s() -> None:
    """Criterion 3: the numbers of the table are computed by ``worst_cost``, not by hand. Since
    M14.6b (decision 4) the table of today is ADR 0067 §2, which has a row for every model of the
    list; the table of §4 here is the history of 2026-10-08, with Haiku 4.5 in it."""
    rows = WORST_ROW.findall(TODAY_PATH.read_text(encoding="utf-8"))

    assert rows
    for model, output, amount in rows:
        expected = Decimal(amount.replace(",", "."))
        assert worst_cost(MODELS[model], output_tokens=int(output)) == expected, model


def test_the_sentence_that_kept_haiku_4_5_is_history_and_the_cheap_profile_is_haiku_5_5() -> None:
    """Criterion 5 was true for the month: Haiku 4.5 stayed in the list, with no profile. Since
    M14.6b it is out of the list (ADR 0067 §1), and the sentence stays here with its dated note."""
    flat = " ".join(adr_text().split())
    assert {hint for hint, model in PROFILES.items() if model == HAIKU_5_5} == {
        "fast",
        "cheap",
        "classification",
        "extraction",
        "routine",
    }
    assert "**Haiku 4.5 resta nel listino**" in flat
    assert "Haiku 4.5 non resta nel listino, il mese di cui parla è passato" in flat


def test_it_was_accepted_with_the_proof_of_m14_3(shown: str = "2026-10-09") -> None:
    """Decision 27: no proof by hand of its own; accepted when the proof of M14.3, which has the
    step that checks it, passed — with its file and its commit (decision 49)."""
    (row,) = INDEX_ROW.findall((ADR_DIR / "README.md").read_text(encoding="utf-8"))
    status = status_of(adr_text())

    assert row[1] == "Accettata"
    assert status.strip().startswith(f"Accettata il **{shown}**")
    assert "prova-m14.3-20261009-104118.txt" in status and "`f58a6cb`" in status
    assert "**Non ha una prova a mano sua**" in status


def test_the_adr_it_revises_says_so_on_its_state_line_and_keeps_its_acceptance() -> None:
    """The form of ADR 0046 and ADR 0049: an ADR is not rewritten, its «Stato:» line points on."""
    status = status_of((ADR_DIR / "0057-spending-cap.md").read_text(encoding="utf-8"))

    assert status.strip().startswith("Accettata il **2026-10-07**")
    assert "**Rivista da ADR 0061 (M14.6)** il 2026-10-08" in status


def test_the_sentence_of_m14_1_it_revises_is_still_there_with_its_annotation() -> None:
    text = (ROOT / "docs" / "milestones" / "M14.1.md").read_text(encoding="utf-8")
    flat = " ".join(text.split())

    assert "i profili economici restano su Haiku 4.5, che non ha un successore." in flat
    assert "***Dal 2026-10-08 (M14.6, ADR 0061)*** il successore c'è: Haiku 5.5" in flat


def test_the_field_it_adds_is_the_usage_s() -> None:
    """§5: a number beside the tokens, ``None`` when no request was built."""
    assert "**`request_bytes`**" in adr_text()
    assert ProviderUsage(input_tokens=0, output_tokens=0).request_bytes is None
