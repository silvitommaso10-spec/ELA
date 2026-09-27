"""The one place a page of ELA is composed (M12.5 dec. D; ADR 0043 §5; M17.2 dec. E).

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
which nothing but this module produces — a template of ``apps/<surface>/``, a partial of the design
system, or, since M17.2c, the two sheets of the design system inside a ``<style>`` block: all of
them files of this repository.

**Two pages carry their sheets inside** (M17.2c, ADR 0050): the enrolment form and the page
«rifiutata», the two that can reach a browser nobody has recognised. The sheets stay behind the
middleware — no route answers anybody who is nobody yet (ADR 0037 §3) —, so they travel in the
answer the browser gets anyway, and the policy of those two pages admits them by their ``sha256``,
computed from the very text the block carries, at every answer. Every other page links the sheets
and keeps :data:`CONTENT_SECURITY_POLICY`.

**It composes for every surface, and knows none of them by name.** Since M17.2 ELA serves two
browsers — the phone and the Command Center — and this module takes the folder of the templates
and the prefix the stylesheets are served under as **arguments**. It does not import the table of
surfaces: that table lives with the cookies, in ``api/security.py``, which imports *this*, and a
second edge would be a cycle.

**Nothing is invented here.** The markup lives in ``apps/<surface>/``, the look in
``apps/design-system/`` (ADR 0042), and the sphere is *included* from ``_orb.html`` rather than
copied: the one place where the declared constraint of ADR 0042 — «il markup di un componente si
ricopia» — stops holding, because here a copy would be a second sphere nobody keeps in step.
"""

from __future__ import annotations

import base64
import hashlib
import html
import re
from collections.abc import Iterable, Mapping
from enum import Enum
from functools import cache, lru_cache
from pathlib import Path
from typing import Final

from fastapi import Response
from fastapi.responses import HTMLResponse

from ela.composition import ConfigurationError

__all__ = [
    "APPS",
    "CONTENT_SECURITY_POLICY",
    "DESIGN_SYSTEM",
    "INSIDE",
    "PARTIALS",
    "STYLESHEETS",
    "Markup",
    "Sheets",
    "closes_the_block",
    "ensure_readable",
    "fragment",
    "inside_policy",
    "joined",
    "page",
    "sheet_text",
    "stylesheet",
    "templates_of",
]

APPS: Final = Path(__file__).resolve().parents[3] / "apps"
"""The folder of what is not Python, derived from the package: ELA runs from the repository (5.5).

Checked once at start-up (:func:`ensure_readable`), because a companion without its markup is a
configuration ELA cannot serve, and that is an exit code and not a traceback on the first request.
"""
PARTIALS: Final = APPS / "design-system" / "components"
DESIGN_SYSTEM: Path = APPS / "design-system"
"""Where the two sheets are read from — by the routes of the sheets and by the block of a page, the
same function for both (:func:`sheet_text`). Read at every call and not held: the sheets a
recognised browser downloads and the ones inside the page of whoever is nobody yet are the same
files, read the same way, and a change to them moves both at once (M17.2c dec. 7)."""
STYLESHEETS: Final = ("tokens.css", "components.css")
"""What ``ela.api`` serves of the design system, and nothing else: the two derived sheets, read
only, in the order a page links them — and the order they are joined in inside a block. The specimen
page, the tokens and the sources stay where they are (ADR 0042)."""

_STANDING: Final = "form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
CONTENT_SECURITY_POLICY: Final = f"default-src 'none'; style-src 'self'; {_STANDING}"
"""The policy of a page that **links** its sheets: no script from anywhere, styles only from ELA,
forms only back to ELA, and no frame.

``style-src 'self'`` and not ``'unsafe-inline'``: the fragments of M17.1 have no inline style, so
the policy costs nothing. The two pages that carry their sheets inside have a policy of their own,
the same in everything but ``style-src`` (:func:`inside_policy`, M17.2c dec. 8).
"""
NO_STORE: Final = "no-store"
"""A question that was answered, or an identity that was revoked, must not come back from the
browser's cache when the user opens the page again."""

