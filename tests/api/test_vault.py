"""The routes of the vault (M13.9, ADR 0063; decisions 16 and 32).

``GET /vault`` says what the vault is, asked of its program every time; ``POST /vault/session``
receives the session key — **from this machine only**: both ends of the socket loopback, the
tailnet does not deliver a key —; ``POST /vault/lock`` forgets it and asks the vault to lock. The
key enters ELA here and goes nowhere else: not into an answer, a refusal, the audit or a log.
"""

from __future__ import annotations

import logging
import shlex
import stat
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ela.api import create_app
from ela.composition import Ela, Settings, build
from ela.composition.system import own_command
from ela.domain import ActorKind, AuditEvent, AuditEventType
from ela.ports import VAULT_LOCKED, VAULT_UNAUTHENTICATED, VaultTimeout
from ela.testing.fakes import FakeClock, FakePower, FakeVault
from ela.tools.vault import VAULT_OPEN_SECONDS
from tests.api.support import AUTHORIZED
from tests.api.test_console import FORGED_PEER, LOOPBACK, PHONE_PEER, TAILNET, code_for, opened
from tests.composition.support import create_schema, database_url, declare

PROGRAM = "ELA_VAULT_PROGRAM"
KEY = "the-key-of-the-fake-vault"
HERE = "http://127.0.0.1:8351"
LOCAL_PEER = ("127.0.0.1", 50123)
ROUTES = (("GET", "/vault"), ("POST", "/vault/session"), ("POST", "/vault/lock"))


def program(folder: Path, content: bytes = b"\xcf\xfa\xed\xfe a native program") -> Path:
    made = folder / "bw"
    made.write_bytes(content)
    made.chmod(made.stat().st_mode | stat.S_IXUSR)
    return made


@dataclass(frozen=True)
class Vaulted:
    """An ELA with a declared program and a vault of the test's behind the door, its
    application, and the Core's client **at this machine**: both ends of its socket loopback."""

    ela: Ela
    vault: FakeVault
    clock: FakeClock
    app: FastAPI
    client: AsyncClient
    at: Path

    def core(self, base: str, peer: tuple[str, int]) -> AsyncClient:
        """The Core's token, from a socket accepted on ``base`` and dialled by ``peer``."""
        return AsyncClient(
            transport=ASGITransport(app=self.app, client=peer), base_url=base, headers=AUTHORIZED
        )

    async def events(self, kind: AuditEventType) -> list[AuditEvent]:
        return [event for event in await self.ela.audit.read() if event.event_type is kind]


@pytest.fixture
async def vaulted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[Vaulted]:
    at = program(tmp_path)
    declare(monkeypatch, tmp_path, **{PROGRAM: str(at)})
    await create_schema(database_url(tmp_path))
    vault, clock = FakeVault(state=VAULT_LOCKED), FakeClock(datetime.now(UTC))
    ela = await build(Settings.load(), clock=clock, power=FakePower(), vault=vault)
    app = create_app(ela)
    try:
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app, client=LOCAL_PEER),
                base_url=HERE,
                headers=AUTHORIZED,
            ) as client,
        ):
            yield Vaulted(ela, vault, clock, app, client, at)
    finally:
        await ela.aclose()


# ----------------------------------------------------------------------------------------
# The state, derived
# ----------------------------------------------------------------------------------------


async def test_without_a_declared_program_the_state_says_what_is_missing(
    client: AsyncClient,
) -> None:
    answered = await client.get("/vault")

    assert answered.status_code == 200
    said = answered.json()
    assert said["state"] == "undeclared"
    assert said["program"] is None and said["opens_with"] is None and said["forgets_at"] is None
    assert PROGRAM in said["message"]


async def test_a_locked_vault_answers_with_the_whole_line_to_paste(vaulted: Vaulted) -> None:
    """Decisions 32 and 98: the line is composed with the declared program and with **the
    command this ELA runs with** — both by their absolute path, neither a name to look for, and
    no placeholder."""
    command = own_command()
    assert command is not None
    line = f"{vaulted.at} unlock --raw | {shlex.quote(str(command))} vault open"

    said = (await vaulted.client.get("/vault")).json()

    assert said == {
        "state": "locked",
        "forgets_at": None,
        "program": str(vaulted.at),
        "opens_with": line,
        "message": f"the vault is locked: run `{line}` in your terminal",
    }
    assert "<" not in said["opens_with"] and " | ela " not in said["opens_with"]


