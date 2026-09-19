"""What is written by hand reads tokens, and writes no value of its own (M17.1, criteri 3 e 4).

The rule of dec. 1 — «un test cerca colori, dimensioni e durate scritte a mano fuori da
tokens.json e fallisce se ne trova» — made into something that can fail: a colour, a length, a
duration, an angle, a curve, a gradient, a bare number where a token exists, a ``var()`` that
``tokens.css`` does not define. What stays allowed is :data:`ALLOWED`, a closed list with a
reason for every entry (review of 2026-09-18, point 11: past ten entries it goes back to review).

Gradients live in three places and nowhere else — **the presence** (ELA's sphere), **the
materials** (glass and the room), **the primary action** — and there every stop is a token: the
checks on literals still run inside a gradient, so a colour or a percentage written by hand
fails there as anywhere. ``filter``, ``backdrop-filter`` and ``mix-blend-mode`` live in the
presence and in the materials only (the user's decisions of 2026-09-18 and 2026-09-19;
ADR 0042).

And no token is an orphan: a custom property of ``tokens.css`` is read by something written by
hand, or by a derived rule of ``tokens.css`` itself. The samples of the specimen page do not
count — they live in ``specimen-switch.css`` for that reason — or the rule would be true by
construction.
"""

from __future__ import annotations

import re

import pytest

from tests.design import markup, stylesheet
from tests.design.tree import fragments, generator, handwritten_stylesheets, read, tokens

ALLOWED = {
    "0": "nothing: a margin, an inset, a translation that ends where it began",
    "1": "the whole: a flex factor, the scale an animation settles on",
    "-1": "the sign, inside calc(): the wordmark takes back the tracking after its last letter",
    "100%": "the whole of the container",
    "1fr": "an equal share of a grid",
    "1turn": "a full rotation: the orbit of an indicator",
}
"""The literals a hand-written value may hold. Closed, and pinned by a test below."""

BARE_NUMBER_IS_A_TOKEN = {"opacity", "line-height", "font-weight", "z-index"}
"""Properties whose number is a design decision, and therefore a token — even ``1``."""

MEDIA_FEATURES = {
    "min-width": None,
    "prefers-reduced-motion": {"no-preference", "reduce"},
    "pointer": {"coarse", "fine"},
}
"""What a hand-written ``@media`` may ask. ``min-width`` takes a breakpoint token, and only one."""

COLOUR_FUNCTIONS = {
    "rgb",
    "rgba",
    "hsl",
    "hsla",
    "hwb",
    "lab",
    "lch",
    "oklab",
    "oklch",
    "color",
    "color-mix",
    "light-dark",
}
CURVE_FUNCTIONS = {"cubic-bezier", "steps", "linear"}
PRESENCE = (".ela-orb", ".ela-presence")
"""The sphere, and the component that shows it with the key of the state."""
MATERIALS = (".ela-room", ".ela-panel")
"""The room, and glass."""
GRADIENTS_LIVE_IN = (*PRESENCE, *MATERIALS, ".ela-button--primary")
"""Where a rule may hold a gradient: **every** selector of the rule starts with one of these.
A rule shared with anything else does not qualify."""
EFFECTS = {"filter", "backdrop-filter", "-webkit-backdrop-filter", "mix-blend-mode"}
EFFECTS_LIVE_IN = (*PRESENCE, *MATERIALS)
"""Where a rule may blur, saturate or blend: light and glass, and nothing else."""
CURVE_KEYWORDS = {"ease", "ease-in", "ease-out", "ease-in-out", "linear", "step-start", "step-end"}
_NAMED_COLOURS = """
    aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet
    brown burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan
    darkblue darkcyan darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta
    darkolivegreen darkorange darkorchid darkred darksalmon darkseagreen darkslateblue
    darkslategray darkslategrey darkturquoise darkviolet deeppink deepskyblue dimgray dimgrey
    dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite gold goldenrod gray
    green greenyellow grey honeydew hotpink indianred indigo ivory khaki lavender lavenderblush
    lawngreen lemonchiffon lightblue lightcoral lightcyan lightgoldenrodyellow lightgray lightgreen
    lightgrey lightpink lightsalmon lightseagreen lightskyblue lightslategray lightslategrey
    lightsteelblue lightyellow lime limegreen linen magenta maroon mediumaquamarine mediumblue
    mediumorchid mediumpurple mediumseagreen mediumslateblue mediumspringgreen mediumturquoise
    mediumvioletred midnightblue mintcream mistyrose moccasin navajowhite navy oldlace olive
    olivedrab orange orangered orchid palegoldenrod palegreen paleturquoise palevioletred
    papayawhip peachpuff peru pink plum powderblue purple rebeccapurple red rosybrown royalblue
    saddlebrown salmon sandybrown seagreen seashell sienna silver skyblue slateblue slategray
    slategrey snow springgreen steelblue tan teal thistle tomato turquoise violet wheat white
    whitesmoke yellow yellowgreen
"""
NAMED_COLOURS = frozenset(_NAMED_COLOURS.split())
"""The named colours of CSS Color 4: a closed list of a standard, not a list of ours.
``transparent`` and ``currentColor`` are not in it, and are not colours written by hand."""

