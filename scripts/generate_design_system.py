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

A fourth thing is a decision and not a limit: **the three lists exist only in the source**. One
rule per key of ``state``, ``risk`` and ``attention`` is derived, and ``components.css`` reads the
generic properties that rule sets. For a state those properties are the light of ELA's sphere —
its colour, its rhythm, its intensity, its core.

The script depends on nothing but the standard library and does not import ``ela``: the design
system is not part of the Core. It is seen by ``ruff`` and by its tests, not by ``mypy`` nor by
the coverage gate — the level of verification of everything in ``scripts/``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
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
COMPOSITIONS = "compositions"
"""Under :data:`FRAGMENTS`: screens rebuilt with nothing but the components. Not views."""
PARTIAL = "_"
"""A fragment whose name begins with this is included by others and never shown on its own."""

PREFIX = "--ela-"
THEMES = ("dark", "light")
"""The first is the default: it is the one ``:root`` carries."""
THEMED = ("color", "shadow")
"""What depends on the theme, and therefore lives under each theme with the same keys."""
LISTS = {"state": "data-ela-state", "risk": "data-ela-risk", "attention": "data-ela-attention"}
"""The three lists that exist only in ``tokens.json``, and the attribute that carries a key."""
LEVELS = ("risk", "attention")
PLAIN = (
    "palette",
    "typography",
    "space",
    "radius",
    "border",
    "opacity",
    "layer",
    "material",
    "glow",
    "frame",
    "motion",
    "icon",
    "wordmark",
    "control",
    "presence",
)
"""Top-level groups whose leaves become one custom property each, mechanically."""
NOT_EMITTED = {("motion", "pattern"), ("presence", "rest"), ("presence", "core", "kind")}
"""Sub-groups of :data:`PLAIN` that this script reads, and that are not custom properties."""
RECORDS = {("contrast", "pairs")}
"""The one place where the source holds a list of records and not a tree of tokens."""
TYPES = {
    "angle",
    "boolean",
    "color",
    "core",
    "dimension",
    "duration",
    "easing",
    "fontFamily",
    "fontWeight",
    "keyframes",
    "keyword",
    "light",
    "number",
    "pattern",
    "shadow",
}
GROUPS = {"core", "light", "pattern"}
"""Types whose value is the alias of a *group* — a kind of core, a role of light, a pattern."""
STATE_LEAVES = ("light", "text", "spin", "turning", "glow", "plasma", "core", "ambient")
LEVEL_LEAVES = ("color", "text")
LIGHT_PARTS = ("c", "c2", "veil")
CORE_PARTS = ("opacity", "inset", "motion")
PATTERN_PARAMETERS = ("keyframes", "duration", "easing", "iterations", "direction")

ALIAS = re.compile(r"^\{([^{}]+)\}$")
OPAQUE = re.compile(r"^#[0-9A-Fa-f]{6}$")
KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]*$")
"""A key of a list travels verbatim into a selector and into markup: nothing that needs escaping."""
INCLUDE = re.compile(r"\{include:([a-z0-9_-]+)\}")
EACH = re.compile(r'\s+data-ela-each="([a-z]+)"')

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
    return colour_of(tokens, value, theme)[0]


def colour_of(tokens: Tokens, value: object, theme: str) -> tuple[object, float]:
    """The literal an alias ends in, and the alpha gathered on the way (1 when there is none)."""
    seen: list[tuple[str, ...]] = []
    alpha = 1.0
    while (path := target_of(value)) is not None:
        if path in seen:
            raise ValueError(f"alias cycle through {{{'.'.join(path)}}}")
        seen.append(path)
        node = node_at(tokens, path, theme)
        if not is_leaf(node):
            raise ValueError(f"alias {{{'.'.join(path)}}} names a group, not a token")
        assert isinstance(node, dict)
        alpha *= float(node.get("$alpha", 1))
        value = node["$value"]
    return value, alpha


def group_at(tokens: Tokens, value: object, theme: str, kind: str) -> dict:
    """The group — a role of light, a kind of core, a pattern — a leaf of type ``kind`` aliases."""
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


def with_alpha(colour: str, alpha: float) -> str:
    """``#RRGGBB`` and an alpha as ``#RRGGBBAA``: what a semantic colour with ``$alpha`` becomes."""
    return f"{colour.upper()}{round(alpha * 255):02X}"


