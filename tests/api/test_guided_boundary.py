"""A gesture of a guided session and the boundary of its page (M13.4f, ADR 0064): nothing paid.

A gesture is a child task of one step, walked by the runner: the same tools as a plan's, each
with the boundary of its own step — the site of the session. So the predicate holds for a
gesture as for a step (decision 115), and what the model reads of it is the result of the
gesture: that the page was elsewhere, by its origin and with nothing of the page; and that the
page opened another, which was stopped (decision 123).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ela.domain import TaskState
from tests.api.guided import Script, approved_and_run, call, gesture, guided, planned
from tests.api.test_guided_session import children

ELSEWHERE = "https://altro.example/percorso?chiave=1"
SHOWN = "-".join(("what", "the", "other", "page", "shows"))
READ = {"site": "www.youtube.com", "path": "/results?search_query=MrBeast"}


async def test_a_gesture_that_finds_its_page_elsewhere_gives_the_model_nothing_of_that_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = Script([call(), gesture("read", **READ), call()])
    async with guided(monkeypatch, tmp_path, script) as g:
        g.browser.page.texts = {None: SHOWN}
        g.browser.moves["text"] = ELSEWHERE
        task = await planned(g)

        await approved_and_run(g, task)
        (child,) = await children(g, task)

    assert child.state is TaskState.FAILED
    said = script.read[0]
    assert "https://altro.example" in said, "the model is told where, by the origin"
    assert SHOWN not in said and "percorso" not in said and "chiave" not in said
    assert g.browser.kept == [], "and the page is handed to nobody"


async def test_a_gesture_whose_page_opened_another_tells_the_model_so(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from ela.ports import AnotherPage

    script = Script([call(), gesture("read", **READ), call()])
    async with guided(monkeypatch, tmp_path, script) as g:
        g.browser.page.texts = {None: "Risultati: @MrBeast"}
        g.browser.page.another = AnotherPage("GET", ELSEWHERE)
        task = await planned(g)

        await approved_and_run(g, task)
        (child,) = await children(g, task)

    assert child.state is TaskState.COMPLETED
    said = script.read[0]
    assert "another_page: https://altro.example" in said
    assert "percorso" not in said and "chiave" not in said
    assert "@MrBeast" in said, "the gesture worked all the same"
