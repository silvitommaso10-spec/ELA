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

import colorsys
import hashlib
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


HUE_TOLERANCE = 6.0
"""Degrees of hue a part of the light may move between the themes.

The light of the sphere is the same colour in both themes — azure is azure, amber is amber —
but on the white room it is darker and more saturated, or it would vanish (review of
2026-09-19). A darker, more saturated version of a colour picked by eye, then rounded to sRGB,
moves a few degrees; past six a blue starts to read as another blue, toward cyan or toward
indigo, and that would be a different light, not the same one in another room."""

ACHROMATIC = 0.08
"""Chroma — the widest channel minus the narrowest — under which a colour has no hue to keep:
white, and the greys of a sphere that is off or waiting."""


def hue_and_chroma(colour: str) -> tuple[float, float]:
    red, green, blue = channels(colour)
    hue, _, _ = colorsys.rgb_to_hls(red, green, blue)
    return hue * 360, max(red, green, blue) - min(red, green, blue)


def hue_distance(one: float, other: float) -> float:
    return min(abs(one - other), 360 - abs(one - other))


def light_that_changes_hue(source: Tokens) -> list[str]:
    """Every part of the light of the sphere keeps its hue from the dark theme to the light
    one, and is not lighter there: on white it is darker and more saturated, never paler.

    The shell is another matter (review of 2026-09-19): a dark shell over white loses its
    transparency and turns the sphere into a grey marble, so in the light theme it is pale glass
    with tokens of its own, and nothing here compares it.
    """
    module = generator()
    found = []
    for path, _ in module.leaves(source[THEMES[0]]["color"]["light"], ("color", "light")):
        alias = "{" + ".".join(path) + "}"
        dark, light = (str(module.colour_of(source, alias, theme)[0]) for theme in THEMES)
        (dark_hue, dark_chroma), (light_hue, light_chroma) = map(hue_and_chroma, (dark, light))
        name = ".".join(path)
        if (dark_chroma < ACHROMATIC) != (light_chroma < ACHROMATIC):
            found.append(f"{name}: a hue in one theme and none in the other ({dark}, {light})")
        elif dark_chroma >= ACHROMATIC and hue_distance(dark_hue, light_hue) > HUE_TOLERANCE:
            found.append(
                f"{name}: {dark} and {light} are {hue_distance(dark_hue, light_hue):.1f}° apart"
            )
        if luminance(channels(light)) > luminance(channels(dark)):
            found.append(
                f"{name}: {light} is lighter on the white room than {dark} on the dark one"
            )
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


def test_the_light_of_the_sphere_keeps_its_hue_and_its_shell_does_not_keep_its_glass() -> None:
    source = tokens()
    assert light_that_changes_hue(source) == []
    shell = {
        theme: generator().colour_of(source, "{color.orb.shell-core}", theme) for theme in THEMES
    }
    assert shell["dark"] != shell["light"], "pale glass in the light theme, or a grey marble"
    azure = {
        theme: generator().colour_of(source, "{color.light.azure.c}", theme) for theme in THEMES
    }
    assert azure["dark"] != azure["light"], "the same hex would vanish on the white room"


def test_the_reflection_of_the_room_is_a_small_hot_spot_and_a_faint_sheen() -> None:
    """Review of 2026-09-19: one large opaque white oval read as a sticker. Now a hot spot of
    about 7% by 5%, opaque at 0.9, and a broad sheen at 10–14%; on the white room the hot spot is
    smaller and fainter, because white on azure shows more there."""
    source = tokens()
    module = generator()
    alpha = {
        (part, theme): module.colour_of(source, "{color.orb." + part + "}", theme)[1]
        for part in ("hotspot", "sheen")
        for theme in THEMES
    }
    assert alpha[("hotspot", "dark")] == pytest.approx(0.9)
    assert alpha[("hotspot", "light")] < alpha[("hotspot", "dark")]
    assert all(0.10 <= alpha[("sheen", theme)] <= 0.14 for theme in THEMES)

    def radius(theme: str, name: str) -> float:
        return float(source[theme]["tone"]["hotspot"][name]["$value"].removesuffix("%"))

    assert (radius("dark", "width") * 2, radius("dark", "height") * 2) == (7.0, 5.0)
    assert radius("light", "width") < radius("dark", "width")
    assert radius("light", "height") < radius("dark", "height")
    sheen = source["presence"]["sheen"]
    assert float(sheen["width"]["$value"].removesuffix("%")) > 4 * radius("dark", "width")


DARK_SPHERE = (
    "e0cebb24a6fdbb076d982e810bb3849edb4fad8add1bb3b31a9788fbbb20770f"  # pragma: allowlist secret
)
"""The fingerprint of the sphere of the dark theme, approved by the reviewer on 2026-09-19 at
520eb3f: «la sfera è quella giusta e non si tocca più». It changes only with a new review.

Taken when the light theme got its glass: every token the sphere read at 520eb3f resolves in
the dark theme to the same value as then, and what came in is neutral there — a
multiplier of 1, an offset of 0, a colour with no alpha."""


