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
SECTION_MENTION = re.compile(r"§\s?(\d+)")


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
        cited |= {int(number) for number in SECTION_MENTION.findall(path.read_text("utf-8"))}

    assert generator.CLOSING_SECTIONS & cited == set()
    assert frozenset(range(66, 71)) == generator.CLOSING_SECTIONS


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
