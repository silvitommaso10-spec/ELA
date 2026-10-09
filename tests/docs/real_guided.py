"""What a real ELA answers along the proof of M14.3, recorded once, for the tests of its script.

The form of ``tests/docs/real_planning.py`` (decision 25 of the review of the proof of M14.2): every
kind of ``scripts/prova_m14_3.py`` that reads the API is fed by **the routes themselves** — ELA as
``build`` makes it, with the cap, the key and the three sites of section 26, the real Anthropic
gateway over a transport that answers as Anthropic streams, and a fake session of Claude Code that
runs the turn of its sentence (``tests/api/guided.py``). The commands of the guide are run by the
command line in this process, and their output is what Tommaso reads; a run that goes on while a
gesture asks is the one exception — two command lines in two threads would share one
``sys.stdout`` —, sent to its route and printed by the CLI's own renderer. Five sessions, as in
section 26: the sentence of the registration, a site outside the session, a gesture that asks
answered no and answered yes, and a stop while the gesture waits.

A negative case starts from one of these answers and changes it; nothing else is written by hand.
"""

from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final
from uuid import UUID

import pytest

from ela.cli import client as cli_client
from ela.cli.client import ApiRefusal
from ela.cli.tasks import _ran
from ela.domain import StepId, TaskId
from ela.executive.sessions import gesture_key
from ela.ports import SessionEnd, SessionHost, SessionPlan
from ela.tasks.engine import child_id
from tests.api.guided import Guided, Script, call, gesture, guided
from tests.cli.support import Cli, LoopTransport, plain

ROOT: Final = Path(__file__).resolve().parents[2]
EXAMPLES: Final = ROOT / "docs" / "examples"
YOUTUBE: Final = "guided-youtube.json"
OUTSIDE: Final = "guided-outside.json"
FORM: Final = "guided-form.json"
MARKER: Final = "ELA prova 26"
STOP_WORDS: Final = "la prova del ferma"


def sentence(name: str) -> str:
    (step,) = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))["steps"]
    return str(step["arguments"]["goal"])


@dataclass
class ByGoal(Script):
    """The sessions of the proof, each with the turn of its own sentence."""

    turns: dict[str, Script] = field(default_factory=dict)

    async def __call__(self, plan: SessionPlan, host: SessionHost) -> SessionEnd:
        chosen = self.turns[plan.goal]
        chosen.app = self.app
        return await chosen(plan, host)


def turns() -> ByGoal:
    act = gesture(
        "act",
        site="httpbin.org",
        path="/forms/post",
        fill=[["input[name=custname]", MARKER]],
        click="form button",
        expect_text=MARKER,
    )
    return ByGoal(
        [],
        turns={
            sentence(YOUTUBE): Script(
                [
                    call(),
                    gesture("read", site="www.youtube.com", path="/results?search_query=MrBeast"),
                    call(),
                ]
            ),
            sentence(OUTSIDE): Script(
                [call(), gesture("read", site="eu.httpbin.org", path="/html"), call()],
                answer="ELA non mi ha lasciato leggere eu.httpbin.org: non è fra i siti.",
            ),
            sentence(FORM): Script(
                [call(), act, call()], answer="Il modulo di httpbin.org: ecco com'è andata."
            ),
        },
    )


@dataclass(frozen=True)
class Session:
    """One session of the proof, as the routes and the command line answered along it."""

    task: str
    waiting_output: str
    """``ela task run <task>``, the first: the question of the session."""
    question: Any
    """``GET /approvals`` while the session asks."""
    queued: Any
    """``GET /tasks/<task>`` after the yes."""
    run_output: str
    """The run of the session, to its end."""
    detail: Any
    results: Any
    children: dict[str, Any]
    """``GET /tasks/<child>`` at the end, for every gesture the session's result counts."""
    audits: dict[str, Any]
    """``GET /audit?task_id=<child>``, for each of them."""
    missing: tuple[str, ...]
    """The ids of the gestures counted that have no child: ``GET /tasks/<id>`` answers 404."""
    asking: Any = None
    """``GET /approvals`` while the gesture asks."""
    child: str | None = None
    child_asking: Any = None
    """``GET /tasks/<child>`` while it asks."""
    answer_output: str = ""
    """The commands of the answer to the gesture, as Tommaso reads them."""
    child_answered: Any = None
    """``GET /tasks/<child>`` after the answer."""
    audit: Any = None
    """``GET /audit?task_id=<task>`` at the end: the yes to the session, and who gave it."""


