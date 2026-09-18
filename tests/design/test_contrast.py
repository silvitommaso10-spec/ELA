"""WCAG 2.1 AA, in both themes, for every declared pair (M17.1, criterio 12; dec. 5, dec. G).

The threshold of a pair is **not declared**: it derives from the group of its foreground. A
text colour wants 4.5 (WCAG 1.4.3); anything else — a role of state, of risk, of attention, the
border of a field, the focus ring — wants 3 (WCAG 1.4.11). A kind declared by the pair would be
the lever this file exists to remove, and so would thresholds kept in ``tokens.json``: a rule
that a JSON edit can lower is not a rule. ``test_tokens_only.py`` closes the other half — the
``color`` property takes only text tokens.

The limit, declared in ADR 0042: a colour inherited from one rule over a background set by
another is not seen by a static check.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.design import stylesheet
from tests.design.tree import generator, handwritten_stylesheets, token_paths, tokens

TEXT = 4.5
NON_TEXT = 3.0
THEMES = ("dark", "light")

EXEMPT = {
    "color.text.disabled": "WCAG 1.4.3 excludes the text of an inactive user interface component",
    "color.text.on-action": "drawn on the primary action only: paired with every shade of it below",
    "color.text.on-danger": "drawn on the danger action only: paired with every shade of it below",
    "color.border.subtle": "a hairline that decorates: nothing is identified by it (WCAG 1.4.11)",
}
"""Foregrounds that are not paired with every surface, each with its reason."""

Tokens = dict[str, Any]


def luminance(colour: str) -> float:
    """Relative luminance of an opaque ``#RRGGBB``, as WCAG 2.1 defines it."""
    channels = [int(colour[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def ratio(one: str, other: str) -> float:
    lighter, darker = sorted((luminance(one), luminance(other)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def path_of(alias: str) -> str:
    return alias.strip("{}")


def threshold(foreground: str) -> float:
    return TEXT if path_of(foreground).startswith("color.text.") else NON_TEXT


def failing(source: Tokens) -> list[str]:
    found = []
    for pair in source["contrast"]["pairs"]:
        for theme in THEMES:
            fg = str(generator().resolve(source, pair["fg"], theme))
            bg = str(generator().resolve(source, pair["bg"], theme))
            if (measured := ratio(fg, bg)) < threshold(pair["fg"]):
                found.append(
                    f"{theme}: {path_of(pair['fg'])} on {path_of(pair['bg'])} is "
                    f"{measured:.2f}, under {threshold(pair['fg'])}"
                )
    return found


def colours(source: Tokens, group: str) -> list[str]:
    module = generator()
    return [
        ".".join(path)
        for path, _ in module.leaves(source[THEMES[0]]["color"][group], ("color", group))
    ]


def declared(source: Tokens) -> set[tuple[str, str]]:
    return {(path_of(pair["fg"]), path_of(pair["bg"])) for pair in source["contrast"]["pairs"]}


def undeclared(source: Tokens) -> list[str]:
    """Every foreground against every surface, and every action under something."""
    pairs = declared(source)
    surfaces = colours(source, "surface")
    foregrounds = colours(source, "text") + colours(source, "signal") + colours(source, "focus")
    foregrounds += colours(source, "border")
    found = [
        f"{fg} on {bg}"
        for fg in foregrounds
        if fg not in EXEMPT
        for bg in surfaces
        if (fg, bg) not in pairs
    ]
    backgrounds = {bg for _, bg in pairs}
    found += [f"nothing on {bg}" for bg in colours(source, "action") if bg not in backgrounds]
    return found


def rule_pairs_not_declared(text: str, pairs: set[tuple[str, str]]) -> list[str]:
    """A hand-written rule that sets both the colour of text and its background, from tokens."""
    names = token_paths()
    found = []
    for rule in stylesheet.parse(text):
        colour = rule.value("color")
        background = rule.value("background") or rule.value("background-color")
        if colour is None or background is None:
            continue
        read = [stylesheet.VAR.findall(value) for value in (colour, background)]
        if not all(len(one) == 1 and one[0] in names for one in read):
            continue
        pair = tuple(".".join(names[one[0]]) for one in read)
        if pair not in pairs:
            found.append(
                f"{', '.join(rule.selectors)}: {pair[0]} on {pair[1]} is not a declared pair"
            )
    return found


# ----------------------------------------------------------------------------------------
# The formula, on values anybody can check
# ----------------------------------------------------------------------------------------


def test_the_formula_on_known_values() -> None:
    assert ratio("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert ratio("#FFFFFF", "#000000") == pytest.approx(21.0)
    assert ratio("#777777", "#FFFFFF") == pytest.approx(4.478, abs=0.001)
    assert ratio("#767676", "#FFFFFF") == pytest.approx(4.542, abs=0.001)
    assert ratio("#777777", "#FFFFFF") < TEXT < ratio("#767676", "#FFFFFF")


def test_the_thresholds_are_those_of_wcag_2_1_aa_and_derive_from_the_group() -> None:
    assert (TEXT, NON_TEXT) == (4.5, 3.0)
    assert threshold("{color.text.secondary}") == 4.5
    assert threshold("{color.text.error}") == 4.5
    assert threshold("{color.signal.fault}") == 3.0
    assert threshold("{color.focus.ring}") == 3.0
    assert "kind" not in {key for pair in tokens()["contrast"]["pairs"] for key in pair}


# ----------------------------------------------------------------------------------------
# The tree
# ----------------------------------------------------------------------------------------


def test_every_declared_pair_holds_in_both_themes() -> None:
    assert tokens()["contrast"]["pairs"], "there must be pairs, or this test is vacuous"
    assert failing(tokens()) == []


def test_no_pair_is_forgotten() -> None:
    assert undeclared(tokens()) == []
    assert all(reason.strip() for reason in EXEMPT.values())
    assert set(EXEMPT) <= set(colours(tokens(), "text") + colours(tokens(), "border"))


def test_a_rule_that_sets_text_on_a_background_is_a_declared_pair() -> None:
    for name, text in handwritten_stylesheets().items():
        assert rule_pairs_not_declared(text, declared(tokens())) == [], name


# ----------------------------------------------------------------------------------------
# Negatives
# ----------------------------------------------------------------------------------------


def test_a_text_colour_under_4_5_fails_in_the_theme_where_it_is_under() -> None:
    source = tokens()
    source["light"]["color"]["text"]["secondary"]["$value"] = "{palette.graphite.450}"
    found = failing(source)
    assert found and all(line.startswith("light: color.text.secondary") for line in found), found


def test_a_text_colour_cannot_pass_at_3() -> None:
    """3.4:1 is enough for the border of a field and not for a word: the group decides."""
    source = tokens()
    assert ratio("#7A8594", "#F4F5F6") == pytest.approx(3.43, abs=0.01)
    assert not [line for line in failing(source) if "color.border.field" in line]
    source["light"]["color"]["text"]["primary"]["$value"] = "{palette.graphite.450}"
    assert [line for line in failing(source) if "color.text.primary" in line]


def test_a_role_under_3_fails() -> None:
    source = tokens()
    source["dark"]["color"]["signal"]["off"]["$value"] = "{palette.graphite.700}"
    assert [line for line in failing(source) if line.startswith("dark: color.signal.off")]


def test_a_pair_removed_is_missed() -> None:
    source = tokens()
    source["contrast"]["pairs"] = [
        pair for pair in source["contrast"]["pairs"] if pair["bg"] != "{color.surface.raised}"
    ]
    found = undeclared(source)
    assert "color.signal.fault on color.surface.raised" in found
    assert "color.text.disabled on color.surface.raised" not in found


def test_a_new_colour_without_pairs_is_missed() -> None:
    source = tokens()
    for theme in THEMES:
        source[theme]["color"]["signal"]["urgent"] = {
            "$value": "{palette.red.300}",
            "$type": "color",
        }
        source[theme]["color"]["action"]["ghost"] = {
            "$value": "{palette.red.300}",
            "$type": "color",
        }
    found = undeclared(source)
    assert "color.signal.urgent on color.surface.base" in found
    assert "nothing on color.action.ghost" in found


def test_a_rule_with_an_undeclared_pair_is_found() -> None:
    text = (
        ".x { color: var(--ela-color-text-secondary); background: var(--ela-color-action-danger); }"
    )
    found = rule_pairs_not_declared(text, declared(tokens()))
    assert found == [".x: color.text.secondary on color.action.danger is not a declared pair"]
    fine = (
        ".x { color: var(--ela-color-text-on-danger); background: var(--ela-color-action-danger); }"
    )
    assert rule_pairs_not_declared(fine, declared(tokens())) == []
