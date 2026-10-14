"""A login the model of a session with the profile asks for (M13.10, ADR 0065 §4).

Two children: a read of the page, covered by the session as every read, whose result names the
one login form — and, only then, a ``browser.login`` with those selectors, which asks the user.
The model gives the site; it never gives or sees the password, the entry or the username.
"""

from __future__ import annotations

import asyncio
import json
import stat
from pathlib import Path
from typing import Any

import pytest

from ela.domain import TaskState
from ela.ports import LOGIN_FORM, LOGIN_FORM_NOT_FOUND, Field, Secret, SessionHost, SessionPlan
from ela.testing.fakes import FakeAccountBrowser, FakePage, FakeVault, FakeVaultEntry
from ela.tools.account import login_form_of
from tests.api.guided import Guided, Script, approve, body_of, gesture, guided, run
from tests.api.test_guided_session_as_you import (
    WAIT_SECONDS,
    children,
    going,
    no,
    planned,
    tid,
    waiting,
    yes,
)
from tests.tools.test_login_form import LOGIN, SIGN_UP

SITE = "www.youtube.com"
WORD = "-".join(("SENTINEL", "word", "of", "the", "model", "login"))
USERNAME = "-".join(("SENTINEL", "username")) + "@example.com"
ENTRY = FakeVaultEntry(
    "22222222-3333-4444-8555-666666666666",
    "SENTINEL-name-of-the-entry",
    (f"https://{SITE}/",),
    USERNAME,
    WORD,
    "S…@example.com",
)
WRITTEN = login_form_of([LOGIN, SIGN_UP])
assert isinstance(WRITTEN, dict)


def a_login_page(**changed: Any) -> FakePage:
    """The page the read finds the form on, and the page the login fills: the same script."""
    return FakePage(
        texts={None: "Accedi al tuo account"},
        forms=(LOGIN, SIGN_UP),
        fields={
            WRITTEN["username_field"]: Field("text", "username", "post"),
            WRITTEN["password_field"]: Field("password", "current-password", "post"),
            WRITTEN["click"]: Field("submit", "", "post"),
        },
        counts_after_click={WRITTEN["password_field"]: 0},
        landed=f"https://{SITE}/feed",
        landed_status=200,
        **changed,
    )


def speaks() -> Any:
    """A call of the session whose messages carry everything the model has read so far: what a
    session sends its provider after a gesture."""

    async def step(script: Script, plan: SessionPlan, host: SessionHost) -> None:
        body = body_of(plan, messages=[{"role": "user", "content": "\n".join(script.read)}])
        response = await script.http(plan).post(
            "/v1/messages?beta=true",
            content=json.dumps(body).encode(),
            headers={"x-api-key": plan.token},
        )
        script.answered.append((response.status_code, response.content))

    return step


async def opened(g: Guided, vault: FakeVault) -> None:
    assert await g.ela.vault.open(Secret(vault.key)) is None


def program(tmp_path: Path) -> str:
    path = tmp_path / "bw"
    path.write_bytes(b"\xcf\xfa\xed\xfe a native program")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


async def test_a_login_the_model_asks_for_is_a_read_then_a_question_that_names_the_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Criteria 23 and 24: the login asks the user, its question names the entry — and toward the
    gateway goes neither the password, nor the entry, nor the username, in any byte."""
    script = Script([gesture("login", site=SITE, path="/login"), speaks()])
    accounts = FakeAccountBrowser(a_login_page())
    vault = FakeVault([ENTRY])
    async with guided(
        monkeypatch,
        tmp_path,
        script,
        accounts=accounts,
        vault=vault,
        ELA_VAULT_PROGRAM=program(tmp_path),
    ) as g:
        await opened(g, vault)
        task = await planned(g)
        assert (await run(g, task))["outcome"] == "waiting_approval"
        await approve(g, task)
        async with going(run(g, task)) as running:
            login = await waiting(g, task)
            asked = [
                one
                for one in (await g.client.get("/approvals")).json()
                if one["task_id"] == str(login.id)
            ]
            made = await yes(g, login)
            ran = await asyncio.wait_for(running, WAIT_SECONDS)
        kids = await children(g, task)
        sent = b"\n".join(request.content for request in g.anthropic.received)

    assert ran["outcome"] == "completed", ran
    assert made["outcome"] == "completed", made
    (question,) = asked
    assert question["capability_id"] == "browser.login"
    assert question["entry"] == ENTRY.name, "the question names the entry"
    assert [kid.state for kid in kids] == [TaskState.COMPLETED, TaskState.COMPLETED]
    assert accounts.secrets == [
        (WRITTEN["username_field"], USERNAME),
        (WRITTEN["password_field"], WORD),
    ]
    told = "\n".join(script.read)
    assert told.startswith("gesture 2: COMPLETED"), told
    for sentinel in (WORD, USERNAME, ENTRY.name, ENTRY.id):
        assert sentinel.encode() not in sent, f"{sentinel} went toward the gateway"
        assert sentinel not in told, f"the model read {sentinel}"
    assert json.dumps(told)[1:-1] in sent.decode(), "the reader reads what was sent: its control"


async def test_a_page_with_no_login_form_asks_nobody_and_says_its_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Criterion 22: no form ELA can name, no second child, no question, no yes spent."""
    script = Script([gesture("login", site=SITE)])
    accounts = FakeAccountBrowser(FakePage(texts={None: "Benvenuto"}, forms=(SIGN_UP,)))
    async with guided(monkeypatch, tmp_path, script, accounts=accounts) as g:
        task = await planned(g)
        assert (await run(g, task))["outcome"] == "waiting_approval"
        await approve(g, task)
        ran = await asyncio.wait_for(run(g, task), WAIT_SECONDS)
        kids = await children(g, task)
        approvals = (await g.client.get("/approvals")).json()

    assert ran["outcome"] == "completed", ran
    assert [kid.state for kid in kids] == [TaskState.COMPLETED], "one child: the read"
    assert approvals == []
    assert accounts.opened == [f"https://{SITE}/"], "the root, when no path is given"
    (told,) = script.read
    assert LOGIN_FORM_NOT_FOUND in told and "no question was asked" in told


