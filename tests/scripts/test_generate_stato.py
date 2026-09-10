"""Behaviour of ``scripts/generate_stato.py`` on synthetic repositories.

``STATO.md`` is the restart point, and the whole reason it is generated is that a restart point
which has quietly gone stale is worse than none: the reader has no reason to doubt it. So what is
checked here is the negative case — a milestone added, a phase named, a debt declared and nobody
paying it — on trees built for the purpose, so that these tests say something about the generator
and not about today's shape of ELA. That the real document is in step with the real repository is
the last test, and it is the one ``make check`` fails on.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "generate_stato.py"

MILESTONE = "# {identifier} — {title}\n\n- **Stato:** **{state}**\n\n{body}\n"


@pytest.fixture(scope="module")
def generate_stato() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_stato", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before it is executed: the script's dataclasses resolve their annotations
    # through ``sys.modules``, and a module loaded by path alone is not in there.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def milestone(root: Path, identifier: str, *, state: str = "Implementata", body: str = "") -> Path:
    return write(
        root / "docs" / "milestones" / f"{identifier}.md",
        MILESTONE.format(
            identifier=identifier, title=f"titolo di {identifier}", state=state, body=body
        ),
    )


# ----------------------------------------------------------------------------------------
# The milestones
# ----------------------------------------------------------------------------------------


def test_the_letter_of_a_repair_sorts_between_the_two_milestones(
    tmp_path: Path, generate_stato: ModuleType
) -> None:
    """M6.1b belongs where somebody looking for the defect will look — after M6.1, before M6.2."""
    for identifier in ("M6.2", "M6.1b", "M6.1", "M10.1"):
        milestone(tmp_path, identifier)

    found = [entry.identifier for entry in generate_stato.milestones(tmp_path)]

    assert found == ["M6.1", "M6.1b", "M6.2", "M10.1"]


def test_a_milestone_without_a_state_is_refused(tmp_path: Path, generate_stato: ModuleType) -> None:
    """The state is the column: a document that does not declare one cannot be rendered as one."""
    write(tmp_path / "docs" / "milestones" / "M1.1.md", "# M1.1 — senza stato\n\ncorpo\n")

    with pytest.raises(ValueError, match="Stato"):
        generate_stato.milestones(tmp_path)


def test_a_phase_the_changelog_has_not_named_is_shown_as_such(
    tmp_path: Path, generate_stato: ModuleType
) -> None:
    """A phase gets its name when it delivers; until then the table says so instead of guessing."""
    milestone(tmp_path, "M12.1", state="Proposta")
    write(tmp_path / "docs" / "CHANGELOG.md", "### Fase 11 — La voce\n")

    rendered = generate_stato.render_milestones(
        generate_stato.milestones(tmp_path), generate_stato.phase_names(tmp_path)
    )

    assert "| 12 — *senza nome* | `M12.1` | Proposta |" in rendered


# ----------------------------------------------------------------------------------------
# The phases nobody has built yet
# ----------------------------------------------------------------------------------------


def test_only_the_phases_past_the_last_milestone_are_counted(
    tmp_path: Path, generate_stato: ModuleType
) -> None:
    milestone(tmp_path, "M1.1")
    write(tmp_path / "docs" / "adr" / "0001-uno.md", "rimandato alla Fase 2 e alla Fase 1\n")
    write(tmp_path / "docs" / "CHANGELOG.md", "anche qui la Fase 2, e la Fase 5\n")

    assert generate_stato.future_phases(tmp_path) == [(2, 2), (5, 1)]


def test_the_document_this_script_writes_is_not_evidence_about_itself(
    tmp_path: Path, generate_stato: ModuleType
) -> None:
    """``STATO.md`` names Fase 12 in its own prose; counting itself would describe the block."""
    milestone(tmp_path, "M1.1")
    write(tmp_path / "docs" / "STATO.md", "la Fase 2 e la Fase 3\n")
    write(tmp_path / "docs" / "adr" / "0001-uno.md", "la Fase 2\n")

    assert generate_stato.future_phases(tmp_path) == [(2, 1)]


# ----------------------------------------------------------------------------------------
# The dated debts
# ----------------------------------------------------------------------------------------


DEBT = """# ADR

## 3. Un debito datato: qualcosa non torna

Trovato lavorando qui.

