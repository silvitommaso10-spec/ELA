"""The policies of the login and of the files from the browser, through the routes (M13.15, ADR
0071).

- **The birth names the product**: the folders resolved on the Core's disk, the sites — or the
  entries of the vault by their name and their masked username —, the product in words, the uses
  with their singular, the end; ``VALUES`` refuses what is not the argument named by value.
- **The id of an entry is never shown** (decision 10, answer 35): not in a preview, a policy, a
  list, an event of the audit, a page of the console or an error body — searched for, with an id
  sent on purpose where a refusal could repeat it. And no model a route answers with carries the
  grant whole.
- **The revocation says what goes on only for a session** (decision 20, answer 40), derived.
- **The result of an upload reaches no model** (answer 37, §57): no session's gestures and no
  planning call read it.
"""

from __future__ import annotations

import asyncio
import html
import inspect
import json
import stat
import typing
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from click.testing import Result
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from typer.testing import CliRunner

from ela.api import create_app, schemas
from ela.api.policies import READS_GO_ON, SESSION_GOES_ON, running_of
from ela.cli import client as cli_client
from ela.cli.app import app as ela_app
from ela.composition import Ela, Settings, build
from ela.domain import AuditEventType, Authorization, CapabilityId, PolicyBounds
from ela.permissions import production_catalogue
from ela.ports import Secret
from ela.testing.fakes import FakeAccountBrowser, FakeBrowser, FakePower, FakeVault
from ela.tools.guided import EMPTY_SESSION, SESSION_AS_YOU
from tests.api.support import AUTHORIZED, BASE
from tests.api.test_login_surfaces import ENTRY, LOOPBACK, MASKED, NAMELESS
from tests.cli.support import LoopTransport, plain
from tests.composition.support import SCOPE, create_schema, database_url, declare
from tests.permissions.catalogue_calls import CATALOGUE
from tests.permissions.policy_support import policy_for

SITES = ["posta.example", "forum.example"]
WRONG_ID = "33333333-4444-4555-8666-777777777777"
"""An id of an entry the vault does not hold, sent on purpose: a refusal must not repeat it."""
TOO_LONG = "4" * 65
"""An id longer than the schema of ``entry`` allows: the refusal of ``VALUES`` must not repeat
it."""


@pytest.fixture
async def ela(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[Ela]:
    """An ELA with a root and its scope, two declared sites, and a vault open on two entries."""
    program = tmp_path / "bw"
    program.write_bytes(b"\xcf\xfa\xed\xfe a native program")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    root = tmp_path / "root"
    (root / "ELA" / "giu").mkdir(parents=True)
    (root / "ELA" / "un-file.txt").write_text("ciao")
    declare(
        monkeypatch,
        tmp_path,
        ELA_BROWSER_SITES=json.dumps(SITES),
        ELA_VAULT_PROGRAM=str(program),
        ELA_FS_ROOT=str(root),
        ELA_FS_SCOPE=SCOPE,
    )
    await create_schema(database_url(tmp_path))
    vault = FakeVault([ENTRY, NAMELESS])
    built = await build(
        Settings.load(),
        power=FakePower(),
        browser=FakeBrowser(),
        accounts=FakeAccountBrowser(),
        vault=vault,
    )
    assert await built.vault.open(Secret(vault.key)) is None
    try:
        yield built
    finally:
        await built.aclose()


@pytest.fixture
def app(ela: Ela) -> FastAPI:
    return create_app(ela)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED) as http,
    ):
        yield http


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


DOWNLOAD = {
    "capability": "browser.download",
    "scope": ["ELA/giu"],
    "values": {"site": ["posta.example"]},
    "days": 1,
    "uses": 2,
}
LOGIN = {
    "capability": "browser.login",
    "scope": ["posta.example"],
    "values": {"entry": [ENTRY.id]},
    "days": 1,
    "uses": 1,
}


async def test_a_policy_of_a_download_names_its_folders_its_sites_and_the_product(
    client: AsyncClient, ela: Ela
) -> None:
    shown = await client.post("/policies/preview", json=DOWNLOAD)
    made = await client.post("/policies", json={**DOWNLOAD, "model": None})
    (policy,) = (await client.get("/policies")).json()["policies"]
    granted = [
        one
        for one in await ela.audit.read()
        if one.event_type is AuditEventType.AUTHORIZATION_GRANTED
    ]

    assert shown.status_code == 200, shown.text
    preview = shown.json()
    root = Path(ela.settings.filesystem.root).resolve()
    assert preview["resolved"] == [str(root / "ELA" / "giu")]
    assert (preview["by_value"], preview["values"]) == ("site", ["posta.example"])
    assert preview["together"] == "every one of these folders with every one of these sites"
    assert preview["uses"] == "at most 2 uses"
    assert "the site, not by the plan" in preview["goes"]
    assert made.status_code == 201, made.text
    assert policy["values"] == ["posta.example"] and policy["by_value"] == "site"
    assert policy["resolved"] == [str(root / "ELA" / "giu")]
    assert policy["goes"] == preview["goes"]
    (event,) = granted
    assert event.payload["values"] == 1 and list(event.payload["sites"]) == ["posta.example"]
    assert event.summary.endswith(", 1 day")


