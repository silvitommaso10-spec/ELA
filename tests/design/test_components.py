"""What a component promises (M17.1, criteri 10, 11 e 15; dec. D, dec. H, dec. J).

- **A key is always text.** It is what survives where no CSS arrives — the text of a push
  notification — and what carries WCAG 1.4.1: never colour alone. Colour and shape group the
  states; no two share both, compared on the **resolved** values in each theme.
- **Every interaction state exists, and its preview cannot drift**: a pseudo-class and its twin
  class live in the same selector list, so the specimen shows the real declarations.
- **Native elements**, which a keyboard already operates; ids that are unique, labels that
  point at their own field.
- **Targets**: every interactive element of the page — the fragments, and the page's own
  controls — takes its minimum size from the token, which is the touch size under
  ``pointer: coarse``.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from tests.design import markup, stylesheet
from tests.design.tree import fragments, generator, read, tokens

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
    """What a state looks like when it stands still: its colour and the parameters of its shape."""
    module = generator()
    entry = source["state"][key]
    shape = module.group_at(source, entry["shape"]["$value"], theme, "shape")
    parameters = tuple(
        module.resolve(source, shape[name]["$value"], theme) for name in module.SHAPE_PARAMETERS
    )
    return (module.resolve(source, entry["color"]["$value"], theme), *parameters)


def states_that_look_the_same(source: Tokens) -> list[str]:
    found = []
    for theme in generator().THEMES:
        seen: dict[tuple[object, ...], str] = {}
        for key in generator().entries(source["state"]):
            look = signature(source, key, theme)
            if look in seen:
                found.append(
                    f"{theme}: {seen[look]} and {key} have the same colour and the same shape"
                )
            seen.setdefault(look, key)
    return found


def test_every_key_is_rendered_as_text() -> None:
    assert faults_in_keys(markup.parse(read("index.html")), tokens()) == []


def test_no_two_states_share_colour_and_shape() -> None:
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
    source["state"]["UPDATING"]["color"]["$value"] = "{color.signal.wait}"
    source["state"]["UPDATING"]["shape"]["$value"] = "{shape.arc}"
    found = states_that_look_the_same(source)
    assert found and all("RECOVERING and UPDATING" in line for line in found)

    source = tokens()
    for theme in generator().THEMES:
        source[theme]["color"]["signal"]["change"]["$value"] = source[theme]["color"]["signal"][
            "activity"
        ]["$value"]
    assert any("WORKING and UPDATING" in line for line in states_that_look_the_same(source)), (
        "two roles that resolve to one colour are one colour: the comparison is on values"
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
