"""The one place a page of ELA is composed (M12.5 dec. D; ADR 0043 §5).

``ela.api`` serves the companion's pages itself: the same process, the same middleware, the same
route functions the JSON answers come from, and the browser as the client. What makes that safe is
not a promise but this module — **every** HTML answer of ``ela.api`` is built here, and therefore
carries the :data:`CONTENT_SECURITY_POLICY` that makes «niente JavaScript» true in the browser and
not only in the templates. A page composed beside it would be a page without that header
(architecture rule 57).

Two defences, and they are deliberately not the same one twice: the templates carry no script (a
test in ``tests/ios/``), and the policy forbids one — from outside and inline — so a value that one
day escaped the escaping would be refused by the browser rather than run by it.

**The escape is by construction.** A value handed to :func:`fragment` or :func:`page` is escaped;
there is no argument that turns that off. The only markup that goes in raw is :class:`Markup`,
which nothing but this module produces — a template of ``apps/ios/`` or a partial of the design
system, both of them files of this repository.

**Nothing is invented here.** The markup lives in ``apps/ios/``, the look in ``apps/design-system/``
(ADR 0042), and the sphere is *included* from ``_orb.html`` rather than copied: the one place where
the declared constraint of ADR 0042 — «il markup di un componente si ricopia» — stops holding,
because here a copy would be a second sphere nobody keeps in step.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable, Mapping
from functools import lru_cache
from pathlib import Path
from typing import Final

from fastapi import Response
from fastapi.responses import HTMLResponse

from ela.composition import ConfigurationError

__all__ = [
    "CONTENT_SECURITY_POLICY",
    "PARTIALS",
    "STYLESHEETS",
    "TEMPLATES",
    "Markup",
    "fragment",
    "joined",
    "page",
    "stylesheet",
]

APPS: Final = Path(__file__).resolve().parents[3] / "apps"
"""The folder of what is not Python, derived from the package: ELA runs from the repository (5.5).

Checked once at start-up (:func:`ensure_readable`), because a companion without its markup is a
configuration ELA cannot serve, and that is an exit code and not a traceback on the first request.
"""
TEMPLATES: Final = APPS / "ios"
PARTIALS: Final = APPS / "design-system" / "components"
STYLESHEETS: Final = ("tokens.css", "components.css")
"""What ``ela.api`` serves of the design system, and nothing else: the two derived sheets, read
only. The specimen page, the tokens and the sources stay where they are (ADR 0042)."""

CONTENT_SECURITY_POLICY: Final = (
    "default-src 'none'; style-src 'self'; form-action 'self'; "
    "frame-ancestors 'none'; base-uri 'none'"
)
"""No script from anywhere, styles only from ELA, forms only back to ELA, and no frame.

``style-src 'self'`` and not ``'unsafe-inline'``: the fragments of M17.1 have no inline style, so
the policy costs nothing — and the page of the enrolment, which is the one page served before an
identity exists, therefore has no style at all (dec. D).
"""
NO_STORE: Final = "no-store"
"""A question that was answered, or an identity that was revoked, must not come back from the
browser's cache when the user opens the page again."""

SLOT: Final = re.compile(r"\{([a-z][a-z0-9_]*)\}")
INCLUDE: Final = re.compile(r"\{include:([a-z0-9_-]+)\}")
SUFFIX: Final = ".html"


class Markup(str):
    """Composed markup: what goes into a page without being escaped again.

    A ``str`` subclass and not a wrapper, so it prints as itself in a template; produced only by
    :func:`fragment` and :func:`joined`, which is what makes "escaped unless it came from this
    repository" a property of the type rather than of everybody's attention.
    """

    __slots__ = ()