SLOT: Final = re.compile(r"\{([a-z][a-z0-9_]*)\}")
INCLUDE: Final = re.compile(r"\{include:([a-z0-9_-]+)\}")
SUFFIX: Final = ".html"


class Sheets(Enum):
    """How a page carries the sheets of the design system when it does not link them."""

    INSIDE = "inside"
    """In one ``<style>`` block, admitted by its ``sha256`` (M17.2c, ADR 0050)."""


INSIDE: Final = Sheets.INSIDE
"""The value of ``sheets`` for a page that carries its sheets inside: a name, never a default.

ADR 0044 §4 wrote that ``sheets=None`` had no default that could dress a page by distraction,
because dressing a page meant an anonymous route. Now the page of whoever is nobody yet is dressed,
and ``None`` would change meaning in silence: every composition says which it is (M17.2c)."""


class Markup(str):
    """Composed markup: what goes into a page without being escaped again.

    A ``str`` subclass and not a wrapper, so it prints as itself in a template; produced only by
    :func:`fragment` and :func:`joined`, which is what makes "escaped unless it came from this
    repository" a property of the type rather than of everybody's attention.
    """

    __slots__ = ()


def templates_of(surface: str) -> Path:
    """Where a surface keeps its markup: a folder of ``apps/``, named by the surface."""
    return APPS / surface


def ensure_readable(*surfaces: str) -> None:
    """Fail the start-up if the markup of any surface is not where it should be.

    Every surface, not the first one: a Command Center that started and answered the phone while
    its own folder was missing would fail on the first page instead of on the first second.

    :raises ConfigurationError: named for whoever reads it — the person who moved the folder or
        installed ELA outside its repository (5.5) — and raised before the first request.
    """
    for folder in (*(templates_of(surface) for surface in surfaces), PARTIALS):
        if not folder.is_dir():
            raise ConfigurationError(
                f"the markup of a page is missing: {folder} does not exist. ELA runs from its "
                "repository, and the pages it serves are files of it (M12.5 dec. D)."
            )
    # The sheets too (M17.2c): the enrolment form carries them inside, so a sheet that is not there,
    # or that would close its block, would take away the only door. Said once, here — a refusal at
    # every answer would be a ``500`` on that door, and a typo in a comment a door that stays shut.
    for name in STYLESHEETS:
        sheet = DESIGN_SYSTEM / name
        if not sheet.is_file():
            raise ConfigurationError(
                f"a sheet of the design system is missing: {sheet} does not exist. The pages of "
                "whoever is not recognised yet carry it inside (M17.2c)."
            )
        if closes_the_block(sheet.read_text(encoding="utf-8")):
            raise ConfigurationError(
                f"the sheet {sheet} contains «</style»: inside the block of a page it would close "
                "the block, and what follows would be read as HTML (M17.2c, ADR 0050)."
            )
    _templates.cache_clear()
    _partials.cache_clear()


@cache
def _templates(surface: str) -> Mapping[str, str]:
    """The templates of one surface, read once. One cache entry per surface, not one in all."""
    return _read(templates_of(surface))


@lru_cache(maxsize=1)
def _partials() -> Mapping[str, str]:
    return _read(PARTIALS)


def _read(folder: Path) -> Mapping[str, str]:
    if not folder.is_dir():
        raise ConfigurationError(
            f"the markup of a page is missing: {folder} does not exist. ELA runs from its "
            "repository, and the pages it serves are files of it (M12.5 dec. D)."
        )
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


def fragment(surface: str, name: str, /, **values: object) -> Markup:
    """The template ``name`` of ``apps/<surface>/``, filled and escaped.

    A slot with no value and a value with no slot are both errors: a page that silently showed
    ``{risk}`` to the user, or silently dropped what it was given, is the failure this forbids.
    """
    templates = _templates(surface)
    if name not in templates:
        raise ValueError(f"{name}{SUFFIX} is not a template of {templates_of(surface)}")
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


