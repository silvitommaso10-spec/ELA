"""What a component promises (M17.1, criteri 10, 11 e 15; dec. D, dec. H, dec. J).

- **A key is always text.** It is what survives where no CSS arrives — the text of a push
  notification — and what carries WCAG 1.4.1: never colour alone, and never motion alone. The
  state is the light of the sphere — its colour, its rhythm, its intensity, its core — and no
  two states have the same light, compared on the **resolved** values in each theme. With
  reduced motion several states of ELA at work look alike, and that is declared: the word
  beneath says which.
- **The components are enough**: the compositions use classes of ``components.css`` and nothing
  else, and the meter has as many segments as the longer of its two lists.
- **Every interaction state exists, and its preview cannot drift**: a pseudo-class and its twin
  class live in the same selector list, so the specimen shows the real declarations.
- **Native elements**, which a keyboard already operates; ids that are unique, labels that
  point at their own field.
- **Targets**: every interactive element of the page — the fragments, and the page's own
  controls — takes its minimum size from the token, which is the touch size under
  ``pointer: coarse``.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from tests.design import markup, stylesheet
from tests.design.tree import compositions, fragments, generator, read, tokens

LIST_ATTRIBUTES = {
    "data-ela-state": "state",
    "data-ela-risk": "risk",
    "data-ela-attention": "attention",
}
INTERACTIVE = {"button", "input", "textarea", "select", "summary"}
FORM_CONTROLS = {"button", "input", "textarea", "select"}
TWINS = {":hover": ".is-hover", ":focus-visible": ".is-focus-visible", ":active": ".is-active"}
ROLES_OF_NATIVE_ELEMENTS = {"button", "link", "textbox", "checkbox", "radio", "switch", "combobox"}
TOUCH = "44px"
"""Dec. 5 of the user: the number is pinned here, not only in ``tokens.json``."""

Tokens = dict[str, Any]


def is_interactive(element: markup.Element) -> bool:
    return element.tag in INTERACTIVE or (element.tag == "a" and element.get("href") is not None)


# ----------------------------------------------------------------------------------------
# The key is text; colour and shape never coincide
# ----------------------------------------------------------------------------------------


def faults_in_keys(page: markup.Element, source: Tokens) -> list[str]:
    found = []
    rendered: dict[str, set[str]] = {group: set() for group in LIST_ATTRIBUTES.values()}
    for element in page.walk():
        for attribute, group in LIST_ATTRIBUTES.items():
            key = element.get(attribute)
            if key is None:
                continue
            if key not in generator().entries(source[group]):
                found.append(f'{attribute}="{key}": not a key of {group}')
            elif key not in element.text():
                found.append(f'{attribute}="{key}": the key is not rendered as text')
            rendered[group].add(key)
    for group, keys in rendered.items():
        missing = [key for key in generator().entries(source[group]) if key not in keys]
        found += [f"{group}: {key} is never rendered" for key in missing]
    return found


def signature(source: Tokens, key: str, theme: str) -> tuple[object, ...]:
    """The light of a state, resolved: everything its derived rule sets, but the colour of the
    text — two states may well share that."""
    module = generator()
    entry = source["state"][key]
    light = module.group_at(source, entry["light"]["$value"], theme, "light")
    core = module.group_at(source, entry["core"]["$value"], theme, "core")
    return (
        *(module.colour_of(source, light[part]["$value"], theme) for part in module.LIGHT_PARTS),
        *(module.resolve(source, entry[name]["$value"], theme) for name in ("spin", "turning")),
        *(module.resolve(source, entry[name]["$value"], theme) for name in ("glow", "plasma")),
        *(str(core[part]["$value"]) for part in module.CORE_PARTS),
        str(entry["ambient"]["$value"]),
    )


def states_that_look_the_same(source: Tokens) -> list[str]:
    found = []
    for theme in generator().THEMES:
        seen: dict[tuple[object, ...], str] = {}
        for key in generator().entries(source["state"]):
            look = signature(source, key, theme)
            if look in seen:
                found.append(f"{theme}: {seen[look]} and {key} have the same light")
            seen.setdefault(look, key)
    return found


def test_every_key_is_rendered_as_text() -> None:
    assert faults_in_keys(markup.parse(read("index.html")), tokens()) == []


SIZES = {"sm": "ela-presence--sm", "md": None, "lg": "ela-presence--lg"}
"""The three sizes of the presence, and the class that says which: md is the one without."""
PIXELS = {"sm": "24px", "md": "96px", "lg": "220px"}
"""The user's decision of 2026-09-19: pinned here, not only in ``tokens.json``."""


