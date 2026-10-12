"""Which answers are a document of the main frame (M13.9, decision 106).

The adapter of the browser keeps the status of every document the main frame was given, so that
a login that did not work can say with which status its page came back. What a page loads beside
its document — an image, a script, the document of a frame inside it — is not that, and an
answer of theirs that arrived last would be told as the page's. Asked here of the function alone,
with answers the test makes: on a real page the order those answers arrive in is the network's.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ela.infrastructure.machine.browser import _document


@dataclass
class Asked:
    navigation: bool
    frame: object

    def is_navigation_request(self) -> bool:
        return self.navigation


@dataclass
class Answer:
    request: Asked
    status: int


@dataclass
class Shown:
    main_frame: object


def said(answer: Answer, page: Shown) -> tuple[int, ...]:
    anything: Any = answer
    where: Any = page
    return _document(anything, where)


def test_the_document_of_the_main_frame_is_told_with_its_status() -> None:
    main = object()

    assert said(Answer(Asked(True, main), 302), Shown(main)) == (302,)
    assert said(Answer(Asked(True, main), 200), Shown(main)) == (200,)


def test_what_the_page_loads_beside_its_document_is_not_a_document_of_the_page() -> None:
    main = object()

    assert said(Answer(Asked(False, main), 404), Shown(main)) == (), "an image, a script"


def test_the_document_of_a_frame_inside_the_page_is_not_the_page_s() -> None:
    main, inner = object(), object()

    assert said(Answer(Asked(True, inner), 500), Shown(main)) == ()