def page(
    surface: str, name: str, /, *, sheets: str | Sheets, status: int = 200, **values: object
) -> Response:
    """A whole page of ``surface``: the shell, the fragment ``name``, and the headers of dec. D.

    ``sheets`` has no default (M17.2c). A **prefix** — ``/companion/`` or ``/console/`` — links the
    two derived sheets served under it, and the page gets :data:`CONTENT_SECURITY_POLICY`.
    :data:`INSIDE` puts them **in the page**: the two pages that can reach a browser nobody has
    recognised carry them in one ``<style>`` block, read at this answer by the same function that
    serves them (:func:`sheet_text`), and the page gets :func:`inside_policy` of **that** text — the
    block and its hash are one value (M17.2c dec. 7, ADR 0050). The sheets stay behind the
    middleware: nothing here answers anybody who is nobody yet.
    """
    if isinstance(sheets, Sheets):
        text = "".join(sheet_text(sheet) for sheet in STYLESHEETS)
        styles = fragment(surface, "style", sheets=Markup(text))
        policy = inside_policy(text)
    else:
        styles = joined(
            fragment(surface, "stylesheet", href=f"{sheets}{sheet}") for sheet in STYLESHEETS
        )
        policy = CONTENT_SECURITY_POLICY
    document = fragment(surface, "shell", styles=styles, content=fragment(surface, name, **values))
    return HTMLResponse(
        content=document,
        status_code=status,
        headers={"Content-Security-Policy": policy, "Cache-Control": NO_STORE},
    )


def sheet_text(name: str) -> str:
    """One of the two derived sheets of the design system, as text, read now from ``apps/``.

    The one reading of a sheet: the route of a sheet serves it, and a page with its sheets inside
    joins it into its block — the same file, the same way, for a recognised browser and for whoever
    is nobody yet (M17.2c dec. 7). Named against :data:`STYLESHEETS` and never joined to a path from
    the request: what the browser asks for chooses **between two files**, and cannot describe one.
    ``read_text`` turns every ``\r\n`` into ``\n``, as a browser's parser does inside the block.
    """
    if name not in STYLESHEETS:
        raise ValueError(f"{name} is not one of the sheets ela.api serves: {STYLESHEETS}")
    return (DESIGN_SYSTEM / name).read_text(encoding="utf-8")


def stylesheet(name: str) -> Response:
    """One of the two derived sheets of the design system, as a response (ADR 0042)."""
    return Response(
        content=sheet_text(name), media_type="text/css", headers={"Cache-Control": NO_STORE}
    )


def closes_the_block(text: str) -> bool:
    """Whether ``text``, inside a ``<style>`` block, would close it (M17.2c correction C).

    ``</style`` in any case — more than the exact rule of the parser, which wants a space, ``/`` or
    ``>`` after it, and containing it. **The one statement of the rule**: the start-up asks it of
    every sheet, and so does ``tests/design/test_inline_block.py``; a second, wider rule «to be
    safe» would be a second opinion on the same question.
    """
    return "</style" in text.lower()


def inside_policy(text: str) -> str:
    """The policy of a page whose sheets are ``text``, inside it (M17.2c dec. 8, ADR 0050).

    The same as :data:`CONTENT_SECURITY_POLICY` in everything but ``style-src``, which admits the
    ``sha256`` of ``text`` encoded in UTF-8 — what a browser hashes of a ``<style>`` element — and
    nothing else: not ``'self'``, because the page loads nothing, and never ``'unsafe-inline'``.
    Derived at every answer from the text the block carries, never written down and never listed.
    """
    digest = base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii")
    return f"default-src 'none'; style-src 'sha256-{digest}'; {_STANDING}"
