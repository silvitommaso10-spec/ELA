"""Derive the design system's CSS and its specimen page from ``tokens.json`` (ADR 0042).

``apps/design-system/tokens.json`` is the one source. Everything in :data:`DERIVED` is written by
this script and compared **byte for byte** by ``tests/design/test_generated.py`` at every
``make check``: a token changed without regenerating, or a derived file touched by hand, fails.

    uv run python scripts/generate_design_system.py            # rewrite the derived files
    uv run python scripts/generate_design_system.py --check    # exit 1 if any is stale

Unlike ``generate_stato.py``, which replaces blocks inside a document written by hand, these files
are generated **whole**: the specimen page must not hold a copy of its own of the tokens or of the
markup, or it stops being true at the first change. What is written by hand lives beside them —
``components.css``, ``components/*.html``, ``specimen.css`` — and may only read tokens.

Three things CSS cannot do are the reason three kinds of rule are written here and not by hand:
a media query cannot read a custom property (the grid per band, the touch target, reduced motion);
a custom property holding ``var()`` resolves where it is declared (so every theme block re-emits
everything themed); and ``:has()`` reads a control but cannot set an attribute (so the specimen's
whole-page theme switch needs the light tokens under a selector of its own).

The script depends on nothing but the standard library and does not import ``ela``: the design
system is not part of the Core. It is seen by ``ruff`` and by its tests, not by ``mypy`` nor by
the coverage gate — the level of verification of everything in ``scripts/``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterator, Mapping, Sequence
from html import escape
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DESIGN_SYSTEM = ROOT / "apps" / "design-system"

SOURCE = "tokens.json"
DERIVED = ("tokens.css", "specimen-switch.css", "index.html")
"""The files this script writes, and the list ADR 0042 and the tests read."""

HANDWRITTEN_STYLESHEETS = ("components.css", "specimen.css")
FRAGMENTS = "components"

PREFIX = "--ela-"
THEMES = ("dark", "light")
"""The first is the default: it is the one ``:root`` carries."""
THEMED = ("color", "shadow", "elevation")
"""What depends on the theme, and therefore lives under each theme with the same keys."""
LISTS = {"state": "data-ela-state", "risk": "data-ela-risk", "attention": "data-ela-attention"}
"""The three lists that exist only in ``tokens.json``, and the attribute that carries a key."""
PLAIN = (
    "palette",
    "typography",
    "space",
    "radius",
    "border",
    "opacity",
    "layer",
    "motion",
    "icon",
    "wordmark",
)
"""Top-level groups whose leaves become one custom property each, mechanically."""
NOT_EMITTED = {("motion", "pattern")}
"""Sub-groups of :data:`PLAIN` that are read by this script and are not custom properties."""
RECORDS = {("typography", "fonts"), ("contrast", "pairs")}
"""The two places where the source holds a list of records and not a tree of tokens."""
TYPES = {
    "angle",
    "boolean",
    "color",
    "dimension",
    "duration",
    "easing",
    "fontFamily",
    "fontWeight",
    "keyframes",
    "keyword",
    "number",
    "pattern",
    "shadow",
    "shape",
}
SHAPE_PARAMETERS = (
    "radius",
    "fill",
    "border-style",
    "rotate",
    "scale-y",
    "cut-a",
    "cut-b",
    "dot",
)
PATTERN_PARAMETERS = ("keyframes", "duration", "easing", "iterations", "direction")

ALIAS = re.compile(r"^\{([^{}]+)\}$")
OPAQUE = re.compile(r"^#[0-9A-Fa-f]{6}$")
KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]*$")
"""A key of a list travels verbatim into a selector and into markup: nothing that needs escaping."""

Tokens = Mapping[str, Any]


# ----------------------------------------------------------------------------------------
# Reading the tree
# ----------------------------------------------------------------------------------------


def is_leaf(node: object) -> bool:
    return isinstance(node, dict) and "$value" in node


def leaves(node: object, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], dict]]:
    """Every leaf under ``node``, in the order of the file, with its path."""
    if is_leaf(node):
        assert isinstance(node, dict)
        yield path, node
        return
    if path in RECORDS:
        return
    if not isinstance(node, dict):
        raise ValueError(f"{'.'.join(path)}: a group must be an object, found {node!r}")
    for key, child in node.items():
        if key.startswith("$"):
            continue
        yield from leaves(child, (*path, key))


def entries(node: Mapping[str, Any]) -> dict[str, Any]:
    """The children of a group, without its ``$description``: what a list or a style *has*."""
    return {key: child for key, child in node.items() if not key.startswith("$")}


def node_at(tokens: Tokens, path: Sequence[str], theme: str) -> object:
    """The node an alias names. A themed path is looked up inside ``theme``."""
    node: object = tokens[theme] if path[0] in THEMED else tokens
    for part in path:
        if not isinstance(node, dict) or part not in node:
            raise ValueError(f"alias {{{'.'.join(path)}}} names nothing")
        node = node[part]
    return node


def target_of(value: object) -> tuple[str, ...] | None:
    """The path an alias points at, or ``None`` when the value is not an alias."""
    if isinstance(value, str) and (found := ALIAS.match(value)) is not None:
        return tuple(found.group(1).split("."))
    return None


def resolve(tokens: Tokens, value: object, theme: str) -> object:
    """Follow aliases to a literal. A cycle is refused rather than followed."""
    seen: list[tuple[str, ...]] = []
    while (path := target_of(value)) is not None:
        if path in seen:
            raise ValueError(f"alias cycle through {{{'.'.join(path)}}}")
        seen.append(path)
        node = node_at(tokens, path, theme)
        if not is_leaf(node):
            raise ValueError(f"alias {{{'.'.join(path)}}} names a group, not a token")
        assert isinstance(node, dict)
        value = node["$value"]
    return value


def group_at(tokens: Tokens, value: object, theme: str, kind: str) -> dict:
    """The group (a shape, a pattern) that a leaf of type ``kind`` aliases."""
    path = target_of(value)
    if path is None:
        raise ValueError(f"a {kind} must be an alias, found {value!r}")
    node = node_at(tokens, path, theme)
    if is_leaf(node) or not isinstance(node, dict):
        raise ValueError(f"{{{'.'.join(path)}}} is not a {kind}")
    return node


def normalised(part: str) -> str:
    """What CSS demands of an identifier, and nothing more: lower case, a hyphen for a space."""
    return part.lower().replace(" ", "-").replace("_", "-")


def css_name(path: Sequence[str]) -> str:
    return PREFIX + "-".join(normalised(part) for part in path)


def css_value(tokens: Tokens, leaf: dict, theme: str) -> str:
    """An alias stays an alias in CSS — ``var()`` — so the relation is visible where it is read."""
    value = leaf["$value"]
    if (path := target_of(value)) is not None:
        resolve(tokens, value, theme)
        return f"var({css_name(path)})"
    if isinstance(value, bool):
        raise ValueError("a boolean is a parameter of a shape, not a custom property")
    return str(value)


# ----------------------------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------------------------


def validate(tokens: Tokens, root: Path | None = None) -> None:
    """Refuse a malformed source with a sentence, before a byte is derived from it."""
    for theme in THEMES:
        if theme not in tokens:
            raise ValueError(f"the theme {theme!r} is missing")
    first, *others = (sorted(".".join(path) for path, _ in leaves(tokens[t])) for t in THEMES)
    for theme, keys in zip(THEMES[1:], others, strict=True):
        if keys != first:
            odd = sorted(set(keys) ^ set(first))
            raise ValueError(f"the themes {THEMES[0]!r} and {theme!r} differ in their keys: {odd}")

    for path, leaf in leaves({key: tokens[key] for key in tokens if not key.startswith("$")}):
        name = ".".join(path)
        if leaf.get("$type") not in TYPES:
            raise ValueError(f"{name}: unknown $type {leaf.get('$type')!r}")
        theme = path[0] if path[0] in THEMES else THEMES[0]
        if path[0] == "palette" and not OPAQUE.match(str(leaf["$value"])):
            raise ValueError(
                f"{name}: a palette colour is opaque #RRGGBB, found {leaf['$value']!r}"
            )
        if leaf["$type"] not in ("shape", "pattern"):
            resolve(tokens, leaf["$value"], theme)

    for group in LISTS:
        keys = list(entries(tokens.get(group, {})))
        if not keys:
            raise ValueError(f"the list {group!r} is missing or empty")
        for key in keys:
            if not KEY.match(key):
                raise ValueError(f"{group}: the key {key!r} cannot travel verbatim into CSS")
        collided = {normalised(key) for key in keys}
        if len(collided) != len(keys):
            raise ValueError(f"{group}: two keys are the same once normalised: {keys}")

    for key, entry in entries(tokens["state"]).items():
        shape = group_at(tokens, entry["shape"]["$value"], THEMES[0], "shape")
        missing = [name for name in SHAPE_PARAMETERS if name not in shape]
        if missing:
            raise ValueError(f"state {key!r}: its shape lacks {missing}")
        if entry["motion"]["$value"] != "none":
            pattern = group_at(tokens, entry["motion"]["$value"], THEMES[0], "pattern")
            missing = [name for name in PATTERN_PARAMETERS if name not in pattern]
            if missing:
                raise ValueError(f"state {key!r}: its motion lacks {missing}")

    for pair in tokens.get("contrast", {}).get("pairs", []):
        for side in ("fg", "bg"):
            for theme in THEMES:
                resolve(tokens, pair[side], theme)

    bands = list(entries(tokens["breakpoint"]))
    for prop, per_band in entries(tokens["grid"]).items():
        if not is_leaf(per_band) and list(entries(per_band)) != bands:
            raise ValueError(f"grid.{prop}: one value per breakpoint, in order: {bands}")

    if root is not None:
        for font in tokens["typography"].get("fonts", []):
            if not (root / font["file"]).is_file():
                raise ValueError(f"typography.fonts: {font['file']} is declared and is not there")


# ----------------------------------------------------------------------------------------
# tokens.css
# ----------------------------------------------------------------------------------------


def banner(comment_open: str, comment_close: str) -> str:
    return (
        f"{comment_open} GENERATED by scripts/generate_design_system.py from tokens.json."
        f" Do not edit: run `uv run python scripts/generate_design_system.py`. {comment_close}\n"
    )


def block(selector: str, declarations: Sequence[tuple[str, str]], indent: str = "") -> str:
    lines = [f"{indent}{selector} {{"]
    lines += [f"{indent}  {name}: {value};" for name, value in declarations]
    lines.append(f"{indent}}}")
    return "\n".join(lines) + "\n"


def plain_declarations(tokens: Tokens) -> list[tuple[str, str]]:
    found = []
    for group in PLAIN:
        for path, leaf in leaves(tokens.get(group, {}), (group,)):
            if path[:2] in NOT_EMITTED:
                continue
            found.append((css_name(path), css_value(tokens, leaf, THEMES[0])))
    return found


def themed_declarations(tokens: Tokens, theme: str) -> list[tuple[str, str]]:
    found = [("color-scheme", theme)]
    for path, leaf in leaves(tokens[theme]):
        found.append((css_name(path), css_value(tokens, leaf, theme)))
    return found


def band_declarations(tokens: Tokens, band: str) -> list[tuple[str, str]]:
    """The grid of one band: the custom property is the same, the value is the band's."""
    return [
        (css_name(("grid", prop)), str(per_band[band]["$value"]))
        for prop, per_band in entries(tokens["grid"]).items()
        if not is_leaf(per_band)
    ]


