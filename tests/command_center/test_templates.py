"""The rules of ``apps/command-center/``, which do not walk Python (M17.2 dec. E; ADR 0044).

The same rules as the phone's folder, and deliberately the same **checks**: they live in
``tests/design/surface.py`` and take the surface, so tightening one tightens both. What is here
is this folder's answer to each, and the one thing that is its own — the links, which must be
routes of the console and not of the companion.
"""

from __future__ import annotations

from ela.api.security import CONSOLE_SURFACE
from tests.design import markup, surface
from tests.design.test_components import classes_defined, classes_of_nobody
from tests.design.tree import DESIGN_SYSTEM

CONSOLE = CONSOLE_SURFACE.templates
PAGES = "console.py"


def test_no_template_carries_a_script_or_an_event_handler() -> None:
    assert surface.scripts_in(CONSOLE) == []


def test_a_script_in_a_template_would_be_found() -> None:
    """The negative case, in a string: the check is not vacuous."""
    element = markup.parse("<div><script>alert(1)</script></div>")

    assert [one.tag for one in element.walk() if one.tag == "script"] == ["script"]


def test_every_class_is_one_the_design_system_defines() -> None:
    """A class of nobody is a style that does not exist in the Command Center (ADR 0042)."""
    defined = classes_defined((DESIGN_SYSTEM / "components.css").read_text(encoding="utf-8"))

    assert classes_of_nobody(surface.templates(CONSOLE), defined) == []


def test_a_class_the_design_system_does_not_define_would_be_found() -> None:
    """The negative case of the check above, on markup of its own."""
    defined = classes_defined(".ela-panel { color: red }")

    assert classes_of_nobody({"x.html": '<div class="ela-invented"></div>'}, defined) != []


def test_the_title_says_nothing_and_no_link_carries_content() -> None:
    """Chrome's history syncs to a Google account on the Mac too, which is why an address of the
    Command Center carries at most an opaque id and its title is one word."""
    assert surface.titles_of(CONSOLE) == [surface.TITLE]


def test_every_link_of_a_template_names_a_route_of_the_console() -> None:
    """A page that linked somewhere ELA does not serve would be a ``404`` with the user's name on
    it — and one that linked to the *companion's* routes would send the Mac to the phone."""
    served = {path for _, path in CONSOLE_SURFACE.routes | CONSOLE_SURFACE.code_routes}

    for name, target in surface.targets_of(CONSOLE):
        assert target.split("?")[0] in served, f"{name}: {target}"
        assert "id=" not in target.split("?")[0], f"{name}: an id belongs in the query"


def test_the_templates_and_the_code_that_fills_them_are_one_closed_world() -> None:
    """Both directions: a template nobody fills, and a name nobody wrote a template for."""
    assert surface.filled(surface.composers(PAGES)) == set(surface.templates(CONSOLE))


def test_every_slot_of_every_template_is_lower_case_and_named() -> None:
    """The composer refuses a slot nobody filled; this refuses one it could not even see."""
    for name, inside in surface.slots_of(CONSOLE):
        assert inside.startswith("include:") or surface.SLOT.fullmatch(f"{{{inside}}}"), (
            f"{name}: {inside}"
        )
