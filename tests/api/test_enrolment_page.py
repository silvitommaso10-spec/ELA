"""The pages that reach whoever ELA does not recognise yet (M17.2c; ADR 0050).

Two pages can reach a browser that no cookie has recognised — the enrolment form and the page
«rifiutata» — and they carry the design system **inside**, in one ``<style>`` block the policy
admits by its ``sha256``: no route answers anybody who is nobody yet (ADR 0037 §3), and no policy
says ``'unsafe-inline'``. Everything here is read off the response the browser would get, never
recomputed beside it: the hash a test calculates from its own copy of the sheets would agree with
the code on every day the two were wrong together.

Every way to those two pages is walked, on both surfaces (dec. 9): no cookie, a cookie that is
nobody's, a secret that does not match, an empty code, a code that does not exist, a declaration
the surface refuses, a form that did not come from ELA, and a failure under the prefix — the
``_handler`` of ``api/app.py`` composes the page «rifiutata» too.
"""

from __future__ import annotations

import base64
import hashlib
import re
import shutil
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from hypothesis import given
from hypothesis import strategies as st

from ela.api import pages
from ela.api.pages import CONTENT_SECURITY_POLICY, STYLESHEETS
from ela.api.security import COMPANION_SURFACE, CONSOLE_SURFACE, SEPARATOR, Surface
from tests.api.support import BASE
from tests.design import markup
from tests.design.test_no_network import CSS_IMPORT, CSS_URL, HINTS, IMAGE_SET, URL_ATTRIBUTES

ORIGIN = {"Origin": BASE}
ELSEWHERE = {"Origin": "http://altrove"}
NAVIGATION = {("a", "href"), ("form", "action"), ("button", "formaction")}
"""Where an address in a page is a place the user goes, not a thing the browser loads."""


@dataclass(frozen=True)
class Ground:
    """A surface, and what a browser declares on it."""

    surface: Surface
    declared: dict[str, str]
    refused_declaration: dict[str, str]
    """A declaration this surface answers ``422``: the phone is an iPhone, the console takes any
    system but not a code of another role — for the console, the refusal is carried by the code."""
    role: str
    other_role: str

    @property
    def enroll(self) -> str:
        return f"{self.surface.prefix}enroll"


PHONE = Ground(
    COMPANION_SURFACE,
    {"name": "iPhone", "os": "IOS"},
    {"name": "iPhone", "os": "MACOS"},
    "COMPANION",
    "COMPANION",
)
CONSOLE = Ground(
    CONSOLE_SURFACE,
    {"name": "MacBook", "os": "MACOS"},
    {"name": "MacBook", "os": "MACOS"},
    "CONSOLE",
    "COMPANION",
)
GROUNDS = (PHONE, CONSOLE)


def ground_id(ground: Ground) -> str:
    return ground.surface.name


# ----------------------------------------------------------------------------------------
# Reading a response as the browser reads it
# ----------------------------------------------------------------------------------------


