"""ADR 0039 and the tree say the same thing (M12.3).

The ADR that a milestone writes is the one that carries its numbers, and this one carries four that
nothing else pins: the rule that was added, the two that were widened, the route that was added, and
the species of command that was invented. It also inherits **the pin on today's totals** from
``test_adr_work.py``, the way that one inherited it from ADR 0037 — the ADR that changes a total is
the ADR that pins it, because the previous one is immutable and keeps saying what it saw.
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.api.security import NODE_ROUTES
from ela.composition import build_node
from ela.node import Node
from tests.architecture.rules import (
    COMPOSED_NAMES,
    INFRA_PACKAGES,
    NODE_RUNNER_MODULE,
    NODE_TOOL_RECEIVERS,
    RULES,
)
from tests.docs.test_adr_cli import RESIDENT, commands_of_species
from tests.docs.test_adr_placement import _rules_up_to

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0039-node-macos.md"
PACKAGE = Path(__file__).resolve().parents[2] / "src" / "ela" / "node"
RULE_ROW = re.compile(r"^\| (\d+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$")


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def conseguenze() -> str:
    return adr_text().split("## Conseguenze", 1)[1]


def documented_rule_numbers() -> set[int]:
    return {
        int(match.group(1))
        for line in adr_text().splitlines()
        if (match := RULE_ROW.match(line)) is not None
    }


# ----------------------------------------------------------------------------------------
# §1 — where the code of a node lives
# ----------------------------------------------------------------------------------------


def test_the_code_of_a_node_lives_inside_the_package_the_tools_measure() -> None:
    """The whole argument of §1 is that the node is *inside* what verifies ELA.

    Cheap to assert and worth asserting: the day somebody moves it to ``nodes/macos/`` for the
    tidiness of the spec's drawing, everything that checks ELA goes quiet about it at once and no
    other test would notice — which is precisely the failure the ADR is about.
    """
    assert PACKAGE.is_dir()
    assert sorted(path.name for path in PACKAGE.glob("*.py")) == [
        "__init__.py",
        "client.py",
        "errors.py",
        "runner.py",
        "state.py",
    ]


def test_the_placeholder_folder_says_where_its_content_went() -> None:
    """``nodes/`` stays (§1), and a folder of the spec that does not say where its content went is
    a map that lies."""
    for readme in (Path("nodes") / "README.md", Path("nodes") / "macos" / "README.md"):
        text = (Path(__file__).resolve().parents[2] / readme).read_text(encoding="utf-8")
        assert "src/ela/node" in text, readme


# ----------------------------------------------------------------------------------------
# §2 — the route a node that restarted reads itself with
# ----------------------------------------------------------------------------------------


def test_the_route_it_adds_is_one_a_node_may_call() -> None:
    """Classified by name, never exempted by silence (ADR 0037 §4): without the line in
    ``NODE_ROUTES`` a node would read ``401`` there and could never announce again."""
    assert ("GET", "/nodes/me") in NODE_ROUTES
    assert len(NODE_ROUTES) == 6


def test_a_node_reads_its_revision_and_never_counts_one() -> None:
    """§2: a node is *told* its revision. The setter is the only writer, and it is named."""
    assert hasattr(Node, "saw")
    assert "told" in (Node.saw.__doc__ or "")


# ----------------------------------------------------------------------------------------
# §3, §5, §8 — the rules: one new, two widened, one tightened
# ----------------------------------------------------------------------------------------


def test_the_rules_the_adr_names_are_the_rules_that_exist() -> None:
    """Four rows, and each names a rule that is registered and declares that number."""
    numbers = documented_rule_numbers()

    assert numbers == {3, 16, 28, 53}
    declared = {
        int(found.group(1))
        for check in RULES.values()
        if (found := re.search(r"Rule (\d+)", check.__doc__ or "")) is not None
    }
    assert numbers <= declared


def test_the_new_rule_is_the_fifty_third_and_it_is_about_the_time() -> None:
    assert "a-node-mints-no-deadline" in RULES
    assert len(_rules_up_to(53)) == 53


def test_rule_16_is_widened_by_path_and_by_receiver_and_not_by_package() -> None:
    """§3: one module of the node, and in it one receiver. A package-wide exemption would have
    made every module of ``ela.node`` a place a tool may run, which is the thing the rule is."""
    assert Path("node") / "runner.py" == NODE_RUNNER_MODULE
    assert frozenset({"tool"}) == NODE_TOOL_RECEIVERS


def test_rule_28_learned_the_second_way_to_compose_a_world() -> None:
    """§8: a fence with a new gate in it is not a fence."""
    assert {"build", "Ela", "build_node", "NodeWorld"} <= COMPOSED_NAMES


# ----------------------------------------------------------------------------------------
# §4 — the third species of command
# ----------------------------------------------------------------------------------------


def test_the_third_species_is_declared_and_has_exactly_one_member() -> None:
    assert commands_of_species(RESIDENT) == {"node run"}
    assert "residente" in adr_text()


# ----------------------------------------------------------------------------------------
# §6 — what a node is built out of
# ----------------------------------------------------------------------------------------


def test_build_node_declares_both_of_its_seams() -> None:
    """The clock and the voice, both named parameters (dec. G, dec. H).

    A monkeypatch would be invisible to this text and to every architecture rule — and the voice
    one is not a convenience: without it the conformance suite would speak out loud on this Mac.
    """
    import inspect

    parameters = inspect.signature(build_node).parameters

    assert parameters["clock"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["speech"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["clock"].default is None
    assert parameters["speech"].default is None


# ----------------------------------------------------------------------------------------
# The pin on today's totals, inherited from the ADR that held it before
# ----------------------------------------------------------------------------------------


def test_the_conseguenze_count_what_this_adr_changed() -> None:
    """The totals this ADR moved, and it is the one that pins them until another moves them."""
    text = conseguenze()

    assert "**cinquantatré**" in text
    assert len(RULES) == 53
    assert "**ventinove**" in text
    assert "**sei**" in text
    assert "**ventisei**" in text
    assert "**tre**" in text
    assert set(INFRA_PACKAGES) == {"providers", "infrastructure", "api", "cli", "node"}