def shape_declarations(tokens: Tokens, entry: dict) -> list[tuple[str, str]]:
    shape = group_at(tokens, entry["shape"]["$value"], THEMES[0], "shape")
    colour = f"var({PREFIX}state-color)"

    def painted(name: str) -> str:
        return colour if shape[name]["$value"] else "transparent"

    return [
        (f"{PREFIX}state-fill", painted("fill")),
        (f"{PREFIX}state-radius", css_value(tokens, shape["radius"], THEMES[0])),
        (f"{PREFIX}state-border-style", str(shape["border-style"]["$value"])),
        (f"{PREFIX}state-rotate", str(shape["rotate"]["$value"])),
        (f"{PREFIX}state-scale-y", str(shape["scale-y"]["$value"])),
        (f"{PREFIX}state-cut-a", painted("cut-a")),
        (f"{PREFIX}state-cut-b", painted("cut-b")),
        (f"{PREFIX}state-dot", "1" if shape["dot"]["$value"] else "0"),
    ]


def motion_declarations(tokens: Tokens, entry: dict) -> list[tuple[str, str]]:
    value = entry["motion"]["$value"]
    if value == "none":
        still = css_name(("motion", "easing", "standard"))
        return [
            (f"{PREFIX}state-motion", "none"),
            (f"{PREFIX}state-motion-duration", "0s"),
            (f"{PREFIX}state-motion-easing", f"var({still})"),
            (f"{PREFIX}state-motion-iterations", "1"),
            (f"{PREFIX}state-motion-direction", "normal"),
        ]
    pattern = group_at(tokens, value, THEMES[0], "pattern")
    return [
        (f"{PREFIX}state-motion", str(pattern["keyframes"]["$value"])),
        (f"{PREFIX}state-motion-duration", css_value(tokens, pattern["duration"], THEMES[0])),
        (f"{PREFIX}state-motion-easing", css_value(tokens, pattern["easing"], THEMES[0])),
        (f"{PREFIX}state-motion-iterations", str(pattern["iterations"]["$value"])),
        (f"{PREFIX}state-motion-direction", str(pattern["direction"]["$value"])),
    ]