async def test_started_where_a_dotenv_is_the_line_enters_that_folder_by_itself(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The command of the line reads its token from the ``.env`` of the folder it is launched
    in: an ELA that read one gives a line that enters that folder — the folder, and not the file
    in it —, and the sentence beside it does not say where to run it any more (decision 145 of
    the review of 2026-10-13)."""
    at = tmp_path / "bw"
    at.write_bytes(b"\xcf\xfa\xed\xfe a native program")
    at.chmod(at.stat().st_mode | stat.S_IXUSR)
    declare(monkeypatch, tmp_path, ELA_VAULT_PROGRAM=str(at))
    (tmp_path / ".env").write_text("", encoding="utf-8")
    await create_schema(database_url(tmp_path))
    ela = await build(Settings.load(), power=FakePower(), vault=FakeVault(state=VAULT_LOCKED))
    try:
        state = await ela.vault.state()
    finally:
        await ela.aclose()

    assert state.opens_with is not None
    folder = shlex.quote(str(tmp_path.resolve()))
    assert state.opens_with.startswith(f"(cd {folder} && ") and state.opens_with.endswith(")")
    assert state.message == f"the vault is locked: run `{state.opens_with}` in your terminal"
    assert ".env" not in state.message


async def test_the_state_is_asked_of_the_vault_at_every_request(vaulted: Vaulted) -> None:
    """Derived, never remembered (16e): what changed in the vault is in the next answer."""
    assert (await vaulted.client.get("/vault")).json()["state"] == "locked"

    vaulted.vault.state = VAULT_UNAUTHENTICATED
    said = (await vaulted.client.get("/vault")).json()

    assert said["state"] == "unauthenticated" and said["opens_with"] is None
    assert vaulted.vault.calls.count("status") == 2

    vaulted.vault.raising["status"] = VaultTimeout("bw status did not answer within 15 s")
    assert (await vaulted.client.get("/vault")).json()["state"] == "timeout"


async def test_the_address_of_the_account_is_nowhere_in_the_state(vaulted: Vaulted) -> None:
    """What the answer may carry is a closed set of fields: a field added tomorrow is seen here."""
    assert set((await vaulted.client.get("/vault")).json()) == {
        "state",
        "forgets_at",
        "program",
        "opens_with",
        "message",
    }


# ----------------------------------------------------------------------------------------
# The key: from this machine, and nowhere after
# ----------------------------------------------------------------------------------------


async def test_the_key_that_opens_is_kept_and_the_answer_says_until_when(vaulted: Vaulted) -> None:
    opened_at = vaulted.clock.now()

    answered = await vaulted.client.post("/vault/session", json={"key": KEY})

    assert answered.status_code == 200, answered.text
    forgets_at = (opened_at + timedelta(seconds=VAULT_OPEN_SECONDS)).isoformat()
    assert answered.json() == {"forgets_at": forgets_at.replace("+00:00", "Z")}
    state = (await vaulted.client.get("/vault")).json()
    assert state["state"] == "unlocked" and state["forgets_at"] == answered.json()["forgets_at"]
    assert state["opens_with"] is None and state["message"] == ""


async def test_an_opening_is_a_row_of_the_audit_signed_by_who_handed_the_key(
    vaulted: Vaulted,
) -> None:
    await vaulted.client.post("/vault/session", json={"key": KEY})

    (row,) = await vaulted.events(AuditEventType.VAULT_OPENED)
    assert row.actor.kind is ActorKind.USER
    assert row.task_id is None and row.capability_id is None
    assert set(row.payload) == {"forgets_at"}
    assert KEY not in row.model_dump_json()


@pytest.mark.parametrize("closing", ["written", "not-written-either"])
async def test_an_opening_nobody_could_write_down_is_not_kept(
    vaulted: Vaulted, monkeypatch: pytest.MonkeyPatch, closing: str
) -> None:
    """The door takes the key before the row is written. A row that cannot be written — a
    database that went away in between — must not leave ELA holding a key for an hour that the
    audit knows nothing of: the key is forgotten, the vault asked to lock, and the failure is the
    answer. Whether or not the closing can be written down either."""
    append = vaulted.ela.audit.append
    unwritable = {AuditEventType.VAULT_OPENED}
    if closing == "not-written-either":
        unwritable.add(AuditEventType.VAULT_CLOSED)

    async def failing(event: AuditEvent) -> None:
        if event.event_type in unwritable:
            raise OSError(f"the audit could not write {event.event_type.value}")
        await append(event)

    monkeypatch.setattr(vaulted.ela.audit, "append", failing)

    with pytest.raises(OSError, match="could not write VAULT_OPENED$"):
        await vaulted.client.post("/vault/session", json={"key": KEY})

    assert vaulted.ela.vault.forgets_at is None, "the door holds nothing"
    assert vaulted.vault.calls[-1] == "lock", "and the vault was asked to lock"
    monkeypatch.undo()
    assert (await vaulted.client.get("/vault")).json()["state"] == "locked"
    assert await vaulted.events(AuditEventType.VAULT_OPENED) == []


@pytest.mark.parametrize(
    ("base", "peer"),
    [
        (TAILNET, PHONE_PEER),
        (TAILNET, FORGED_PEER),
        (LOOPBACK, PHONE_PEER),
        ("http://ela", LOCAL_PEER),
    ],
    ids=["the-tailnet", "a-forged-local-peer", "a-remote-peer", "a-name-that-is-not-loopback"],
)
async def test_a_key_that_does_not_come_from_this_machine_is_refused_and_never_tried(
    vaulted: Vaulted, base: str, peer: tuple[str, int]
) -> None:
    """Both ends of the socket, as for the console's ceiling (M17.2 dec. J): the tailnet does not
    deliver a key, whatever token it carries."""
    async with vaulted.core(base, peer) as remote:
        answered = await remote.post("/vault/session", json={"key": KEY})

        assert answered.status_code == 403
        assert answered.json()["error"]["code"] == "vault.refused"
        assert answered.json()["error"]["message"].startswith("vault.not_local: ")
        assert KEY not in answered.text
        assert "unlock" not in vaulted.vault.calls, "the vault was never asked"
        assert await vaulted.events(AuditEventType.VAULT_OPENED) == []
        assert (await remote.get("/vault")).status_code == 200, "the state is not the key"


async def test_a_key_that_does_not_open_is_refused_forgotten_and_not_said_back(
    vaulted: Vaulted,
) -> None:
    wrong = "a-key-that-opens-nothing-SENTINEL"

    answered = await vaulted.client.post("/vault/session", json={"key": wrong})

    assert answered.status_code == 409
    assert answered.json()["error"]["code"] == "vault.refused"
    assert answered.json()["error"]["message"].startswith("vault.key_refused: ")
    assert wrong not in answered.text
    assert await vaulted.events(AuditEventType.VAULT_OPENED) == []
    assert (await vaulted.client.get("/vault")).json()["state"] == "locked"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"key": ""},
        {"key": ["SENTINEL-in-a-list"]},
        {"key": {"SENTINEL-as-a-name": "SENTINEL-as-a-value"}},
        {"key": "SENTINEL" * 2000},
        {"key": KEY, "master": "SENTINEL-the-master-password"},
        {"key": "SENTINEL-a-key", "master": "x"},
    ],
    ids=[
        "no-key",
        "empty",
        "a-list",
        "an-object",
        "too-long",
        "a-field-nobody-declared",
        "a-key-beside-a-field-nobody-declared",
    ],
)
async def test_a_body_that_is_not_one_key_is_refused_without_being_said_back(
    vaulted: Vaulted, body: dict[str, object]
) -> None:
    """The master password has no field to travel in: the route takes one key and nothing else —
    and a refusal names the field that is wrong and **never what it held**, whoever's it was."""
    answered = await vaulted.client.post("/vault/session", json=body)

    assert answered.status_code == 422
    assert "SENTINEL" not in answered.text
    assert "unlock" not in vaulted.vault.calls


async def test_a_vault_whose_program_changed_takes_no_key(vaulted: Vaulted) -> None:
    program(vaulted.at.parent, b"\xcf\xfa\xed\xfe an update ELA did not see start")

    answered = await vaulted.client.post("/vault/session", json={"key": KEY})

    assert answered.status_code == 409
    assert answered.json()["error"]["message"].startswith("vault.program_changed: ")
    assert "unlock" not in vaulted.vault.calls


async def test_the_key_is_in_no_log_and_no_stream_accepted_or_refused(
    vaulted: Vaulted, caplog: pytest.LogCaptureFixture, capfd: pytest.CaptureFixture[str]
) -> None:
    """Criterion 11: not in a log, not in the body of an answer, not in a row of the audit."""
    sentinel = " ".join(("SENTINEL", "of", "the", "session", "key"))
    vaulted.vault.key = sentinel
    caplog.set_level(logging.DEBUG)

    accepted = await vaulted.client.post("/vault/session", json={"key": sentinel})
    refused = await vaulted.client.post("/vault/session", json={"key": sentinel + "-wrong"})
    state = await vaulted.client.get("/vault")
    locked = await vaulted.client.post("/vault/lock")

    assert (accepted.status_code, refused.status_code, locked.status_code) == (200, 409, 200)
    streams = capfd.readouterr()
    trail = "".join(event.model_dump_json() for event in await vaulted.ela.audit.read())
    for where in (
        accepted.text,
        refused.text,
        state.text,
        locked.text,
        caplog.text,
        streams.out,
        streams.err,
        trail,
    ):
        assert sentinel not in where


# ----------------------------------------------------------------------------------------
# The lock
# ----------------------------------------------------------------------------------------


async def test_closing_locks_the_vault_forgets_the_key_and_writes_who_asked(
    vaulted: Vaulted,
) -> None:
    await vaulted.client.post("/vault/session", json={"key": KEY})

    answered = await vaulted.client.post("/vault/lock")

    assert answered.status_code == 200 and answered.json() == {"locked": True}
    assert vaulted.vault.calls[-1] == "lock"
    assert vaulted.ela.vault.forgets_at is None
    (row,) = await vaulted.events(AuditEventType.VAULT_CLOSED)
    assert row.actor.kind is ActorKind.USER
    assert row.payload == {"reason": "command", "locked": True, "code": None}


async def test_a_close_that_could_not_lock_says_so_and_the_key_is_forgotten_all_the_same(
    vaulted: Vaulted,
) -> None:
    await vaulted.client.post("/vault/session", json={"key": KEY})
    program(vaulted.at.parent, b"\xcf\xfa\xed\xfe an update ELA did not see start")

    answered = await vaulted.client.post("/vault/lock")

    assert answered.status_code == 409
    said = answered.json()["error"]
    assert said["code"] == "vault.refused"
    assert said["message"].startswith("vault.program_changed: ")
    assert "ELA forgot the key" in said["message"]
    assert vaulted.vault.calls[-1] == "forget" and vaulted.ela.vault.forgets_at is None
    (row,) = await vaulted.events(AuditEventType.VAULT_CLOSED)
    assert row.payload == {"reason": "command", "locked": False, "code": "vault.program_changed"}


async def test_closing_is_not_bound_to_this_machine(vaulted: Vaulted) -> None:
    """Only the key is: whoever holds the Core's token may always close."""
    async with vaulted.core(TAILNET, PHONE_PEER) as remote:
        assert (await remote.post("/vault/lock")).status_code == 200


# ----------------------------------------------------------------------------------------
# Who reaches them
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(("method", "path"), ROUTES)
async def test_without_the_core_s_token_nothing_of_the_vault_answers(
    vaulted: Vaulted, method: str, path: str
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=vaulted.app, client=LOCAL_PEER), base_url=HERE
    ) as nobody:
        answered = await nobody.request(method, path, json={"key": KEY})

    assert answered.status_code == 401
    assert vaulted.vault.calls == []


@pytest.mark.parametrize(("method", "path"), ROUTES)
async def test_a_console_s_cookie_is_not_the_core_s_token(
    vaulted: Vaulted, method: str, path: str
) -> None:
    """The routes are the Core's: a console reaches the vault through its own page, which closes
    it and never opens it — a key is not pasted into a page."""
    async with opened(vaulted.app, LOOPBACK) as browser:
        enrolled = await browser.post(
            "/console/enroll",
            data={"code": await code_for(vaulted.client), "name": "MacBook", "os": "MACOS"},
            headers={"Origin": LOOPBACK},
        )
        assert enrolled.status_code == 303

        answered = await browser.request(method, path, json={"key": KEY})

    assert answered.status_code == 401
    assert vaulted.vault.calls == []