def css_value(tokens: Tokens, leaf: dict, theme: str) -> str:
    """An alias stays an alias in CSS — ``var()`` — so the relation is visible where it is read.

    The exception is a colour that carries ``$alpha``: CSS has no way to thin out a custom
    property without a colour function, so the generator composes the eight digits itself.
    """
    value = leaf["$value"]
    if "$alpha" in leaf:
        return with_alpha(str(resolve(tokens, value, theme)), float(leaf["$alpha"]))
    if (path := target_of(value)) is not None:
        resolve(tokens, value, theme)
        return f"var({css_name(path)})"
    if isinstance(value, bool):
        raise ValueError("a boolean is a parameter of a state, not a custom property")
    return str(value)


# ----------------------------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------------------------


def validate_colour(tokens: Tokens, name: str, path: tuple[str, ...], leaf: dict) -> None:
    theme = path[0] if path[0] in THEMES else THEMES[0]
    literal = str(resolve(tokens, leaf["$value"], theme))
    if not OPAQUE.match(literal):
        raise ValueError(
            f"{name}: a colour is opaque #RRGGBB or an alias of one, found {literal!r}"
        )
    if "$alpha" not in leaf:
        return
    if path[0] == "palette":
        raise ValueError(f"{name}: the palette is opaque — $alpha belongs to a semantic colour")
    if not isinstance(leaf["$alpha"], int | float) or not 0 <= leaf["$alpha"] <= 1:
        raise ValueError(f"{name}: $alpha is a number between 0 and 1, found {leaf['$alpha']!r}")
    if colour_of(tokens, leaf["$value"], theme)[1] != 1:
        raise ValueError(f"{name}: $alpha over a colour that already has one")


def validate_pattern(tokens: Tokens, owner: str, value: object) -> None:
    if value == "none":
        return
    pattern = group_at(tokens, value, THEMES[0], "pattern")
    missing = [name for name in PATTERN_PARAMETERS if name not in pattern]
    if missing:
        raise ValueError(f"{owner}: its pattern lacks {missing}")


def validate_text(owner: str, leaf: dict) -> None:
    path = target_of(leaf["$value"])
    if path is None or path[:2] != ("color", "text"):
        raise ValueError(f"{owner}: the colour of a key is a text colour, found {leaf['$value']!r}")


def validate(tokens: Tokens) -> None:
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
        kind = leaf.get("$type")
        if kind not in TYPES:
            raise ValueError(f"{name}: unknown $type {kind!r}")
        if kind == "color":
            validate_colour(tokens, name, path, leaf)
        elif "$alpha" in leaf:
            raise ValueError(f"{name}: $alpha belongs to a colour")
        elif kind not in GROUPS:
            resolve(tokens, leaf["$value"], path[0] if path[0] in THEMES else THEMES[0])

    for group in LISTS:
        keys = list(entries(tokens.get(group, {})))
        if not keys:
            raise ValueError(f"the list {group!r} is missing or empty")
        for key in keys:
            if not KEY.match(key):
                raise ValueError(f"{group}: the key {key!r} cannot travel verbatim into CSS")
        if len({normalised(key) for key in keys}) != len(keys):
            raise ValueError(f"{group}: two keys are the same once normalised: {keys}")

    for key, entry in entries(tokens["state"]).items():
        owner = f"state {key!r}"
        missing = [name for name in STATE_LEAVES if name not in entry]
        if missing:
            raise ValueError(f"{owner} lacks {missing}")
        light = group_at(tokens, entry["light"]["$value"], THEMES[0], "light")
        if [name for name in LIGHT_PARTS if name not in light]:
            raise ValueError(f"{owner}: its light lacks one of {list(LIGHT_PARTS)}")
        core = group_at(tokens, entry["core"]["$value"], THEMES[0], "core")
        if [name for name in CORE_PARTS if name not in core]:
            raise ValueError(f"{owner}: its core lacks one of {list(CORE_PARTS)}")
        validate_pattern(tokens, f"{owner}, core", core["motion"]["$value"])
        validate_pattern(tokens, f"{owner}, ambient", entry["ambient"]["$value"])
        validate_text(owner, entry["text"])

    for group in LEVELS:
        for key, entry in entries(tokens[group]).items():
            if [name for name in LEVEL_LEAVES if name not in entry]:
                raise ValueError(f"{group} {key!r} lacks one of {list(LEVEL_LEAVES)}")
            validate_text(f"{group} {key!r}", entry["text"])

    rest = tokens["presence"]["rest"]["$value"]
    if rest not in entries(tokens["state"]):
        raise ValueError(f"presence.rest: {rest!r} is not a state")

    for pair in tokens.get("contrast", {}).get("pairs", []):
        for side in ("fg", "bg"):
            for theme in THEMES:
                resolve(tokens, pair[side], theme)

    bands = list(entries(tokens["breakpoint"]))
    for prop, per_band in entries(tokens["grid"]).items():
        if not is_leaf(per_band) and list(entries(per_band)) != bands:
            raise ValueError(f"grid.{prop}: one value per breakpoint, in order: {bands}")


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
            if any(path[: len(skipped)] == skipped for skipped in NOT_EMITTED):
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