def list_rules(tokens: Tokens) -> str:
    """One rule per key: the three lists exist in ``tokens.json`` and nowhere else."""
    out = []
    for key, entry in entries(tokens["state"]).items():
        declarations = [(f"{PREFIX}state-color", css_value(tokens, entry["color"], THEMES[0]))]
        declarations += shape_declarations(tokens, entry)
        declarations += motion_declarations(tokens, entry)
        out.append(block(f'[{LISTS["state"]}="{key}"]', declarations))
    for group in ("risk", "attention"):
        keys = list(entries(tokens[group]))
        for step, key in enumerate(keys, start=1):
            declarations = [
                (f"{PREFIX}level-color", css_value(tokens, tokens[group][key]["color"], THEMES[0])),
                (f"{PREFIX}level-step", str(step)),
                (f"{PREFIX}level-steps", str(len(keys))),
            ]
            out.append(block(f'[{LISTS[group]}="{key}"]', declarations))
    return "\n".join(out)


def font_faces(tokens: Tokens) -> str:
    """Relative ``url()`` only, never ``local()``: an installed copy may be another version."""
    out = []
    for font in tokens["typography"].get("fonts", []):
        declarations = [
            ("font-family", f'"{font["family"]}"'),
            ("font-style", font["style"]),
            ("font-weight", font["weight"]),
            ("font-display", "swap"),
            ("src", f'url("{font["file"]}") format("woff2")'),
        ]
        out.append(block("@font-face", declarations))
    return "\n".join(out)