@dataclass(frozen=True)
class Real:
    """The answers of the routes and of the command line, in the order of the proof."""

    health: Any
    openapi: Any
    diagnostics: Any
    spend_start: Any
    approvals_output: str
    """``ela approvals`` while the session of step 2 asks."""
    youtube: Session
    outside: Session
    refused: Session
    accepted: Session
    stopped: Session
    cancel_output: str
    spend_end: Any
    devices: Any
    """``GET /devices``: the registry that names who answered a question (ADR 0059)."""


class Recorder:
    def __init__(self, g: Guided, cli: Cli) -> None:
        self.g = g
        self.cli = cli

    async def get(self, path: str) -> Any:
        response = await self.g.client.get(path)
        assert response.status_code == 200, (path, response.text)
        return response.json()

    async def command(self, *words: str) -> str:
        result = await self.cli(*words)
        assert result.exit_code == 0, result.output
        return plain(result.stdout)

    async def asked(self, name: str) -> tuple[str, str, Any]:
        """A task with the plan of ``name``, run up to its question: the task, the output, the
        questions that wait."""
        created = await self.command("task", "create", sentence(name), "--json")
        task = str(json.loads(created)["id"])
        await self.command("task", "plan", task, "--file", str(EXAMPLES / name))
        waiting = await self.command("task", "run", task)
        return task, waiting, await self.get("/approvals")

    async def yes(self, task: str, question: Any) -> Any:
        (found,) = [one for one in question if one["task_id"] == task]
        await self.command("task", "approve", task, "--approval", str(found["id"]))
        return await self.get(f"/tasks/{task}")

    async def asking(self, task: str) -> tuple[str, Any, Any]:
        """The child whose gesture asks, found as the script finds it: from the questions."""
        for _ in range(1000):
            questions = await self.get("/approvals")
            for one in questions:
                if one["capability_id"] == "browser.act":
                    child = await self.get(f"/tasks/{one['task_id']}")
                    if child["parent_id"] == task:
                        return str(one["task_id"]), questions, child
            await asyncio.sleep(0.01)
        raise AssertionError("the gesture never asked")

    async def ended(self, task: str, **asked: Any) -> Session:
        detail = await self.get(f"/tasks/{task}")
        results = await self.get(f"/tasks/{task}/results")
        (step,) = detail["steps"]
        last = [one for one in results if one["status"] != "STARTED"][-1]
        children: dict[str, Any] = {}
        audits: dict[str, Any] = {}
        missing: list[str] = []
        for number in range(1, int(last["output"]["looks"]) + 1):
            one = str(child_id(TaskId(UUID(task)), gesture_key(number, StepId(UUID(step["id"])))))
            response = await self.g.client.get(f"/tasks/{one}")
            if response.status_code == 404:
                missing.append(one)
                continue
            children[one] = response.json()
            audits[one] = await self.get(f"/audit?task_id={one}")
        asked.setdefault("audit", await self.get(f"/audit?task_id={task}"))
        return Session(
            task=task,
            detail=detail,
            results=results,
            children=children,
            audits=audits,
            missing=tuple(missing),
            **asked,
        )

    async def run(self, task: str) -> Any:
        response = await self.g.client.post(f"/tasks/{task}/run")
        assert response.status_code == 200, response.text
        return response.json()