STRING = re.compile(r"\"[^\"]*\"|'[^']*'")
PROPERTY = re.compile(r"--[A-Za-z0-9_-]+")
HEX = re.compile(r"#[0-9A-Fa-f]{3,8}\b")
FUNCTION = re.compile(r"([A-Za-z][A-Za-z0-9-]*)\(")
NUMBER = re.compile(r"(?<![\w.#-])(-?\d*\.?\d+)([A-Za-z%]*)")
WORD = re.compile(r"(?<![\w-])([A-Za-z][A-Za-z-]*)(?![\w(-])")
TEXT_COLOUR = re.compile(r"^var\(--ela-(?:color-text-[a-z0-9-]+|state-text|level-text)\)$")
"""What the ``color`` property may read: a text token, or the text colour a derived rule gives
to the key of a state or of a level — which the generator refuses unless it is a text token."""
FEATURE = re.compile(r"\(\s*([a-z-]+)\s*:\s*([^)]+?)\s*\)")

UNITS = {
    "length": {"px", "rem", "em", "ex", "ch", "vh", "vw", "vmin", "vmax", "svh", "lvh", "dvh"}
    | {"cm", "mm", "in", "pt", "pc", "fr", "%"},
    "duration": {"s", "ms"},
    "angle": {"deg", "rad", "grad", "turn"},
}


def kind_of(unit: str) -> str:
    return next((kind for kind, units in UNITS.items() if unit in units), "number")


def live_in(selectors: tuple[str, ...], homes: tuple[str, ...]) -> bool:
    return bool(selectors) and all(selector.startswith(homes) for selector in selectors)


def faults_in_value(
    name: str, value: str, defined: set[str], selectors: tuple[str, ...] = ()
) -> list[str]:
    found = []
    for custom in PROPERTY.findall(value):
        if custom.startswith("--ela-palette-"):
            found.append(f"{custom}: a primitive skips the theme, read a semantic colour")
        elif custom.startswith("--ela-") and custom not in defined:
            found.append(f"{custom}: tokens.css defines no such property")
        elif not custom.startswith(("--ela-", "--_")):
            found.append(f"{custom}: a custom property is a token (--ela-) or private (--_)")

    bare = PROPERTY.sub("", STRING.sub("", value))
    found += [f"{match}: a colour written by hand" for match in HEX.findall(bare)]
    for function in FUNCTION.findall(bare):
        lowered = function.lower()
        if lowered in COLOUR_FUNCTIONS:
            found.append(f"{function}(): a colour written by hand")
        elif "gradient" in lowered and not live_in(selectors, GRADIENTS_LIVE_IN):
            found.append(f"{function}(): a gradient outside the sphere, glass and the action")
        elif lowered in CURVE_FUNCTIONS:
            found.append(f"{function}(): a curve written by hand")
    for number, unit in NUMBER.findall(HEX.sub("", bare)):
        literal = number + unit
        if name in BARE_NUMBER_IS_A_TOKEN and not unit:
            found.append(f"{literal}: the number of {name} is a token")
        elif literal not in ALLOWED:
            found.append(f"{literal}: a {kind_of(unit)} written by hand")
    for word in WORD.findall(bare):
        lowered = word.lower()
        if lowered in NAMED_COLOURS:
            found.append(f"{word}: a colour written by hand")
        elif lowered in CURVE_KEYWORDS:
            found.append(f"{word}: a curve written by hand")

    if name in EFFECTS and value != "none" and not live_in(selectors, EFFECTS_LIVE_IN):
        found.append(f"{name}: light and glass only — the sphere and the materials")
    if name == "color" and value != "inherit" and not TEXT_COLOUR.match(value):
        found.append(f"color: {value}: the colour of text is a text token (dec. G)")
    return found