class _Styles(HTMLParser):
    """The text of every ``<style>`` element, exactly as the parser hands it over."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[str] = []
        self._inside = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "style":
            self._inside = True
            self.found.append("")

    def handle_endtag(self, tag: str) -> None:
        if tag == "style":
            self._inside = False

    def handle_data(self, data: str) -> None:
        if self._inside:
            self.found[-1] += data


def blocks(page: str) -> list[str]:
    parser = _Styles()
    parser.feed(page)
    parser.close()
    return parser.found


def the_block(page: str) -> str:
    found = blocks(page)
    assert len(found) == 1, f"one <style> block, not {len(found)}"
    return found[0]


def outside_the_block(page: str) -> str:
    return re.sub(r"<style>.*?</style>", "", page, flags=re.DOTALL)


def hash_of(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return f"'sha256-{base64.b64encode(digest).decode('ascii')}'"


def directives(policy: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for directive in policy.split(";"):
        words = directive.split()
        if words:
            found[words[0]] = words[1:]
    return found


def faults_of(policy: str) -> list[str]:
    """Why a policy admits something ELA did not write, or a script."""
    found = []
    written = directives(policy)
    if written.get("default-src") != ["'none'"]:
        found.append("default-src is not 'none'")
    if "script-src" in written or "script-src-elem" in written:
        found.append("a script-src")
    for word in ("'unsafe-inline'", "'unsafe-hashes'", "'unsafe-eval'", "'nonce-"):
        if word in policy:
            found.append(word)
    return found


# ----------------------------------------------------------------------------------------
# The ways to the two pages
# ----------------------------------------------------------------------------------------


async def mint(client: AsyncClient, role: str) -> str:
    minted = await client.post("/nodes/enrollments", json={"privacy": "TRUSTED", "role": role})
    assert minted.status_code == 201, minted.text
    code: str = minted.json()["code"]
    return code


def browser(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url=BASE)


async def enrolled(app: FastAPI, client: AsyncClient, ground: Ground) -> str:
    """The cookie a browser leaves with, after a real enrolment on ``ground``."""
    async with browser(app) as opened:
        answered = await opened.post(
            ground.enroll,
            data={"code": await mint(client, ground.role), **ground.declared},
            headers=ORIGIN,
        )
        assert answered.status_code == 303, answered.text
        cookie = opened.cookies.get(ground.surface.cookie)
    assert cookie is not None
    return cookie


Way = Callable[[FastAPI, AsyncClient, Ground], Awaitable[Response]]


async def no_cookie(app: FastAPI, client: AsyncClient, ground: Ground) -> Response:
    async with browser(app) as opened:
        return await opened.get(ground.surface.prefix)


async def a_cookie_of_nobody(app: FastAPI, client: AsyncClient, ground: Ground) -> Response:
    async with browser(app) as opened:
        opened.cookies.set(ground.surface.cookie, "nobody")
        return await opened.get(ground.surface.prefix)


async def a_wrong_secret(app: FastAPI, client: AsyncClient, ground: Ground) -> Response:
    claimed = (await enrolled(app, client, ground)).split(SEPARATOR, 1)[0]
    async with browser(app) as opened:
        opened.cookies.set(ground.surface.cookie, f"{claimed}{SEPARATOR}{'x' * 43}")
        return await opened.get(ground.surface.prefix)


async def an_empty_code(app: FastAPI, client: AsyncClient, ground: Ground) -> Response:
    async with browser(app) as opened:
        return await opened.post(
            ground.enroll, data={"code": "", **ground.declared}, headers=ORIGIN
        )


async def a_code_that_does_not_exist(app: FastAPI, client: AsyncClient, ground: Ground) -> Response:
    async with browser(app) as opened:
        return await opened.post(
            ground.enroll, data={"code": "y" * 43, **ground.declared}, headers=ORIGIN
        )


async def a_declaration_refused(app: FastAPI, client: AsyncClient, ground: Ground) -> Response:
    async with browser(app) as opened:
        return await opened.post(
            ground.enroll,
            data={"code": await mint(client, ground.other_role), **ground.refused_declaration},
            headers=ORIGIN,
        )


async def a_form_not_from_ela(app: FastAPI, client: AsyncClient, ground: Ground) -> Response:
    async with browser(app) as opened:
        return await opened.post(
            ground.enroll, data={"code": "z" * 43, **ground.declared}, headers=ELSEWHERE
        )


async def a_failure_under_the_prefix(app: FastAPI, client: AsyncClient, ground: Ground) -> Response:
    """The ``_handler`` of ``api/app.py``: a question that does not exist becomes the page
    «rifiutata», composed after an identity — the rule is the page's, not the request's."""
    cookie = await enrolled(app, client, ground)
    async with browser(app) as opened:
        opened.cookies.set(ground.surface.cookie, cookie)
        return await opened.get(f"{ground.surface.prefix}approval?id={uuid.uuid4()}")


WAYS: dict[str, tuple[Way, int]] = {
    "no-cookie": (no_cookie, 401),
    "a-cookie-of-nobody": (a_cookie_of_nobody, 401),
    "a-wrong-secret": (a_wrong_secret, 401),
    "an-empty-code": (an_empty_code, 401),
    "a-code-that-does-not-exist": (a_code_that_does_not_exist, 401),
    "a-declaration-refused": (a_declaration_refused, 422),
    "a-form-not-from-ela": (a_form_not_from_ela, 403),
    "a-failure-under-the-prefix": (a_failure_under_the_prefix, 404),
}
EVERY_WAY = [
    pytest.param(ground, way, id=f"{ground.surface.name}-{way}")
    for ground in GROUNDS
    for way in WAYS
]


async def reached(app: FastAPI, client: AsyncClient, ground: Ground, way: str) -> Response:
    walk, status = WAYS[way]
    answered = await walk(app, client, ground)
    assert answered.status_code == status, answered.text[:300]
    return answered


# ----------------------------------------------------------------------------------------
# The three tests of the registration
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(("ground", "way"), EVERY_WAY)
async def test_the_hash_of_the_policy_is_the_hash_of_the_block_it_serves(
    ground: Ground, way: str, app: FastAPI, client: AsyncClient
) -> None:
    """The block is read off the response, and so is the policy: the one source of ``style-src``
    is the hash of those very bytes."""
    answered = await reached(app, client, ground, way)

    block = the_block(answered.text)
    policy = answered.headers["content-security-policy"]

    assert directives(policy)["style-src"] == [hash_of(block)]


@pytest.mark.parametrize("ground", GROUNDS, ids=ground_id)
async def test_a_change_to_the_design_system_moves_the_block_and_the_hash_together(
    ground: Ground,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A copy of the design system, the composer pointed at it, one rule added to the end of
    ``components.css`` — and nothing else. The same application answers before and after, so a
    cache between the two would make this red."""
    copy = tmp_path / "design-system"
    shutil.copytree(pages.APPS / "design-system", copy)
    monkeypatch.setattr(pages, "DESIGN_SYSTEM", copy)
    rule = ".ela-m17-2c-probe { outline: 0; }\n"

    async with browser(app) as opened:
        before = await opened.get(ground.surface.prefix)
        sheet = copy / "components.css"
        sheet.write_text(sheet.read_text(encoding="utf-8") + rule, encoding="utf-8")
        after = await opened.get(ground.surface.prefix)

    assert rule not in the_block(before.text)
    assert the_block(after.text).endswith(rule)
    policy = after.headers["content-security-policy"]
    assert directives(policy)["style-src"] == [hash_of(the_block(after.text))]
    assert policy != before.headers["content-security-policy"]


