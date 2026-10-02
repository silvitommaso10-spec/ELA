"""ADR 0056 and the running code describe the same rule and the same catalogue (M9.6).

The test the ADR names exists, with the name the ADR gives it, and reads the networks the ADR says
from where the ADR says; the setting the ADR names is the one the Core reads, in a section the node
does not; the field and the sentence of an empty catalogue are the API's and the CLI's; and every
test the ADR cites is there.
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.api.schemas import VoiceStatusOut
from ela.cli.voice import EMPTY_CATALOGUE
from ela.composition.settings import (
    CANDIDATES_VARIABLE,
    AuditionSettings,
    NodeConfig,
    Settings,
)

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0056-the-author-is-not-in-the-product.md"
RULE_MODULE = "tests/architecture/test_the_author_is_not_in_the_product.py"
RULE = "test_no_tailnet_host_and_no_path_inside_a_home_in_src_and_apps"
CITED = re.compile(r"`(test_\w+)`")
CITED_PATH = re.compile(r"`(tests/[\w/]+\.py)`")


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def section(number: int) -> str:
    text = adr_text()
    start = text.index(f"\n### {number}. ")
    end = text.find("\n### ", start + 1)
    return text[start : text.index("\n## ", start) if end == -1 else end]


def test_the_rule_test_is_the_one_the_adr_names_and_reads_tailnet_ranges() -> None:
    text = section(1)
    module = (ROOT / RULE_MODULE).read_text(encoding="utf-8")

    assert f"**`{RULE_MODULE}`**" in text and f"**`{RULE}`**" in text
    assert re.search(rf"^def {RULE}\(", module, re.MULTILINE)
    assert "`TAILNET_RANGES`" in text
    assert "from ela.composition.settings import TAILNET_RANGES" in module


def test_claude_md_names_the_test_and_the_networks() -> None:
    """Decision 10 of the review: the line of ``CLAUDE.md`` changed with the test, and says so."""
    text = " ".join((ROOT / "CLAUDE.md").read_text(encoding="utf-8").split())

    assert f"`{RULE_MODULE}`" in text
    assert "`TAILNET_RANGES`" in text
    assert "`100.64.0.0/10`" not in text, "the line of before, which named one network of two"


def test_the_setting_is_the_core_s_and_not_the_node_s() -> None:
    text = section(3)
    node_fields = {
        name
        for section_name in NodeConfig.model_fields
        for name in NodeConfig.model_fields[section_name].annotation.model_fields  # type: ignore[union-attr]
    }

    assert f"**`{CANDIDATES_VARIABLE}`**" in text
    assert "ELA_" + "elevenlabs_candidates".upper() == CANDIDATES_VARIABLE
    assert "elevenlabs_candidates" in AuditionSettings.model_fields
    assert Settings.model_fields["audition"].annotation is AuditionSettings
    assert "elevenlabs_candidates" not in node_fields
    assert "**`AuditionSettings`**" in text


def test_the_empty_value_is_read_before_the_json_parser_as_the_adr_says() -> None:
    assert "(`env_ignore_empty`)" in section(3)
    assert AuditionSettings.model_config.get("env_ignore_empty") is True


def test_the_field_and_the_sentence_of_an_empty_catalogue_are_the_api_s_and_the_cli_s() -> None:
    text = " ".join(section(3).split())

    assert "**`empty_catalogue_setting`**" in text
    assert "empty_catalogue_setting" in VoiceStatusOut.model_fields
    assert EMPTY_CATALOGUE.format(setting=CANDIDATES_VARIABLE) in text


def test_every_test_the_adr_cites_exists() -> None:
    sources = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "tests").rglob("*.py"))
    cited = CITED.findall(adr_text())
    paths = CITED_PATH.findall(adr_text())

    assert cited and paths
    for name in cited:
        assert re.search(rf"^(?:async )?def {name}\(", sources, re.MULTILINE), name
    for path in paths:
        assert (ROOT / path).is_file(), path
