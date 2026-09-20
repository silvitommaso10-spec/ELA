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
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from ela.api import pages
from tests.design import markup
from tests.design.test_components import classes_defined, classes_of_nobody
from tests.design.tree import DESIGN_SYSTEM

TEMPLATES = pages.TEMPLATES
COMPOSERS = (
    Path(pages.__file__).parent / "pages.py",
    Path(pages.__file__).parent / "companion.py",
    Path(pages.__file__).parent / "security.py",
)
"""Every module that fills a template: the composer, the pages, and the middleware's two."""
TITLE = "ELA"
SLOT = re.compile(r"\{([a-z][a-z0-9_]*)\}")


def templates() -> dict[str, str]:
    found = {path.name: path.read_text(encoding="utf-8") for path in TEMPLATES.glob("*.html")}
    assert found, "or every test here would be vacuous"
    return found


def test_no_template_carries_a_script_or_an_event_handler() -> None:
    """The shape of ``tests/design/test_no_network.py``, for the folder that is served."""
    faults = []
    for name, text in templates().items():
        for element in markup.parse(text).walk():
            if element.tag in {"script", "base", "iframe", "object", "embed"}:
                faults.append(f"{name}: <{element.tag}>")
            faults += [
                f"{name}: <{element.tag} {attribute}=…>"
                for attribute in element.attributes
                if attribute.lower().startswith("on")
            ]
            for value in element.attributes.values():
                if value is not None and value.strip().lower().startswith("javascript:"):
                    faults.append(f"{name}: a javascript: URL")

    assert faults == []


def test_a_script_in_a_template_would_be_found(tmp_path: Path) -> None:
    """The negative case, in a string: the check is not vacuous."""
    element = markup.parse("<div><script>alert(1)</script></div>")

    assert [one.tag for one in element.walk() if one.tag == "script"] == ["script"]


def test_every_class_is_one_the_design_system_defines() -> None:
    """A class of nobody is a style that does not exist on the phone (ADR 0042)."""
    defined = classes_defined((DESIGN_SYSTEM / "components.css").read_text(encoding="utf-8"))

    assert classes_of_nobody(templates(), defined) == []


def test_the_title_says_nothing_and_no_link_carries_content() -> None:
    """Dec. D: the history of Safari travels to every Apple device of the user, and Chrome's to
    the Google account — so a title is "ELA" and a link is a path and at most an opaque id."""
    shell = markup.parse(templates()["shell.html"])
    titles = [one for one in shell.walk() if one.tag == "title"]

    assert [one.text() for one in titles] == [TITLE]


def test_every_link_of_a_template_names_a_route_of_the_companion() -> None:
    """A page that linked somewhere ELA does not serve would be a ``404`` with the user's name
    on it: the targets are the routes, with the id in the query as dec. D asks."""
    from ela.api.security import COMPANION_CODE_ROUTES, COMPANION_ROUTES

    served = {path for _, path in COMPANION_ROUTES | COMPANION_CODE_ROUTES}
    for name, text in templates().items():
        for element in markup.parse(text).walk():
            target = element.get("href") or element.get("action")
            if target is None or "{" in target:
                continue  # a slot: what fills it is a route, and the composer is what fills it
            assert target.split("?")[0] in served, f"{name}: {target}"


def test_the_templates_and_the_code_that_fills_them_are_one_closed_world() -> None:
    """Both directions: a template nobody fills, and a name nobody wrote a template for.

    The names are read from the source — every ``pages.fragment("x", …)`` and
    ``pages.page("x", …)`` — so a page added tomorrow without markup fails here, and markup left
    behind after a page was removed fails too.
    """
    filled = set()
    for module in COMPOSERS:
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            called = _called(node.func)
            first = node.args[0]
            if called in {"fragment", "page"} and isinstance(first, ast.Constant):
                filled.add(f"{first.value}.html")

    assert filled == set(templates())


def _called(func: ast.expr) -> str | None:
    """The name of what is being called: ``fragment(...)`` inside the composer, ``pages.fragment``
    outside it — the same call written from two sides of an import."""
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else None


def test_every_slot_of_every_template_is_lower_case_and_named() -> None:
    """The composer refuses a slot nobody filled; this refuses one it could not even see — a
    ``{Risk}`` would be markup the escape never touches and nobody would notice."""
    for name, text in templates().items():
        for found in re.finditer(r"\{([^{}]*)\}", text):
            inside = found.group(1)
            assert inside.startswith("include:") or SLOT.fullmatch(f"{{{inside}}}"), (
                f"{name}: {inside}"
            )