@pytest.mark.parametrize(("ground", "way"), EVERY_WAY)
async def test_the_enrolment_page_names_nothing_to_load(
    ground: Ground, way: str, app: FastAPI, client: AsyncClient
) -> None:
    """The block is there — otherwise every clause about it would pass on nothing — and nothing
    in the page makes the browser fetch: no element that loads, no address that is not a place
    the user goes on this surface, nothing in the sheets that reaches a file, and a policy with
    no ``'self'`` to allow it.

    The predicates of ``tests/design/test_no_network.py`` are reused, not written a second time;
    what differs is that here **every** reference in the sheets is a fault, because a page served
    to nobody has nothing it could load them with.
    """
    answered = await reached(app, client, ground, way)
    places = {path for _, path in ground.surface.routes | ground.surface.code_routes}

    block = the_block(answered.text)
    document = markup.parse(outside_the_block(answered.text))
    faults = []
    for element in document.walk():
        if element.tag in {"script", "base", "link", "img", "iframe", "object", "embed"}:
            faults.append(f"<{element.tag}>")
        if element.tag == "meta" and (element.get("http-equiv") or "").lower() == "refresh":
            faults.append('<meta http-equiv="refresh">')
        if set((element.get("rel") or "").lower().split()) & HINTS:
            faults.append(f'rel="{element.get("rel")}"')
        for name, value in element.attributes.items():
            if name.lower().startswith("on"):
                faults.append(f"{name}=")
            if name.lower() not in URL_ATTRIBUTES or value is None:
                continue
            if (element.tag, name.lower()) not in NAVIGATION or value not in places:
                faults.append(f"<{element.tag} {name}={value!r}>")
    references = CSS_URL.findall(block) + CSS_IMPORT.findall(block) + IMAGE_SET.findall(block)

    assert faults == []
    assert references == []
    assert "local(" not in block
    policy = directives(answered.headers["content-security-policy"])
    assert policy["default-src"] == ["'none'"]
    assert "'self'" not in policy["style-src"]


# ----------------------------------------------------------------------------------------
# The same files, the two policies, the recognised pages
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("ground", GROUNDS, ids=ground_id)
async def test_the_block_is_what_the_sheet_routes_serve(
    ground: Ground, app: FastAPI, client: AsyncClient
) -> None:
    """The same files, read the same way: what a recognised browser downloads, in the order it
    links it, is byte for byte what the page of whoever is nobody yet carries."""
    cookie = await enrolled(app, client, ground)
    async with browser(app) as recognised:
        recognised.cookies.set(ground.surface.cookie, cookie)
        served = [
            (await recognised.get(f"{ground.surface.prefix}{sheet}")).text for sheet in STYLESHEETS
        ]
    async with browser(app) as nobody:
        page = await nobody.get(ground.surface.prefix)

    assert the_block(page.text) == "".join(served)