def render_tokens_css(tokens: Tokens) -> str:
    default, *rest = THEMES
    bands = list(entries(tokens["breakpoint"]))
    target = tokens["target"]["min"]
    durations = [
        (css_name(path), "0s")
        for path, _ in leaves(tokens["motion"]["duration"], ("motion", "duration"))
    ]

    root = plain_declarations(tokens)
    root += band_declarations(tokens, bands[0])
    root += [
        (css_name(("grid", prop)), css_value(tokens, leaf, default))
        for prop, leaf in entries(tokens["grid"]).items()
        if is_leaf(leaf)
    ]
    root.append((css_name(("target", "min")), str(target["pointer"]["$value"])))

    parts = [banner("/*", "*/")]
    if faces := font_faces(tokens):
        parts.append(faces)
    parts.append(block(":root", root))
    parts.append(block(f':root, [data-theme="{default}"]', themed_declarations(tokens, default)))
    for theme in rest:
        parts.append(block(f'[data-theme="{theme}"]', themed_declarations(tokens, theme)))
    for band in bands[1:]:
        width = tokens["breakpoint"][band]["$value"]
        inner = block(":root", band_declarations(tokens, band), indent="  ")
        parts.append(f"@media (min-width: {width}) {{\n{inner}}}\n")
    touch = block(":root", [(css_name(("target", "min")), str(target["touch"]["$value"]))], "  ")
    parts.append(f"@media (pointer: coarse) {{\n{touch}}}\n")
    still = block(":root", durations, indent="  ")
    parts.append(f"@media (prefers-reduced-motion: reduce) {{\n{still}}}\n")
    parts.append(list_rules(tokens))
    return "\n".join(parts)