def faults_in_media(prelude: str, breakpoints: set[str]) -> list[str]:
    found = []
    leftover = FEATURE.sub("", prelude).replace("and", "").strip()
    if leftover:
        found.append(f"@media {prelude}: not a list of features this design system knows")
    for feature, value in FEATURE.findall(prelude):
        if feature not in MEDIA_FEATURES:
            found.append(f"@media ({feature}): a feature outside the closed list")
        elif feature == "min-width":
            if value not in breakpoints:
                found.append(f"@media (min-width: {value}): not a breakpoint token")
        elif value not in (MEDIA_FEATURES[feature] or set()):
            found.append(f"@media ({feature}: {value}): not a value of that feature")
    return found


def faults_in_stylesheet(text: str, defined: set[str], breakpoints: set[str]) -> list[str]:
    try:
        rules = stylesheet.parse(text)
    except stylesheet.Unrecognised as unknown:
        return [f"not recognised: {unknown}"]
    found = []
    for prelude in sorted({rule.media for rule in rules if rule.media is not None}):
        found += faults_in_media(prelude, breakpoints)
    for rule in rules:
        for name, value in rule.declarations:
            found += [
                f"{', '.join(rule.selectors)} — {fault}"
                for fault in faults_in_value(name, value, defined, rule.selectors)
            ]
    return found


def faults_in_fragment(text: str) -> list[str]:
    found = []
    for element in markup.parse(text).walk():
        if element.tag == "style":
            found.append("<style>: a fragment carries no CSS of its own")
        if "style" in element.attributes:
            found.append(f"<{element.tag} style=…>: a fragment carries no CSS of its own")
    return found


def defined_properties() -> set[str]:
    return stylesheet.custom_properties(stylesheet.parse(read("tokens.css")))


def breakpoints() -> set[str]:
    return {leaf["$value"] for _, leaf in generator().leaves(tokens()["breakpoint"])}


# ----------------------------------------------------------------------------------------
# The tree
# ----------------------------------------------------------------------------------------


def test_nothing_written_by_hand_writes_a_value_of_its_own() -> None:
    sheets = handwritten_stylesheets()
    assert sheets, "there must be stylesheets to read, or this test is vacuous"
    for name, text in sheets.items():
        assert faults_in_stylesheet(text, defined_properties(), breakpoints()) == [], name
    for name, text in fragments().items():
        assert faults_in_fragment(text) == [], name


def test_the_allowed_literals_are_a_closed_list_with_a_reason_each() -> None:
    assert set(ALLOWED) == {"0", "1", "-1", "100%", "1fr", "1turn"}
    assert len(ALLOWED) <= 10, "past ten entries the list goes back to review"
    assert all(reason.strip() for reason in ALLOWED.values())
    assert set(MEDIA_FEATURES) == {"min-width", "prefers-reduced-motion", "pointer"}


def test_every_allowed_literal_is_used() -> None:
    """An entry nobody needs is an exception nobody decided."""
    values = " ".join(
        value
        for text in handwritten_stylesheets().values()
        for rule in stylesheet.parse(text)
        for _, value in rule.declarations
    )
    used = {number + unit for number, unit in NUMBER.findall(PROPERTY.sub("", values))}
    assert set(ALLOWED) <= used, set(ALLOWED) - used


# ----------------------------------------------------------------------------------------
# One negative for every way of being wrong
# ----------------------------------------------------------------------------------------

DEFINED = {
    "--ela-space-1",
    "--ela-color-text-primary",
    "--ela-color-signal-fault",
    "--ela-state-text",
    "--ela-level-text",
}
BREAKPOINTS = {"0px", "720px", "1200px"}