def dark_sphere(source: Tokens) -> str:
    """Every token the sphere reads, as the dark theme resolves it: colours down to the palette,
    everything else as it is written. The CSS keeps its side by construction: what the light
    theme needed is a token of each theme, neutral in the dark one."""
    module = generator()
    trees: dict[tuple[str, ...], Any] = {
        ("presence",): source["presence"],
        ("motion",): source["motion"],
        ("state",): source["state"],
        ("color", "orb"): source["dark"]["color"]["orb"],
        ("color", "light"): source["dark"]["color"]["light"],
        ("tone",): source["dark"]["tone"],
    }
    lines = []
    for prefix, node in trees.items():
        for path, leaf in module.leaves(node, prefix):
            value: object = leaf["$value"]
            if leaf.get("$type") == "color":
                value = module.colour_of(source, "{" + ".".join(path) + "}", "dark")
            lines.append(f"{'.'.join(path)}={value!r}")
    return hashlib.sha256("\n".join(sorted(lines)).encode()).hexdigest()


def test_the_dark_sphere_is_approved_and_does_not_move() -> None:
    assert dark_sphere(tokens()) == DARK_SPHERE, (
        "the sphere of the dark theme changed: it was approved on 2026-09-19, and a change is a"
        " new review — if it has had one, write its fingerprint here"
    )


def test_a_change_to_the_dark_sphere_is_seen_and_one_to_the_light_theme_is_not() -> None:
    source = tokens()
    source["light"]["tone"]["halo"]["$value"] = 0.2
    source["light"]["color"]["orb"]["ground"]["$alpha"] = 0.9
    assert dark_sphere(source) == dark_sphere(tokens())
    source["presence"]["far"]["blur"]["$value"] = 0.2
    assert dark_sphere(source) != dark_sphere(tokens())
    source = tokens()
    source["palette"]["azure"]["300"]["$value"] = "#7CCBFE"
    assert dark_sphere(source) != dark_sphere(tokens()), "a colour is read down to the palette"


def test_in_the_light_theme_the_sphere_is_an_object_of_glass_that_holds_light() -> None:
    """Review of 2026-09-19 after 520eb3f: on white the sphere was a flat, saturated ball with a
    whitish halo, no glass and no shadow — a soap bubble. In the light theme it is glass that
    holds light: a ring of glass between the light and the rim, a marked edge and a thread
    along the silhouette, a light a third less saturated that darkens toward its edge, almost no
    halo, a contact shadow that shows, and a heart moved toward the light of the room."""
    module = generator()
    source = tokens()
    tone = source["light"]["tone"]

    def percent(leaf: dict[str, Any]) -> float:
        return float(str(leaf["$value"]).removesuffix("%").removesuffix("px"))

    inset = percent(source["presence"]["plasma"]["inset"]) + percent(tone["plasma"]["shrink"])
    assert inset / 50 == pytest.approx(0.15, abs=0.01), "a ring of glass, 15% of the radius"
    assert tone["border"]["$value"] > 1 and percent(tone["silhouette"]) >= 1
    assert module.colour_of(source, "{color.orb.silhouette}", "light")[1] > 0
    assert module.colour_of(source, "{color.orb.limb}", "light")[1] > 0
    assert tone["ambient"]["$value"] <= 0.05 < 0.3, "almost nothing: a halo on white dirties it"
    assert tone["halo"]["$value"] > 0
    ground = tone["ground"]
    assert percent(ground["narrow"]) > 0 and ground["flat"]["$value"] < 1
    assert ground["sharp"]["$value"] < 1 and percent(ground["hold"]) > 0
    assert module.colour_of(source, "{color.orb.ground}", "light")[1] >= 0.4
    core = tone["core"]
    assert core["x"]["$value"] < 0 and core["y"]["$value"] < 0, "toward the light, top left"
    assert percent(core["grow"]) > 0
    for path, _ in module.leaves(source["light"]["color"]["light"], ("color", "light")):
        colour = str(module.colour_of(source, "{" + ".".join(path) + "}", "light")[0])
        red, green, blue = channels(colour)
        _, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
        if max(red, green, blue) - min(red, green, blue) >= ACHROMATIC:
            assert saturation <= 0.7, f"{'.'.join(path)}: {colour} is too saturated for white"


def test_the_hue_of_known_colours() -> None:
    assert hue_and_chroma("#FF0000") == pytest.approx((0.0, 1.0))
    assert hue_and_chroma("#7CCBFF")[0] == pytest.approx(203.8, abs=0.1)
    assert hue_and_chroma("#009AFF")[0] == pytest.approx(203.8, abs=0.1)
    assert hue_and_chroma("#FFFFFF")[1] == 0
    assert hue_distance(355, 5) == 10
    assert hue_distance(10, 200) == 170


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


def test_a_light_that_changes_hue_or_turns_paler_is_found_and_a_shell_that_changes_is_not() -> None:
    source = tokens()
    light = source["light"]["color"]["light"]
    light["azure"]["c"]["$value"] = "{palette.orange.500}"
    light["amber"]["c2"]["$value"] = "{palette.frost.0}"
    light["red"]["c"]["$value"] = "{palette.red.100}"
    source["light"]["color"]["orb"]["drop"]["$alpha"] = 0.05
    found = light_that_changes_hue(source)
    assert [line.split(":")[0] for line in found] == [
        "color.light.azure.c",
        "color.light.amber.c2",
        "color.light.amber.c2",
        "color.light.red.c",
    ]
    assert "° apart" in found[0] and "none in the other" in found[1]
    assert "lighter" in found[2] and "lighter" in found[3]