def test_a_policy_that_admits_what_ela_did_not_write_is_a_fault() -> None:
    """The negative case of the predicate the next two tests lean on."""
    assert faults_of("default-src 'none'; style-src 'unsafe-inline'") == ["'unsafe-inline'"]
    assert faults_of("default-src 'self'") == ["default-src is not 'none'"]
    assert faults_of("default-src 'none'; script-src 'nonce-abc'") == ["a script-src", "'nonce-"]


@given(st.text())
def test_no_policy_admits_a_style_or_a_script_it_did_not_write(text: str) -> None:
    """Correction D: the two producers of a policy in ``pages.py`` — the constant of the pages that
    link their sheets, and the function of the pages that carry them — are where the coverage
    comes from, for **every** text of a block, not from a list of pages."""
    from ela.api.pages import inside_policy

    derived = inside_policy(text)

    assert faults_of(CONTENT_SECURITY_POLICY) == []
    assert faults_of(derived) == []
    assert directives(derived)["style-src"] == [hash_of(text)]
    assert {name: words for name, words in directives(derived).items() if name != "style-src"} == {
        name: words
        for name, words in directives(CONTENT_SECURITY_POLICY).items()
        if name != "style-src"
    }


@pytest.mark.parametrize("ground", GROUNDS, ids=ground_id)
async def test_a_sample_of_pages_carries_one_of_the_two_policies(
    ground: Ground, app: FastAPI, client: AsyncClient
) -> None:
    """Only a sample: the home, a page that does not exist, the form, the page «rifiutata». The
    coverage is the functions' (the test above); this says the pages use them."""
    cookie = await enrolled(app, client, ground)
    async with browser(app) as recognised:
        recognised.cookies.set(ground.surface.cookie, cookie)
        linked = [
            await recognised.get(ground.surface.prefix),
            await recognised.get(f"{ground.surface.prefix}qualcosa"),
        ]
    inside = [
        await reached(app, client, ground, way) for way in ("no-cookie", "a-form-not-from-ela")
    ]

    for answered in linked:
        assert answered.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    for answered in inside:
        assert directives(answered.headers["content-security-policy"])["style-src"] == [
            hash_of(the_block(answered.text))
        ]


@pytest.mark.parametrize("ground", GROUNDS, ids=ground_id)
async def test_a_recognized_page_links_its_sheets_and_carries_no_block(
    ground: Ground, app: FastAPI, client: AsyncClient
) -> None:
    cookie = await enrolled(app, client, ground)
    async with browser(app) as recognised:
        recognised.cookies.set(ground.surface.cookie, cookie)
        home = await recognised.get(ground.surface.prefix)

    links = [
        element.get("href")
        for element in markup.parse(home.text).walk()
        if element.tag == "link" and element.get("rel") == "stylesheet"
    ]
    assert links == [f"{ground.surface.prefix}{sheet}" for sheet in STYLESHEETS]
    assert blocks(home.text) == []
    assert home.headers["content-security-policy"] == CONTENT_SECURITY_POLICY


# ----------------------------------------------------------------------------------------
# The page, dressed (dec. 10)
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("ground", GROUNDS, ids=ground_id)
async def test_the_enrolment_page_is_dressed_with_the_design_system(
    ground: Ground, app: FastAPI
) -> None:
    """The title, the sentences, every field as the component is made — a label bound to its input
    by ``for`` and ``id`` — and the primary button: the sheet arrives, and the part the user
    touches is drawn by it and not by the browser."""
    async with browser(app) as nobody:
        page = await nobody.get(ground.surface.prefix)

    document = markup.parse(outside_the_block(page.text))
    elements = list(document.walk())
    inputs = [one for one in elements if one.tag == "input"]
    labels = {one.get("for"): one for one in elements if one.tag == "label"}

    assert any("ela-title" in one.classes for one in elements if one.tag == "h1")
    assert inputs and all("ela-field__input" in one.classes for one in inputs)
    assert all(
        one.get("id") in labels and "ela-field__label" in labels[one.get("id")].classes
        for one in inputs
    )
    buttons = [one for one in elements if one.tag == "button"]
    assert buttons and all(
        {"ela-button", "ela-button--primary"} <= set(one.classes) for one in buttons
    )