WRONG = [
    ("a { background: #0B0D10; }", "a colour written by hand"),
    ("a { background: #fff; }", "a colour written by hand"),
    ("a { background: rgb(0 0 0 / 0.5); }", "rgb(): a colour written by hand"),
    ("a { background: oklch(60% 0.1 200); }", "oklch(): a colour written by hand"),
    ("a { border-color: rebeccapurple; }", "rebeccapurple: a colour written by hand"),
    ("a { padding: 12px; }", "12px: a length written by hand"),
    ("a { padding: 0.5rem; }", "0.5rem: a length written by hand"),
    ("a { inline-size: 50%; }", "50%: a length written by hand"),
    ("a { transition-duration: 120ms; }", "120ms: a duration written by hand"),
    ("a { transition-duration: 0.2s; }", "0.2s: a duration written by hand"),
    ("a { rotate: 45deg; }", "45deg: a angle written by hand"),
    ("a { transition-timing-function: ease-in-out; }", "ease-in-out: a curve written by hand"),
    ("a { animation-timing-function: linear; }", "linear: a curve written by hand"),
    ("a { transition: opacity var(--ela-space-1) cubic-bezier(0.2, 0, 0, 1); }", "cubic-bezier()"),
    ("a { animation-timing-function: steps(4, end); }", "steps(): a curve written by hand"),
    ("a { opacity: 0.5; }", "0.5: the number of opacity is a token"),
    ("a { opacity: 1; }", "1: the number of opacity is a token"),
    ("a { line-height: 1.5; }", "the number of line-height is a token"),
    ("a { font-weight: 600; }", "the number of font-weight is a token"),
    ("a { z-index: 10; }", "the number of z-index is a token"),
    ("a { flex: 2; }", "2: a number written by hand"),
    ("a { background: linear-gradient(var(--ela-space-1), var(--ela-space-1)); }", "a gradient"),
    (
        ".ela-button { background: radial-gradient(var(--ela-space-1), var(--ela-space-1)); }",
        "a gradient outside the sphere, glass and the action",
    ),
    (
        ".ela-orb__core, .ela-pill { background: radial-gradient(var(--ela-space-1)); }",
        "a gradient outside the sphere, glass and the action",
    ),
    (
        ".specimen-hero { background: conic-gradient(var(--ela-space-1), var(--ela-space-1)); }",
        "a gradient outside the sphere, glass and the action",
    ),
    (
        ".ela-orb__core { background: radial-gradient(#7CCBFF 0%, var(--ela-space-1)); }",
        "a colour written by hand",
    ),
    (
        ".ela-panel { background: linear-gradient(to bottom, var(--ela-space-1) 44%); }",
        "44%: a length written by hand",
    ),
    (".ela-pill { backdrop-filter: blur(var(--ela-space-1)); }", "light and glass only"),
    (".ela-button--primary { filter: blur(var(--ela-space-1)); }", "light and glass only"),
    (".ela-orb__cloud, .ela-tile { mix-blend-mode: screen; }", "light and glass only"),
    (".specimen-bar { -webkit-backdrop-filter: blur(var(--ela-space-1)); }", "light and glass"),
    ("a { padding: var(--ela-space-7); }", "tokens.css defines no such property"),
    ("a { background: var(--ela-palette-ink-900); }", "a primitive skips the theme"),
    ("a { padding: var(--gap); }", "a custom property is a token"),
    ("a { color: var(--ela-color-signal-fault); }", "the colour of text is a text token"),
    ("a { color: currentColor; }", "the colour of text is a text token"),
    ("@keyframes k { to { opacity: 0.4; } }", "the number of opacity is a token"),
    ("@media (min-width: 800px) { a { margin: 0; } }", "not a breakpoint token"),
    ("@media (max-width: 720px) { a { margin: 0; } }", "a feature outside the closed list"),
    ("@media (pointer: none) { a { margin: 0; } }", "not a value of that feature"),
    ("@media screen and (min-width: 720px) { a { margin: 0; } }", "not a list of features"),
    ("@supports (display: grid) { a { margin: 0; } }", "not recognised"),
    ("@import 'other.css';", "not recognised"),
    ("a { margin: 0; b { margin: 0; } }", "not recognised"),
    ("a { margin 0 }", "not recognised"),
]


@pytest.mark.parametrize(("text", "fault"), WRONG, ids=[case[0][:48] for case in WRONG])
def test_a_value_written_by_hand_is_a_fault(text: str, fault: str) -> None:
    found = faults_in_stylesheet(text, DEFINED, BREAKPOINTS)
    assert any(fault in line for line in found), found