async def recorded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Real:
    async with guided(monkeypatch, tmp_path, turns()) as g:
        transport = LoopTransport(g.app, asyncio.get_running_loop())
        monkeypatch.setattr(
            cli_client,
            "connect",
            lambda: cli_client.open_client(g.ela.settings.api, transport=transport),
        )
        r = Recorder(g, Cli(transport))
        health, openapi = await r.get("/health"), await r.get("/openapi.json")
        diagnostics, spend_start = await r.get("/diagnostics"), await r.get("/spend")

        task, waiting, question = await r.asked(YOUTUBE)
        approvals_output = await r.command("approvals")
        queued = await r.yes(task, question)
        run_output = await r.command("task", "run", task)
        youtube = await r.ended(
            task, waiting_output=waiting, question=question, queued=queued, run_output=run_output
        )

        task, waiting, question = await r.asked(OUTSIDE)
        queued = await r.yes(task, question)
        run_output = await r.command("task", "run", task)
        outside = await r.ended(
            task, waiting_output=waiting, question=question, queued=queued, run_output=run_output
        )

        sessions: list[Session] = []
        for answer in ("deny", "approve"):
            task, waiting, question = await r.asked(FORM)
            queued = await r.yes(task, question)
            running = asyncio.ensure_future(r.run(task))
            child, asking, child_asking = await r.asking(task)
            (found,) = [one for one in asking if one["task_id"] == child]
            answer_output = await r.command("task", answer, child, "--approval", str(found["id"]))
            if answer == "approve":
                answer_output += await r.command("task", "run", child)
            child_answered = await r.get(f"/tasks/{child}")
            ran = await running
            sessions.append(
                await r.ended(
                    task,
                    waiting_output=waiting,
                    question=question,
                    queued=queued,
                    run_output=_ran(ran),
                    asking=asking,
                    child=child,
                    child_asking=child_asking,
                    answer_output=answer_output,
                    child_answered=child_answered,
                )
            )
        refused, accepted = sessions

        task, waiting, question = await r.asked(FORM)
        queued = await r.yes(task, question)
        running = asyncio.ensure_future(r.run(task))
        child, asking, child_asking = await r.asking(task)
        cancel_output = await r.command("task", "cancel", task, "--reason", STOP_WORDS)
        ran = await running
        stopped = await r.ended(
            task,
            waiting_output=waiting,
            question=question,
            queued=queued,
            run_output=_ran(ran),
            asking=asking,
            child=child,
            child_asking=child_asking,
            child_answered=await r.get(f"/tasks/{child}"),
        )
        spend_end = await r.get("/spend")
        devices = await r.get("/devices")
    return Real(
        health=health,
        openapi=openapi,
        diagnostics=diagnostics,
        spend_start=spend_start,
        approvals_output=approvals_output,
        youtube=youtube,
        outside=outside,
        refused=refused,
        accepted=accepted,
        stopped=stopped,
        cancel_output=cancel_output,
        spend_end=spend_end,
        devices=devices,
    )


def record(tmp_path_factory: pytest.TempPathFactory) -> Real:
    """The answers, from a world that lives only while they are asked."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        return asyncio.run(recorded(monkeypatch, tmp_path_factory.mktemp("guided")))


class Recorded:
    """An API that answers what the real one answered: by path, a copy each time — and, for a
    task it was not given, the 404 the route answers."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers
        self.asked: list[str] = []

    def get(self, path: str) -> Any:
        self.asked.append(path)
        if path in self.answers:
            return copy.deepcopy(self.answers[path])
        if path.startswith("/tasks/") and path.count("/") == 2:
            raise ApiRefusal(404, "task.not_found", f"no task {path.rsplit('/', 1)[1]}")
        raise AssertionError(f"the script asked {path}, which this test did not record")

    def close(self) -> None:
        return None


def answers_of(session: Session, **more: Any) -> dict[str, Any]:
    """What the routes answer about one session at its end, by path."""
    return {
        f"/tasks/{session.task}": session.detail,
        f"/tasks/{session.task}/results": session.results,
        **{f"/tasks/{one}": child for one, child in session.children.items()},
        **{f"/audit?task_id={one}": events for one, events in session.audits.items()},
        **more,
    }