async def test_a_no_to_the_login_is_denied_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Decision 12: the model reads «denied», and no sentence of the end."""
    script = Script([gesture("login", site=SITE, path="/login")])
    accounts = FakeAccountBrowser(a_login_page())
    vault = FakeVault([ENTRY])
    async with guided(
        monkeypatch,
        tmp_path,
        script,
        accounts=accounts,
        vault=vault,
        ELA_VAULT_PROGRAM=program(tmp_path),
    ) as g:
        await opened(g, vault)
        task = await planned(g)
        assert (await run(g, task))["outcome"] == "waiting_approval"
        await approve(g, task)
        async with going(run(g, task)) as running:
            login = await waiting(g, task)
            await no(g, login)
            await asyncio.wait_for(running, WAIT_SECONDS)

    assert script.read == ["gesture 2: DENIED"]
    assert accounts.secrets == []


async def test_a_login_that_fails_its_verification_says_its_code_and_facts_and_no_sentence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Criterion 25: the state, the code, and the three facts of the result — never the sentence
    the verifier wrote, which for any other gesture the room shows whole."""
    script = Script([gesture("login", site=SITE, path="/login")])
    page = a_login_page()
    page.counts_after_click = {WRITTEN["password_field"]: 1}  # the form is on the page still
    accounts = FakeAccountBrowser(page)
    vault = FakeVault([ENTRY])
    async with guided(
        monkeypatch,
        tmp_path,
        script,
        accounts=accounts,
        vault=vault,
        ELA_VAULT_PROGRAM=program(tmp_path),
    ) as g:
        await opened(g, vault)
        task = await planned(g)
        assert (await run(g, task))["outcome"] == "waiting_approval"
        await approve(g, task)
        async with going(run(g, task)) as running:
            login = await waiting(g, task)
            await yes(g, login)
            await asyncio.wait_for(running, WAIT_SECONDS)
        ended = await g.ela.engine.ending(await g.ela.repository.get(tid(str(login.id))))

    (told,) = script.read
    assert told.splitlines()[0] == "gesture 2: FAILED"
    assert "code: browser.login_form_still_there" in told
    assert "ended_at: www.youtube.com/feed" in told and "ended_status: 200" in told
    assert ended is not None and ended.reason not in told and "may have refused" not in told


async def test_the_login_form_of_the_read_is_in_nothing_the_model_reads_nor_in_the_audit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Criterion 26."""
    script = Script([gesture("read", site=SITE, path="/login")])
    accounts = FakeAccountBrowser(a_login_page())
    async with guided(monkeypatch, tmp_path, script, accounts=accounts) as g:
        task = await planned(g)
        assert (await run(g, task))["outcome"] == "waiting_approval"
        await approve(g, task)
        await asyncio.wait_for(run(g, task), WAIT_SECONDS)
        (kid,) = await children(g, task)
        step = (await g.ela.repository.plan(kid.id)).steps[0].id
        rows = await g.ela.results.for_step(kid.id, step)
        audit = json.dumps([event.model_dump(mode="json") for event in await g.ela.audit.read()])

    (result,) = [row for row in rows if row.output]
    assert result.output[LOGIN_FORM] == WRITTEN, "the read did find the form: the control"
    for selector in WRITTEN.values():
        assert selector not in script.read[0]
        assert selector not in audit
