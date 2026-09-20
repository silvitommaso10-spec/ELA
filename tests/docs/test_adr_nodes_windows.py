"""ADR 0040 and the tree say the same thing (M12.4).

The ADR a milestone writes carries its numbers, and this one carries the ones nothing else pins: the
rule that was added and the one that was tightened, the version below which a Windows node refuses
to start, the three systems a composition names and what each of them gets, the three kits. It
also inherits **the pin on today's totals** from ``test_adr_nodes_macos.py`` — the ADR that changes
a total is the ADR that pins it, because the previous one is immutable and keeps saying what it saw.
"""

from __future__ import annotations

import inspect
import re
import tomllib
from pathlib import Path

from ela.api.security import COMPANION_CODE_ROUTES, COMPANION_ROUTES, NODE_ROUTES
from ela.composition import build_node
from ela.composition.node import ACL_SINCE, PermissionMode, online_player
from ela.infrastructure.machine import AFPLAY, OnlineSpeechCommand
from ela.infrastructure.machine.windows import POWERSHELL, SPEAK
from ela.permissions import production_catalogue
from ela.ports import WireCode
from tests.architecture.rules import (
    INFRA_PACKAGES,
    MACHINE_ADAPTER_DIR,
    RULES,
    SYSTEM_SPEECH_OUTPUTS,
    VOICE_MODULES,
)
from tests.conformance.test_node_contract import KITS
from tests.conformance.test_unsupported import PINNED
from tests.docs.test_adr_cli import SPECIES, coded_commands, documented_species
from tests.docs.test_adr_composition import coded_routes
from tests.docs.test_adr_listening import ports_before
from tests.docs.test_adr_placement import _rules_up_to

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0040-node-windows.md"
PYPROJECT = ROOT / "pyproject.toml"
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
# §1 — the composition chooses, naming the system
# ----------------------------------------------------------------------------------------


def test_the_player_of_the_online_voice_is_chosen_in_one_place() -> None:
    """``afplay`` on Darwin and nobody elsewhere, asked by ``build_node`` and by the kit alike."""
    assert online_player("Darwin") == AFPLAY
    assert online_player("Windows") is None
    assert online_player("Linux") is None
    assert "online_player" in adr_text()


def test_build_node_declares_the_six_parameters_the_adr_counts() -> None:
    """«**sei** parametri dichiarati»: the clock, the two voices, the system, the power, and the
    version of Python."""
    parameters = inspect.signature(build_node).parameters
    declared = {
        name
        for name, parameter in parameters.items()
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY
    }

    assert declared == {"clock", "speech", "speech_online", "system", "power", "python_version"}
    assert all(parameters[name].default is None for name in declared)


# ----------------------------------------------------------------------------------------
# §2 — the secret
# ----------------------------------------------------------------------------------------


def test_the_version_below_which_a_windows_node_refuses_is_the_one_the_adr_names() -> None:
    assert ACL_SINCE == (3, 12, 4)
    assert "**3.12.4**" in adr_text()


def test_the_two_ways_of_protecting_the_secret_are_the_two_the_adr_names() -> None:
    assert {mode.name for mode in PermissionMode} == {"BITS", "ACL"}
    assert "`PermissionMode.BITS`" in adr_text()
    assert "`PermissionMode.ACL`" in adr_text()


# ----------------------------------------------------------------------------------------
# §3, §4 — the voice of a PC, and nobody to play the online one
# ----------------------------------------------------------------------------------------


def test_the_voice_of_a_pc_runs_the_literal_binary_the_adr_quotes() -> None:
    assert POWERSHELL == r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    assert POWERSHELL in adr_text()


def test_the_script_sends_its_sentence_nowhere_but_the_speaker() -> None:
    """Rule 40 would say so; this says it of the constant the ADR describes."""
    assert not any(method in SPEAK for method in SYSTEM_SPEECH_OUTPUTS)
    assert "SetOutputToDefaultAudioDevice" in SPEAK


def test_nobody_is_a_value_the_online_voice_accepts() -> None:
    """``binary=None``: a value, not an omission — the default stays ``afplay``."""
    binary = inspect.signature(OnlineSpeechCommand).parameters["binary"]

    assert binary.default == AFPLAY
    assert "`binary=None`" in adr_text()


# ----------------------------------------------------------------------------------------
# §5 — where it is proved
# ----------------------------------------------------------------------------------------


def test_the_contract_is_recited_by_the_three_kits_and_none_declares_a_story_away() -> None:
    assert {kit.name for kit in KITS} == {"fake-node", "macos-node", "windows-node"}
    assert all(unsupported == frozenset() for unsupported in PINNED.values())
    assert "**tre** kit" in conseguenze()