def ensure_readable() -> None:
    """Fail the start-up if the markup of the companion is not where it should be.

    :raises ConfigurationError: named for whoever reads it — the person who moved the folder or
        installed ELA outside its repository (5.5) — and raised before the first request.
    """
    for folder in (TEMPLATES, PARTIALS):
        if not folder.is_dir():
            raise ConfigurationError(
                f"the companion's markup is missing: {folder} does not exist. ELA runs from its "
                "repository, and the pages of the iPhone are files of it (M12.5 dec. D)."
            )
    _templates.cache_clear()
    _partials.cache_clear()


@lru_cache(maxsize=1)
def _templates() -> Mapping[str, str]:
    return _read(TEMPLATES)


@lru_cache(maxsize=1)
def _partials() -> Mapping[str, str]:
    return _read(PARTIALS)


def _read(folder: Path) -> Mapping[str, str]:
    if not folder.is_dir():
        ensure_readable()
    return {path.stem: path.read_text(encoding="utf-8") for path in sorted(folder.glob("*.html"))}


def _with_partials(markup: str) -> str:
    """``{include:_orb}`` becomes the sphere, from the design system (ADR 0042).

    One level, like the generator of M17.1: a partial that included another would be a template
    language, and this is not one.
    """
    partials = _partials()

    def replace(found: re.Match[str]) -> str:
        name = found.group(1)
        if name not in partials:
            raise ValueError(f"{{include:{name}}} names no partial of {PARTIALS}")
        if INCLUDE.search(partials[name]):
            raise ValueError(f"the partial {name} includes another: one level only")
        return partials[name].strip()

    return INCLUDE.sub(replace, markup)


def fragment(name: str, /, **values: object) -> Markup:
    """The template ``name`` of ``apps/ios/``, filled and escaped.

    A slot with no value and a value with no slot are both errors: a page that silently showed
    ``{risk}`` to the user, or silently dropped what it was given, is the failure this forbids.
    """
    templates = _templates()
    if name not in templates:
        raise ValueError(f"{name}{SUFFIX} is not a template of {TEMPLATES}")
    used: set[str] = set()

    def replace(found: re.Match[str]) -> str:
        slot = found.group(1)
        if slot not in values:
            raise ValueError(f"{name}{SUFFIX} has a slot {{{slot}}} and nothing was given for it")
        used.add(slot)
        value = values[slot]
        return value if isinstance(value, Markup) else html.escape(str(value))

    filled = SLOT.sub(replace, _with_partials(templates[name]))
    unused = sorted(set(values) - used)
    if unused:
        raise ValueError(f"{name}{SUFFIX} has no slot for {', '.join(unused)}")
    return Markup(filled)


def joined(pieces: Iterable[Markup]) -> Markup:
    """Several fragments as one: a list of rows, a list of pairs."""
    return Markup("\n".join(pieces))


def page(name: str, /, *, status: int = 200, styled: bool = True, **values: object) -> Response:
    """A whole page: the shell, the fragment ``name`` inside it, and the headers of dec. D.

    ``styled`` is false for the one page served before an identity exists — the enrolment form, a
    ``401`` — because the stylesheets are behind the middleware like everything else (dec. D).
    """
    document = fragment(
        "shell",
        styles=joined(fragment("stylesheet", href=f"/companion/{sheet}") for sheet in STYLESHEETS)
        if styled
        else Markup(""),
        content=fragment(name, **values),
    )
    return HTMLResponse(
        content=document,
        status_code=status,
        headers={"Content-Security-Policy": CONTENT_SECURITY_POLICY, "Cache-Control": NO_STORE},
    )


def stylesheet(name: str) -> Response:
    """One of the two derived sheets of the design system, read from ``apps/`` (ADR 0042).

    Named against :data:`STYLESHEETS` and never joined to a path from the request: what the
    browser asks for chooses **between two files**, and cannot describe one.
    """
    if name not in STYLESHEETS:
        raise ValueError(f"{name} is not one of the sheets ela.api serves: {STYLESHEETS}")
    return Response(
        content=(APPS / "design-system" / name).read_text(encoding="utf-8"),
        media_type="text/css",
        headers={"Cache-Control": NO_STORE},
    )
