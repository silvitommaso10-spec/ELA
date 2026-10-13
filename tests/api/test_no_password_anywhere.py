"""A password enters none of the places ELA writes in (M13.9, criterion 1; decision 25).

*«Una password non entra mai in un piano, nel database, nell'audit, in una domanda, in un
risultato, in un log o in un testo mandato a un modello. Un test lo afferma per ciascuno di quei
posti.»*

One ELA, on its real database, does what M13.9 adds from one end to the other: a ``browser.login``
that is asked, approved, made and verified — the vault hands the password, the browser types it
—, and then a guided session with the profile that reads a page of the same site through the
gateway. The password of the entry is a sentinel, and so is its whole username, which never
leaves the vault's adapter before a yes.

Then each place has **a reader**, and each reader has **its negative case**: a marker the test put
in that very place by the road content takes to it — the purpose of the plan, a line of a logger,
the text of a page. A reader that finds its marker would have found the sentinel; a reader that
does not is not reading the place, and the test is red before it claims anything.
"""

from __future__ import annotations

import asyncio
import json
import logging
import stat
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from ela.domain import TaskId, TaskState
from ela.ports import Field, Secret
from ela.testing.fakes import FakeAccountBrowser, FakePage, FakeVault, FakeVaultEntry
from tests.api.guided import Guided, Script, approve, call, gesture, guided, plan_of, question, run

SITE = "www.youtube.com"
WORD = "-".join(("SENTINEL", "the", "word", "of", "the", "entry", "7f3a"))
"""The password of the entry: what must be in none of the places."""
USERNAME = "-".join(("SENTINEL", "whole", "username")) + "@example.com"
"""The whole username: typed into the page like the password, and shown nowhere."""
MASKED = "S…@example.com"
ENTRY = FakeVaultEntry(
    "11111111-2222-4333-8444-555555555555",
    "Il canale di casa",
    (f"https://{SITE}/login",),
    USERNAME,
    WORD,
    MASKED,
)
PURPOSE = "MARKER-in-the-purpose-of-the-plan"
LOGGED = "MARKER-in-a-line-of-the-log"
ON_THE_PAGE = "MARKER-in-the-text-of-a-page"
WORD_FIELD = "_".join(("password", "field"))
A_LOGIN_FORM = {
    "#user": Field("text", "username", "post"),
    "#word": Field("password", "current-password", "post"),
    "#go": Field("submit", "", "post"),
}


def login_plan() -> dict[str, Any]:
    return {
        "goal": "entrare nel canale",
        "steps": [
            {
                "id": "b4c2d7e1-5a3f-4b69-8d20-0000000000ac",
                "goal": "entrare nel canale",
                "required_capabilities": ["browser.login"],
                "arguments": {
                    "site": SITE,
                    "path": "/login",
                    "username_field": "#user",
                    WORD_FIELD: "#word",
                    "click": "#go",
                    "expect_text": "MARKER",
                    "purpose": PURPOSE,
                },
                "risk": "HIGH",
                "expected_result": "il canale aperto",
                "success_conditions": ["browser.expect_visible"],
                "requires_authorization": True,
            }
        ],
    }


def session_plan() -> dict[str, Any]:
    plan = plan_of()
    plan["steps"][0]["required_capabilities"] = ["browser.guided_as_you"]
    return plan


async def planned(g: Guided, plan: dict[str, Any]) -> str:
    created = await g.client.post("/tasks", json={"text": "una prova"})
    task = str(created.json()["id"])
    attached = await g.client.post(f"/tasks/{task}/plan", json=plan)
    assert attached.status_code == 200, attached.text
    return task


@dataclass
class Places:
    """What each place held when everything was done, as text: the seven of criterion 1."""

    plan: str
    database: str
    audit: str
    question: str
    result: str
    log: str
    model: str

    def all(self) -> dict[str, str]:
        return dict(vars(self))


def raw(folder: Path) -> str:
    """Every byte of every file of the database — the journal beside it included —, as text: a
    value in any column of any table is here, whatever table it is."""
    files = sorted(path for path in folder.rglob("*") if path.is_file() and ".db" in path.name)
    assert files, "the database of this ELA is a file under the test's folder"
    return "\n".join(path.read_bytes().decode("utf-8", "replace") for path in files)