async def test_one_use_is_said_in_the_singular(client: AsyncClient) -> None:
    shown = await client.post("/policies/preview", json={**DOWNLOAD, "uses": 1})

    assert shown.json()["uses"] == "at most 1 use"


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"entry": ["posta.example"]},
        {"site": []},
        {"site": ["posta.example", "posta.example"]},
        {"site": ["not a site"]},
    ],
    ids=["none", "another argument", "empty", "twice", "not a site"],
)
async def test_the_values_of_a_policy_are_the_argument_named_by_value_and_only_it(
    client: AsyncClient, values: dict[str, Any]
) -> None:
    answer = await client.post("/policies/preview", json={**DOWNLOAD, "values": values})

    assert answer.status_code == 422, answer.text
    assert answer.json()["error"]["message"].startswith("VALUES:")


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({**DOWNLOAD, "values": {"site": ["altro.example"]}}, "browser.site_not_declared"),
        ({**DOWNLOAD, "scope": ["ELA/un-file.txt"]}, "fs.not_a_folder"),
        ({**DOWNLOAD, "scope": ["ELA/nessuna"]}, "path.missing"),
        (
            {**DOWNLOAD, "capability": "browser.upload", "scope": ["ELA/un-file.txt"]},
            "fs.not_a_folder",
        ),
    ],
)
async def test_a_place_or_a_site_no_call_could_start_with_is_not_born(
    client: AsyncClient, body: dict[str, Any], code: str
) -> None:
    answer = await client.post("/policies/preview", json=body)

    assert answer.status_code == 422, answer.text
    assert answer.json()["error"]["message"].startswith(f"{code}:")


async def test_a_policy_of_a_login_shows_its_entry_by_name_and_masked_username_never_the_id(
    client: AsyncClient, console: AsyncClient, ela: Ela
) -> None:
    """Decision 10 and answer 35: what is shown is the name and the masked username; the id stays
    in the policy's row, where no route, page or event reads it."""
    preview = await client.post("/policies/preview", json=LOGIN)
    made = await client.post("/policies", json={**LOGIN, "model": None})
    listed_ = await client.get("/policies", params={"all": "true"})
    page = await console.get("/console/policies")
    form = await console.get("/console/policies")
    wrong = await client.post("/policies/preview", json={**LOGIN, "values": {"entry": [WRONG_ID]}})
    long = await client.post("/policies/preview", json={**LOGIN, "values": {"entry": [TOO_LONG]}})
    typed = await client.post("/policies/preview", json={**LOGIN, "values": {"entry": [123]}})
    revoked = await client.post(f"/policies/{made.json()['id']}/revoke")
    again = await client.post(f"/policies/{made.json()['id']}/revoke")
    events = await ela.audit.read()

    assert preview.status_code == 200, preview.text
    assert preview.json()["values"] == [f"La posta di casa ({MASKED})"]
    assert preview.json()["together"] == "every one of these sites with every one of these entries"
    assert made.status_code == 201, made.text
    assert made.json()["values"] == [f"La posta di casa ({MASKED})"]
    assert wrong.status_code == 422 and "vault.no_entry" in wrong.text
    assert long.status_code == 422 and "VALUES" in long.text
    assert typed.status_code == 422
    assert again.status_code == 409
    for said in (
        preview.text,
        made.text,
        listed_.text,
        page.text,
        form.text,
        wrong.text,
        long.text,
        typed.text,
        revoked.text,
        again.text,
        *(event.model_dump_json() for event in events),
    ):
        for secret in (ENTRY.id, WRONG_ID, TOO_LONG):
            assert secret not in said
    (granted,) = [one for one in events if one.event_type is AuditEventType.AUTHORIZATION_GRANTED]
    assert granted.payload["values"] == 1 and "sites" not in granted.payload
    assert "La posta" not in granted.model_dump_json(), "the name of an entry is not audited"


async def test_with_the_vault_closed_no_policy_of_a_login_is_born(
    client: AsyncClient, ela: Ela
) -> None:
    """Decision 10: the vault is opened by you; no policy opens it, and none is born without it."""
    await ela.vault.close()

    answer = await client.post("/policies/preview", json=LOGIN)

    assert answer.status_code == 422, answer.text
    assert answer.json()["error"]["message"].startswith("vault.locked:")
    assert (await client.get("/policies")).json()["policies"] == []