def motion_declarations(tokens: Tokens, value: object, prefix: str) -> list[tuple[str, str]]:
    """The five properties an ``animation`` reads, under ``prefix``; stillness when ``none``."""
    if value == "none":
        still = css_name(("motion", "easing", "standard"))
        return [
            (prefix, "none"),
            (f"{prefix}-duration", "0s"),
            (f"{prefix}-easing", f"var({still})"),
            (f"{prefix}-iterations", "1"),
            (f"{prefix}-direction", "normal"),
        ]
    pattern = group_at(tokens, value, THEMES[0], "pattern")
    return [
        (prefix, str(pattern["keyframes"]["$value"])),
        (f"{prefix}-duration", css_value(tokens, pattern["duration"], THEMES[0])),
        (f"{prefix}-easing", css_value(tokens, pattern["easing"], THEMES[0])),
        (f"{prefix}-iterations", str(pattern["iterations"]["$value"])),
        (f"{prefix}-direction", str(pattern["direction"]["$value"])),
    ]


def state_declarations(tokens: Tokens, entry: dict) -> list[tuple[str, str]]:
    """A state is the light of the sphere: its colour, its rhythm, its intensity, its core —
    and the colour of its key as text, which is what says the state where no sphere is seen."""
    light_path = target_of(entry["light"]["$value"])
    assert light_path is not None
    core = group_at(tokens, entry["core"]["$value"], THEMES[0], "core")
    declarations = [
        (f"{PREFIX}state-light", f"var({css_name((*light_path, 'c'))})"),
        (f"{PREFIX}state-light-soft", f"var({css_name((*light_path, 'c2'))})"),
        (f"{PREFIX}state-light-veil", f"var({css_name((*light_path, 'veil'))})"),
        (f"{PREFIX}state-text", css_value(tokens, entry["text"], THEMES[0])),
        (f"{PREFIX}state-spin", css_value(tokens, entry["spin"], THEMES[0])),
        (f"{PREFIX}state-play", "running" if entry["turning"]["$value"] else "paused"),
        (f"{PREFIX}state-glow", str(entry["glow"]["$value"])),
        (f"{PREFIX}state-plasma", css_value(tokens, entry["plasma"], THEMES[0])),
        (f"{PREFIX}state-core-opacity", str(core["opacity"]["$value"])),
        (f"{PREFIX}state-core-inset", str(core["inset"]["$value"])),
    ]
    declarations += motion_declarations(
        tokens, core["motion"]["$value"], f"{PREFIX}state-core-motion"
    )
    declarations += motion_declarations(
        tokens, entry["ambient"]["$value"], f"{PREFIX}state-ambient-motion"
    )
    return declarations


def list_rules(tokens: Tokens) -> str:
    """One rule per key: the three lists exist in ``tokens.json`` and nowhere else."""
    out = []
    for key, entry in entries(tokens["state"]).items():
        out.append(block(f'[{LISTS["state"]}="{key}"]', state_declarations(tokens, entry)))
    longest = 0
    for group in LEVELS:
        keys = list(entries(tokens[group]))
        longest = max(longest, len(keys))
        for step, key in enumerate(keys, start=1):
            declarations = [
                (f"{PREFIX}level-color", css_value(tokens, tokens[group][key]["color"], THEMES[0])),
                (f"{PREFIX}level-text", css_value(tokens, tokens[group][key]["text"], THEMES[0])),
                (f"{PREFIX}level-step", str(step)),
            ]
            out.append(block(f'[{LISTS[group]}="{key}"]', declarations))
    for index in range(1, longest + 1):
        selector = f".ela-meter__segment:nth-child({index})"
        out.append(block(selector, [(f"{PREFIX}meter-index", str(index))]))
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


def step_class(path: Sequence[str]) -> str:
    return "specimen-step--" + css_name(path).removeprefix(PREFIX)