def sizes_shown(page: markup.Element, key: str) -> set[str]:
    modifiers = {name for name in SIZES.values() if name is not None}
    found = set()
    for element in page.walk():
        if "ela-presence" in element.classes and element.get("data-ela-state") == key:
            said = set(element.classes) & modifiers
            found |= {size for size, name in SIZES.items() if (name in said if name else not said)}
    return found


def test_every_state_shows_the_sphere_in_its_three_sizes_and_the_header_shows_it_at_rest() -> None:
    """The user's decision of 2026-09-18: the presence of ELA is the sphere (dec. Q)."""
    page = markup.parse(read("index.html"))
    source = tokens()
    sizes = generator().entries(source["presence"]["size"])
    assert {name: leaf["$value"] for name, leaf in sizes.items()} == PIXELS
    for key in generator().entries(source["state"]):
        assert sizes_shown(page, key) == set(SIZES), key

    (hero,) = [el for el in page.walk() if el.tag == "header"]
    rest = source["presence"]["rest"]["$value"]
    shown = [el for el in hero.walk() if "ela-presence" in el.classes]
    assert [(el.get("data-ela-state"), "ela-presence--lg" in el.classes) for el in shown] == [
        (rest, True)
    ]
    assert [el for el in hero.walk() if "ela-orb__core" in el.classes]
    assert [el.text() for el in hero.walk() if "ela-wordmark" in el.classes] == ["ELA"]


def test_the_state_of_a_row_is_the_small_sphere_with_its_key() -> None:
    """«Il componente state diventa la sfera sm»: a sphere, and the key as text beside it."""
    page = markup.parse(read("index.html"))
    rows = [el for el in page.walk() if "ela-state" in el.classes]
    assert rows, "there must be states to read, or this test is vacuous"
    for row in rows:
        assert [el for el in row.walk() if "ela-orb" in el.classes], row.get("data-ela-state")
        assert row.get("data-ela-state") in row.text()
    rules = stylesheet.parse(read("components.css"))
    sized = [r.value("--_s") for r in rules if ".ela-state .ela-orb" in r.selectors]
    assert sized == ["var(--ela-presence-size-sm)"]


def rows_out_of_order(page: markup.Element) -> list[str]:
    """A row reads left to right: the small sphere, what it is, and the key of ELA at the end."""
    found = []
    for row in page.walk():
        if "ela-row" not in row.classes:
            continue
        parts = [
            next(
                (
                    name
                    for name in ("ela-orb", "ela-row__title", "ela-row__key")
                    if name in el.classes
                ),
                None,
            )
            for el in row.children
            if isinstance(el, markup.Element)
        ]
        if parts != ["ela-orb", "ela-row__title", "ela-row__key"]:
            found.append(f"a row holds {parts}")
        elif [el.text() for el in row.walk() if "ela-row__key" in el.classes] != [
            row.get("data-ela-state")
        ]:
            found.append(f"the key of a row is not its state: {row.get('data-ela-state')}")
    return found


