"""No logo, no symbol, no icon — defended, not only declared (M17.1, criterio 6; dec. 7, dec. K).

Two closed worlds. Under ``apps/design-system/`` only the kinds of file the design system is
made of exist, so a ``logo.png`` has nowhere to be; and no page carries an element that brings
an image. The wordmark is the word, as text.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.design import markup
from tests.design.tree import DESIGN_SYSTEM, fragments, read

EXTENSIONS = {".json", ".css", ".html", ".md", ".txt", ".woff2"}
PICTURES = {"img", "svg", "picture", "canvas", "video", "audio", "object", "embed", "iframe"}


def faults_in_folder(folder: Path) -> list[str]:
    found = []
    for path in sorted(folder.rglob("*")):
        if path.is_file() and path.suffix.lower() not in EXTENSIONS:
            found.append(
                f"{path.relative_to(folder)}: not a kind of file the design system is made of"
            )
    return found


def faults_in_page(text: str) -> list[str]:
    found = []
    for element in markup.parse(text).walk():
        if element.tag in PICTURES:
            found.append(f"<{element.tag}>: the design system draws nothing (dec. 7)")
        if element.tag == "link" and "icon" in (element.get("rel") or "").lower():
            found.append('<link rel="icon">: a favicon is a symbol')
        if "ela-wordmark" in element.classes and element.text() != "ELA":
            found.append(f"the wordmark says {element.text()!r}: it is the word «ELA», as text")
    return found


def test_only_the_kinds_of_file_the_design_system_is_made_of() -> None:
    assert list(DESIGN_SYSTEM.rglob("*")), "the folder must exist, or this test is vacuous"
    assert faults_in_folder(DESIGN_SYSTEM) == []


def test_no_page_brings_an_image_and_the_wordmark_is_text() -> None:
    for name, text in {"index.html": read("index.html"), **fragments()}.items():
        assert faults_in_page(text) == [], name


def test_the_wordmark_is_there_to_be_checked() -> None:
    page = markup.parse(read("index.html"))
    assert [el for el in page.walk() if "ela-wordmark" in el.classes], (
        "or the check above is vacuous"
    )


def test_a_logo_has_nowhere_to_be(tmp_path: Path) -> None:
    (tmp_path / "tokens.json").write_text("{}", encoding="utf-8")
    assert faults_in_folder(tmp_path) == []
    (tmp_path / "logo.png").write_bytes(b"\x89PNG")
    (tmp_path / "components").mkdir()
    (tmp_path / "components" / "mark.svg").write_text("<svg/>", encoding="utf-8")
    assert len(faults_in_folder(tmp_path)) == 2


WRONG = [
    ('<img src="logo.png" alt="ELA">', "<img>"),
    ('<svg viewBox="0 0 24 24"><path d="M0 0"/></svg>', "<svg>"),
    ("<picture></picture>", "<picture>"),
    ("<canvas></canvas>", "<canvas>"),
    ('<iframe src="other.html"></iframe>', "<iframe>"),
    ('<link rel="icon" href="favicon.ico">', "a favicon is a symbol"),
    ('<link rel="apple-touch-icon" href="icon.png">', "a favicon is a symbol"),
    ('<span class="ela-wordmark">E.L.A.</span>', "it is the word"),
    ('<span class="ela-wordmark"><b>E</b>LA ©</span>', "it is the word"),
]


@pytest.mark.parametrize(("text", "fault"), WRONG, ids=[case[0][:32] for case in WRONG])
def test_a_drawing_is_a_fault(text: str, fault: str) -> None:
    assert any(fault in line for line in faults_in_page(text))


def test_the_word_as_text_is_not_a_fault() -> None:
    assert faults_in_page('<span class="ela-wordmark ela-wordmark--lg">ELA</span>') == []