def colour_paths(tokens: Tokens) -> list[tuple[str, ...]]:
    """Every colour that has a custom property: the palette, then the semantic ones."""
    found = [path for path, _ in leaves(tokens["palette"], ("palette",))]
    found += [path for path, _ in leaves(tokens[THEMES[0]]["color"], ("color",))]
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
# The fragments
# ----------------------------------------------------------------------------------------


def read_fragments(folder: Path) -> dict[str, str]:
    return {path.stem: path.read_text(encoding="utf-8") for path in sorted(folder.glob("*.html"))}


def with_includes(markup: str, partials: Mapping[str, str]) -> str:
    """``{include:_orb}`` becomes the partial of that name. One level: a partial includes nothing.

    The sphere is seven layers of markup, and every component that shows it would otherwise
    carry a copy of them.
    """

    def replace(found: re.Match[str]) -> str:
        name = found.group(1)
        if name not in partials:
            raise ValueError(f"{{include:{name}}} names no partial")
        if INCLUDE.search(partials[name]):
            raise ValueError(f"the partial {name} includes another: one level only")
        return partials[name].strip()

    return INCLUDE.sub(replace, markup)


def fragments(root: Path) -> tuple[dict[str, str], dict[str, str]]:
    """The canonical markup of every component, and the compositions, by name, includes resolved.

    In the order of the file names. A name that begins with :data:`PARTIAL` is a partial.
    """
    found = read_fragments(root / FRAGMENTS)
    if not found:
        raise ValueError(f"{root / FRAGMENTS} holds no fragment")
    partials = {name: markup for name, markup in found.items() if name.startswith(PARTIAL)}
    components = {
        name: with_includes(markup, partials)
        for name, markup in found.items()
        if not name.startswith(PARTIAL)
    }
    compositions = {
        name: with_includes(markup, partials)
        for name, markup in read_fragments(root / FRAGMENTS / COMPOSITIONS).items()
    }
    return components, compositions


