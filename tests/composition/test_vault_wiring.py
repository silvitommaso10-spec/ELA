"""The vault in the composition root (M13.9, ADR 0063; decisions 16 and 33).

``build`` binds the vault's port to its adapter — the program of ``ELA_VAULT_PROGRAM``, launched
with the closed environment of a program of the terminal and nothing of ELA — and puts the door
of the tools in front of it, with the identity of the program fixed **at the start**. Whoever is
told of a closing is the audit: every one is a row, with why and never with anything of the vault.
And when ELA closes, the key is forgotten before the browser is settled and before the database
is released — nothing is launched.
"""

from __future__ import annotations

import stat
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import pytest

from ela.composition import ELA_ACTOR, Ela, Settings, build
from ela.domain import Actor, ActorKind, AuditEvent, AuditEventType
from ela.infrastructure.machine import BitwardenVault
from ela.infrastructure.persistence import SqlAuditLog, make_engine
from ela.ports import VAULT_LOCKED, Secret
from ela.testing.fakes import FakeBrowser, FakePower, FakeVault
from ela.tools.terminal import CLOSED_PATH, LANGUAGE
from ela.tools.vault import VAULT_TIMEOUT_SECONDS
from tests.composition.support import create_schema, database_url, declare
from tests.composition.test_closing import an_ela, pooled

PROGRAM = "ELA_VAULT_PROGRAM"
KEY = "the-key-of-the-fake-vault"
TOMMASO = Actor(kind=ActorKind.USER, id="the-user-of-the-test")


def program(folder: Path, content: bytes = b"\xcf\xfa\xed\xfe a native program") -> Path:
    """A file that executes and does not begin as a script: what the door fixes the identity of.
    No test launches it — the vault a test opens is the fake."""
    made = folder / "bw"
    made.write_bytes(content)
    made.chmod(made.stat().st_mode | stat.S_IXUSR)
    return made


