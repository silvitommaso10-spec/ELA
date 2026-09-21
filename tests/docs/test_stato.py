"""``docs/STATO.md`` is the restart point, and it cannot say something the repository denies.

Five of its blocks are generated from the repository by ``scripts/generate_stato.py`` and compared
here byte for byte, so a milestone added, a rule written, a capability registered or a debt paid
fails ``make check`` until the document is regenerated. The sixth thing it holds — the decisions
that live in no ADR — is written by hand and says so: no code can derive a choice nobody wrote
down, and the document that claims otherwise would be the first thing to go stale.

What is checked besides "it is up to date" is the two places the script had to duplicate something
in order not to depend on the test suite (the rule count, the declared constraints), and the one
exclusion it makes (§66–§70): an exclusion nobody verifies is a place where a citation could hide.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType

import pytest

from tests.architecture import rules
from tests.docs.test_simplifications import declared_constraints

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = ROOT / "docs" / "STATO.md"
SCRIPT = ROOT / "scripts" / "generate_stato.py"
SPEC = ROOT / "docs" / "spec" / "ELA_spec.md"
MILESTONES = ROOT / "docs" / "milestones"


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_stato", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before it is executed: the script's dataclasses resolve their annotations
    # through ``sys.modules``, and a module loaded by path alone is not in there.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def document() -> str:
    return DOCUMENT.read_text(encoding="utf-8")


# ----------------------------------------------------------------------------------------
# The generated blocks
# ----------------------------------------------------------------------------------------


def test_the_generated_blocks_are_the_ones_the_repository_produces(generator: ModuleType) -> None:
    """Byte for byte. A restart point that can be right by accident is not a restart point."""
    assert generator.generate(document(), ROOT) == document()


def test_the_document_declares_which_blocks_are_generated_and_which_is_not() -> None:
    text = document()
    assert "**Cinque blocchi sono generati**" in text
    assert "**La §5 è scritta a mano**" in text
    assert "scripts/generate_stato.py" in text
    assert len(generator_names()) == 5


def generator_names() -> set[str]:
    return set(re.findall(r"<!-- generato da scripts/generate_stato\.py: (.+?) -->", document()))


def test_every_block_the_script_knows_how_to_write_is_in_the_document(
    generator: ModuleType,
) -> None:
    """A block the script renders and the document does not hold is a number nobody reads."""
    assert generator_names() == set(generator.blocks(ROOT))


# ----------------------------------------------------------------------------------------
# The two numbers the script had to derive without importing the suite
# ----------------------------------------------------------------------------------------


def test_the_rule_count_is_the_one_the_suite_holds(generator: ModuleType) -> None:
    """The script reads ``RULES`` with ``ast`` rather than importing ``tests``; this is the seam.

    Same shape as ``INFRA_LIBRARIES`` in ``scripts/generate_architecture.py``: the script stays
    independent of the suite, and a test that may import both asserts they agree.
    """
    assert generator.rules_count(ROOT) == len(rules.RULES)


def test_the_constraint_count_is_the_one_the_list_of_m94_is_checked_against(
    generator: ModuleType,
) -> None:
    assert generator.constraints_count(ROOT) == len(declared_constraints())


# ----------------------------------------------------------------------------------------
# The one exclusion
# ----------------------------------------------------------------------------------------


def test_the_closing_sections_of_the_spec_really_are_uncited(generator: ModuleType) -> None:
    """§66–§70 are left out as vision rather than features; that they are uncited is not assumed.

    The day a milestone cites one, this fails and somebody decides whether the exclusion still
    holds — instead of the citation disappearing into a constant nobody re-reads.
    """
    cited: set[int] = set()
    for path in sorted(MILESTONES.glob("M*.md")):
        cited |= generator.spec_citations(path.read_text("utf-8"))

    assert generator.CLOSING_SECTIONS & cited == set()
    assert frozenset(range(66, 71)) == generator.CLOSING_SECTIONS


# ----------------------------------------------------------------------------------------
# «Una registrazione non è un inizio» — the criterion §4.1 rests on, read as facts
# ----------------------------------------------------------------------------------------


def phases_out_of_step(named: Iterable[int], started: Iterable[int]) -> set[int]:
    """The phases the changelog and the milestones disagree about.

    A phase gets its name in the changelog when it delivers its first milestone out of
    ``Proposta`` (``phase_names``), and it leaves the block of future phases on the very same
    fact (``future_phases``). Two derived lists, one fact — so the two sets must be equal, and
    a phase in the symmetric difference is a disagreement: named before it delivered, or
    delivered and still nameless.
    """
    return set(named) ^ set(started)


def test_a_phase_has_a_name_exactly_when_one_of_its_milestones_has_left_proposta(
    generator: ModuleType,
) -> None:
    """The criterion §4.1 states in prose, checked where it is a fact instead of a sentence.

    On 2026-09-21 §4.1 said the Fase 13 «è cominciata» ten lines above a generated block that
    still listed it among the future phases. No test saw it, because the contradiction was a
    verb. This does not read the verb — a test that matched words would be bypassed by the next
    rewrite — it closes the world on the fact the verb is about.
    """
    started = {m.phase for m in generator.milestones(ROOT) if m.state != generator.PROPOSED}

    assert started  # a criterion with nothing on either side would make this vacuous
    assert phases_out_of_step(generator.phase_names(ROOT), started) == set()


def test_a_phase_named_before_it_delivered_is_detected() -> None:
    """The negative case, both ways round: named and undelivered, delivered and nameless."""
    assert phases_out_of_step({13: "L'azione"}, {12, 13}) == {12}
    assert phases_out_of_step({12: "I nodi sulla rete"}, {12, 13}) == {13}
    assert phases_out_of_step({12: "I nodi sulla rete"}, {12}) == set()


def test_the_fase_13_has_not_started_and_41_says_so(generator: ModuleType) -> None:
    """The pin, in the shape of ADR 0035 §7: it fires on the day the prose goes stale.

    §4.1 says three things that all rest on one fact — the Fase 13 is registered and not begun,
    the Fase 12 keeps the first entry until the 13 begins, and the 13 stays among the future
    phases. The day M13.1 leaves ``Proposta`` all three become false together, and the message
    below is what somebody reads instead of discovering it at the next merge.
    """
    started = {m.phase for m in generator.milestones(ROOT) if m.state != generator.PROPOSED}

    assert 13 not in started, (
        "M13.1 è uscita da Proposta: la Fase 13 è cominciata. Allora §4.1 di docs/STATO.md non la "
        "chiama più «registrata», la voce della Fase 12 esce da §4.1, e il changelog le dà un nome."
    )
    assert 13 in dict(generator.future_phases(ROOT))
    assert 13 not in generator.phase_names(ROOT)


# ----------------------------------------------------------------------------------------
# The part no code can derive
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "decision",
    [
        "Niente app iPhone nativa",
        "La rete è Tailscale",
        "La voce è ElevenLabs, con `eleven_flash_v2_5`",
        "La ritenzione di ElevenLabs è accettata",
        "Lo sviluppo è in locale, sul Mac",
        "La wake word è rimandata a M15.1",
        "Chi paga il lavoro agentico",
        "Come si paga una sessione",
        "Il tetto di spesa",
        "Il design è una fase, non una rifinitura",
        "Il permesso prima dell'azione: l'ordine della Fase 13",
    ],
)
def test_every_decision_that_lives_in_no_adr_is_written_here(decision: str) -> None:
    """These are the reason the document exists: a decision that lives only in a conversation is
    a decision the next session will re-take differently."""
    assert decision in document()


def test_the_decisions_carry_their_reason_and_not_only_themselves() -> None:
    """Decision without a reason is an instruction, and an instruction is what gets overruled."""
    section = document().split("## 5. Le decisioni")[1].split("## 6.")[0]

    assert section.count("*Perché") >= 3
    assert section.count("*Che cosa ne discende") >= 3