# ----------------------------------------------------------------------------------------
# specimen-switch.css — what only the specimen page needs, and cannot be written by hand:
# the whole-page theme switch, and one rule per token the page shows as a sample. A sample is
# not a reader of its token — it would make "no orphan token" true by construction — which
# is why these rules are derived here and do not count, instead of being written in
# specimen.css where they would.
# ----------------------------------------------------------------------------------------


def switch_id(theme: str) -> str:
    return f"specimen-theme-{theme}"


def swatch_class(path: Sequence[str]) -> str:
    return "specimen-swatch--" + css_name(path).removeprefix(PREFIX)


def colour_paths(tokens: Tokens) -> list[tuple[str, ...]]:
    """Every colour that has a custom property: the palette, then the semantic ones."""
    found = [path for path, leaf in leaves(tokens["palette"], ("palette",))]
    found += [path for path, leaf in leaves(tokens[THEMES[0]]["color"], ("color",))]
    return found


def render_switch_css(tokens: Tokens) -> str:
    parts = [banner("/*", "*/")]
    for theme in THEMES[1:]:
        selector = f":root:has(#{switch_id(theme)}:checked)"
        parts.append(block(selector, themed_declarations(tokens, theme)))
    for path in colour_paths(tokens):
        parts.append(block(f".{swatch_class(path)}", [("--_swatch", f"var({css_name(path)})")]))
    for group in ("space", "radius"):
        for path, _ in leaves(tokens[group], (group,)):
            parts.append(block(f".{step_class(path)}", [("--_step", f"var({css_name(path)})")]))
    for name, style in entries(tokens["typography"]["style"]).items():
        declarations = [
            (f"--_{prop}", f"var({css_name(('typography', 'style', name, prop))})")
            for prop in entries(style)
        ]
        parts.append(block(f".specimen-type--{normalised(name)}", declarations))
    return "\n".join(parts)


# ----------------------------------------------------------------------------------------
# index.html
# ----------------------------------------------------------------------------------------

EACH = re.compile(r'\s+data-ela-each="([a-z]+)"')


def fragments(root: Path) -> dict[str, str]:
    """The canonical markup of every component, by name, in the order of the file names."""
    found = {
        path.stem: path.read_text(encoding="utf-8")
        for path in sorted((root / FRAGMENTS).glob("*.html"))
    }
    if not found:
        raise ValueError(f"{root / FRAGMENTS} holds no fragment")
    return found


def instances(tokens: Tokens, markup: str, suffix: str) -> str:
    """A fragment as the page shows it: once, or once per key of the list it names.

    ``{key}`` is the key, verbatim. ``{id}`` is different for every copy: the same fragment
    rendered twice would otherwise repeat its ``id``, and a ``<label for>`` would point at the
    field of the other copy.
    """
    each = EACH.search(markup)
    if each is None:
        return markup.replace("{id}", suffix)
    group = each.group(1)
    if group not in LISTS:
        raise ValueError(f'data-ela-each="{group}" names no list')
    bare = EACH.sub("", markup, count=1)
    copies = [
        bare.replace("{key}", escape(key)).replace("{id}", f"{suffix}-{index}")
        for index, key in enumerate(entries(tokens[group]), start=1)
    ]
    return "".join(copies)


