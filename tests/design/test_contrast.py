"""WCAG 2.1 AA, in both themes, for every declared pair (M17.1, criterio 12; dec. 5, dec. G).

The threshold of a pair is **not declared**: it derives from the group of its foreground. A
text colour wants 4.5 (WCAG 1.4.3); anything else — a signal of state, of risk, of attention,
the border of a field, the focus ring — wants 3 (WCAG 1.4.11). A kind declared by the pair would
be the lever this file exists to remove, and so would thresholds kept in ``tokens.json``: a rule
that a JSON edit can lower is not a rule. ``test_tokens_only.py`` closes the other half — the
``color`` property takes only text tokens.

**A colour may have alpha** (decision of 2026-09-19: glass is white at a low opacity, body text
is white at 78%). What the eye sees is the colour *composed over what is behind it*, so both
sides of a pair are composed over ``surface.base`` before they are measured — the foreground
over the composed background.

**The light of the sphere does not change with the theme** — azure and white in both — while
its shell does: dark glass in the dark theme, pale glass in the light one.

**The sphere is exempt, by name.** Its glass, its light and its halo are not controls and carry
no meaning alone: the key, as text, says the state, and the key is measured. The same for the
materials — the room, the panes of glass, the hairlines of light — which are decoration.

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
BASE = "{color.surface.base}"

FOREGROUNDS = ("text", "signal", "focus", "field")
"""Groups of ``color`` whose every token is drawn on a surface and means something."""
SURFACES = "surface"
BACKGROUNDS = "fill"
"""Groups whose every token is a background with something drawn on it."""

EXEMPT_GROUPS = {
    "orb": "the glass of the sphere: not a control, and the key as text says the state",
    "light": "the light inside the sphere and its halo: the key as text says the state",
    "room": "the background of a surface and its two lights: decoration",
    "glass": "panes of glass, tracks and tints: decoration, nothing is identified by them",
    "line": "hairlines of light at the edge of glass and of a labelled button: decoration",
    "glow": "the light behind the wordmark: decoration",
}
"""Groups of ``color`` that are paired with nothing, each with its reason."""

EXEMPT = {
    "color.text.disabled": "WCAG 1.4.3 excludes the text of an inactive user interface component",
    "color.text.on-action": "drawn on the primary action only: paired with every shade of it",
    "color.text.on-danger": "drawn on the danger action only: paired with every shade of it",
}
"""Foregrounds that are not paired with every surface, each with its reason."""

Tokens = dict[str, Any]
Colour = tuple[float, float, float]


def channels(colour: str) -> Colour:
    return tuple(int(colour[index : index + 2], 16) / 255 for index in (1, 3, 5))  # type: ignore[return-value]


def over(top: Colour, alpha: float, bottom: Colour) -> Colour:
    """``top`` at ``alpha`` composed over an opaque ``bottom``: what the eye sees."""
    return tuple(t * alpha + b * (1 - alpha) for t, b in zip(top, bottom, strict=True))  # type: ignore[return-value]


def luminance(colour: Colour) -> float:
    """Relative luminance, as WCAG 2.1 defines it."""
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in colour]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def ratio(one: Colour, other: Colour) -> float:
    lighter, darker = sorted((luminance(one), luminance(other)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def hex_ratio(one: str, other: str) -> float:
    return ratio(channels(one), channels(other))


def seen(source: Tokens, alias: str, theme: str, behind: Colour) -> Colour:
    colour, alpha = generator().colour_of(source, alias, theme)
    return over(channels(str(colour)), alpha, behind)


def measured(source: Tokens, pair: dict[str, str], theme: str) -> float:
    base_colour, base_alpha = generator().colour_of(source, BASE, theme)
    assert base_alpha == 1, "the base of a theme is opaque: everything is composed over it"
    base = channels(str(base_colour))
    background = seen(source, pair["bg"], theme, base)
    return ratio(seen(source, pair["fg"], theme, background), background)


def path_of(alias: str) -> str:
    return alias.strip("{}")


def threshold(foreground: str) -> float:
    return TEXT if path_of(foreground).startswith("color.text.") else NON_TEXT


def failing(source: Tokens) -> list[str]:
    found = []
    for pair in source["contrast"]["pairs"]:
        for theme in THEMES:
            if (value := measured(source, pair, theme)) < threshold(pair["fg"]):
                found.append(
                    f"{theme}: {path_of(pair['fg'])} on {path_of(pair['bg'])} is "
                    f"{value:.2f}, under {threshold(pair['fg'])}"
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
    """Every foreground against every surface, every background under something, and no group
    of colours that is neither measured nor exempt by name."""
    pairs = declared(source)
    found = [
        f"{fg} on {bg}"
        for group in FOREGROUNDS
        for fg in colours(source, group)
        if fg not in EXEMPT
        for bg in colours(source, SURFACES)
        if (fg, bg) not in pairs
    ]
    under = {bg for _, bg in pairs}
    found += [f"nothing on {bg}" for bg in colours(source, BACKGROUNDS) if bg not in under]
    known = {*FOREGROUNDS, SURFACES, BACKGROUNDS, *EXEMPT_GROUPS}
    groups = generator().entries(source[THEMES[0]]["color"])
    found += [
        f"color.{group}: neither measured nor exempt" for group in groups if group not in known
    ]
    return found


def rule_pairs_not_declared(text: str, pairs: set[tuple[str, str]]) -> list[str]:
    """A hand-written rule that sets both the colour of text and its background, from tokens."""
    names = token_paths()
    found = []
    for rule in stylesheet.parse(text):
        colour = rule.value("color")
        background = rule.value("background-color") or rule.value("background")
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


def light_that_changes_with_the_theme(source: Tokens) -> list[str]:
    """The light of the sphere stays azure and white in the light theme: no dark blue.

    The **light**, not the shell (review of 2026-09-19): a dark shell over white loses its
    transparency and turns the sphere into a grey marble, so in the light theme the shell is
    pale glass, with tokens of its own under ``light``.
    """
    module = generator()
    found = []
    for path, _ in module.leaves(source[THEMES[0]]["color"]["light"], ("color", "light")):
        alias = "{" + ".".join(path) + "}"
        looks = {theme: module.colour_of(source, alias, theme) for theme in THEMES}
        if len(set(looks.values())) != 1:
            found.append(f"{'.'.join(path)}: {looks}")
    return found


# ----------------------------------------------------------------------------------------
# The formula, on values anybody can check
# ----------------------------------------------------------------------------------------


def test_the_formula_on_known_values() -> None:
    assert hex_ratio("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert hex_ratio("#FFFFFF", "#000000") == pytest.approx(21.0)
    assert hex_ratio("#777777", "#FFFFFF") == pytest.approx(4.478, abs=0.001)
    assert hex_ratio("#767676", "#FFFFFF") == pytest.approx(4.542, abs=0.001)
    assert hex_ratio("#777777", "#FFFFFF") < TEXT < hex_ratio("#767676", "#FFFFFF")


def test_a_colour_with_alpha_is_composed_over_what_is_behind_it() -> None:
    white, black = channels("#FFFFFF"), channels("#000000")
    assert over(white, 1, black) == white
    assert over(white, 0, black) == black
    assert over(white, 0.5, black) == pytest.approx((0.5, 0.5, 0.5))
    # white at 50% over black is a mid grey, and measures as one — not as white
    assert ratio(over(white, 0.5, black), black) == pytest.approx(
        hex_ratio("#808080", "#000000"), abs=0.05
    )
    assert ratio(over(white, 0.5, black), black) < hex_ratio("#FFFFFF", "#000000")


def test_the_thresholds_are_those_of_wcag_2_1_aa_and_derive_from_the_group() -> None:
    assert (TEXT, NON_TEXT) == (4.5, 3.0)
    assert threshold("{color.text.muted}") == 4.5
    assert threshold("{color.text.warn}") == 4.5
    assert threshold("{color.signal.fault}") == 3.0
    assert threshold("{color.focus.ring}") == 3.0
    assert "kind" not in {key for pair in tokens()["contrast"]["pairs"] for key in pair}


# ----------------------------------------------------------------------------------------
# The tree
# ----------------------------------------------------------------------------------------


def test_every_declared_pair_holds_in_both_themes() -> None:
    assert tokens()["contrast"]["pairs"], "there must be pairs, or this test is vacuous"
    assert failing(tokens()) == []


def test_no_pair_is_forgotten_and_every_exemption_has_a_name_and_a_reason() -> None:
    assert undeclared(tokens()) == []
    assert all(reason.strip() for reason in (*EXEMPT.values(), *EXEMPT_GROUPS.values()))
    assert set(EXEMPT) <= set(colours(tokens(), "text"))
    assert set(EXEMPT_GROUPS) <= set(generator().entries(tokens()["dark"]["color"]))


def test_a_rule_that_sets_text_on_a_background_is_a_declared_pair() -> None:
    for name, text in handwritten_stylesheets().items():
        assert rule_pairs_not_declared(text, declared(tokens())) == [], name


def test_the_light_of_the_sphere_does_not_change_with_the_theme_and_its_shell_does() -> None:
    source = tokens()
    assert light_that_changes_with_the_theme(source) == []
    shell = {
        theme: generator().colour_of(source, "{color.orb.shell-core}", theme) for theme in THEMES
    }
    assert shell["dark"] != shell["light"], "pale glass in the light theme, or a grey marble"


# ----------------------------------------------------------------------------------------
# Negatives
# ----------------------------------------------------------------------------------------


def test_a_text_colour_thinned_out_too_far_fails_in_the_theme_where_it_does() -> None:
    source = tokens()
    source["light"]["color"]["text"]["muted"]["$alpha"] = 0.45
    found = failing(source)
    assert found and all(line.startswith("light: color.text.muted") for line in found), found


def test_the_alpha_counts_on_the_background_too() -> None:
    """Text on glass is text on glass *over the room*: the pane is composed first."""
    source = tokens()
    pair = {"fg": "{color.text.muted}", "bg": "{color.surface.glass}"}
    before = measured(source, pair, "dark")
    source["dark"]["color"]["surface"]["glass"]["$alpha"] = 0.5
    assert measured(source, pair, "dark") < before
    assert [line for line in failing(source) if "color.surface.glass" in line]


def test_a_text_colour_cannot_pass_at_3() -> None:
    """The border of a field passes at 3 where a word would not: the group decides."""
    source = tokens()
    border = {"fg": "{color.field.border}", "bg": BASE}
    assert NON_TEXT <= measured(source, border, "dark") < TEXT
    assert not [line for line in failing(source) if "color.field.border" in line]
    source["dark"]["color"]["text"]["primary"] = dict(source["dark"]["color"]["field"]["border"])
    assert [line for line in failing(source) if "color.text.primary" in line]


def test_a_signal_under_3_fails() -> None:
    source = tokens()
    source["dark"]["color"]["signal"]["off"]["$value"] = "{palette.grey.700}"
    assert [line for line in failing(source) if line.startswith("dark: color.signal.off")]


def test_a_pair_removed_is_missed() -> None:
    source = tokens()
    source["contrast"]["pairs"] = [
        pair for pair in source["contrast"]["pairs"] if pair["bg"] != "{color.surface.glass}"
    ]
    found = undeclared(source)
    assert "color.signal.fault on color.surface.glass" in found
    assert "color.text.disabled on color.surface.glass" not in found


def test_a_new_colour_and_a_new_group_without_pairs_are_missed() -> None:
    source = tokens()
    for theme in THEMES:
        colour = source[theme]["color"]
        colour["signal"]["urgent"] = {"$value": "{palette.red.300}", "$type": "color"}
        colour["fill"]["ghost"] = {"$value": "{palette.red.300}", "$type": "color"}
        colour["aura"] = {"soft": {"$value": "{palette.red.300}", "$type": "color"}}
    found = undeclared(source)
    assert "color.signal.urgent on color.surface.base" in found
    assert "nothing on color.fill.ghost" in found
    assert "color.aura: neither measured nor exempt" in found


def test_a_rule_with_an_undeclared_pair_is_found() -> None:
    text = (
        ".x { color: var(--ela-color-text-muted); background-color: var(--ela-color-fill-danger); }"
    )
    found = rule_pairs_not_declared(text, declared(tokens()))
    assert found == [".x: color.text.muted on color.fill.danger is not a declared pair"]
    fine = (
        ".x { color: var(--ela-color-text-on-danger); background: var(--ela-color-fill-danger); }"
    )
    assert rule_pairs_not_declared(fine, declared(tokens())) == []


def test_a_light_that_changes_with_the_theme_is_found_and_a_shell_that_does_is_not() -> None:
    source = tokens()
    source["light"]["color"]["light"]["azure"]["c"]["$value"] = "{palette.azure.800}"
    source["light"]["color"]["light"]["amber"]["veil"]["$alpha"] = 0.9
    source["light"]["color"]["orb"]["drop"]["$alpha"] = 0.05
    found = light_that_changes_with_the_theme(source)
    assert [line.split(":")[0] for line in found] == [
        "color.light.azure.c",
        "color.light.amber.veil",
    ]
