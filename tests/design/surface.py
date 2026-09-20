"""What a surface's folder of markup must satisfy, written once for every surface (M17.2 dec. E).

``CLAUDE.md`` asks that what lives in ``apps/`` be defended by tests in its own folder, and that
the folder's README name each rule with the test that holds it. Since M17.2 there are two such
folders — ``apps/ios/`` and ``apps/command-center/`` — and the rules are the same rules: the
**tests** stay in their own folders, and what they share is here, as functions that take the
surface. Two copies of these checks would be two checks, and the first one somebody tightened
would leave the other behind.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from ela.api import pages
from tests.design import markup

SLOT = re.compile(r"\{([a-z][a-z0-9_]*)\}")
TITLE = "ELA"
FORBIDDEN = frozenset({"script", "base", "iframe", "object", "embed"})
"""What a page of ELA never contains: the first of the two defences of «niente JavaScript»."""
API = Path(pages.__file__).parent
SHARED_COMPOSERS = ("pages.py", "security.py", "app.py")
"""Every module that fills a template for **all** surfaces: the composer itself, the middleware's
refusals, and the error handler that turns a failure into a page under a prefix."""


def templates(surface: str) -> dict[str, str]:
    """The markup of one surface, by file name. Empty would make every check here vacuous."""
    folder = pages.templates_of(surface)
    found = {path.name: path.read_text(encoding="utf-8") for path in folder.glob("*.html")}
    assert found, f"{folder} has no templates, or every test of it would be vacuous"
    return found


def composers(page_module: str) -> tuple[Path, ...]:
    """Which modules fill this surface's templates: the shared ones, and its own pages."""
    return (*(API / name for name in SHARED_COMPOSERS), API / page_module)


def filled(modules: tuple[Path, ...]) -> set[str]:
    """Every template name those modules compose, read from the source.

    The name is the **second** positional argument since M17.2 — ``pages.fragment(HERE, "notice",
    …)`` — because the first says which surface. A page added tomorrow with no markup fails the
    closed world here, and markup left behind after a page was removed fails too.
    """
    names: set[str] = set()
    for module in modules:
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or len(node.args) < 2:
                continue
            called = _called(node.func)
            second = node.args[1]
            if called in {"fragment", "page"} and isinstance(second, ast.Constant):
                names.add(f"{second.value}.html")
    assert names, f"{modules} fill no template: the closed world would be vacuous"
    return names


def _called(func: ast.expr) -> str | None:
    """The name of what is being called: ``fragment(...)`` inside the composer, ``pages.fragment``
    outside it — the same call written from two sides of an import."""
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else None


def scripts_in(surface: str) -> list[str]:
    """Every script, event handler and ``javascript:`` URL of a surface's markup: none, or a bug.

    The shape of ``tests/design/test_no_network.py``, for the folders that are served.
    """
    faults = []
    for name, text in templates(surface).items():
        for element in markup.parse(text).walk():
            if element.tag in FORBIDDEN:
                faults.append(f"{name}: <{element.tag}>")
            faults += [
                f"{name}: <{element.tag} {attribute}=…>"
                for attribute in element.attributes
                if attribute.lower().startswith("on")
            ]
            for value in element.attributes.values():
                if value is not None and value.strip().lower().startswith("javascript:"):
                    faults.append(f"{name}: a javascript: URL")
    return faults


def titles_of(surface: str) -> list[str]:
    """What the shell calls every page of this surface: the history of a browser travels."""
    shell = markup.parse(templates(surface)["shell.html"])
    return [one.text() for one in shell.walk() if one.tag == "title"]


def targets_of(surface: str) -> list[tuple[str, str]]:
    """Every ``href`` and ``action`` a template names, with the file it is in.

    A slot is skipped: what fills it is a route, and the composer is what fills it.
    """
    found = []
    for name, text in templates(surface).items():
        for element in markup.parse(text).walk():
            target = element.get("href") or element.get("action")
            if target is not None and "{" not in target:
                found.append((name, target))
    return found


def slots_of(surface: str) -> list[tuple[str, str]]:
    """Every ``{…}`` of a surface's markup, with the file it is in — includes as well as slots."""
    return [
        (name, found.group(1))
        for name, text in templates(surface).items()
        for found in re.finditer(r"\{([^{}]*)\}", text)
    ]
