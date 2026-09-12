"""What a driver cannot recite is declared, pinned, and visible (M12.2, dec. P; ADR 0031 §6).

A conformance suite dies the day a story stops running without anybody noticing. Three ways that
happens, and one guard each:

* a driver **skips** a story with an ``if`` inside the test — so the map is the only way to skip,
  and :func:`~tests.conformance.driver.needs` turns it into a ``skip`` that reaches the summary;
* the map **grows** quietly — so it is pinned here, per driver, and a new entry fails this file
  until somebody writes down the reason;
* a story **disappears** — so :data:`~tests.conformance.driver.STORIES` is held to the tests that
  play it, and a key nobody recites fails even if every test passes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conformance.driver import STORIES, NodeKit, needs
from tests.conformance.fake_node import FAKE
from tests.conformance.macos_node import MACOS
from tests.conformance.test_node_contract import KITS

CONTRACT = Path(__file__).with_name("test_node_contract.py")
"""The stories, read as text: what plays a story is the file that plays it, not a list kept here.

:data:`~tests.conformance.test_node_contract.KITS` is imported from there for the same reason — two
lists of drivers would be two places to forget one."""

PINNED: dict[str, frozenset[str]] = {FAKE.name: frozenset(), MACOS.name: frozenset()}
"""Driver → the stories it has declared it cannot recite, as they stand today.

Empty for both, and the second empty set is what M12.3 was for: a **real** node, a process with a
secret on disk and a connection that can drop, recites the protocol whole. macOS can be two
processes, can die and come back, can keep a file — it has nothing to declare. An entry like "a
Shortcut is not two processes" says something about **that platform**, which is the only thing a
declaration may ever say.
"""


def test_every_kit_is_pinned() -> None:
    assert {kit.name for kit in KITS} == set(PINNED)


@pytest.mark.parametrize("kit", KITS, ids=lambda kit: kit.name)
def test_what_a_driver_cannot_recite_is_what_it_declared(kit: NodeKit) -> None:
    """The map cannot grow in silence: a story declared unrecitable without this line changing
    fails, which is the point of pinning a set nobody derives."""
    assert frozenset(kit.unsupported) == PINNED[kit.name]


@pytest.mark.parametrize("kit", KITS, ids=lambda kit: kit.name)
def test_a_declaration_is_about_a_story_that_exists(kit: NodeKit) -> None:
    """A key outside the contract would be a driver excusing itself from nothing."""
    assert set(kit.unsupported) <= set(STORIES)


@pytest.mark.parametrize("kit", KITS, ids=lambda kit: kit.name)
def test_a_reason_is_a_sentence_and_not_a_shrug(kit: NodeKit) -> None:
    """Whoever reads the skip has to learn something from it: ``"platform"`` is not a reason."""
    for story, reason in kit.unsupported.items():
        assert len(reason.split()) >= 4, (story, reason)


def test_every_story_of_the_contract_is_played_by_a_test() -> None:
    """The other direction: a story nobody recites is a hole, and a passing suite would hide it.

    Derived from the source of ``test_node_contract.py``, because a list of names kept by hand is
    exactly what the thirteen stories must not depend on.
    """
    source = CONTRACT.read_text(encoding="utf-8")

    missing = [story for story in STORIES if f'needs(kit, "{story}")' not in source]

    assert missing == []
    assert len(STORIES) == 13  # dec. P: thirteen, and a fourteenth arrives with its own decision


def test_the_skip_of_an_unrecitable_story_says_which_driver_and_why() -> None:
    """:func:`needs` is the one door, and it leaves a trace: a skip with the driver, the story and
    the reason in it. Without this, a driver could declare a story and the summary would say only
    that something was skipped."""

    class _Shortcut:
        name = "a-shortcut"
        unsupported = {"comes_back_twice_over": "a Shortcut is not two processes"}

        async def node(self, world: object, **kwargs: object) -> object:  # pragma: no cover
            raise AssertionError("never built: the story is skipped before it asks for a node")

    with pytest.raises(pytest.skip.Exception) as skipped:
        needs(_Shortcut(), "comes_back_twice_over")  # type: ignore[arg-type]

    assert "a-shortcut" in str(skipped.value)
    assert "comes_back_twice_over" in str(skipped.value)
    assert "not two processes" in str(skipped.value)


def test_a_story_outside_the_contract_is_refused_before_it_can_be_skipped() -> None:
    """A typo in a key must not read as "nothing to skip": it fails loudly instead."""
    with pytest.raises(AssertionError, match="is not a story of the contract"):
        needs(FAKE, "comes_back_on_tuesday")