@pytest.fixture
async def places(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    capfd: pytest.CaptureFixture[str],
) -> AsyncIterator[tuple[Places, FakeAccountBrowser]]:
    """The whole road, once: a login made and verified, then a session with the profile that
    reads a page — and what every place held at the end."""
    caplog.set_level(logging.DEBUG)
    program = tmp_path / "bw"
    program.write_bytes(b"\xcf\xfa\xed\xfe a native program")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    accounts = FakeAccountBrowser(
        FakePage(fields=dict(A_LOGIN_FORM), texts={None: f"Benvenuto. {ON_THE_PAGE}"})
    )
    vault = FakeVault([ENTRY])
    script = Script([call(), gesture("read", site=SITE, path="/feed/subscriptions"), call()])
    async with guided(
        monkeypatch,
        tmp_path,
        script,
        accounts=accounts,
        vault=vault,
        ELA_VAULT_PROGRAM=str(program),
    ) as g:
        assert await g.ela.vault.open(Secret(vault.key)) is None
        logging.getLogger("ela.the_test").debug(LOGGED)

        # The login: asked, approved, made, verified.
        login = await planned(g, login_plan())
        assert (await run(g, login))["outcome"] == "waiting_approval"
        asked = await question(g, login)
        await approve(g, login)
        made = await run(g, login)
        assert made["outcome"] == "completed", made

        # A session with the profile, which reads a page of the site through the gateway.
        session = await planned(g, session_plan())
        assert (await run(g, session))["outcome"] == "waiting_approval"
        asked_session = await question(g, session)
        await approve(g, session)
        ran = await asyncio.wait_for(run(g, session), 30)
        assert ran["outcome"] == "completed", ran

        tasks = await g.ela.repository.tasks()
        plans = [await g.ela.repository.plan(TaskId(task.id)) for task in tasks]
        results = [(await g.client.get(f"/tasks/{task.id}/results")).json() for task in tasks]
        events = await g.ela.audit.read()
        assert all(task.state is TaskState.COMPLETED for task in tasks), tasks
        sent = [request.content.decode("utf-8", "replace") for request in g.anthropic.received]
        handed = [plan.instructions + plan.goal for plan in script.plans]
    out, err = capfd.readouterr()
    yield (
        Places(
            plan=json.dumps([plan.model_dump(mode="json") for plan in plans], ensure_ascii=False),
            database=raw(tmp_path),
            audit=json.dumps(
                [event.model_dump(mode="json") for event in events], ensure_ascii=False
            ),
            question=json.dumps([asked, asked_session], ensure_ascii=False),
            result=json.dumps(results, ensure_ascii=False),
            log="\n".join((caplog.text, out, err)),
            model="\n".join((*sent, *handed, *script.read)),
        ),
        accounts,
    )
    assert UUID(login) and UUID(session)


async def test_the_login_was_really_made_with_the_password_of_the_vault(
    places: tuple[Places, FakeAccountBrowser],
) -> None:
    """The precondition of everything below, asserted: the sentinel did travel — from the vault
    to the browser's field — and the whole username with it. A road on which no password moved
    would keep every place clean for nothing."""
    _, accounts = places

    assert accounts.secrets == [("#user", USERNAME), ("#word", WORD)]
    assert accounts.clicks == ["#go"]


CONTROLS = {
    "plan": PURPOSE,
    "database": PURPOSE,
    "audit": SITE,
    "question": ENTRY.name,
    "result": '"gestures"',
    "log": LOGGED,
    "model": ON_THE_PAGE,
}
"""The negative case of each reader: what the test put in that place, by the road content takes
to it. The purpose of the plan reaches the plan and the database; the site reaches the audit; the
name of the entry reaches the question; a result names its gestures; a line of a logger reaches
the log; and the text of a page read in a session reaches what the model is handed."""


@pytest.mark.parametrize("place", sorted(CONTROLS))
async def test_the_password_is_in_no_place_and_each_reader_reads_its_place(
    places: tuple[Places, FakeAccountBrowser], place: str
) -> None:
    held = places[0].all()[place]

    assert CONTROLS[place] in held, f"the reader of «{place}» does not read it: nothing is proved"
    assert WORD not in held, f"the password is in «{place}»"
    assert USERNAME not in held, f"the whole username is in «{place}»"


def test_the_places_are_the_seven_of_the_criterion() -> None:
    """A closed world: a place added to the criterion is a reader and a control added here."""
    assert set(CONTROLS) == {"plan", "database", "audit", "question", "result", "log", "model"}
    assert set(CONTROLS) == set(Places.__dataclass_fields__)
