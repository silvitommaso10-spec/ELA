"""Three breakpoints, and only those (M17.1, criterio 14; dec. 6, dec. I).

A media query cannot read a custom property: the grid per band is derived, and what is written
by hand may only ask for a width that is a breakpoint token (``test_tokens_only.py``). What a
static check cannot see — no horizontal scroll at 320 px, text at 200% — is in the manual test.
"""

from __future__ import annotations

import re
from typing import Any

from tests.design import markup, stylesheet
from tests.design.tree import generator, read, token_paths, tokens

BANDS = ["phone", "desktop-compact", "desktop-extended"]
VIEWPORT = "width=device-width, initial-scale=1"
REM = re.compile(r"^(\d*\.?\d+)rem$")


def faults_in_breakpoints(source: dict[str, Any]) -> list[str]:
    found = []
    bands = generator().entries(source["breakpoint"])
    if list(bands) != BANDS:
        found.append(f"the bands are {list(bands)}, and the decision names {BANDS}")
    widths = [leaf["$value"] for leaf in bands.values()]
    pixels = [int(str(width).removesuffix("px")) for width in widths if str(width).endswith("px")]
    if len(pixels) != len(widths):
        found.append(f"a breakpoint is a width in px: {widths}")
    elif pixels != sorted(set(pixels)) or pixels[0] != 0:
        found.append(f"phone first, then wider and wider: {widths}")
    return found


def bands_the_grid_forgets(source: dict[str, Any], derived: str) -> list[str]:
    rules = stylesheet.parse(derived)
    found = []
    for band, leaf in list(generator().entries(source["breakpoint"]).items())[1:]:
        media = f"(min-width: {leaf['$value']})"
        declared = {name for rule in rules if rule.media == media for name, _ in rule.declarations}
        if "--ela-grid-columns" not in declared:
            found.append(f"{band}: no grid under @media {media}")
    return found


def field_text_size(source: dict[str, Any], components: str) -> float:
    """The size of the text of a field, in rem, followed from the rule to its token."""
    rules = [rule for rule in stylesheet.parse(components) if ".ela-field__input" in rule.selectors]
    sizes = [rule.value("font-size") for rule in rules if rule.value("font-size")]
    assert len(sizes) == 1, (
        "the field must set its font size once, or this check reads the wrong rule"
    )
    (name,) = stylesheet.VAR.findall(sizes[0] or "")
    value = generator().node_at(source, token_paths()[name], "dark")["$value"]
    found = REM.match(str(generator().resolve(source, value, "dark")))
    assert found is not None, f"the text of a field is in rem, found {value!r}"
    return float(found.group(1))


def test_the_breakpoints_are_the_three_the_decision_names() -> None:
    assert faults_in_breakpoints(tokens()) == []


def test_the_grid_of_every_band_is_derived() -> None:
    assert bands_the_grid_forgets(tokens(), read("tokens.css")) == []


def test_the_page_declares_its_viewport() -> None:
    page = markup.parse(read("index.html"))
    found = [
        el.get("content") for el in page.walk() if el.tag == "meta" and el.get("name") == "viewport"
    ]
    assert found == [VIEWPORT]


def test_the_text_of_a_field_never_goes_under_one_rem() -> None:
    """Under 16 px Safari on iPhone zooms the page when a field takes the focus."""
    assert field_text_size(tokens(), read("components.css")) >= 1.0


def test_wrong_breakpoints_are_found() -> None:
    source = tokens()
    source["breakpoint"]["tablet"] = {"$value": "900px", "$type": "dimension"}
    assert any("the decision names" in line for line in faults_in_breakpoints(source))

    source = tokens()
    source["breakpoint"]["desktop-compact"]["$value"] = "1300px"
    assert any("wider and wider" in line for line in faults_in_breakpoints(source))

    source = tokens()
    source["breakpoint"]["desktop-compact"]["$value"] = "45rem"
    assert any("a width in px" in line for line in faults_in_breakpoints(source))


def test_a_band_without_its_grid_is_found() -> None:
    derived = read("tokens.css").replace("@media (min-width: 1200px)", "@media (min-width: 1201px)")
    assert bands_the_grid_forgets(tokens(), derived) == [
        "desktop-extended: no grid under @media (min-width: 1200px)"
    ]


def test_a_field_with_small_text_is_found() -> None:
    source = tokens()
    source["typography"]["style"]["body"]["size"]["$value"] = "0.875rem"
    assert field_text_size(source, read("components.css")) < 1.0
