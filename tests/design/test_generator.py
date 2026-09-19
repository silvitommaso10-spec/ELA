"""The generator refuses a malformed source, with a sentence (M17.1, criterio 2).

One case for every refusal, each on the real tokens with one thing broken — so the case says
something about the generator and not about a toy file — and the control that the real tokens
pass.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.design.tree import generator, tokens

Tokens = dict[str, Any]


def test_the_real_tokens_are_accepted() -> None:
    generator().validate(tokens())


def dangling_alias(source: Tokens) -> None:
    source["dark"]["color"]["text"]["primary"]["$value"] = "{palette.frost.999}"


def alias_to_a_group(source: Tokens) -> None:
    source["dark"]["color"]["text"]["primary"]["$value"] = "{palette.frost}"


def alias_cycle(source: Tokens) -> None:
    source["space"]["1"]["$value"] = "{space.2}"
    source["space"]["2"]["$value"] = "{space.1}"


def themes_that_differ(source: Tokens) -> None:
    del source["light"]["color"]["signal"]["fault"]


def missing_theme(source: Tokens) -> None:
    del source["light"]


def unknown_type(source: Tokens) -> None:
    source["space"]["1"]["$type"] = "length"


def translucent_palette(source: Tokens) -> None:
    source["palette"]["ink"]["900"]["$value"] = "#0B122080"


def alpha_on_the_palette(source: Tokens) -> None:
    source["palette"]["ink"]["900"]["$alpha"] = 0.5


def alpha_out_of_range(source: Tokens) -> None:
    source["dark"]["color"]["text"]["body"]["$alpha"] = 1.5


def alpha_that_is_not_a_number(source: Tokens) -> None:
    source["dark"]["color"]["text"]["body"]["$alpha"] = "78%"


def alpha_over_alpha(source: Tokens) -> None:
    source["state"]["IDLE"]["text"]["$alpha"] = 0.5


def alpha_on_a_length(source: Tokens) -> None:
    source["space"]["1"]["$alpha"] = 0.5


def keys_that_collide(source: Tokens) -> None:
    source["state"]["WAITING_APPROVAL"] = source["state"]["WAITING APPROVAL"]


def key_that_cannot_travel(source: Tokens) -> None:
    source["state"]['BAD"KEY'] = source["state"]["IDLE"]


def empty_list(source: Tokens) -> None:
    source["attention"] = {"$description": "nothing"}


def state_without_its_glow(source: Tokens) -> None:
    del source["state"]["IDLE"]["glow"]


def light_that_does_not_exist(source: Tokens) -> None:
    source["state"]["IDLE"]["light"]["$value"] = "{color.light.violet}"


def light_without_its_veil(source: Tokens) -> None:
    for theme in ("dark", "light"):
        del source[theme]["color"]["light"]["azure"]["veil"]


def core_that_does_not_exist(source: Tokens) -> None:
    source["state"]["IDLE"]["core"]["$value"] = "{presence.core.kind.molten}"


def core_with_a_motion_that_does_not_exist(source: Tokens) -> None:
    source["presence"]["core"]["kind"]["steady"]["motion"]["$value"] = "{motion.pattern.wobble}"


def ambient_that_does_not_exist(source: Tokens) -> None:
    source["state"]["IDLE"]["ambient"]["$value"] = "{motion.pattern.wobble}"


def pattern_without_its_easing(source: Tokens) -> None:
    del source["motion"]["pattern"]["core-pulse"]["easing"]


def key_coloured_by_a_signal(source: Tokens) -> None:
    source["state"]["ERROR"]["text"]["$value"] = "{color.signal.fault}"


def level_coloured_by_a_signal(source: Tokens) -> None:
    source["risk"]["HIGH"]["text"]["$value"] = "{color.signal.alert}"


def level_without_its_colour(source: Tokens) -> None:
    del source["attention"]["SILENT"]["color"]


def resting_state_that_is_no_state(source: Tokens) -> None:
    source["presence"]["rest"]["$value"] = "ASLEEP"


def pair_that_names_nothing(source: Tokens) -> None:
    source["contrast"]["pairs"].append({"fg": "{color.text.ghost}", "bg": "{color.surface.base}"})


def grid_without_a_band(source: Tokens) -> None:
    del source["grid"]["columns"]["desktop-extended"]


def list_of_font_files(source: Tokens) -> None:
    """The family is the system stack (ADR 0042): the source has no place for a font file."""
    source["typography"]["fonts"] = [{"family": "Inter", "file": "fonts/inter/Inter.woff2"}]


REFUSALS: list[tuple[Callable[[Tokens], None], str]] = [
    (dangling_alias, "names nothing"),
    (alias_to_a_group, "names a group"),
    (alias_cycle, "cycle"),
    (themes_that_differ, "differ in their keys"),
    (missing_theme, "is missing"),
    (unknown_type, "unknown $type"),
    (translucent_palette, "opaque #RRGGBB"),
    (alpha_on_the_palette, "the palette is opaque"),
    (alpha_out_of_range, "between 0 and 1"),
    (alpha_that_is_not_a_number, "between 0 and 1"),
    (alpha_over_alpha, "already has one"),
    (alpha_on_a_length, "$alpha belongs to a colour"),
    (keys_that_collide, "once normalised"),
    (key_that_cannot_travel, "verbatim"),
    (empty_list, "missing or empty"),
    (state_without_its_glow, "lacks ['glow']"),
    (light_that_does_not_exist, "names nothing"),
    (light_without_its_veil, "its light lacks"),
    (core_that_does_not_exist, "names nothing"),
    (core_with_a_motion_that_does_not_exist, "names nothing"),
    (ambient_that_does_not_exist, "names nothing"),
    (pattern_without_its_easing, "its pattern lacks ['easing']"),
    (key_coloured_by_a_signal, "the colour of a key is a text colour"),
    (level_coloured_by_a_signal, "the colour of a key is a text colour"),
    (level_without_its_colour, "lacks one of"),
    (resting_state_that_is_no_state, "is not a state"),
    (pair_that_names_nothing, "names nothing"),
    (grid_without_a_band, "one value per breakpoint"),
    (list_of_font_files, "a group must be an object"),
]


@pytest.mark.parametrize(
    ("breaks", "sentence"), REFUSALS, ids=[case[0].__name__ for case in REFUSALS]
)
def test_a_malformed_source_is_refused(breaks: Callable[[Tokens], None], sentence: str) -> None:
    source = tokens()
    breaks(source)
    with pytest.raises(ValueError, match=re.escape(sentence)):
        generator().validate(source)


def test_a_refused_source_derives_nothing(tmp_path: Path) -> None:
    (tmp_path / "tokens.json").write_text('{"dark": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="is missing"):
        generator().render_all(tmp_path)
    assert [path.name for path in tmp_path.iterdir()] == ["tokens.json"]


# ----------------------------------------------------------------------------------------
# Colours with alpha
# ----------------------------------------------------------------------------------------


def test_a_semantic_colour_with_alpha_becomes_eight_digits_and_the_palette_stays_opaque() -> None:
    module = generator()
    source = tokens()
    assert module.with_alpha("#ffffff", 0.1) == "#FFFFFF1A"
    assert module.with_alpha("#F5F7FA", 1) == "#F5F7FAFF"
    assert module.with_alpha("#F5F7FA", 0) == "#F5F7FA00"
    body = source["dark"]["color"]["text"]["body"]
    assert module.css_value(source, body, "dark") == "#F5F7FAC7"
    assert module.css_value(source, source["dark"]["color"]["text"]["primary"], "dark") == (
        "var(--ela-palette-frost-50)"
    )
    assert module.colour_of(source, "{color.text.body}", "dark") == ("#F5F7FA", 0.78)
    assert module.colour_of(source, "{color.text.primary}", "dark") == ("#F5F7FA", 1.0)
    for _, leaf in module.leaves(source["palette"]):
        assert "$alpha" not in leaf


# ----------------------------------------------------------------------------------------
# Fragments: copies, single keys, includes
# ----------------------------------------------------------------------------------------


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


def test_a_fragment_can_be_rendered_for_one_key() -> None:
    markup = '<b data-ela-each="state" data-ela-state="{key}" id="s{id}">{key}</b>'
    rendered = generator().instances(tokens(), markup, "-x", only="WORKING")
    assert rendered.count("<b ") == 1 and 'data-ela-state="WORKING"' in rendered
    with pytest.raises(ValueError, match="is not a key of state"):
        generator().instances(tokens(), markup, "-x", only="DREAMING")


def test_a_fragment_that_repeats_an_unknown_list_is_refused() -> None:
    with pytest.raises(ValueError, match="names no list"):
        generator().instances(tokens(), '<b data-ela-each="mood">{key}</b>', "-x")


def test_a_partial_is_included_once_and_one_level_deep() -> None:
    """The sphere is seven layers of markup: every component that shows it includes them."""
    module = generator()
    partials = {"_orb": "<i class='orb'></i>\n", "_nested": "{include:_orb}"}
    assert module.with_includes("<b>{include:_orb}</b>", partials) == "<b><i class='orb'></i></b>"
    assert module.with_includes("<b>no include</b>", partials) == "<b>no include</b>"
    with pytest.raises(ValueError, match="names no partial"):
        module.with_includes("{include:_halo}", partials)
    with pytest.raises(ValueError, match="one level only"):
        module.with_includes("{include:_nested}", partials)


def test_a_partial_is_not_a_component_and_a_composition_is_not_one_either(tmp_path: Path) -> None:
    folder = tmp_path / "components" / "compositions"
    folder.mkdir(parents=True)
    (tmp_path / "components" / "_orb.html").write_text("<i></i>", encoding="utf-8")
    (tmp_path / "components" / "state.html").write_text("<b>{include:_orb}</b>", encoding="utf-8")
    (folder / "home.html").write_text("<main>{include:_orb}</main>", encoding="utf-8")
    components, compositions = generator().fragments(tmp_path)
    assert components == {"state": "<b><i></i></b>"}
    assert compositions == {"home": "<main><i></i></main>"}


# ----------------------------------------------------------------------------------------
# What a state is, in the derived rule
# ----------------------------------------------------------------------------------------


def declarations(key: str) -> dict[str, str]:
    source = tokens()
    return dict(generator().state_declarations(source, source["state"][key]))


def test_a_state_is_the_light_of_the_sphere_its_rhythm_and_its_intensity() -> None:
    working, approval, offline = (
        declarations("WORKING"),
        declarations("WAITING APPROVAL"),
        declarations("OFFLINE"),
    )
    assert working["--ela-state-light"] == "var(--ela-color-light-full-c)"
    assert working["--ela-state-light-soft"] == "var(--ela-color-light-full-c2)"
    assert working["--ela-state-spin"] == "var(--ela-motion-duration-spin-working)"
    assert working["--ela-state-play"] == "running"
    assert working["--ela-state-glow"] == "1"
    assert working["--ela-state-text"] == "var(--ela-color-text-key)"

    assert approval["--ela-state-light"] == "var(--ela-color-light-amber-c)"
    assert approval["--ela-state-play"] == "paused"
    assert approval["--ela-state-text"] == "var(--ela-color-text-warn)"

    assert offline["--ela-state-core-opacity"] == "0.25"
    assert offline["--ela-state-core-motion"] == "none"
    assert offline["--ela-state-plasma"] == "var(--ela-presence-plasma-lit-low)"


def test_the_core_and_the_ambient_move_only_where_the_state_says_so() -> None:
    assert declarations("IDLE")["--ela-state-core-motion"] == "ela-orb-breathe"
    assert declarations("LISTENING")["--ela-state-core-motion"] == "ela-orb-pulse"
    assert declarations("ERROR")["--ela-state-core-motion"] == "none"
    signalling = [
        key
        for key in generator().entries(tokens()["state"])
        if declarations(key)["--ela-state-ambient-motion"] != "none"
    ]
    assert signalling == ["ATTENTION REQUIRED"]
    assert declarations("ATTENTION REQUIRED")["--ela-state-ambient-motion-iterations"] == "2"


def test_a_segment_of_the_meter_knows_its_index_because_css_cannot_count() -> None:
    derived = generator().render_tokens_css(tokens())
    longest = max(len(generator().entries(tokens()[group])) for group in generator().LEVELS)
    for index in range(1, longest + 1):
        assert (
            f".ela-meter__segment:nth-child({index}) {{\n  --ela-meter-index: {index};" in derived
        )
    assert f":nth-child({longest + 1})" not in derived


def test_a_key_becomes_a_css_identifier_only_where_css_demands_one() -> None:
    assert generator().css_name(("state", "WAITING APPROVAL", "color")) == (
        "--ela-state-waiting-approval-color"
    )
    assert '[data-ela-state="WAITING APPROVAL"]' in generator().render_tokens_css(tokens())
