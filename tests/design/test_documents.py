"""The documents say what is there (M17.1, criterio 18).

``CLAUDE.md``: the rules of what lives in ``apps/`` do not walk Python — they live in the tests
of their folder, *and the README of the folder names every rule with the test that defends it*.
So the README and the folder of tests are a closed world, in both directions; and the folder
§48 does not foresee is named where a reader of ``apps/`` would look for it.

ADR 0042 says what the generator does — the derived files are the ones it declares — quotes the
criterion of the gate it applies, decides the names of attention that the tokens carry, and stays
«Proposta» exactly as long as the proof by hand of M17.1 has not been written down.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.design.tree import DESIGN_SYSTEM, ROOT, generator, tokens

TESTS = Path(__file__).resolve().parent
NAMED = re.compile(r"`tests/design/(test_[a-z_]+\.py)`")
ADRS = ROOT / "docs" / "adr"
MILESTONE = ROOT / "docs" / "milestones" / "M17.1.md"
ROW = re.compile(r"^\| `([^`]+)` \|", re.MULTILINE)
STATE = re.compile(r"^- \*\*Stato:\*\*\s*([A-Za-zÀ-ÿ]+)", re.MULTILINE)
CRITERION = (
    "Un package entra in `cov-critical` quando ogni suo ramo può essere eseguito in CI. Dove "
    "questo è falso, il package non deve contenere nessun ramo che decida qualcosa."
)
PENDING = "*La prova a mano non è finita.*"


def files_of_the_folder() -> set[str]:
    found = {path.name for path in TESTS.glob("test_*.py")}
    assert found, "there must be tests, or this test is vacuous"
    return found


def named_by(readme: str) -> set[str]:
    return set(NAMED.findall(readme))


def readme() -> str:
    return (DESIGN_SYSTEM / "README.md").read_text(encoding="utf-8")


def test_the_readme_names_every_test_of_the_design_system_and_no_other() -> None:
    assert named_by(readme()) == files_of_the_folder()


def test_the_readme_names_every_derived_file_as_derived() -> None:
    for name in generator().DERIVED:
        assert f"| `{name}` | **derivato** |" in readme(), name
    assert "scripts/generate_design_system.py" in readme()


def test_the_folder_the_spec_does_not_foresee_is_named_in_apps() -> None:
    assert "`design-system/`" in (ROOT / "apps" / "README.md").read_text(encoding="utf-8")


def test_claude_md_says_where_the_rules_of_apps_live() -> None:
    text = " ".join((ROOT / "CLAUDE.md").read_text(encoding="utf-8").split())
    assert "Le regole di ciò che sta in `apps/` non camminano Python" in text
    assert "`tests/design/` per il design system" in text


def test_a_test_the_readme_forgets_and_one_it_invents_are_seen() -> None:
    text = "| a | `tests/design/test_generated.py` |\n| b | `tests/design/test_imaginary.py` |"
    assert named_by(text) == {"test_generated.py", "test_imaginary.py"}
    assert named_by(text) - files_of_the_folder() == {"test_imaginary.py"}
    assert "test_contrast.py" in files_of_the_folder() - named_by(text)


# ----------------------------------------------------------------------------------------
# ADR 0042
# ----------------------------------------------------------------------------------------


def adr(number: str = "0042") -> str:
    (path,) = ADRS.glob(f"{number}-*.md")
    return path.read_text(encoding="utf-8")


def flat(text: str) -> str:
    """One line, and a quotation without its markers: ADR 0028 writes its criterion as ``> …``."""
    return " ".join(re.sub(r"^>\s?", "", text, flags=re.MULTILINE).split())


def section_of(text: str, number: int) -> str:
    start = text.index(f"\n## {number}. ")
    return text[start : text.index("\n## ", start + 1)]


def derived_named(text: str) -> list[str]:
    """The files the ADR says are derived: the first cell of the rows of its section 2."""
    return ROW.findall(section_of(text, 2))


def test_the_adr_lists_the_derived_files_the_generator_declares() -> None:
    assert derived_named(adr()) == list(generator().DERIVED)
    assert "È il primo caso, nel repository, di file generati per intero." in flat(adr())


def test_the_adr_quotes_the_criterion_of_the_gate_it_applies() -> None:
    assert CRITERION in flat(adr("0028")), "the quotation must still be what ADR 0028 says"
    assert CRITERION in flat(adr())
    assert "`apps/design-system/` **non ha rami**" in flat(adr())


def test_the_adr_decides_the_names_of_attention_the_tokens_carry() -> None:
    names = ", ".join(generator().entries(tokens()["attention"]))
    assert f"**{names}**" in flat(section_of(adr(), 5))


def test_the_adr_is_a_proposal_exactly_as_long_as_the_proof_by_hand_is_not_written() -> None:
    """The two move together, as ADR 0040 and its guide did: an ADR accepted over a proof still
    in the future tense is the thing that was refused, and so is the reverse."""
    found = STATE.search(adr())
    assert found is not None
    proposed = found.group(1) == "Proposta"
    assert found.group(1) in {"Proposta", "Accettata"}
    assert (PENDING in MILESTONE.read_text(encoding="utf-8")) == proposed


def test_the_adr_names_the_font_and_it_is_the_one_of_the_tokens() -> None:
    """The user's decision of 2026-09-19: the system stack. The ADR quotes the token itself."""
    family = tokens()["typography"]["family"]["sans"]["$value"]
    chosen = section_of(adr(), 9)
    assert f"`{family}`" in chosen
    assert "San Francisco" in chosen and "Segoe UI" in chosen
    assert "In bianco" not in chosen


def test_the_adr_and_the_readme_record_the_direction_in_the_words_of_the_user() -> None:
    words = "«stile Apple, futuristico stile JARVIS, azzurro e bianco per tutto, premium»"
    assert words in flat(adr())
    assert words in flat(readme())


def test_a_derived_file_the_adr_forgets_is_seen() -> None:
    text = "\n## 2. Derived\n\n| Derivato | x |\n|---|---|\n| `tokens.css` | a |\n\n## 3. Next\n"
    assert derived_named(text) == ["tokens.css"]
    assert derived_named(text) != list(generator().DERIVED)
