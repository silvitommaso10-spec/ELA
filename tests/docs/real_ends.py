"""What a real ELA answers along the proof of M13.1e, recorded once, for the tests of its script.

The lesson of the proof of M14.2 (decision 25 of its review): every kind of a script that reads the
API is fed **the answers of the routes themselves**. Here the script walks steps 2–10 of section 25
on ELA as ``build`` makes it, in this process: the commands of the guide through the command line
in this process (``in_this_process`` of the dry run of §22), the API through the CLI's own client,
the browser of ``ela.testing`` with ``#non-esiste`` missing from the page, and a console and a phone
enrolled through their own pages (``tests/api/ends.py``). The hand of each ``mano`` — the
«Rifiuta» of the console, the «No» of the phone — is given through that page, between the blocks
before it and the ``guarda`` after it, as Tommaso gives it while the script watches.

Then the answers the script read are recorded, by route: a negative case starts from one of them
and changes it (:func:`changed`); nothing else is written by hand.
"""

from __future__ import annotations

import asyncio
import copy
import io
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from ela.api import companion, console
from ela.testing.fakes import FakePage
from tests.api.ends import Surfaces, opened_surfaces, the_console_says_no, the_phone_says_no
from tests.cli.test_section_22_on_the_cli import in_this_process

MISSING = FakePage(counts={"#non-esiste": 0})
"""What example.com does for the plan of step 5: the page has no ``#non-esiste``."""
HANDS: Mapping[str, Callable[[Surfaces, str], Awaitable[None]]] = {
    "Dalla console": the_console_says_no,
    "Dal telefono": the_phone_says_no,
}
"""How each ``mano`` of the section starts, and the page that gives it."""
FAILING_STEP = 5


@dataclass(frozen=True)
class Real:
    """What the script wrote walking steps 2–10, and the answers of the routes it read."""

    lines: tuple[str, ...]
    asked: tuple[str, ...]
    """The questions it asked: the yes of step 5, and the ten of the eye."""
    ids: Mapping[int, str]
    """The task of each step."""
    health: Any
    openapi: Any
    devices: Any
    waiting: Mapping[int, Any]
    """``GET /tasks/<id>`` of each step with a ``mano``, while its question waited for the hand."""
    approvals: Any
    """``GET /approvals`` while the question of step 3 waited."""
    tasks: Mapping[int, Any]
    """``GET /tasks/<id>`` of each step's task, at the end."""
    audits: Mapping[int, Any]
    """``GET /audit?task_id=<id>`` of each step's task, at the end."""
    finished: Mapping[int, Any]
    """``GET /tasks/finished?limit=N`` at the end, for each ``N`` the script reads."""

    def answers(self, step: int) -> dict[str, Any]:
        """What ``fine`` reads for ``step``, by path, as the script asks it."""
        task = self.ids[step]
        return {
            f"/tasks/{task}": self.tasks[step],
            f"/audit?task_id={task}": self.audits[step],
            "/devices": self.devices,
            f"/tasks/finished?limit={max(self.finished)}": self.finished[max(self.finished)],
        }


def todo_of(module: ModuleType) -> dict[int, list[Any]]:
    by_step: dict[int, list[Any]] = module.base.steps(
        module.base.blocks(module.GUIDE.read_text(encoding="utf-8"), module.HEADING)
    )
    return by_step


async def recorded(module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Real:
    async with opened_surfaces(monkeypatch, tmp_path) as s:
        client = s.world.client
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(module.base, "run", in_this_process)
        asked: list[str] = []

        def ask(question: str) -> str:
            asked.append(question)
            return "s"

        async def get(path: str) -> Any:
            response = await client.get(path)
            assert response.status_code == 200, (path, response.text)
            return response.json()

        def on_the_loop(work: Awaitable[Any]) -> Any:
            return asyncio.run_coroutine_threadsafe(work, loop).result()  # type: ignore[arg-type]

        proof = module.Proof(module.base.Api(), module.base.Report(io.StringIO()), ask)
        waiting: dict[int, Any] = {}
        approvals: list[Any] = []

        def walk() -> None:
            for number, blocks in todo_of(module).items():
                if number == FAILING_STEP:
                    s.world.browser.page = MISSING
                hands = [at for at, block in enumerate(blocks) if block.kind == "mano"]
                if not hands:
                    module.a_step(number, blocks, proof)
                    continue
                (at,) = hands
                turn = module.Turn()
                module.a_step(number, blocks[: at + 1], proof, turn)
                waiting[number] = on_the_loop(get(f"/tasks/{turn.task_id}"))
                approvals.append(on_the_loop(get("/approvals")))
                (hand,) = [one for start, one in HANDS.items() if blocks[at].body.startswith(start)]
                on_the_loop(hand(s, turn.task_id))
                module.a_step(number, blocks[at + 1 :], proof, turn)

        # ``a_step`` is synchronous, and the CLI and the API reach the application on this loop.
        await asyncio.to_thread(walk)
        proof.api.close()
        ids = dict(proof.ids)
        shown = sorted({module.FINISHED_LOOK, console.SHOWN, companion.SHOWN})
        return Real(
            lines=tuple(proof.report.lines),
            asked=tuple(asked),
            ids=ids,
            health=await get("/health"),
            openapi=await get("/openapi.json"),
            devices=await get("/devices"),
            waiting=waiting,
            approvals=approvals[0],
            tasks={step: await get(f"/tasks/{task}") for step, task in ids.items()},
            audits={step: await get(f"/audit?task_id={task}") for step, task in ids.items()},
            finished={limit: await get(f"/tasks/finished?limit={limit}") for limit in shown},
        )


def record(module: ModuleType, tmp_path_factory: pytest.TempPathFactory) -> Real:
    """The answers, from a world that lives only while they are asked."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        return asyncio.run(recorded(module, monkeypatch, tmp_path_factory.mktemp("real")))


class Recorded:
    """An API that answers what the real one answered: by path, a copy each time."""

    def __init__(self, answers: Mapping[str, Any]) -> None:
        self.answers = dict(answers)
        self.asked: list[str] = []

    def get(self, path: str) -> Any:
        self.asked.append(path)
        assert path in self.answers, f"the script asked {path}, which this test did not record"
        return copy.deepcopy(self.answers[path])

    def close(self) -> None:
        return None


def changed(answer: Any, **fields: Any) -> Any:
    """A real answer with some of its fields changed: where a negative case starts."""
    copied = copy.deepcopy(answer)
    copied.update(fields)
    return copied
