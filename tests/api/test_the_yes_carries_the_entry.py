"""The yes carries the entry its question named, across a restart of ELA (M13.10, ADR 0065 §2).

*«Il sì resta legato a ciò che Tommaso ha letto anche attraverso un riavvio di ELA.»*

One ELA composes the question of a ``browser.login`` — it finds the one entry of the vault for the
site and names it — and stops. A second ELA, on the same database, with a vault that has changed
in between — another entry for the same site, added after the question — takes the yes and makes
the login. Before M13.10 the entry was remembered in the memory of the first ELA's tool: the second
had none, looked again, and found two. Now the entry travels with the yes, in the row of the
approval, and the second ELA types **that** entry.
"""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Any

import pytest

from ela.ports import Field, Secret
from ela.testing.fakes import FakeAccountBrowser, FakePage, FakeVault, FakeVaultEntry
from tests.api.guided import Guided, Script, approve, guided, question, run

SITE = "www.youtube.com"
NAMED = FakeVaultEntry(
    "11111111-2222-4333-8444-555555555555",
    "Il canale di casa",
    (f"https://{SITE}/login",),
    "the-username-of-the-named-entry@example.com",
    "the-password-of-the-named-entry",
    "t…@example.com",
)
ADDED = FakeVaultEntry(
    "99999999-8888-4777-8666-555555555555",
    "Un canale aggiunto dopo la domanda",
    (f"https://{SITE}/login",),
    "the-username-of-the-added-entry@example.com",
    "the-password-of-the-added-entry",
    "t…@example.com",
)
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
                "id": "b4c2d7e1-5a3f-4b69-8d20-0000000000ad",
                "goal": "entrare nel canale",
                "required_capabilities": ["browser.login"],
                "arguments": {
                    "site": SITE,
                    "path": "/login",
                    "username_field": "#user",
                    WORD_FIELD: "#word",
                    "click": "#go",
                    "expect_text": "Benvenuto",
                    "purpose": "entrare nel canale di casa",
                },
                "risk": "HIGH",
                "expected_result": "il canale aperto",
                "success_conditions": ["browser.expect_visible"],
                "requires_authorization": True,
            }
        ],
    }


def program(tmp_path: Path) -> str:
    path = tmp_path / "bw"
    path.write_bytes(b"\xcf\xfa\xed\xfe a native program")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


async def opened(g: Guided, vault: FakeVault) -> None:
    assert await g.ela.vault.open(Secret(vault.key)) is None


def accounts() -> FakeAccountBrowser:
    return FakeAccountBrowser(FakePage(fields=dict(A_LOGIN_FORM), texts={None: "Benvenuto."}))


async def test_a_second_ela_types_the_entry_the_first_one_named_though_the_vault_changed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bw = program(tmp_path)
    before = FakeVault([NAMED])
    async with guided(
        monkeypatch, tmp_path, Script([]), accounts=accounts(), vault=before, ELA_VAULT_PROGRAM=bw
    ) as first:
        await opened(first, before)
        task = str((await first.client.post("/tasks", json={"text": "una prova"})).json()["id"])
        attached = await first.client.post(f"/tasks/{task}/plan", json=login_plan())
        assert attached.status_code == 200, attached.text
        assert (await run(first, task))["outcome"] == "waiting_approval"
        assert (await question(first, task))["entry"] == NAMED.name

    after = FakeVault([NAMED, ADDED])
    browser = accounts()
    async with guided(
        monkeypatch, tmp_path, Script([]), accounts=browser, vault=after, ELA_VAULT_PROGRAM=bw
    ) as second:
        await opened(second, after)
        await approve(second, task)
        made = await run(second, task)

    assert made["outcome"] == "completed", made
    assert browser.secrets == [("#user", NAMED.username), ("#word", NAMED.password)]
    assert [call for call in after.calls if call.startswith("take")] == [f"take:{NAMED.id}"]


async def test_the_second_ela_of_before_would_have_found_two_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The negative case of the test above: the changed vault, asked afresh, does not name one
    entry — a question composed by the second ELA finds two, and refuses. What the first test
    proves is not a vault that would have answered the same anyway."""
    after = FakeVault([NAMED, ADDED])
    async with guided(
        monkeypatch,
        tmp_path,
        Script([]),
        accounts=accounts(),
        vault=after,
        ELA_VAULT_PROGRAM=program(tmp_path),
    ) as g:
        await opened(g, after)
        task = str((await g.client.post("/tasks", json={"text": "una prova"})).json()["id"])
        attached = await g.client.post(f"/tasks/{task}/plan", json=login_plan())
        assert attached.status_code == 200, attached.text
        refused = await run(g, task)

    assert refused["outcome"] == "failed", refused
    assert "vault.entry_ambiguous" in refused["reason"], refused