**Debito a carico di chi passerà di qui**, dichiarato il **2026-09-09**.

## 4. Altro
"""


def test_a_debt_nobody_has_paid_is_open(tmp_path: Path, generate_stato: ModuleType) -> None:
    write(tmp_path / "docs" / "adr" / "0001-uno.md", DEBT)

    (debt,) = generate_stato.dated_debts(tmp_path)

    assert (debt.adr, debt.section, debt.declared) == ("0001", "3", "2026-09-09")
    assert debt.charged == "di chi passerà di qui"
    assert debt.open and debt.paid_by is None


def test_a_debt_another_document_declares_paid_names_who_paid_it(
    tmp_path: Path, generate_stato: ModuleType
) -> None:
    """The payment is read from whoever wrote it down, with the section: a debt that does not know
    it has been paid is the same species of lie as the numbers it describes (ADR 0035 §7)."""
    write(tmp_path / "docs" / "adr" / "0001-uno.md", DEBT)
    write(
        tmp_path / "docs" / "adr" / "0002-due.md",
        "# ADR\n\n## 10. Il debito di ADR 0001 §3, saldato\n\nEcco.\n",
    )

    (debt,) = generate_stato.dated_debts(tmp_path)

    assert not debt.open
    assert debt.paid_by == "ADR 0002 §10"


def test_an_adr_cannot_declare_its_own_debt_paid(
    tmp_path: Path, generate_stato: ModuleType
) -> None:
    """Otherwise the cheapest way to close a debt would be to write that it is closed."""
    write(tmp_path / "docs" / "adr" / "0001-uno.md", DEBT + "\nIl debito di ADR 0001 §3, saldato\n")

    (debt,) = generate_stato.dated_debts(tmp_path)

    assert debt.open


def test_a_debt_that_says_neither_who_pays_nor_when_is_refused(
    tmp_path: Path, generate_stato: ModuleType
) -> None:
    """A dated debt without a date and a payer is a complaint, and the form is the point."""
    write(
        tmp_path / "docs" / "adr" / "0001-uno.md",
        "# ADR\n\n## 3. Un debito datato: qualcosa non torna\n\nTrovato e basta.\n",
    )

    with pytest.raises(ValueError, match="charged to"):
        generate_stato.dated_debts(tmp_path)


def test_the_line_of_the_debt_below_is_not_borrowed_by_the_one_above(
    tmp_path: Path, generate_stato: ModuleType
) -> None:
    """Two debts in one ADR: each carries its own date, or the first inherits the second's."""
    write(
        tmp_path / "docs" / "adr" / "0001-uno.md",
        "# ADR\n\n## 3. Un debito datato: il primo\n\nnulla\n\n"
        "## 4. Un debito datato: il secondo\n\n"
        "**Debito a carico di qualcuno**, dichiarato il **2026-09-09**.\n",
    )

    with pytest.raises(ValueError, match="§3"):
        generate_stato.dated_debts(tmp_path)


# ----------------------------------------------------------------------------------------
# The spec nobody has cited yet
# ----------------------------------------------------------------------------------------


def test_a_section_no_milestone_has_named_is_the_one_reported(
    tmp_path: Path, generate_stato: ModuleType
) -> None:
    write(
        tmp_path / "docs" / "spec" / "ELA_spec.md",
        "# spec\n\n## 1. Prima\n\ntesto\n\n## 2. Seconda\n\ntesto\n",
    )
    milestone(tmp_path, "M1.1", body="questa milestone costruisce §1, e non nomina l'altra")

    assert generate_stato.unnamed_sections(tmp_path) == [(2, "Seconda")]


# ----------------------------------------------------------------------------------------
# The markers, and the real document
# ----------------------------------------------------------------------------------------


def test_a_document_without_the_markers_is_refused(generate_stato: ModuleType) -> None:
    """Rewriting a document that never asked to be generated would be worse than failing."""
    with pytest.raises(ValueError, match="marcatori|markers|missing"):
        generate_stato.replace("# niente marcatori\n", generate_stato.NUMBERS, "corpo")


def test_the_repository_document_is_up_to_date(generate_stato: ModuleType) -> None:
    """``main --check`` is the form ``make check`` would use, exit code and all."""
    assert generate_stato.main(["generate_stato.py", "--check"]) == 0