async def test_the_page_that_carries_the_id_back_is_kept_by_nobody(
    console: AsyncClient,
) -> None:
    """Answer 45: the hidden field of the preview is the field of the creation — and the page that
    carries it is ``no-store``."""
    answer = await console.post(
        "/console/policies/preview",
        data={
            "capability": "browser.login",
            "scope": "posta.example",
            "by_value": "entry",
            "value": ENTRY.id,
            "days": "1",
        },
        headers={"Origin": LOOPBACK},
    )

    assert answer.status_code == 200, answer.text
    assert answer.headers["cache-control"] == "no-store"
    visible = answer.text.replace(f'value="{ENTRY.id}"', "")
    assert ENTRY.id not in visible, "the id is in the page outside its hidden field"


def test_no_model_a_route_answers_with_carries_the_grant_whole() -> None:
    """Answer 35 (ii): no route and no output serializes a grant — its ``bounds`` hold the ids."""
    carried = []
    for name, model in inspect.getmembers(schemas, inspect.isclass):
        if not issubclass(model, BaseModel) or model.__module__ != schemas.__name__:
            continue
        for field, info in model.model_fields.items():
            seen = repr(info.annotation)
            for kind in (Authorization, PolicyBounds):
                if kind.__name__ in seen or kind in typing.get_args(info.annotation):
                    carried.append((name, field))
    assert carried == []


@pytest.mark.parametrize(
    "capability",
    [spec.id for spec in CATALOGUE.specs() if spec.policy_terms is not None],
)
def test_a_revocation_says_what_goes_on_only_for_a_session(capability: str) -> None:
    """Decision 20 and answer 40: the session's sentence for a declaration that names a model's
    route, the reads' for one that ``covers`` them — derived, never a list."""
    spec = CATALOGUE.get(capability)  # type: ignore[arg-type]
    born = policy_for(spec)
    assert born.bounds is not None
    # As the birth copies it (ADR 0062 §3): what the capability's sessions cover, on the grant.
    said = running_of(
        born.model_copy(update={"bounds": born.bounds.model_copy(update={"covers": spec.covers})})
    )

    if spec.id == "browser.guided":
        assert said == SESSION_GOES_ON
    elif spec.id == "browser.guided_as_you":
        assert said == f"{SESSION_GOES_ON}. {READS_GO_ON}"
    else:
        assert said is None, spec.id


def test_the_result_of_an_upload_reaches_no_model() -> None:
    """Answer 37 and §57: what reads the result of a step and hands it to a model is a session's
    gesture — its model reads what each gesture made — and the Planner's own planning call. The
    uploads are no session's gesture, and the Planner reads only the result of its call to the
    model."""
    uploads = {"browser.upload", "browser.upload_as_you"}
    for kind in (EMPTY_SESSION, SESSION_AS_YOU):
        assert not uploads & kind.gestures.capabilities()
    from ela.executive import planner

    source = inspect.getsource(planner)
    assert source.count("self._results.") == 1, "the Planner reads results somewhere new"
    assert "for_step(child.id" in source


async def test_the_console_shows_the_folders_the_sites_and_the_entries_of_the_five(
    client: AsyncClient, console: AsyncClient
) -> None:
    """Decision 15: the view of the policies says, for a policy of the five, the folders as the
    birth resolved them, the sites, and the entries by their name and masked username — and the
    form offers the declared sites for a file, a field for the id of an entry for a login."""
    await client.post("/policies", json={**DOWNLOAD, "model": None})
    await client.post("/policies", json={**LOGIN, "model": None})

    page = " ".join((await console.get("/console/policies")).text.split())

    assert "Siti" in page and '"posta.example"' in page
    assert "ELA/giu = " in page, "the folder as the birth resolved it"
    assert "Voci del vault" in page and f"La posta di casa ({MASKED})" in page
    assert "Id della voce" in page, "the field of the creation of a login"
    assert 'name="value" value="forum.example"' in page, "a declared site to tick"
    assert "1 di 2, 1 rimasto" not in page and "0 di 2, 2 rimasti" in page
    assert ENTRY.id not in page


