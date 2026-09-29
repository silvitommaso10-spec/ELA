"""The grammar of a browser call, in the one place it is decided (M13.4 forms E, F, H; ADR 0052).

A site is a host name and nothing else, read by the schema, the settings and the tool from
``SITE_PATTERN``; a path is the rest of an address; a selector is Playwright's, with nothing that
would change its engine. The boundary is a function of origins — the declared sites for a read, the
site of the question for an action —, and ``http`` against ``https`` is another origin. These are
pure: no browser, no network.
"""

from __future__ import annotations

import re

import pytest

from ela.permissions import PATH_PATTERN, SITE_PATTERN
from ela.tools.base import ARGUMENTS_INVALID
from ela.tools.browser import (
    SECRET_AUTOCOMPLETE,
    TEXT_MAX_BYTES,
    _secret,
    _selector,
    boundary,
    cut,
    https_origin,
    origin_of,
)


@pytest.mark.parametrize(
    "site",
    ["example.com", "www.example.com", "a-b.example.com", "xn--bcher-kva.example", "httpbin.org"],
)
def test_a_host_name_is_a_site(site: str) -> None:
    assert re.search(SITE_PATTERN, site)


@pytest.mark.parametrize(
    "site",
    [
        "EXAMPLE.com",
        "192.168.1.1",
        "localhost",
        "example.com.",
        "example.com:8080",
        "https://example.com",
        "example.com/path",
        "exa mple.com",
        "bücher.example",
        "-a.example.com",
        "a-.example.com",
        "*.example.com",
        "example.com\n",
        "undeclared",
        "",
        "a." * 127 + "com",
    ],
)
def test_anything_else_is_not(site: str) -> None:
    assert re.search(SITE_PATTERN, site) is None


@pytest.mark.parametrize("path", ["/", "/forms/post", "/a?b=c&d=%20e#f", "/redirect-to?url=x"])
def test_a_path_is_the_rest_of_an_address(path: str) -> None:
    assert re.search(PATH_PATTERN, path)


@pytest.mark.parametrize("path", ["", "forms", "/a b", "/x\n", "/tab\there", "/\\", "/ü"])
def test_a_path_holds_only_the_characters_of_a_url(path: str) -> None:
    assert re.search(PATH_PATTERN, path) is None


def test_an_origin_is_the_scheme_and_the_host_and_never_what_is_written_before_it() -> None:
    assert origin_of("https://Example.com/a?b") == "https://example.com"
    assert origin_of("http://127.0.0.1:8765/x") == "http://127.0.0.1:8765"
    written_before = "https://user:secret@evil.example/login"  # pragma: allowlist secret
    assert origin_of(written_before) == "https://evil.example"
    assert origin_of("https://example.com:notaport/") == "https://example.com"
    assert https_origin("example.com") == "https://example.com"


def test_the_boundary_is_a_set_of_origins() -> None:
    allowed = boundary(frozenset({"https://example.com"}))

    assert allowed("https://example.com/")
    assert allowed("https://EXAMPLE.com/a")
    assert not allowed("http://example.com/"), "http against https is another origin"
    assert not allowed("https://example.com:8443/"), "and so is another port"
    assert not allowed("https://www.example.com/"), "a site is itself and nothing else"
    assert not allowed("https://example.com.evil.org/")
    assert not allowed("about:blank")


@pytest.mark.parametrize(
    "selector",
    ["#name", "input[name=custname]", "form button", "button:has-text('Invia')", "a >> text"],
)
def test_a_selector_is_handed_as_it_stands_unless_it_changes_engine(selector: str) -> None:
    refused = _selector(selector, "click")

    if ">>" in selector:
        assert refused is not None and refused.code == ARGUMENTS_INVALID
    else:
        assert refused is None


@pytest.mark.parametrize(
    "selector",
    [
        "text=Invia",
        "xpath=//a",
        "css=button",
        "internal:role=button",
        '"Invia"',
        "'Invia'",
        "//a",
        "..",
        "a\nb",
        "",
        "x" * 513,
        7,
        None,
    ],
)
def test_a_selector_that_would_change_engine_is_refused_before_the_question(
    selector: object,
) -> None:
    refused = _selector(selector, "click")

    assert refused is not None and refused.code == ARGUMENTS_INVALID
    assert "click" in refused.message


@pytest.mark.parametrize(
    ("declared", "autocomplete"),
    [
        ("password", ""),
        ("text", "current-password"),
        ("text", "new-password"),
        ("text", "one-time-code"),
        ("text", "cc-number"),
        ("text", "cc-csc"),
        ("text", "cc-exp"),
        ("text", "cc-exp-month"),
        ("text", "shipping cc-number"),
    ],
)
def test_a_field_that_declares_itself_secret_is_secret(declared: str, autocomplete: str) -> None:
    assert _secret(declared, autocomplete)


@pytest.mark.parametrize(
    ("declared", "autocomplete"), [("text", ""), ("email", "email"), ("text", "name"), ("", "")]
)
def test_any_other_is_not_and_the_recognition_is_partial(declared: str, autocomplete: str) -> None:
    """A password in an ordinary text field passes: decision 6 says so of both recognitions."""
    assert not _secret(declared, autocomplete)
    assert "cc-number" in SECRET_AUTOCOMPLETE


def test_a_text_keeps_its_beginning_on_a_character() -> None:
    assert cut("breve") == ("breve", 5, 5)
    long = "è" * TEXT_MAX_BYTES  # two bytes each: the cut falls in the middle of none
    kept, shown, total = cut(long)
    assert total == 2 * TEXT_MAX_BYTES
    assert shown == TEXT_MAX_BYTES
    assert kept == "è" * (TEXT_MAX_BYTES // 2)
    odd = "a" + "è" * TEXT_MAX_BYTES
    kept, shown, _ = cut(odd)
    assert shown == TEXT_MAX_BYTES - 1, "an incomplete character at the end is given back"
    assert kept.encode() == odd.encode()[:shown]