def test_a_row_is_the_sphere_what_it_is_and_the_key_at_the_end() -> None:
    page = markup.parse(read("index.html"))
    assert [el for el in page.walk() if "ela-row" in el.classes], "or this test is vacuous"
    assert rows_out_of_order(page) == []
    rules = stylesheet.parse(read("components.css"))
    assert [r.value("--_s") for r in rules if ".ela-row .ela-orb" in r.selectors] == [
        "var(--ela-presence-size-sm)"
    ]

    wrong = markup.parse(
        '<div class="ela-row" data-ela-state="IDLE"><span class="ela-row__key">IDLE</span>'
        '<span class="ela-orb"></span><p class="ela-row__title">iPhone</p></div>'
        '<div class="ela-row" data-ela-state="IDLE"><span class="ela-orb"></span>'
        '<p class="ela-row__title">iPhone</p><span class="ela-row__key">WORKING</span></div>'
    )
    assert len(rows_out_of_order(wrong)) == 2


def fields_that_do_not_fill(components: str) -> list[str]:
    """A field is as wide as what holds it — never the default width of an input, which cuts
    the text — and how wide it may grow is a token."""
    rules = {s: r for r in stylesheet.parse(components) if r.media is None for s in r.selectors}
    found = []
    for selector in (".ela-field", ".ela-field__input"):
        if selector not in rules or rules[selector].value("inline-size") != "100%":
            found.append(f"{selector} does not fill its container")
    widest = rules[".ela-field"].value("max-inline-size") if ".ela-field" in rules else None
    if widest is not None and not widest.startswith("var(--ela-"):
        found.append(f"the widest a field grows is a token, found {widest}")
    return found


def test_a_field_fills_its_container() -> None:
    assert fields_that_do_not_fill(read("components.css")) == []
    assert fields_that_do_not_fill(
        ".ela-field { margin: 0; } .ela-field__input { margin: 0; }"
    ) == [
        ".ela-field does not fill its container",
        ".ela-field__input does not fill its container",
    ]


def test_a_size_that_is_not_shown_is_seen() -> None:
    page = markup.parse(
        '<div class="ela-presence ela-presence--lg" data-ela-state="IDLE">IDLE</div>'
        '<div class="ela-presence" data-ela-state="IDLE">IDLE</div>'
        '<div class="ela-presence ela-presence--sm" data-ela-state="ERROR">ERROR</div>'
    )
    assert sizes_shown(page, "IDLE") == {"md", "lg"}
    assert sizes_shown(page, "ERROR") == {"sm"}


def test_no_two_states_have_the_same_light() -> None:
    assert states_that_look_the_same(tokens()) == []


def test_a_key_without_its_text_and_a_key_of_no_list_are_found() -> None:
    page = markup.parse(
        '<i data-ela-state="IDLE"><b class="ela-indicator"></b></i>'
        '<i data-ela-state="DREAMING">DREAMING</i><i data-ela-risk="HIGH">HIGH</i>'
    )
    found = faults_in_keys(page, tokens())
    assert 'data-ela-state="IDLE": the key is not rendered as text' in found
    assert 'data-ela-state="DREAMING": not a key of state' in found
    assert "risk: CRITICAL is never rendered" in found
    assert "attention: SILENT is never rendered" in found


def test_two_states_that_differ_only_by_name_are_found() -> None:
    source = tokens()
    source["state"]["PLANNING"] = dict(source["state"]["THINKING"])
    found = states_that_look_the_same(source)
    assert found and all("THINKING and PLANNING" in line for line in found)

    source = tokens()
    source["state"]["EVOLVING"]["spin"]["$value"] = "{motion.duration.spin-updating}"
    source["state"]["EVOLVING"]["glow"]["$value"] = source["state"]["UPDATING"]["glow"]["$value"]
    assert any("UPDATING and EVOLVING" in line for line in states_that_look_the_same(source)), (
        "the comparison is on what the sphere does, not on the name of the state"
    )


# ----------------------------------------------------------------------------------------
# Interaction states, twins, native elements, ids
# ----------------------------------------------------------------------------------------