def test_the_placeholder_folders_say_where_their_content_went() -> None:
    """``nodes/windows/`` joins the two of ADR 0039 §1: a folder of the spec that does not say where
    its content went is a map that lies."""
    for readme in (
        Path("nodes") / "README.md",
        Path("nodes") / "macos" / "README.md",
        Path("nodes") / "windows" / "README.md",
    ):
        assert "src/ela/node" in (ROOT / readme).read_text(encoding="utf-8"), readme


# ----------------------------------------------------------------------------------------
# §6 — the rules: one new, one tightened
# ----------------------------------------------------------------------------------------


def test_the_rules_the_adr_names_are_the_rules_that_exist() -> None:
    """Two rows, and each names a rule that is registered and declares that number."""
    numbers = documented_rule_numbers()

    assert numbers == {40, 54}
    declared = {
        int(found.group(1))
        for check in RULES.values()
        if (found := re.search(r"Rule (\d+)", check.__doc__ or "")) is not None
    }
    assert numbers <= declared


def test_the_new_rule_is_the_fifty_fourth_and_it_is_about_the_machine() -> None:
    assert "a-node-does-not-ask-which-machine-it-is" in RULES
    assert len(_rules_up_to(54)) == 54


def test_rule_40_reads_the_windows_module_and_the_three_methods() -> None:
    assert MACHINE_ADAPTER_DIR / "windows.py" in VOICE_MODULES
    assert (
        frozenset({"SetOutputToWaveFile", "SetOutputToWaveStream", "SetOutputToAudioStream"})
        == SYSTEM_SPEECH_OUTPUTS
    )


# ----------------------------------------------------------------------------------------
# §7 — the vocabulary of the wire
# ----------------------------------------------------------------------------------------


def test_the_vocabulary_of_the_wire_is_the_closed_list_the_adr_counts() -> None:
    """«diciassette membri», in ``ela.ports`` — the one place both ends may import."""
    assert len(WireCode) == 17
    assert WireCode.__module__ == "ela.ports"
    assert "`ela.ports.WireCode`" in adr_text()
    assert "diciassette membri" in adr_text()


# ----------------------------------------------------------------------------------------
# The state, and the proof by hand it waited for
# ----------------------------------------------------------------------------------------


def test_the_adr_was_accepted_only_after_the_proof_by_hand(shown: str = "2026-09-18") -> None:
    """It stayed «Proposta» until the end criterion of M12.4 was met — the proof on the PC — and was
    accepted in the same commit that gave ``GETTING_STARTED.md`` §12 the real outputs (decisions of
    2026-09-17 and 2026-09-18). The guide is read here because the two moved together: an ADR
    accepted over a guide still written in the future tense would be the thing that was refused."""
    guide = (ROOT / "docs" / "GETTING_STARTED.md").read_text(encoding="utf-8")

    assert f"- **Stato:** Accettata il **{shown}**" in adr_text()
    assert "scritta prima della prova" not in guide
    assert "Gli output qui sotto sono quelli della prova a mano del **2026-09-17**" in guide


# ----------------------------------------------------------------------------------------
# The pin on today's totals, inherited from the ADR that held it before
# ----------------------------------------------------------------------------------------


def test_the_conseguenze_count_what_the_tree_has_today() -> None:
    """Taken over from ADR 0039 by the ADR that moved the rules; the rest did not move, and is
    pinned here because this was the newest ADR that states them.

    **Rules up to 54 and not ``len(RULES)``** since M12.5 wrote rule 55, and the routes **without
    the companion's** since ADR 0043 §5 added six: an ADR is immutable, so this one keeps saying
    the totals it saw, the way ADR 0039 does for fifty-three (``test_adr_nodes_macos.py``). The
    pin on *today's* totals moves to the ADR that changes them.
    """
    text = conseguenze()

    assert "**cinquantaquattro**" in text
    assert len(_rules_up_to(54)) == 54
    assert "**restano ventinove**" in text
    assert len(coded_routes() - COMPANION_ROUTES - COMPANION_CODE_ROUTES) == 29
    assert "quelle che un nodo può chiamare **sei**" in text
    assert len(NODE_ROUTES) == 6
    assert "**ventisei**" in text
    assert len(coded_commands()) == 26
    assert "le specie di comando **tre**" in text
    assert set(documented_species().values()) == SPECIES
    assert len(SPECIES) == 3
    assert "restano **quattordici**" in text
    assert (
        len(
            tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["importlinter"][
                "contracts"
            ]
        )
        == 14
    )
    assert "**restano otto**" in text
    assert len(production_catalogue().specs()) == 8
    assert "**venticinque**" in text
    assert len(ports_before(ADR_PATH.with_name("0043-companion.md"))) == 25
    assert set(INFRA_PACKAGES) == {"providers", "infrastructure", "api", "cli", "node"}