def instances(tokens: Tokens, markup: str, suffix: str, only: str | None = None) -> str:
    """A fragment as the page shows it: once, or once per key of the list it names — or for
    the one key ``only``, when the page wants a single state.

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
        if only is None or key == only
    ]
    if not copies:
        raise ValueError(f"{only!r} is not a key of {group}")
    return "".join(copies)


def indent(markup: str, spaces: int) -> str:
    pad = " " * spaces
    return "".join(f"{pad}{line}\n" if line.strip() else "\n" for line in markup.splitlines())


# ----------------------------------------------------------------------------------------
# index.html
# ----------------------------------------------------------------------------------------


def themed_panels(identifier: str, render: Callable[[str], str], stacked: bool = False) -> str:
    """Everything twice: a theme is one attribute on any ancestor, and each side is a room.

    ``render`` is given the suffix that makes the ids of each copy its own.
    """
    modifier = " specimen-pair--stacked" if stacked else ""
    out = [f'<div class="specimen-pair{modifier}" id="{identifier}">\n']
    for theme in THEMES:
        out.append(f'  <div class="specimen-pair__side ela-room" data-theme="{theme}">\n')
        out.append(f'    <p class="specimen-pair__theme ela-eyebrow">{theme}</p>\n')
        out.append(indent(render(f"-{identifier}-{theme}"), 4))
        out.append("  </div>\n")
    out.append("</div>\n")
    return "".join(out)


def heading(text: str) -> str:
    return f'<h3 class="specimen-heading ela-eyebrow">{escape(text)}</h3>\n'


def component_sections(tokens: Tokens, found: Mapping[str, str]) -> dict[str, str]:
    """The fragments, sorted into the sections of the page by the list they repeat.

    A list that more than one fragment repeats is shown **key by key** — for a state, the
    sphere in its three sizes and the small one of a row, together — because what is compared
    there is one key across its renderings. A list one fragment repeats is shown whole.
    """
    by_section: dict[str, dict[str, str]] = {"components": {}, **{group: {} for group in LISTS}}
    for name, markup in found.items():
        each = EACH.search(markup)
        section = each.group(1) if each is not None else "components"
        if section not in by_section:
            raise ValueError(f'{name}.html: data-ela-each="{section}" names no list')
        by_section[section][name] = markup

    sections = {}
    for section, fragments_of in by_section.items():
        out = []
        if section in LISTS and len(fragments_of) > 1:
            for index, key in enumerate(entries(tokens[section]), start=1):

                def one_key(
                    suffix: str, key: str = key, fragments_of: dict[str, str] = fragments_of
                ) -> str:
                    return "".join(
                        instances(tokens, markup, f"{suffix}-{name}", only=key)
                        for name, markup in fragments_of.items()
                    )

                out.append(heading(key))
                out.append(themed_panels(f"{section}-{index}", one_key))
        else:
            for name, markup in fragments_of.items():

                def whole(suffix: str, markup: str = markup) -> str:
                    return instances(tokens, markup, suffix)

                out.append(heading(name))
                out.append(themed_panels(f"component-{name}", whole))
        sections[section] = "".join(out)
    return sections


def composition_section(tokens: Tokens, found: Mapping[str, str]) -> str:
    out = []
    for name, markup in found.items():

        def whole(suffix: str, markup: str = markup) -> str:
            return instances(tokens, markup, suffix)

        out.append(heading(name))
        out.append(themed_panels(f"composition-{name}", whole, stacked=True))
    return "".join(out)


def value_text(leaf: dict) -> str:
    value = leaf["$value"]
    text = json.dumps(value) if isinstance(value, bool) else str(value)
    if "$alpha" in leaf:
        text += f" · α {leaf['$alpha']}"
    return escape(text)


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


def section(identifier: str, eyebrow: str, title: str, body: str, framed: bool = True) -> str:
    """A section of the page: its name, and its content on a pane of glass."""
    content = indent(body, 4)
    if framed:
        content = f'  <div class="specimen-pane ela-panel">\n{content}  </div>\n'
    return (
        f'<section class="specimen-section" id="{identifier}">\n'
        f'  <p class="ela-eyebrow">{escape(eyebrow)}</p>\n'
        f'  <h2 class="specimen-title ela-title">{escape(title)}</h2>\n{content}</section>\n'
    )


def lead(text: str) -> str:
    return f'<p class="specimen-lead ela-body">{text}</p>\n'


def theme_switch() -> str:
    """Radio inputs read with ``:has()``: the whole page in one theme, and no JavaScript."""
    out = [
        '<div class="specimen-switch" role="radiogroup" aria-labelledby="specimen-switch-label">\n'
        '  <span class="specimen-switch__legend ela-eyebrow" id="specimen-switch-label">Theme'
        "</span>\n"
    ]
    for index, theme in enumerate(THEMES):
        checked = " checked" if index == 0 else ""
        out.append(
            f'  <label class="specimen-switch__option ela-caption" for="{switch_id(theme)}">'
            f'<input class="specimen-switch__input" type="radio" name="specimen-theme"'
            f' id="{switch_id(theme)}"{checked}> {theme}</label>\n'
        )
    out.append("</div>\n")
    return "".join(out)


def themed(tokens: Tokens, render: Callable[[str], str]) -> str:
    return "".join(
        f'<div class="specimen-theme" data-theme="{theme}">\n'
        f'  <p class="specimen-pair__theme ela-eyebrow">{theme}</p>\n'
        + indent(render(theme), 2)
        + "</div>\n"
        for theme in THEMES
    )


def render_index_html(
    tokens: Tokens, found: Mapping[str, str], compositions: Mapping[str, str]
) -> str:
    parts = component_sections(tokens, found)
    rest = str(tokens["presence"]["rest"]["$value"])
    bands = "".join(
        f'<span class="specimen-band specimen-band--{normalised(band)} ela-key">'
        f"{escape(band)}</span>\n"
        for band in entries(tokens["breakpoint"])
    )
    columns = "".join('<span class="specimen-grid__column"></span>\n' for _ in range(12))
    sections = [
        (
            "identity",
            "Identity",
            "A sphere of light, held in glass",
            lead(
                "Apple's calm, a JARVIS of light: azure and white for everything, premium. The"
                " sphere is ELA. A dark glass shell, a white core, azure light turning inside;"
                " three sizes, one object. The state is the light — its colour, its rhythm, its"
                " intensity — and always the key, as text. The wordmark is type, not a drawing."
            )
            + heading("palette")
            + swatches(tokens, tokens["palette"], ("palette",)),
        ),
        (
            "color",
            "Tokens",
            "Color",
            themed(tokens, lambda theme: swatches(tokens, tokens[theme]["color"], ("color",))),
        ),
        (
            "typography",
            "Tokens",
            "Typography",
            text_styles(tokens)
            + token_rows(tokens, tokens["typography"]["family"], ("typography", "family"))
            + token_rows(tokens, tokens["typography"]["style"], ("typography", "style"))
            + token_rows(tokens, tokens["wordmark"], ("wordmark",)),
        ),
        (
            "space",
            "Tokens",
            "Space, radius, border",
            steps(tokens, "space")
            + steps(tokens, "radius")
            + token_rows(tokens, tokens["border"], ("border",))
            + token_rows(tokens, tokens["opacity"], ("opacity",))
            + token_rows(tokens, tokens["layer"], ("layer",))
            + token_rows(tokens, tokens["control"], ("control",))
            + token_rows(tokens, tokens["glow"], ("glow",))
            + token_rows(tokens, tokens["frame"], ("frame",)),
        ),
        (
            "material",
            "Tokens",
            "Materials: glass and the room",
            lead(
                "Glass is a pane of low-opacity white with a hairline of light, and what is"
                " behind it blurred and saturated. The room is an almost black blue with two"
                " cold lights. Gradients live here, in the sphere and in the primary action —"
                " and nowhere else — and every stop is a token."
            )
            + token_rows(tokens, tokens["material"], ("material",))
            + themed(
                tokens, lambda theme: token_rows(tokens, tokens[theme]["shadow"], ("shadow",))
            ),
        ),
        (
            "presence",
            "Tokens",
            "The sphere",
            token_rows(tokens, tokens["presence"], ("presence",), named=False),
        ),
        ("components", "Components", "Components", parts["components"]),
        ("states", "The three lists", "States of ELA", parts["state"]),
        ("risk", "The three lists", "Risk", parts["risk"]),
        ("attention", "The three lists", "Attention", parts["attention"]),
        (
            "motion",
            "Tokens",
            "Motion",
            lead(
                "Durations and easings are tokens, and nothing else moves. With “reduce"
                " motion” on, every duration becomes zero and no animation is declared: the"
                " light stands still, and the colour and the word beneath still say everything."
            )
            + token_rows(tokens, tokens["motion"]["duration"], ("motion", "duration"))
            + token_rows(tokens, tokens["motion"]["easing"], ("motion", "easing"))
            + token_rows(tokens, tokens["motion"]["pattern"], ("motion", "pattern"), named=False),
        ),
        (
            "responsive",
            "Rules",
            "Responsive",
            lead("Three bands, phone first. This page is in:")
            + f'<p class="specimen-bands">\n{indent(bands, 2)}</p>\n'
            + f'<div class="specimen-grid">\n{indent(columns, 2)}</div>\n'
            + token_rows(tokens, tokens["breakpoint"], ("breakpoint",), named=False)
            + token_rows(tokens, tokens["grid"], ("grid",), named=False)
            + token_rows(tokens, tokens["target"], ("target",), named=False),
        ),
        (
            "iconography",
            "Rules",
            "Iconography",
            lead(
                "Rules only: a grid, a live area, a stroke, three sizes. No icon is drawn here —"
                " icons arrive with the views that use them."
            )
            + keylines(tokens)
            + token_rows(tokens, tokens["icon"], ("icon",)),
        ),
    ]
    body = [
        section(identifier, eyebrow, title, text) for identifier, eyebrow, title, text in sections
    ]
    body.append(
        section(
            "compositions",
            "The proof that the components are enough",
            "Compositions",
            lead(
                "Four screens rebuilt with the components of the design system and nothing else."
                " They are not views — those belong to the Command Center and to the companion —"
                " they are the proof that the components are enough to compose them."
            )
            + composition_section(tokens, compositions),
            framed=False,
        )
    )
    links = "".join(
        f'    <a class="specimen-nav__link ela-caption" href="#{identifier}">{escape(title)}</a>\n'
        for identifier, _, title, _ in sections
    )
    links += '    <a class="specimen-nav__link ela-caption" href="#compositions">Compositions</a>\n'
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
        + '</head>\n<body class="specimen ela-room">\n'
        + '<header class="specimen-hero">\n'
        + indent(instances(tokens, found["presence-lg"], "-hero", only=rest), 2)
        + '  <h1 class="specimen-hero__title ela-eyebrow">Design System</h1>\n'
        + "</header>\n"
        + '<div class="specimen-bar ela-panel ela-panel--soft">\n'
        + indent(theme_switch(), 2)
        + f'  <nav class="specimen-nav" aria-label="Sections">\n{links}  </nav>\n'
        + "</div>\n<main>\n"
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
    validate(tokens)
    components, compositions = fragments(root)
    rendered = {
        "tokens.css": render_tokens_css(tokens),
        "specimen-switch.css": render_switch_css(tokens),
        "index.html": render_index_html(tokens, components, compositions),
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