def component_classes(found: dict[str, str]) -> dict[str, str]:
    """Base class of every interactive element of the fragments -> its tag."""
    classes: dict[str, str] = {}
    for text in found.values():
        for element in markup.parse(text).walk():
            if is_interactive(element):
                base = next(
                    (
                        name
                        for name in element.classes
                        if "--" not in name and name.startswith("ela-")
                    ),
                    None,
                )
                classes[base or f"<{element.tag}> without a class"] = element.tag
    return classes


def states_wanted(tag: str) -> list[str]:
    wanted = [":hover", ":focus-visible", ":active"]
    if tag in FORM_CONTROLS:
        wanted.append(":disabled")
    if tag in {"input", "textarea", "select"}:
        wanted.append('[aria-invalid="true"]')
    return wanted


def missing_states(components: str, classes: dict[str, str]) -> list[str]:
    selectors = [selector for rule in stylesheet.parse(components) for selector in rule.selectors]
    return [
        f".{base}: no rule for {state}"
        for base, tag in classes.items()
        for state in states_wanted(tag)
        if not any(f".{base}" in selector and state in selector for selector in selectors)
    ]


def missing_previews(found: dict[str, str], classes: dict[str, str]) -> list[str]:
    """The specimen shows every state still: the fragment must hold one of each."""
    shown: dict[str, set[str]] = {base: set() for base in classes}
    for text in found.values():
        for element in markup.parse(text).walk():
            for base in set(element.classes) & set(classes):
                shown[base] |= {f".{name}" for name in element.classes if name.startswith("is-")}
                if "disabled" in element.attributes:
                    shown[base].add(":disabled")
                if element.get("aria-invalid") == "true":
                    shown[base].add('[aria-invalid="true"]')
    return [
        f".{base}: the fragment shows no {TWINS.get(state, state)}"
        for base, tag in classes.items()
        for state in states_wanted(tag)
        if TWINS.get(state, state) not in shown[base]
    ]


def twins_that_could_drift(components: str) -> list[str]:
    found = []
    for rule in stylesheet.parse(components):
        for selector in rule.selectors:
            for pseudo, twin in TWINS.items():
                if pseudo in selector and selector.replace(pseudo, twin) not in rule.selectors:
                    found.append(f"{selector}: its twin {twin} is not in the same rule")
    return found


def faults_in_structure(page: markup.Element) -> list[str]:
    found = []
    identifiers = Counter(element.get("id") for element in page.walk() if element.get("id"))
    found += [
        f'id="{name}" appears {count} times' for name, count in identifiers.items() if count > 1
    ]
    for element in page.walk():
        for attribute in ("for", "aria-describedby", "aria-labelledby"):
            for name in (element.get(attribute) or "").split():
                if name not in identifiers:
                    found.append(f'{attribute}="{name}" points at no id')
        if element.get("role") in ROLES_OF_NATIVE_ELEMENTS and not is_interactive(element):
            found.append(f'<{element.tag} role="{element.get("role")}">: use the native element')
        if "tabindex" in element.attributes:
            found.append(
                f"<{element.tag} tabindex=…>: a native element is already in the tab order"
            )
    return found


def test_every_interactive_component_has_every_state_and_shows_it() -> None:
    classes = component_classes(fragments())
    assert set(classes) == {"ela-button", "ela-field__input"}, (
        "the interactive components of M17.1: a new one must be added here on purpose"
    )
    assert missing_states(read("components.css"), classes) == []
    assert missing_previews(fragments(), classes) == []


def test_a_preview_cannot_drift_from_the_real_state() -> None:
    assert twins_that_could_drift(read("components.css")) == []


def test_ids_are_unique_labels_point_home_and_elements_are_native() -> None:
    page = markup.parse(read("index.html"))
    assert [el for el in page.walk() if el.get("for")], (
        "there must be labels, or this test is vacuous"
    )
    assert faults_in_structure(page) == []
    for name, text in fragments().items():
        assert "{id}" in text or 'id="' not in text, (
            f"{name}: an id without {{id}} repeats on the page"
        )


