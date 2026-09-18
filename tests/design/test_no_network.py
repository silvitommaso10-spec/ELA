"""Nothing is loaded from outside, and nothing runs (M17.1, criterio 5; dec. 2 and dec. M).

Every reference of every ``.html`` and ``.css`` under ``apps/design-system/`` — the derived
files too — is a **relative path that stays inside the folder and exists**. The same property
makes the folder relocatable: M12.5 and M17.2 can serve it from wherever they like.

No JavaScript at all: the decision forbids a library's, and nothing M17.1 renders needs any.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.design import markup
from tests.design.tree import DESIGN_SYSTEM

URL_ATTRIBUTES = {
    "href",
    "src",
    "srcset",
    "poster",
    "action",
    "formaction",
    "data",
    "ping",
    "manifest",
    "cite",
    "background",
    "xlink:href",
}
HINTS = {"preconnect", "dns-prefetch", "prefetch", "prerender", "modulepreload"}
"""``rel`` values whose whole purpose is to reach another host."""

SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
CSS_URL = re.compile(r"url\(\s*(?:\"([^\"]*)\"|'([^']*)'|([^)\"']*?))\s*\)")
CSS_IMPORT = re.compile(r"@import\s+(?:\"([^\"]*)\"|'([^']*)')")
IMAGE_SET = re.compile(r"image-set\(([^;{}]*)\)")
QUOTED = re.compile(r"\"([^\"]*)\"|'([^']*)'")
COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def fault_in_reference(reference: str, base: Path, folder: Path) -> str | None:
    """Why ``reference``, found in a file that lives in ``base``, is not a file of ours."""
    reference = reference.strip()
    if reference.lower().startswith("javascript:"):
        return f"{reference}: a javascript: URL"
    if SCHEME.match(reference):
        return f"{reference}: an absolute URL — nothing is loaded from outside"
    if reference.startswith("//"):
        return f"{reference}: a protocol-relative URL"
    if reference.startswith("/"):
        return f"{reference}: an absolute path — the folder would not be relocatable"
    path = (base / reference.split("#", 1)[0].split("?", 1)[0]).resolve()
    if not path.is_relative_to(folder.resolve()):
        return f"{reference}: leaves the folder"
    if not path.is_file():
        return f"{reference}: no such file"
    return None


def faults_in_html(text: str, base: Path, folder: Path) -> list[str]:
    document = markup.parse(text)
    identifiers = {element.get("id") for element in document.walk() if element.get("id")}
    found = []
    for element in document.walk():
        if element.tag == "script":
            found.append("<script>: the design system runs no JavaScript")
        if element.tag == "base":
            found.append("<base>: it would move every relative reference")
        if element.tag == "meta" and (element.get("http-equiv") or "").lower() == "refresh":
            found.append('<meta http-equiv="refresh">: it navigates away')
        if element.tag == "link" and set((element.get("rel") or "").lower().split()) & HINTS:
            found.append(f'<link rel="{element.get("rel")}">: a hint whose purpose is another host')
        for name, value in element.attributes.items():
            if name.lower().startswith("on"):
                found.append(f"<{element.tag} {name}=…>: an event handler is JavaScript")
            if name.lower() not in URL_ATTRIBUTES or value is None:
                continue
            references = (
                [part.split()[0] for part in value.split(",")] if name == "srcset" else [value]
            )
            for reference in references:
                if reference.startswith("#"):
                    if reference[1:] not in identifiers:
                        found.append(f"{reference}: an anchor to an id this document lacks")
                    continue
                if (fault := fault_in_reference(reference, base, folder)) is not None:
                    found.append(fault)
    return found


def faults_in_css(text: str, base: Path, folder: Path) -> list[str]:
    text = COMMENT.sub("", text)
    found = []
    if "local(" in text:
        found.append("local(): an installed font may be another version — only our files")
    references = ["".join(groups) for groups in CSS_URL.findall(text)]
    references += ["".join(groups) for groups in CSS_IMPORT.findall(text)]
    for arguments in IMAGE_SET.findall(text):
        references += ["".join(groups) for groups in QUOTED.findall(arguments)]
    for reference in references:
        if (fault := fault_in_reference(reference, base, folder)) is not None:
            found.append(fault)
    return found


def files(suffix: str) -> list[Path]:
    found = sorted(DESIGN_SYSTEM.rglob(f"*{suffix}"))
    assert found, f"there must be {suffix} files to read, or this test is vacuous"
    return found


# ----------------------------------------------------------------------------------------
# The tree
# ----------------------------------------------------------------------------------------


def test_every_reference_of_every_page_is_a_file_of_the_folder() -> None:
    for path in files(".html"):
        text = path.read_text(encoding="utf-8")
        assert faults_in_html(text, path.parent, DESIGN_SYSTEM) == [], path.name


def test_every_reference_of_every_stylesheet_is_a_file_of_the_folder() -> None:
    for path in files(".css"):
        text = path.read_text(encoding="utf-8")
        assert faults_in_css(text, path.parent, DESIGN_SYSTEM) == [], path.name


def test_the_page_links_the_stylesheets_a_surface_will_link() -> None:
    """The risk the registration named: a specimen that holds a copy of its own."""
    page = markup.parse((DESIGN_SYSTEM / "index.html").read_text(encoding="utf-8"))
    linked = [
        el.get("href") for el in page.walk() if el.tag == "link" and el.get("rel") == "stylesheet"
    ]
    assert linked[:2] == ["tokens.css", "components.css"]
    assert not [element for element in page.walk() if element.tag == "style"]


# ----------------------------------------------------------------------------------------
# One negative for every way of being wrong
# ----------------------------------------------------------------------------------------


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    root = tmp_path / "design-system"
    (root / "fonts").mkdir(parents=True)
    (root / "tokens.css").write_text("", encoding="utf-8")
    (root / "fonts" / "a.woff2").write_bytes(b"wOF2")
    (tmp_path / "outside.css").write_text("", encoding="utf-8")
    return root


WRONG_HTML = [
    (
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter">',
        "absolute URL",
    ),
    ('<link rel="stylesheet" href="http://example.com/a.css">', "absolute URL"),
    ('<script src="//cdn.example.com/lib.js"></script>', "protocol-relative"),
    ('<img src="data:image/png;base64,AAAA">', "absolute URL"),
    ('<link rel="stylesheet" href="/tokens.css">', "absolute path"),
    ('<link rel="stylesheet" href="../outside.css">', "leaves the folder"),
    ('<link rel="stylesheet" href="missing.css">', "no such file"),
    ('<img srcset="tokens.css 1x, https://example.com/a.png 2x">', "absolute URL"),
    ('<form action="https://example.com/collect"></form>', "absolute URL"),
    ('<button formaction="https://example.com/collect"></button>', "absolute URL"),
    ('<a href="tokens.css" ping="https://example.com/ping">x</a>', "absolute URL"),
    ('<base href="https://example.com/">', "<base>"),
    ('<link rel="preconnect" href="tokens.css">', "a hint whose purpose is another host"),
    ('<link rel="dns-prefetch" href="tokens.css">', "a hint whose purpose is another host"),
    ('<meta http-equiv="refresh" content="0; url=https://example.com">', "navigates away"),
    ("<script>document.title = 1</script>", "<script>"),
    ('<button onclick="go()">x</button>', "an event handler"),
    ('<a href="javascript:go()">x</a>', "javascript:"),
    ('<a href="#nowhere">x</a>', "an anchor to an id this document lacks"),
]


@pytest.mark.parametrize(("text", "fault"), WRONG_HTML, ids=[case[0][:40] for case in WRONG_HTML])
def test_a_page_that_reaches_outside_is_a_fault(folder: Path, text: str, fault: str) -> None:
    found = faults_in_html(text, folder, folder)
    assert any(fault in line for line in found), found


WRONG_CSS = [
    ('@import "https://fonts.googleapis.com/css2?family=Inter";', "absolute URL"),
    ("@import url(//example.com/a.css);", "protocol-relative"),
    ('@font-face { src: url("https://example.com/a.woff2"); }', "absolute URL"),
    ("@font-face { src: url(../outside.css); }", "leaves the folder"),
    ("@font-face { src: url('fonts/missing.woff2'); }", "no such file"),
    ('@font-face { src: local("Inter"), url("fonts/a.woff2"); }', "local()"),
    ('a { background: image-set("https://example.com/a.png" 1x); }', "absolute URL"),
    ("a { background: url(data:image/png;base64,AAAA); }", "absolute URL"),
]


@pytest.mark.parametrize(("text", "fault"), WRONG_CSS, ids=[case[0][:40] for case in WRONG_CSS])
def test_a_stylesheet_that_reaches_outside_is_a_fault(folder: Path, text: str, fault: str) -> None:
    found = faults_in_css(text, folder, folder)
    assert any(fault in line for line in found), found


def test_what_stays_inside_is_not_a_fault(folder: Path) -> None:
    """The control, and the one reference a stylesheet of ours will really make: a font."""
    html = '<link rel="stylesheet" href="tokens.css"><h2 id="here">x</h2><a href="#here">x</a>'
    assert faults_in_html(html, folder, folder) == []
    assert (
        faults_in_css('@font-face { src: url("fonts/a.woff2") format("woff2"); }', folder, folder)
        == []
    )
    assert faults_in_css("/* see https://example.com */ a { margin: 0; }", folder, folder) == []