def indent(markup: str, spaces: int) -> str:
    pad = " " * spaces
    return "".join(f"{pad}{line}\n" if line.strip() else "\n" for line in markup.splitlines())


def themed_panels(tokens: Tokens, name: str, markup: str) -> str:
    """Every component twice, side by side: a theme is one attribute on any ancestor."""
    out = [f'<div class="specimen-pair" id="component-{name}">\n']
    for theme in THEMES:
        out.append(f'  <div class="specimen-pair__side" data-theme="{theme}">\n')
        out.append(f'    <p class="specimen-pair__theme">{theme}</p>\n')
        out.append(indent(instances(tokens, markup, f"-{name}-{theme}"), 4))
        out.append("  </div>\n")
    out.append("</div>\n")
    return "".join(out)


def component_sections(tokens: Tokens, found: Mapping[str, str]) -> dict[str, str]:
    """The fragments, sorted into the sections of the page by the list they repeat."""
    sections = {"components": "", "state": "", "risk": "", "attention": ""}
    for name, markup in found.items():
        each = EACH.search(markup)
        section = each.group(1) if each is not None else "components"
        if section not in sections:
            raise ValueError(f'{name}.html: data-ela-each="{section}" names no list')
        sections[section] += f'<h3 class="specimen-heading">{escape(name)}</h3>\n'
        sections[section] += themed_panels(tokens, name, markup)
    return sections


def value_text(leaf: dict) -> str:
    value = leaf["$value"]
    return escape(json.dumps(value) if isinstance(value, bool) else str(value))


def token_rows(tokens: Tokens, node: object, path: tuple[str, ...], named: bool = True) -> str:
    rows = []
    for leaf_path, leaf in leaves(node, path):
        label = css_name(leaf_path) if named else ".".join(leaf_path)
        rows.append(
            f'  <tr><th scope="row"><code>{escape(label)}</code></th>'
            f"<td><code>{value_text(leaf)}</code></td></tr>\n"
        )
    return '<table class="specimen-table">\n' + "".join(rows) + "</table>\n"


def swatches(tokens: Tokens, node: object, path: tuple[str, ...]) -> str:
    items = []
    for leaf_path, leaf in leaves(node, path):
        items.append(
            f'  <li class="specimen-swatch {swatch_class(leaf_path)}">'
            f'<span class="specimen-swatch__chip"></span>'
            f"<code>{escape(css_name(leaf_path))}</code>"
            f"<code>{value_text(leaf)}</code></li>\n"
        )
    return '<ul class="specimen-swatches">\n' + "".join(items) + "</ul>\n"


def text_styles(tokens: Tokens) -> str:
    out = []
    for name in entries(tokens["typography"]["style"]):
        out.append(
            f'<p class="specimen-type specimen-type--{normalised(name)}">'
            f"<code>{escape(name)}</code> ELA is present. 0123456789</p>\n"
        )
    return "".join(out)


def step_class(path: Sequence[str]) -> str:
    return "specimen-step--" + css_name(path).removeprefix(PREFIX)


def steps(tokens: Tokens, group: str) -> str:
    """A scale shown as geometry: one element per token, sized by the token itself."""
    items = []
    for path, leaf in leaves(tokens[group], (group,)):
        items.append(
            f'  <li class="specimen-step specimen-step--{group} {step_class(path)}">'
            f'<span class="specimen-step__bar"></span>'
            f"<code>{escape(css_name(path))}</code><code>{value_text(leaf)}</code></li>\n"
        )
    return '<ul class="specimen-steps">\n' + "".join(items) + "</ul>\n"


def keylines(tokens: Tokens) -> str:
    """The iconography rules as geometry: the grid with its live area, then one box per size."""
    boxes = ['  <li class="specimen-keyline"><span class="specimen-keyline__live"></span></li>\n']
    for name in entries(tokens["icon"]["size"]):
        boxes.append(
            f'  <li class="specimen-keyline specimen-keyline--{normalised(name)}">'
            f'<span class="specimen-keyline__live"></span></li>\n'
        )
    return '<ul class="specimen-keylines">\n' + "".join(boxes) + "</ul>\n"


