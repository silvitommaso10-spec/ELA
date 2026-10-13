"""Which answers are a document of the main frame, and a document that never came (M13.9,
decision 106).

The adapter of the browser keeps the status of every document the main frame was given, so that
a login that did not work can say with which status its page came back. What a page loads beside
its document — an image, a script, the document of a frame inside it — is not that, and an
answer of theirs that arrived last would be told as the page's. **And a document that was asked
for and never came has no status**: the one of the page before it is not it — a site that takes
a login and answers nothing would be told with the ``200`` of its form (the re-read of
2026-10-12).

Asked here of the two functions alone, with requests and answers the test makes: on a real page
the order those arrive in is the network's.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ela.infrastructure.machine.browser import _answered, _asked


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


def walked(page: Shown, *events: Asked | Answer) -> list[int | None]:
    """The statuses the adapter keeps after these requests and answers, in their order."""
    documents: list[int | None] = []
    where: Any = page
    for event in events:
        anything: Any = event
        if isinstance(event, Asked):
            _asked(documents, anything, where)
        else:
            _answered(documents, anything, where)
    return documents


def test_the_documents_of_the_main_frame_are_told_with_their_status_in_their_order() -> None:
    main = object()
    first, then = Asked(True, main), Asked(True, main)

    kept = walked(Shown(main), first, Answer(first, 302), then, Answer(then, 200))

    assert kept == [302, 200], "the redirect's, and then the page's"


def test_what_the_page_loads_beside_its_document_is_not_a_document_of_the_page() -> None:
    main = object()
    document, image = Asked(True, main), Asked(False, main)

    kept = walked(Shown(main), document, Answer(document, 200), image, Answer(image, 404))

    assert kept == [200], "an image, a script"


def test_the_document_of_a_frame_inside_the_page_is_not_the_page_s() -> None:
    main, inner = object(), object()
    document, framed = Asked(True, main), Asked(True, inner)

    kept = walked(Shown(main), document, Answer(document, 200), framed, Answer(framed, 500))

    assert kept == [200]


def test_a_document_that_was_asked_for_and_never_came_has_no_status() -> None:
    main = object()
    form, sent = Asked(True, main), Asked(True, main)

    kept = walked(Shown(main), form, Answer(form, 200), sent)

    assert kept == [200, None], "the status of the form is not the status of what came after"


def test_an_answer_nobody_was_seen_asking_for_is_kept_all_the_same() -> None:
    """A page the browser opened by itself before the adapter listened: its answer is not lost."""
    main = object()

    assert walked(Shown(main), Answer(Asked(True, main), 200)) == [200]
