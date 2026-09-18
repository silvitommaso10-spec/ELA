"""The generator refuses a malformed source, with a sentence (M17.1, criterio 2).

One case for every refusal of dec. C, each on the real tokens with one thing broken — so the
case says something about the generator and not about a toy file — and the control that the
real tokens pass.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.design.tree import DESIGN_SYSTEM, generator, tokens

Tokens = dict[str, Any]


def test_the_real_tokens_are_accepted() -> None:
    generator().validate(tokens(), DESIGN_SYSTEM)


def dangling_alias(source: Tokens) -> None:
    source["dark"]["color"]["text"]["primary"]["$value"] = "{palette.ivory.999}"


def alias_to_a_group(source: Tokens) -> None:
    source["dark"]["color"]["text"]["primary"]["$value"] = "{palette.ivory}"


def alias_cycle(source: Tokens) -> None:
    source["space"]["1"]["$value"] = "{space.2}"
    source["space"]["2"]["$value"] = "{space.1}"


def themes_that_differ(source: Tokens) -> None:
    del source["light"]["color"]["signal"]["change"]


def missing_theme(source: Tokens) -> None:
    del source["light"]


def unknown_type(source: Tokens) -> None:
    source["space"]["1"]["$type"] = "length"


def translucent_palette(source: Tokens) -> None:
    source["palette"]["ink"]["900"]["$value"] = "#14171C80"


def keys_that_collide(source: Tokens) -> None:
    source["state"]["WAITING_APPROVAL"] = source["state"]["WAITING APPROVAL"]


def key_that_cannot_travel(source: Tokens) -> None:
    source["state"]['BAD"KEY'] = source["state"]["IDLE"]


def empty_list(source: Tokens) -> None:
    source["attention"] = {"$description": "nothing"}


def shape_that_does_not_exist(source: Tokens) -> None:
    source["state"]["IDLE"]["shape"]["$value"] = "{shape.star}"


def shape_without_a_parameter(source: Tokens) -> None:
    del source["shape"]["dot"]["scale-y"]


def motion_that_does_not_exist(source: Tokens) -> None:
    source["state"]["IDLE"]["motion"]["$value"] = "{motion.pattern.wobble}"


def pair_that_names_nothing(source: Tokens) -> None:
    source["contrast"]["pairs"].append({"fg": "{color.text.ghost}", "bg": "{color.surface.base}"})


def grid_without_a_band(source: Tokens) -> None:
    del source["grid"]["columns"]["desktop-extended"]


def font_whose_file_is_missing(source: Tokens) -> None:
    source["typography"]["fonts"] = [
        {
            "family": "Nowhere",
            "file": "fonts/nowhere/Nowhere.woff2",
            "weight": "400",
            "style": "normal",
        }
    ]


REFUSALS: list[tuple[Callable[[Tokens], None], str]] = [
    (dangling_alias, "names nothing"),
    (alias_to_a_group, "names a group"),
    (alias_cycle, "cycle"),
    (themes_that_differ, "differ in their keys"),
    (missing_theme, "is missing"),
    (unknown_type, "unknown $type"),
    (translucent_palette, "opaque"),
    (keys_that_collide, "once normalised"),
    (key_that_cannot_travel, "verbatim"),
    (empty_list, "missing or empty"),
    (shape_that_does_not_exist, "names nothing"),
    (shape_without_a_parameter, "lacks"),
    (motion_that_does_not_exist, "names nothing"),
    (pair_that_names_nothing, "names nothing"),
    (grid_without_a_band, "one value per breakpoint"),
    (font_whose_file_is_missing, "is not there"),
]


@pytest.mark.parametrize(
    ("breaks", "sentence"), REFUSALS, ids=[case[0].__name__ for case in REFUSALS]
)
def test_a_malformed_source_is_refused(breaks: Callable[[Tokens], None], sentence: str) -> None:
    source = tokens()
    breaks(source)
    with pytest.raises(ValueError, match=re.escape(sentence)):
        generator().validate(source, DESIGN_SYSTEM)


def test_a_refused_source_derives_nothing(tmp_path: Path) -> None:
    (tmp_path / "tokens.json").write_text('{"dark": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="is missing"):
        generator().render_all(tmp_path)
    assert [path.name for path in tmp_path.iterdir()] == ["tokens.json"]


def test_every_copy_of_a_fragment_has_ids_of_its_own() -> None:
    """``{id}`` exists for this: the same field rendered twice, and a label per field."""
    markup = '<label for="a{id}">A</label><input id="a{id}">'
    first = generator().instances(tokens(), markup, "-field-dark")
    second = generator().instances(tokens(), markup, "-field-light")
    assert 'id="a-field-dark"' in first and 'for="a-field-dark"' in first
    assert 'id="a-field-light"' in second


def test_a_repeated_fragment_is_rendered_once_per_key_in_order() -> None:
    markup = '<b data-ela-each="risk" data-ela-risk="{key}" id="r{id}">{key}</b>'
    rendered = generator().instances(tokens(), markup, "-x")
    keys = list(generator().entries(tokens()["risk"]))
    assert [f'data-ela-risk="{key}"' in rendered for key in keys] == [True] * len(keys)
    assert rendered.index(keys[0]) < rendered.index(keys[-1])
    assert "data-ela-each" not in rendered
    assert rendered.count('id="r-x-') == len(keys)


def test_a_fragment_that_repeats_an_unknown_list_is_refused() -> None:
    with pytest.raises(ValueError, match="names no list"):
        generator().instances(tokens(), '<b data-ela-each="mood">{key}</b>', "-x")


def test_a_key_becomes_a_css_identifier_only_where_css_demands_one() -> None:
    assert generator().css_name(("state", "WAITING APPROVAL", "color")) == (
        "--ela-state-waiting-approval-color"
    )
    assert '[data-ela-state="WAITING APPROVAL"]' in generator().render_tokens_css(tokens())