RIGHT = [
    "a { padding: var(--ela-space-1) 0; margin: 0; flex: 1; inline-size: 100%; }",
    "a { --_tone: var(--ela-color-signal-fault); border-color: var(--_tone); }",
    "a { color: var(--ela-color-text-primary); background: transparent; }",
    "a { color: inherit; border: var(--ela-space-1) solid currentColor; }",
    'a::after { content: "12px #fff ease"; }',
    "a { margin-inline-end: calc(var(--ela-space-1) * -1); grid-template-columns: 1fr 1fr; }",
    "@keyframes k { to { rotate: 1turn; } }",
    ".ela-orb__core { background: radial-gradient(circle at var(--ela-space-1)"
    " var(--ela-space-1), var(--ela-color-text-primary) var(--ela-space-1), transparent); }",
    ".ela-room { background-image: linear-gradient(to bottom, var(--ela-space-1), transparent); }",
    ".ela-button--primary:hover, .ela-button--primary.is-hover"
    " { background-image: linear-gradient(to bottom, var(--ela-space-1), var(--ela-space-1)); }",
    ".ela-panel { backdrop-filter: blur(var(--ela-space-1)) saturate(var(--ela-space-1)); }",
    ".ela-panel--inset { backdrop-filter: none; }",
    ".ela-orb__cloud { mix-blend-mode: screen; filter: blur(var(--ela-space-1)); }",
    ".ela-state__key { color: var(--ela-state-text); }",
    ".ela-level__key { color: var(--ela-level-text); }",
    "@media (min-width: 720px) { a { margin: 0; } }",
    "@media (prefers-reduced-motion: no-preference) and (pointer: coarse) { a { margin: 0; } }",
]


@pytest.mark.parametrize("text", RIGHT, ids=[case[:48] for case in RIGHT])
def test_what_reads_tokens_is_not_a_fault(text: str) -> None:
    """The control: a check that refuses everything proves nothing about what it refuses."""
    assert faults_in_stylesheet(text, DEFINED, BREAKPOINTS) == []


def test_a_fragment_carries_no_css_of_its_own() -> None:
    assert faults_in_fragment('<p style="color: red">x</p>') != []
    assert faults_in_fragment("<div><style>p { margin: 0 }</style></div>") != []
    assert faults_in_fragment('<p class="ela-tag">x</p>') == []


# ----------------------------------------------------------------------------------------
# No orphan token (criterio 4)
# ----------------------------------------------------------------------------------------

PALETTE = "--ela-palette-"


def orphans(derived: str, handwritten: list[str]) -> set[str]:
    """Properties ``derived`` declares and nothing reads: not by hand, not a derived rule."""
    rules = stylesheet.parse(derived)
    read_somewhere = stylesheet.read_properties(rules)
    for text in handwritten:
        read_somewhere |= stylesheet.read_properties(stylesheet.parse(text))
    declared = {
        name for name in stylesheet.custom_properties(rules) if not name.startswith(PALETTE)
    }
    return declared - read_somewhere


def unaliased_palette(source: dict) -> set[str]:
    """Primitives no semantic colour names: a colour nobody can reach."""
    module = generator()
    named = {
        leaf["$value"]
        for theme in module.THEMES
        for _, leaf in module.leaves(source[theme])
        if isinstance(leaf["$value"], str)
    }
    every = {
        "{" + ".".join(path) + "}" for path, _ in module.leaves(source["palette"], ("palette",))
    }
    assert every, "the palette must have colours, or this check is vacuous"
    return every - named


def test_no_token_is_an_orphan() -> None:
    assert orphans(read("tokens.css"), list(handwritten_stylesheets().values())) == set()
    assert unaliased_palette(tokens()) == set()


def test_the_samples_of_the_page_do_not_count_as_readers() -> None:
    """``specimen-switch.css`` reads every colour to show it: counting it would hide an orphan."""
    derived = ":root { --ela-space-9: 9rem; }"
    sample = ".specimen-step--space-9 { --_step: var(--ela-space-9); }"
    assert orphans(derived, []) == {"--ela-space-9"}
    assert orphans(derived, [sample]) == set(), "a reader written by hand does count"
    assert "specimen-switch.css" not in generator().HANDWRITTEN_STYLESHEETS


def test_a_token_only_a_derived_rule_reads_is_not_an_orphan() -> None:
    derived = ':root { --ela-a: 1px; } [data-x="y"] { --ela-b: var(--ela-a); }'
    assert orphans(derived, ["a { inline-size: var(--ela-b); }"]) == set()


def test_a_primitive_no_semantic_colour_names_is_found() -> None:
    source = tokens()
    source["palette"]["ink"]["1000"] = {"$value": "#000000", "$type": "color"}
    assert unaliased_palette(source) == {"{palette.ink.1000}"}
