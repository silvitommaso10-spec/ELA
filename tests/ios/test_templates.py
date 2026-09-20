"""The rules of ``apps/ios/``, which do not walk Python (M12.5 dec. D; ADR 0043 §5).

``CLAUDE.md`` asks that what lives in ``apps/`` be defended by tests in its own folder, and that
the folder's README name each rule with the test that holds it. These are those tests:

* **no script anywhere** — the first of the two defences of «niente JavaScript»; the second is the
  ``Content-Security-Policy``, and it is proved in ``tests/api/test_companion.py``;
* **only classes the design system defines** — the same check M17.1 makes of its own compositions,
  reused and not copied (``tests/design/test_components.py``);
* **titles and links with no content** — the history of a browser travels (dec. D), so the title
  is "ELA" and a link carries at most an opaque id;
* **the templates and the composer are one closed world** — a template nobody fills is markup that
  cannot be wrong, and a fill with no template is a page that cannot be rendered.

Since M17.2 the **checks** live in ``tests/design/surface.py`` and take the surface: the Command
Center has the same rules, and two copies of them would be two rules the moment somebody tightens
one. What stays here is this folder's answer to each.
"""

from __future__ import annotations

from ela.api.security import COMPANION_SURFACE
from tests.design import markup, surface
from tests.design.test_components import classes_defined, classes_of_nobody
from tests.design.tree import DESIGN_SYSTEM

PHONE = COMPANION_SURFACE.templates
PAGES = "companion.py"


def test_no_template_carries_a_script_or_an_event_handler() -> None:
    assert surface.scripts_in(PHONE) == []


def test_a_script_in_a_template_would_be_found() -> None:
    """The negative case, in a string: the check is not vacuous."""
    element = markup.parse("<div><script>alert(1)</script></div>")

    assert [one.tag for one in element.walk() if one.tag == "script"] == ["script"]


def test_every_class_is_one_the_design_system_defines() -> None:
    """A class of nobody is a style that does not exist on the phone (ADR 0042)."""
    defined = classes_defined((DESIGN_SYSTEM / "components.css").read_text(encoding="utf-8"))

    assert classes_of_nobody(surface.templates(PHONE), defined) == []


def test_the_title_says_nothing_and_no_link_carries_content() -> None:
    """Dec. D: the history of Safari travels to every Apple device of the user, and Chrome's to
    the Google account — so a title is "ELA" and a link is a path and at most an opaque id."""
    assert surface.titles_of(PHONE) == [surface.TITLE]


def test_every_link_of_a_template_names_a_route_of_the_companion() -> None:
    """A page that linked somewhere ELA does not serve would be a ``404`` with the user's name
    on it: the targets are the routes, with the id in the query as dec. D asks."""
    served = {path for _, path in COMPANION_SURFACE.routes | COMPANION_SURFACE.code_routes}

    for name, target in surface.targets_of(PHONE):
        assert target.split("?")[0] in served, f"{name}: {target}"


def test_the_templates_and_the_code_that_fills_them_are_one_closed_world() -> None:
    """Both directions: a template nobody fills, and a name nobody wrote a template for."""
    assert surface.filled(surface.composers(PAGES)) == set(surface.templates(PHONE))


def test_every_slot_of_every_template_is_lower_case_and_named() -> None:
    """The composer refuses a slot nobody filled; this refuses one it could not even see — a
    ``{Risk}`` would be markup the escape never touches and nobody would notice."""
    for name, inside in surface.slots_of(PHONE):
        assert inside.startswith("include:") or surface.SLOT.fullmatch(f"{{{inside}}}"), (
            f"{name}: {inside}"
        )