@pytest.fixture
async def built(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> AsyncIterator[tuple[Ela, FakeVault]]:
    """ELA with a declared program and a vault of the test's behind the door."""
    declare(monkeypatch, tmp_path, **{PROGRAM: str(program(tmp_path))})
    await create_schema(database_url(tmp_path))
    vault = FakeVault(state=VAULT_LOCKED)
    made = await build(Settings.load(), power=FakePower(), vault=vault)
    try:
        yield made, vault
    finally:
        await made.aclose()


def closings(events: tuple[AuditEvent, ...]) -> list[AuditEvent]:
    return [event for event in events if event.event_type is AuditEventType.VAULT_CLOSED]


async def test_without_a_declared_program_there_is_a_door_and_nothing_behind_it(ela: Ela) -> None:
    """ELA starts the same: every use says which line to write, and no adapter exists to launch."""
    assert ela.vault.program is None
    assert ela.vault._vault is None  # noqa: SLF001
    assert (await ela.vault.state()).name == "undeclared"


async def test_the_vault_of_the_core_is_bw_at_the_declared_path_with_the_closed_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ADR 0047 §6, and ADR 0063 beside it: the four variables of a program of the terminal —
    the adapter adds the two of ``bw`` at each launch, and nothing of ELA is in what it inherits."""
    declared = program(tmp_path)
    declare(monkeypatch, tmp_path, **{PROGRAM: str(declared)})
    monkeypatch.setenv("BW_SESSION", "a key left in the environment of whoever started ELA")
    await create_schema(database_url(tmp_path))
    ela = await build(Settings.load(), power=FakePower())
    try:
        adapter = ela.vault._vault  # noqa: SLF001

        assert isinstance(adapter, BitwardenVault)
        assert adapter._program == str(declared)  # noqa: SLF001
        assert adapter._environment == {  # noqa: SLF001
            "PATH": CLOSED_PATH,
            "HOME": str(Path.home()),
            "TMPDIR": tempfile.gettempdir(),
            "LANG": LANGUAGE,
        }
        assert adapter._timeout == VAULT_TIMEOUT_SECONDS == 15  # noqa: SLF001
        assert ela.vault.program == str(declared)
    finally:
        await ela.aclose()


async def test_the_identity_of_the_program_is_the_one_of_the_start(
    built: tuple[Ela, FakeVault], tmp_path: Path
) -> None:
    ela, vault = built
    assert (await ela.vault.state()).name == "locked"

    program(tmp_path, b"\xcf\xfa\xed\xfe an update ELA did not see start")

    assert (await ela.vault.state()).name == "changed"
    assert "unlock" not in vault.calls


async def test_a_closing_on_a_command_is_a_row_of_the_audit_signed_by_who_asked(
    built: tuple[Ela, FakeVault],
) -> None:
    ela, _ = built
    assert await ela.vault.open(Secret(KEY)) is None

    assert await ela.vault.close(TOMMASO) is None

    (row,) = closings(await ela.audit.read())
    assert row.actor == TOMMASO
    assert row.payload == {"reason": "command", "locked": True, "code": None}
    assert row.task_id is None and row.capability_id is None
    assert KEY not in row.model_dump_json()


async def test_a_closing_nobody_asked_for_is_signed_by_ela(
    built: tuple[Ela, FakeVault], tmp_path: Path
) -> None:
    """The hour, here with a program that changed in the meantime: «forgets it and launches
    nothing, and says so» — the row carries the code."""
    ela, vault = built
    assert await ela.vault.open(Secret(KEY)) is None
    program(tmp_path, b"\xcf\xfa\xed\xfe changed")

    await ela.vault._close("expired", None)  # noqa: SLF001 — the keeper's own closing, at its time

    (row,) = closings(await ela.audit.read())
    assert row.actor == ELA_ACTOR
    assert row.payload == {"reason": "expired", "locked": False, "code": "vault.program_changed"}
    assert "lock" not in vault.calls


async def test_closing_ela_forgets_the_key_launches_nothing_and_writes_why(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """«The stop of ELA forgets it», and the row is written while there is a database to write
    it in: read back from the file, by a log opened after ELA closed."""
    declare(monkeypatch, tmp_path, **{PROGRAM: str(program(tmp_path))})
    await create_schema(database_url(tmp_path))
    vault = FakeVault(state=VAULT_LOCKED)
    ela = await build(Settings.load(), power=FakePower(), vault=vault)
    assert await ela.vault.open(Secret(KEY)) is None

    await ela.aclose()

    assert vault.calls[-1] == "forget" and "lock" not in vault.calls
    assert ela.vault.forgets_at is None
    engine = make_engine(database_url(tmp_path))
    try:
        (row,) = closings(await SqlAuditLog(engine).read())
    finally:
        await engine.dispose()
    assert row.actor == ELA_ACTOR
    assert row.payload == {"reason": "stopped", "locked": False, "code": None}


async def test_the_key_is_forgotten_before_the_browser_is_settled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The order of the close: the key first — it costs nothing and waits for nobody —, then the
    browser with its grace, then the database."""
    declare(monkeypatch, tmp_path, **{PROGRAM: str(program(tmp_path))})
    await create_schema(database_url(tmp_path))
    vault = FakeVault(state=VAULT_LOCKED)
    made: list[Ela] = []
    seen: list[tuple[object, str]] = []

    class Looking(FakeBrowser):
        async def settle(self, grace: Callable[[], Awaitable[None]]) -> tuple[str, ...]:
            seen.append((made[0].vault.forgets_at, vault.calls[-1]))
            return await super().settle(grace)

    made.append(await build(Settings.load(), power=FakePower(), browser=Looking(), vault=vault))
    assert await made[0].vault.open(Secret(KEY)) is None

    await made[0].aclose()

    assert seen == [(None, "forget")]


async def test_a_key_that_cannot_be_forgotten_cleanly_does_not_keep_the_browser_or_the_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Whatever the vault's stop raises — a trail that cannot be written —, the browser is still
    brought to rest and the database released: the error is given back after."""
    ela, browser = await an_ela(monkeypatch, tmp_path)

    async def failing() -> None:
        raise OSError("the trail cannot be written")

    monkeypatch.setattr(ela.vault, "stopped", failing)

    with pytest.raises(OSError, match="cannot be written"):
        await ela.aclose()

    assert len(browser.settled) == 1
    assert pooled(ela) == 0