def section(identifier: str, title: str, body: str) -> str:
    return (
        f'<section class="specimen-section" id="{identifier}">\n'
        f'  <h2 class="specimen-title">{escape(title)}</h2>\n{indent(body, 2)}</section>\n'
    )


def theme_switch() -> str:
    """Radio inputs read with ``:has()``: the whole page in one theme, and no JavaScript."""
    out = [
        '<fieldset class="specimen-switch">\n'
        '  <legend class="specimen-switch__legend">Theme</legend>\n'
    ]
    for index, theme in enumerate(THEMES):
        checked = " checked" if index == 0 else ""
        out.append(
            f'  <label class="specimen-switch__option" for="{switch_id(theme)}">'
            f'<input class="specimen-switch__input" type="radio" name="specimen-theme"'
            f' id="{switch_id(theme)}"{checked}> {theme}</label>\n'
        )
    out.append("</fieldset>\n")
    return "".join(out)


def render_index_html(tokens: Tokens, found: Mapping[str, str]) -> str:
    parts = component_sections(tokens, found)
    bands = "".join(
        f'<span class="specimen-band specimen-band--{normalised(band)}">{escape(band)}</span>\n'
        for band in entries(tokens["breakpoint"])
    )
    columns = "".join('<span class="specimen-grid__column"></span>\n' for _ in range(12))
    body = [
        section(
            "identity",
            "Identity",
            '<p class="specimen-lead">The wordmark is type, not a drawing: the word, in the'
            " family of the system. Colour is reserved for what means something — state, risk,"
            " attention. Everything else is neutral.</p>\n"
            + '<h3 class="specimen-heading">palette</h3>\n'
            + swatches(tokens, tokens["palette"], ("palette",)),
        ),
        section(
            "color",
            "Color",
            "".join(
                f'<div class="specimen-theme" data-theme="{theme}">\n'
                f'  <p class="specimen-pair__theme">{theme}</p>\n'
                + indent(swatches(tokens, tokens[theme]["color"], ("color",)), 2)
                + "</div>\n"
                for theme in THEMES
            ),
        ),
        section(
            "typography",
            "Typography",
            text_styles(tokens)
            + token_rows(tokens, tokens["typography"]["family"], ("typography", "family"))
            + token_rows(tokens, tokens["typography"]["style"], ("typography", "style"))
            + token_rows(tokens, tokens["wordmark"], ("wordmark",)),
        ),
        section(
            "space",
            "Space, radius, border",
            steps(tokens, "space")
            + steps(tokens, "radius")
            + token_rows(tokens, tokens["border"], ("border",))
            + token_rows(tokens, tokens["opacity"], ("opacity",))
            + token_rows(tokens, tokens["layer"], ("layer",)),
        ),
        section(
            "elevation",
            "Elevation and shadow",
            "".join(
                f'<div class="specimen-theme" data-theme="{theme}">\n'
                f'  <p class="specimen-pair__theme">{theme}</p>\n'
                + indent(token_rows(tokens, tokens[theme]["elevation"], ("elevation",)), 2)
                + indent(token_rows(tokens, tokens[theme]["shadow"], ("shadow",)), 2)
                + "</div>\n"
                for theme in THEMES
            ),
        ),
        section("components", "Components", parts["components"]),
        section("states", "States of ELA", parts["state"]),
        section("risk", "Risk", parts["risk"]),
        section("attention", "Attention", parts["attention"]),
        section(
            "motion",
            "Motion",
            '<p class="specimen-lead">Durations and easings are tokens, and nothing else moves.'
            " With “reduce motion” on, every duration becomes zero and no animation is"
            " declared: a state is still told by its key, and within a colour by its shape.</p>\n"
            + token_rows(tokens, tokens["motion"]["duration"], ("motion", "duration"))
            + token_rows(tokens, tokens["motion"]["easing"], ("motion", "easing"))
            + token_rows(tokens, tokens["motion"]["pattern"], ("motion", "pattern"), named=False),
        ),
        section(
            "responsive",
            "Responsive",
            '<p class="specimen-lead">Three bands, phone first. This page is in: </p>\n'
            + f'<p class="specimen-bands">\n{indent(bands, 2)}</p>\n'
            + f'<div class="specimen-grid">\n{indent(columns, 2)}</div>\n'
            + token_rows(tokens, tokens["breakpoint"], ("breakpoint",), named=False)
            + token_rows(tokens, tokens["grid"], ("grid",), named=False)
            + token_rows(tokens, tokens["target"], ("target",), named=False),
        ),
        section(
            "iconography",
            "Iconography",
            '<p class="specimen-lead">Rules only: a grid, a live area, a stroke, three sizes.'
            " No icon is drawn here — icons arrive with the views that use them.</p>\n"
            + keylines(tokens)
            + token_rows(tokens, tokens["icon"], ("icon",)),
        ),
    ]
    links = "".join(
        f'    <a class="specimen-nav__link" href="#{identifier}">{escape(label)}</a>\n'
        for identifier, label in (
            ("identity", "Identity"),
            ("color", "Color"),
            ("typography", "Typography"),
            ("space", "Space"),
            ("elevation", "Elevation"),
            ("components", "Components"),
            ("states", "States"),
            ("risk", "Risk"),
            ("attention", "Attention"),
            ("motion", "Motion"),
            ("responsive", "Responsive"),
            ("iconography", "Iconography"),
        )
    )
    stylesheets = "".join(
        f'  <link rel="stylesheet" href="{name}">\n'
        for name in ("tokens.css", "components.css", "specimen.css", "specimen-switch.css")
    )
    return (
        "<!DOCTYPE html>\n"
        + banner("<!--", "-->")
        + '<html lang="en">\n<head>\n  <meta charset="utf-8">\n'
        + '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        + "  <title>ELA — Design System</title>\n"
        + stylesheets
        + '</head>\n<body class="specimen">\n'
        + '<header class="specimen-header">\n'
        + '  <h1 class="specimen-header__title"><span class="ela-wordmark ela-wordmark--lg">ELA'
        + '</span> <span class="specimen-header__subtitle">Design System</span></h1>\n'
        + indent(theme_switch(), 2)
        + f'  <nav class="specimen-nav" aria-label="Sections">\n{links}  </nav>\n'
        + "</header>\n<main>\n"
        + "".join(body)
        + "</main>\n</body>\n</html>\n"
    )