def test_a_missing_state_a_missing_preview_and_a_lone_twin_are_found() -> None:
    components = ".ela-x:hover { margin: 0; } .ela-x:active, .ela-x.is-active { margin: 0; }"
    classes = {"ela-x": "button"}
    assert missing_states(components, classes) == [
        ".ela-x: no rule for :focus-visible",
        ".ela-x: no rule for :disabled",
    ]
    assert twins_that_could_drift(components) == [
        ".ela-x:hover: its twin .is-hover is not in the same rule"
    ]
    shown = {
        "x.html": '<button class="ela-x is-hover">a</button>'
        '<button class="ela-x" disabled>b</button>'
    }
    assert missing_previews(shown, classes) == [
        ".ela-x: the fragment shows no .is-focus-visible",
        ".ela-x: the fragment shows no .is-active",
    ]
    assert states_wanted("input")[-1] == '[aria-invalid="true"]'


def test_a_repeated_id_a_lost_label_and_a_fake_button_are_found() -> None:
    page = markup.parse(
        '<label for="a">A</label><input id="a"><input id="a">'
        '<label for="gone">B</label><div role="button">C</div><span tabindex="0">D</span>'
    )
    assert faults_in_structure(page) == [
        'id="a" appears 2 times',
        'for="gone" points at no id',
        '<div role="button">: use the native element',
        "<span tabindex=…>: a native element is already in the tab order",
    ]


# ----------------------------------------------------------------------------------------
# Targets (criterio 15)
# ----------------------------------------------------------------------------------------

TARGET = "var(--ela-target-min)"
HEIGHTS = ("min-block-size", "min-height")
WIDTHS = ("min-inline-size", "min-width")


def classes_with_a_target(sheets: list[str]) -> set[str]:
    """Classes whose rule, under no condition, takes both minimum sizes from the token."""
    found = set()
    for text in sheets:
        for rule in stylesheet.parse(text):
            tall = any(rule.value(name) == TARGET for name in HEIGHTS)
            wide = any(rule.value(name) == TARGET for name in WIDTHS)
            if tall and wide and rule.media is None:
                found |= {
                    selector.removeprefix(".")
                    for selector in rule.selectors
                    if selector.startswith(".")
                }
    return found


def elements_without_a_target(page: markup.Element, sheets: list[str]) -> list[str]:
    sized = classes_with_a_target(sheets)
    return [
        f'<{element.tag} class="{" ".join(element.classes)}">: no minimum target'
        for element in page.walk()
        if is_interactive(element) and not set(element.classes) & sized
    ]


def faults_in_the_target_token(source: Tokens, derived: str) -> list[str]:
    found = []
    minimum = source["target"]["min"]
    if minimum["touch"]["$value"] != TOUCH:
        found.append(
            f"the touch target is {minimum['touch']['$value']}, and the decision says {TOUCH}"
        )
    rules = stylesheet.parse(derived)
    at_rest = [
        r.value("--ela-target-min") for r in rules if r.media is None and ":root" in r.selectors
    ]
    coarse = [r.value("--ela-target-min") for r in rules if r.media == "(pointer: coarse)"]
    if [value for value in at_rest if value] != [minimum["pointer"]["$value"]]:
        found.append("--ela-target-min is not the pointer size at rest")
    if coarse != [minimum["touch"]["$value"]]:
        found.append("--ela-target-min is not the touch size under (pointer: coarse)")
    return found


def test_every_interactive_element_of_the_page_has_its_target() -> None:
    page = markup.parse(read("index.html"))
    interactive = [element for element in page.walk() if is_interactive(element)]
    assert {element.tag for element in interactive} >= {"button", "input", "textarea", "a"}
    assert elements_without_a_target(page, [read("components.css"), read("specimen.css")]) == []


def test_the_target_is_the_touch_size_under_a_coarse_pointer() -> None:
    assert faults_in_the_target_token(tokens(), read("tokens.css")) == []