async def test_the_console_s_preview_says_the_uses_then_the_end_with_its_date(
    console: AsyncClient,
) -> None:
    """Answer 47: the order of ADR 0068 §9 — the uses before the end — and the date beside the
    time; and «1 giorno», the singular decided in one place."""
    answer = await console.post(
        "/console/policies/preview",
        data={
            "capability": "browser.download",
            "scope": "ELA/giu",
            "by_value": "site",
            "value": "posta.example",
            "days": "1",
            "uses": "1",
        },
        headers={"Origin": LOOPBACK},
    )
    page = " ".join(answer.text.split())

    assert answer.status_code == 200, answer.text
    assert page.index("Usi") < page.index("Scade")
    assert "fra 1 giorno, il 20" in page, "the date, not the time alone"
    assert "at most 1 use" in page and "Insieme" in page


async def test_the_console_says_where_what_a_policy_moves_goes(
    client: AsyncClient, console: AsyncClient
) -> None:
    """Proposal 11 of the SPEC: the view of a policy says ``goes`` beside ``does`` — «Dove va» —
    for the five as for every capability that declares it (finding 4 of the consistency reading:
    only the preview said it)."""
    await client.post("/policies", json={**DOWNLOAD, "model": None})
    page = html.unescape(" ".join((await console.get("/console/policies")).text.split()))

    words = production_catalogue().get(CapabilityId("browser.download")).policy_words
    assert words is not None and words.goes is not None
    assert "Dove va" in page
    assert " ".join(words.goes.split()) in page
    assert page.index("Che cosa fa senza chiederti") < page.index("Dove va")


def command_line(
    monkeypatch: pytest.MonkeyPatch, ela: Ela, app: FastAPI
) -> Callable[..., Awaitable[Result]]:
    """``ela`` against the routes of this ELA, as a person types it: what each command printed."""
    transport = LoopTransport(app, asyncio.get_running_loop())
    monkeypatch.setattr(
        cli_client, "connect", lambda: cli_client.open_client(ela.settings.api, transport=transport)
    )
    runner = CliRunner()

    async def invoke(*arguments: str) -> Result:
        return await asyncio.to_thread(runner.invoke, ela_app, list(arguments))

    return invoke


async def test_the_command_line_says_where_it_goes_in_the_preview_and_in_its_json(
    monkeypatch: pytest.MonkeyPatch, ela: Ela, app: FastAPI, client: AsyncClient
) -> None:
    """Answer 65: ``goes`` is in the console, in the preview of the command line and in its
    ``--json`` — not in the table of ``ela policy list``, where it would be a column of sentences:
    what is approved names it, and that is the preview."""
    invoke = command_line(monkeypatch, ela, app)
    download = ("policy", "create", "browser.download", "--scope", "ELA/giu", "--site")
    shown = await invoke(*download, "posta.example", "--days", "1", "--uses", "2")
    made = await invoke(*download, "posta.example", "--days", "1", "--uses", "2", "--confirm")
    as_json = await invoke("policy", "list", "--json")
    listed = await invoke("policy", "list")

    words = production_catalogue().get(CapabilityId("browser.download")).policy_words
    assert words is not None and words.goes is not None
    assert made.exit_code == 0, made.output
    assert " ".join(words.goes.split()) in " ".join(plain(shown.output).split())
    (policy,) = json.loads(as_json.output)["policies"]
    assert policy["goes"] == words.goes
    assert " ".join(words.goes.split()) not in " ".join(plain(listed.output).split())


async def test_no_output_of_the_command_line_shows_the_id_of_an_entry(
    monkeypatch: pytest.MonkeyPatch, ela: Ela, app: FastAPI, client: AsyncClient
) -> None:
    """Answer 35 and proposal 11 of the SPEC: an id known to the test, looked for in every output
    of ``ela policy`` — the preview, the creation, a refusal that received a wrong id, the list in
    its two forms, the revocation (finding 13 of the consistency reading: the routes were tested,
    the command line was not)."""
    invoke = command_line(monkeypatch, ela, app)
    login = ("policy", "create", "browser.login", "--scope", "posta.example", "--days", "1")
    shown = await invoke(*login, "--entry", ENTRY.id)
    made = await invoke(*login, "--entry", ENTRY.id, "--uses", "1", "--confirm")
    refused = await invoke(*login, "--entry", WRONG_ID, "--confirm")
    listed = await invoke("policy", "list")
    as_json = await invoke("policy", "list", "--json")
    (policy,) = (await client.get("/policies")).json()["policies"]
    revoked = await invoke("policy", "revoke", policy["short"])
    ended = await invoke("policy", "list", "--all")

    for result in (shown, made, refused, listed, as_json, revoked, ended):
        for secret in (ENTRY.id, WRONG_ID):
            assert secret not in result.output, (result.output, secret)
    assert made.exit_code == 0 and revoked.exit_code == 0, made.output + revoked.output
    assert refused.exit_code != 0 and "vault.no_entry" in plain(refused.output)
    assert MASKED in plain(shown.output) and MASKED in plain(listed.output)
