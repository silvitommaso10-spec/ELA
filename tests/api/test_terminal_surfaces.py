"""A question about a command, on the three surfaces that answer it (M13.2 dec. 12, 13; ADR 0047).

**Every surface that offers a yes shows** the program, the file it leads to, the arguments as a
list whose borders are visible, the folder, the timeout and the expected code — the rule H of
M13.1, closed over the fields in ``test_answering_surfaces.py`` and walked here with a real
question. **None of them can be rewritten by what it shows**: an ESC and a U+202E in an argument
reach the command line, the Command Center and the companion as characters a reader sees, never as
a sequence the terminal obeys or a line the browser reorders — and in the output of a result on the
command line, the one surface that shows results. One rendering, ``ela.domain.visible``, for all.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ela.api.schemas import ApprovalOut, Asked
from ela.cli.system import _questions
from ela.cli.tasks import _results
from ela.composition import Ela
from ela.composition.settings import Settings
from ela.domain import TaskId
from ela.executive import ASKED
from ela.tools.terminal import PROGRAM
from tests.api.support import BASE, queued
from tests.composition.support import declare

ESC = "\x1b"
RLO = "\u202e"
PRINTF = "usr/bin/printf"
LOOPBACK = "http://127.0.0.1"


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    declare(monkeypatch, tmp_path, ELA_TERMINAL_PROGRAMS=json.dumps([PRINTF]))
    loaded = Settings.load()
    (loaded.filesystem.root / "ELA").mkdir()
    return loaded


def printf_plan(*arguments: str) -> dict[str, Any]:
    return {
        "goal": "stampare",
        "steps": [
            {
                "id": "e7a3c915-2b64-4d08-9f71-0000000000aa",
                "goal": "stampare con printf",
                "required_capabilities": ["terminal.run"],
                "arguments": {"program": PRINTF, "args": list(arguments), "purpose": "la prova"},
                "risk": "HIGH",
                "expected_result": "una riga",
                "success_conditions": ["terminal.exit_code_matches"],
                "requires_authorization": True,
            }
        ],
    }


HOSTILE = (f"rosso{ESC}[31m", f"abc{RLO}def")


async def question(client: AsyncClient, *arguments: str) -> dict[str, Any]:
    task = await queued(client, printf_plan(*arguments), privacy="TRUSTED")
    await client.post(f"/tasks/{task}/run")
    (waiting,) = [one for one in (await client.get("/approvals")).json() if one["task_id"] == task]
    return dict(waiting)


# ----------------------------------------------------------------------------------------
# The command line
# ----------------------------------------------------------------------------------------


async def test_the_command_line_shows_every_fact_of_a_command(
    client: AsyncClient, settings: Settings
) -> None:
    asked = await question(client, "%s\n", "una parola")

    shown = _questions([asked])

    assert "program" in shown and "/usr/bin/printf" in shown
    assert asked["runs"] in shown
    assert '["%s\\n", "una parola"]' in shown, "the arguments as a list, borders visible"
    assert str(settings.filesystem.root.resolve() / "ELA") in shown
    assert "120 s" in shown
    assert "expects exit" in shown


async def test_two_lists_that_would_read_the_same_joined_by_a_comma_read_differently(
    client: AsyncClient,
) -> None:
    one = _questions([await question(client, "a, b")])
    two = _questions([await question(client, "a", "b")])

    assert '["a, b"]' in one
    assert '["a", "b"]' in two


async def test_the_command_line_shows_the_escape_and_the_reversal_and_obeys_neither(
    client: AsyncClient,
) -> None:
    shown = _questions([await question(client, *HOSTILE)])

    assert ESC not in shown and RLO not in shown
    assert "\\x1b[31m" in shown
    assert "\\u202e" in shown


def test_the_command_line_shows_a_result_with_the_cut_and_the_escape_visible() -> None:
    """Decision 8 and 13: head, a line of the surface's own words, tail — and an ESC the program
    printed reaches the reader as text."""
    stream = {
        "head": f"prima {ESC}[31mROSSO\n",
        "tail": "fine\n",
        "cut_after": 20,
        "missing": 500,
        "shown": 25,
        "total": 525,
        "replaced": 0,
    }
    payload = [
        {
            "step_id": "e7a3c915-2b64-4d08-9f71-0000000000aa",
            "capability_id": "terminal.run",
            "status": "SUCCEEDED",
            "tool_name": "terminal-run",
            "created_at": "2026-09-24T10:00:00+00:00",
            "output": {
                "program": "/usr/bin/printf",
                "ended": "exited",
                "exit_code": 0,
                "stdout": stream,
                "stderr": {
                    **stream,
                    "head": "",
                    "tail": "",
                    "cut_after": 0,
                    "missing": 0,
                    "shown": 0,
                    "total": 0,
                },
            },
            "error": None,
        }
    ]

    shown = _results(payload)

    assert ESC not in shown
    assert "\\x1b[31mROSSO" in shown
    head, _, tail = shown.partition("cut after 20 bytes")
    assert "ROSSO" in head and "fine" in tail, "the cut is said between the two halves"
    assert "500 bytes not shown" in shown


def test_the_command_line_says_what_was_replaced_and_a_cut_with_nothing_after_it() -> None:
    """The other shapes of a stream: bytes that were not text, a head empty, a tail empty."""
    replaced = {
        "head": "a\ufffd",
        "tail": "",
        "cut_after": 2,
        "missing": 0,
        "shown": 2,
        "total": 2,
        "replaced": 1,
    }
    headless = {
        "head": "",
        "tail": "",
        "cut_after": 0,
        "missing": 9,
        "shown": 0,
        "total": 9,
        "replaced": 0,
    }
    payload = [
        {
            "step_id": "e7a3c915-2b64-4d08-9f71-0000000000ab",
            "capability_id": "terminal.run",
            "status": "SUCCEEDED",
            "tool_name": "terminal-run",
            "created_at": "2026-09-24T10:00:00+00:00",
            "output": {"ended": "exited", "stdout": replaced, "stderr": headless},
            "error": None,
        }
    ]

    shown = _results(payload)

    assert "1 sequences that were not text replaced" in shown
    assert "cut after 0 bytes: 9 bytes not shown" in shown


def test_the_arguments_in_a_result_keep_their_borders_too() -> None:
    """Found by the proof with two real processes, not by the suite: ``ela task results`` joined
    ``args`` with a comma — «la parola di prova è, girasole-7431» — which is the reading decision
    12 forbids on the question, reached through the result."""
    stream = {
        "head": "",
        "tail": "",
        "cut_after": 0,
        "missing": 0,
        "shown": 0,
        "total": 0,
        "replaced": 0,
    }

    def result(*args: str) -> list[dict[str, Any]]:
        return [
            {
                "step_id": "e7a3c915-2b64-4d08-9f71-0000000000ac",
                "capability_id": "terminal.run",
                "status": "SUCCEEDED",
                "tool_name": "terminal-run",
                "created_at": "2026-09-24T10:00:00+00:00",
                "output": {"args": list(args), "stdout": stream, "stderr": stream},
                "error": None,
            }
        ]

    one, two = _results(result("a, b")), _results(result("a", "b"))

    assert '["a, b"]' in one and '["a", "b"]' in two
    assert one != two
    assert "args  []" in _results(result()), "no argument is a list too, not an absence"


# ----------------------------------------------------------------------------------------
# The two pages
# ----------------------------------------------------------------------------------------


@pytest.fixture
async def console(app: FastAPI, client: AsyncClient) -> AsyncIterator[AsyncClient]:
    minted = await client.post("/nodes/enrollments", json={"privacy": "TRUSTED", "role": "CONSOLE"})
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 123)), base_url=LOOPBACK
    ) as browser:
        entered = await browser.post(
            "/console/enroll",
            data={"code": minted.json()["code"], "name": "MacBook", "os": "MACOS"},
            headers={"Origin": LOOPBACK},
        )
        assert entered.status_code == 303, entered.text
        yield browser


@pytest.fixture
async def phone(app: FastAPI, client: AsyncClient) -> AsyncIterator[AsyncClient]:
    minted = await client.post(
        "/nodes/enrollments", json={"privacy": "TRUSTED", "role": "COMPANION"}
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as browser:
        entered = await browser.post(
            "/companion/enroll",
            data={"code": minted.json()["code"], "name": "iPhone", "os": "IOS"},
            headers={"Origin": BASE},
        )
        assert entered.status_code == 303, entered.text
        yield browser


@pytest.mark.parametrize("surface", ["console", "companion"])
async def test_a_page_shows_every_fact_of_a_command_and_obeys_nothing_it_shows(
    client: AsyncClient,
    console: AsyncClient,
    phone: AsyncClient,
    settings: Settings,
    surface: str,
) -> None:
    asked = await question(client, *HOSTILE)
    browser = console if surface == "console" else phone

    page = (await browser.get(f"/{surface}/approval?id={asked['id']}")).text

    assert ESC not in page and RLO not in page
    assert "\\x1b[31m" in page and "\\u202e" in page
    assert "/usr/bin/printf" in page
    assert asked["runs"] in page
    assert str(settings.filesystem.root.resolve() / "ELA") in page
    assert "120 s" in page
    assert PROGRAM in page, "the label of the target is the tool's word"
    assert "Il file" not in page, "a program is not called a file by a page that owns the word"


# ----------------------------------------------------------------------------------------
# What the question carries, and where it reaches
# ----------------------------------------------------------------------------------------


async def test_what_the_executor_writes_is_what_the_shape_reads_and_what_the_wire_carries(
    client: AsyncClient, ela: Ela
) -> None:
    """Decision 12: ``_asked`` ⊆ ``Asked`` ⊆ ``ApprovalOut``. A containment and not an equality —
    ``ApprovalOut`` carries what does not come from ``asked``, and ``_asked`` leaves out the target
    when there is none — so that a field written on one side only cannot vanish from the wire in
    silence, which is pydantic's default for a field nobody redeclared."""
    asked = await question(client, "x")
    (stored,) = await ela.approvals.for_task(TaskId(UUID(asked["task_id"])))

    written = set(stored.metadata[ASKED])

    assert written <= set(Asked.model_fields), written - set(Asked.model_fields)
    assert set(Asked.model_fields) <= set(ApprovalOut.model_fields)
    assert written >= {"label", "runs", "arguments", "folder", "timeout_seconds", "expect_exit"}