def test_an_element_without_a_target_is_found() -> None:
    sheet = """
    .sized { min-block-size: var(--ela-target-min); min-inline-size: var(--ela-target-min); }
    .tall { min-block-size: var(--ela-target-min); }
    @media (pointer: fine) {
      .fine { min-height: var(--ela-target-min); min-width: var(--ela-target-min); }
    }
    """
    page = markup.parse(
        '<button class="sized">a</button><button class="tall">b</button>'
        '<button class="fine">c</button><a href="#x" id="x">d</a><a class="sized">not a link</a>'
    )
    assert elements_without_a_target(page, [sheet]) == [
        '<button class="tall">: no minimum target',
        '<button class="fine">: no minimum target',
        '<a class="">: no minimum target',
    ]


def test_a_wrong_target_token_is_found() -> None:
    source = tokens()
    source["target"]["min"]["touch"]["$value"] = "40px"
    assert any(
        "the decision says 44px" in line
        for line in faults_in_the_target_token(source, read("tokens.css"))
    )

    derived = read("tokens.css").replace("@media (pointer: coarse)", "@media (pointer: fine)")
    assert faults_in_the_target_token(tokens(), derived) == [
        "--ela-target-min is not the touch size under (pointer: coarse)"
    ]


# ----------------------------------------------------------------------------------------
# The components are enough (the compositions), and the meter counts what its lists count
# ----------------------------------------------------------------------------------------


def classes_defined(components: str) -> set[str]:
    found = set()
    for rule in stylesheet.parse(components):
        for selector in rule.selectors:
            found |= set(re.findall(r"\.([A-Za-z][A-Za-z0-9_-]*)", selector))
    return found


def classes_of_nobody(found: dict[str, str], defined: set[str]) -> list[str]:
    """Classes a composition uses and ``components.css`` does not define."""
    unknown = []
    for name, text in found.items():
        for element in markup.parse(text).walk():
            unknown += [f"{name}: .{used}" for used in element.classes if used not in defined]
    return sorted(set(unknown))


def meters_that_miscount(page: markup.Element, source: Tokens) -> list[str]:
    longest = max(len(generator().entries(source[group])) for group in generator().LEVELS)
    found = []
    for element in page.walk():
        if "ela-meter" in element.classes:
            segments = [el for el in element.walk() if "ela-meter__segment" in el.classes]
            if len(segments) != longest:
                found.append(f"a meter has {len(segments)} segments, and the lists have {longest}")
    return found


def test_the_compositions_are_made_of_components_and_of_nothing_else() -> None:
    """Not views: the proof that the components are enough to compose them."""
    found = compositions()
    assert {name.split("/")[-1] for name in found} == {
        "home.html",
        "approval.html",
        "widget.html",
        "phone.html",
    }
    assert classes_of_nobody(found, classes_defined(read("components.css"))) == []
    page = markup.parse(read("index.html"))
    assert len([el for el in page.walk() if (el.get("id") or "").startswith("composition-")]) == 4


def test_every_meter_has_a_segment_for_every_level() -> None:
    page = markup.parse(read("index.html"))
    assert [el for el in page.walk() if "ela-meter" in el.classes], "or this test is vacuous"
    assert meters_that_miscount(page, tokens()) == []


def test_a_class_of_nobody_and_a_meter_that_miscounts_are_found() -> None:
    defined = classes_defined(".ela-panel { margin: 0; } .ela-stack > .ela-tile { margin: 0; }")
    assert defined == {"ela-panel", "ela-stack", "ela-tile"}
    found = {
        "x.html": '<div class="ela-panel home-hero"><p class="ela-tile specimen-x">a</p></div>'
    }
    assert classes_of_nobody(found, defined) == ["x.html: .home-hero", "x.html: .specimen-x"]

    short = markup.parse('<span class="ela-meter"><i class="ela-meter__segment"></i></span>')
    assert len(meters_that_miscount(short, tokens())) == 1