# ----------------------------------------------------------------------------------------
# The files
# ----------------------------------------------------------------------------------------


def load(root: Path) -> dict:
    return json.loads((root / SOURCE).read_text(encoding="utf-8"))


def render_all(root: Path) -> dict[str, bytes]:
    """Every derived file, by name. Pure: it reads the source and the fragments, writes nothing."""
    tokens = load(root)
    validate(tokens, root)
    rendered = {
        "tokens.css": render_tokens_css(tokens),
        "specimen-switch.css": render_switch_css(tokens),
        "index.html": render_index_html(tokens, fragments(root)),
    }
    assert tuple(rendered) == DERIVED
    return {name: text.encode("utf-8") for name, text in rendered.items()}


def stale(root: Path) -> list[str]:
    rendered = render_all(root)
    return [
        name
        for name, content in rendered.items()
        if not (root / name).is_file() or (root / name).read_bytes() != content
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if a derived file is stale")
    parser.add_argument("--root", type=Path, default=DESIGN_SYSTEM, help="the design system folder")
    arguments = parser.parse_args(argv)

    if arguments.check:
        behind = stale(arguments.root)
        for name in behind:
            print(f"{arguments.root / name}: stale — run scripts/generate_design_system.py")
        if not behind:
            print(f"{arguments.root}: up to date")
        return 1 if behind else 0

    for name, content in render_all(arguments.root).items():
        (arguments.root / name).write_bytes(content)
        print(f"wrote {arguments.root / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
