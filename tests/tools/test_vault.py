"""The vault as the tools and the routes reach it (M13.9, ADR 0063; decisions 15, 16, 28, 33, 42).

Between ELA and the vault's adapter stands one object, in the gate: it fixes the identity of the
vault's program at the start and compares it again **before every use**; it keeps the key no
longer than an hour from the opening; it says every refusal with a code of its own; and it holds
the one comparison that binds an entry to a site — **the equality of the host, made by ELA**, not
Bitwarden's match by domain.
"""

from __future__ import annotations

import asyncio
import shlex
import stat
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from ela.domain import Actor, ActorKind
from ela.ports import (
    VAULT_LOCKED,
    VAULT_UNAUTHENTICATED,
    Secret,
    VaultEntry,
    VaultFailed,
    VaultTimeout,
)
from ela.testing.fakes import FakeClock, FakeVault, FakeVaultEntry

SITE = "posta.example"
ADDRESS = "https://posta.example"
KEY = "the-key-of-the-fake-vault"
TYPED = "what-the-test-types-in-the-field"
MARIO = FakeVaultEntry(
    "11111111-2222-4333-8444-555555555555",
    "La posta",
    ("https://posta.example/login",),
    "mario.rossi@example.com",
    TYPED,
    "m…@example.com",
)
WITH_A_USER_AND_A_WORD = "https://" + ":".join(("mario", "x")) + "@posta.example"
"""An address with a user and a word before the host — composed, so that no line of this file
looks like one."""


def program(folder: Path, content: bytes = b"\xcf\xfa\xed\xfe a native program") -> Path:
    made = folder / "bw"
    made.write_bytes(content)
    made.chmod(made.stat().st_mode | stat.S_IXUSR)
    return made


async def door(vault: FakeVault | None, at: Path | None, **options: Any) -> Any:
    from ela.tools.vault import VaultDoor

    return await VaultDoor.fixed(
        vault, None if at is None else str(at), clock=options.pop("clock", FakeClock()), **options
    )


def code_of(answer: Any) -> str:
    from ela.tools.vault import VaultProblem

    assert isinstance(answer, VaultProblem), answer
    return answer.code


# ----------------------------------------------------------------------------------------
# The program: declared, native, and the one of the start
# ----------------------------------------------------------------------------------------


async def test_without_a_declared_program_every_use_says_so_and_nothing_is_asked() -> None:
    made = await door(None, None)

    assert code_of(await made.find(SITE)) == "vault.undeclared"
    assert code_of(await made.open(Secret(KEY))) == "vault.undeclared"
    assert (await made.state()).name == "undeclared"


async def test_a_program_that_is_the_one_of_the_start_lets_the_vault_be_asked(
    tmp_path: Path,
) -> None:
    vault = FakeVault([MARIO])
    made = await door(vault, program(tmp_path))

    found = await made.find(SITE)

    assert isinstance(found, VaultEntry) and found.id == MARIO.id
    assert vault.calls == [f"find:{ADDRESS}"], "asked for the address of the site, https and bare"


async def test_a_program_that_changed_after_the_start_is_refused_until_ela_restarts(
    tmp_path: Path,
) -> None:
    vault = FakeVault([MARIO])
    at = program(tmp_path)
    made = await door(vault, at)
    program(tmp_path, b"\xcf\xfa\xed\xfe another program, an update for instance")

    answer = await made.find(SITE)

    assert code_of(answer) == "vault.program_changed"
    assert "restart ELA to accept it" in answer.message
    assert vault.calls == [], "the program that receives the key is not launched changed"


async def test_a_program_that_went_away_is_gone_and_one_that_never_was_is_no_program(
    tmp_path: Path,
) -> None:
    vault = FakeVault([MARIO])
    at = program(tmp_path)
    made = await door(vault, at)
    at.unlink()

    assert code_of(await made.find(SITE)) == "vault.program_gone"
    assert code_of(await (await door(vault, tmp_path / "never")).find(SITE)) == "vault.no_program"
    assert vault.calls == []


async def test_a_program_that_begins_as_a_script_is_refused(tmp_path: Path) -> None:
    """Decision 42: the identity ELA would fix is that of a launcher of a few lines, not of the
    code that receives the key — and the closed environment has no interpreter to find."""
    vault = FakeVault([MARIO])
    made = await door(vault, program(tmp_path, b"#!/usr/bin/env node\nrequire('bw')\n"))

    answer = await made.find(SITE)

    assert code_of(answer) == "vault.program_is_a_script"
    assert (await made.state()).name == "is_a_script"
    assert vault.calls == []


# ----------------------------------------------------------------------------------------
# The state, derived; the key, for an hour
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("said", "code"),
    [(VAULT_UNAUTHENTICATED, "vault.unauthenticated"), (VAULT_LOCKED, "vault.locked")],
)
async def test_a_vault_that_is_not_open_is_said_with_its_own_code(
    tmp_path: Path, said: str, code: str
) -> None:
    vault = FakeVault([MARIO], state=said)
    made = await door(vault, program(tmp_path))

    answer = await made.find(SITE)

    assert code_of(answer) == code
    assert (await made.state()).name == said
    assert str(tmp_path / "bw") in answer.message, "the sentence names the program to run"


async def test_the_key_that_opens_is_kept_for_an_hour_from_the_opening_and_not_from_its_use(
    tmp_path: Path,
) -> None:
    from ela.tools.vault import VAULT_OPEN_SECONDS

    clock = FakeClock()
    vault = FakeVault([MARIO], state=VAULT_LOCKED)
    made = await door(vault, program(tmp_path), clock=clock)

    assert await made.open(Secret(KEY)) is None
    opened_at = clock.now()
    state = await made.state()
    assert state.name == "unlocked"
    assert state.forgets_at == opened_at + timedelta(seconds=VAULT_OPEN_SECONDS)
    assert VAULT_OPEN_SECONDS == 3600

    clock.advance(timedelta(minutes=59))
    assert isinstance(await made.find(SITE), VaultEntry), "used at the fifty-ninth minute"
    assert (await made.state()).forgets_at == state.forgets_at, "a use does not move the end"

    clock.advance(timedelta(minutes=1))
    assert await made.expire() is True
    assert vault.calls[-1] == "lock", "at its time ELA forgets the key and asks the vault to lock"
    assert (await made.state()).name == "locked"
    assert (await made.state()).forgets_at is None
    assert await made.expire() is False, "once"


async def test_a_use_after_the_hour_finds_the_vault_closed_even_if_nobody_closed_it(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    vault = FakeVault([MARIO], state=VAULT_LOCKED)
    made = await door(vault, program(tmp_path), clock=clock)
    assert await made.open(Secret(KEY)) is None
    clock.advance(timedelta(hours=1, seconds=1))

    answer = await made.find(SITE)

    assert code_of(answer) == "vault.locked"
    assert "lock" in vault.calls


async def test_a_key_that_does_not_open_is_refused_and_no_end_is_set(tmp_path: Path) -> None:
    vault = FakeVault([MARIO], state=VAULT_LOCKED)
    made = await door(vault, program(tmp_path))

    answer = await made.open(Secret("another key"))

    assert code_of(answer) == "vault.key_refused"
    assert (await made.state()).forgets_at is None


async def test_closing_locks_and_forgets_and_with_a_changed_program_only_forgets(
    tmp_path: Path,
) -> None:
    vault = FakeVault([MARIO], state=VAULT_LOCKED)
    at = program(tmp_path)
    made = await door(vault, at)
    assert await made.open(Secret(KEY)) is None

    assert await made.close() is None
    assert vault.calls[-1] == "lock"

    assert await made.open(Secret(KEY)) is None
    program(tmp_path, b"\xcf\xfa\xed\xfe changed")
    answer = await made.close()

    assert code_of(answer) == "vault.program_changed"
    assert vault.calls[-1] == "forget", "the key is dropped, and the changed program is not run"
    assert (await made.state()).forgets_at is None


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (VaultTimeout("bw status did not answer within 15 s"), "vault.timeout"),
        (VaultFailed("bw list items failed"), "vault.failed"),
    ],
)
async def test_a_vault_that_does_not_answer_or_fails_is_said_with_its_code(
    tmp_path: Path, failure: Exception, code: str
) -> None:
    vault = FakeVault([MARIO])
    vault.raising["find"] = failure
    made = await door(vault, program(tmp_path))

    answer = await made.find(SITE)

    assert code_of(answer) == code
    assert str(failure) in answer.message


# ----------------------------------------------------------------------------------------
# The entry is bound to the site: the host, compared by ELA
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("address", "host"),
    [
        ("https://posta.example", "posta.example"),
        ("https://posta.example/login?x=1#y", "posta.example"),
        ("https://POSTA.Example./", "posta.example"),
        ("https://posta.example:443/", "posta.example"),
        ("https://bücher.example/", "xn--bcher-kva.example"),
        ("http://posta.example", None),
        ("https://posta.example:8443", None),
        ("https://mario@posta.example", None),
        (WITH_A_USER_AND_A_WORD, None),
        ("posta.example", None),
        ("androidapp://posta.example", None),
        ("https://", None),
        ("https://exa mple.com", None),
        ("https://[::1", None),
        ("https://posta.example:porta", None),
        ("https://a..b.example", None),
        ("https://-posta.example", None),
        ("", None),
    ],
)
def test_the_host_of_an_address_counts_only_if_it_is_plain_https(
    address: str, host: str | None
) -> None:
    """What «the same host» means, written because a comparison left halfway is where an error
    lives: https, no user before the host, the default port, lower case, the ASCII form of an
    international name, no final dot — and what does not read as an address matches nothing."""
    from ela.tools.vault import host_of

    assert host_of(address) == host


def entry(**changes: Any) -> FakeVaultEntry:
    return FakeVaultEntry(**({**MARIO.__dict__, **changes}))


async def chosen(tmp_path: Path, entries: list[FakeVaultEntry], wanted: str | None = None) -> Any:
    made = await door(FakeVault(entries), program(tmp_path))
    return await made.find(SITE, wanted)


async def test_the_one_entry_whose_host_is_the_site_is_the_entry(tmp_path: Path) -> None:
    elsewhere = entry(id="other", addresses=("https://altro.example",))

    found = await chosen(tmp_path, [elsewhere, MARIO])

    assert isinstance(found, VaultEntry) and found.id == MARIO.id
    assert found.username == "m…@example.com", "masked: the whole name never left the adapter"


@pytest.mark.parametrize(
    "addresses",
    [
        ("https://altro.example",),
        ("https://login.posta.example",),
        ("https://example",),
        ("http://posta.example",),
        ("posta.example",),
        (),
    ],
    ids=["another host", "a subdomain", "the domain alone", "not https", "no scheme", "none"],
)
async def test_an_entry_that_does_not_name_that_host_is_no_entry_for_the_site(
    tmp_path: Path, addresses: tuple[str, ...]
) -> None:
    answer = await chosen(tmp_path, [entry(addresses=addresses)])

    assert code_of(answer) == "vault.no_entry"
    assert MARIO.name not in answer.message and MARIO.id not in answer.message, (
        "a refusal born before the question never names an entry"
    )


async def test_two_entries_for_the_site_are_ambiguous_until_one_is_named(tmp_path: Path) -> None:
    second = entry(id="22222222-2222-4333-8444-555555555555", name="La posta, il lavoro")

    answer = await chosen(tmp_path, [MARIO, second])
    named = await chosen(tmp_path, [MARIO, second], second.id)

    assert code_of(answer) == "vault.entry_ambiguous"
    assert MARIO.name not in answer.message and second.name not in answer.message
    assert isinstance(named, VaultEntry) and named.id == second.id


async def test_an_entry_named_that_is_not_there_or_is_not_for_the_site_is_refused(
    tmp_path: Path,
) -> None:
    elsewhere = entry(id="other", addresses=("https://altro.example",))

    assert code_of(await chosen(tmp_path, [MARIO], "no-such-id")) == "vault.no_entry"
    assert code_of(await chosen(tmp_path, [MARIO, elsewhere], "other")) == (
        "vault.entry_not_for_site"
    )


async def test_an_entry_with_no_password_is_said_before_the_question(tmp_path: Path) -> None:
    answer = await chosen(tmp_path, [entry(password=None)])

    assert code_of(answer) == "vault.no_password"


# ----------------------------------------------------------------------------------------
# After the yes: one reading, compared again on what it gave
# ----------------------------------------------------------------------------------------


async def test_after_the_yes_the_entry_is_taken_and_compared_again_on_the_same_reading(
    tmp_path: Path,
) -> None:
    from ela.ports import VaultTaken

    vault = FakeVault([MARIO])
    made = await door(vault, program(tmp_path))

    taken = await made.take(SITE, MARIO.id)

    assert isinstance(taken, VaultTaken)
    assert vault.calls == [f"take:{MARIO.id}"], "one reading, and no listing after the yes"
    assert TYPED not in repr(taken)


async def test_an_entry_that_changed_site_between_the_question_and_the_yes_is_not_taken(
    tmp_path: Path,
) -> None:
    """The comparison and the taking rest on the same reading: an entry whose address was moved
    after the question is found out on the very answer the password would have come from."""
    vault = FakeVault([MARIO])
    made = await door(vault, program(tmp_path))
    vault.entries[0] = entry(addresses=("https://altro.example",))

    answer = await made.take(SITE, MARIO.id)

    assert code_of(answer) == "vault.entry_not_for_site"
    assert TYPED not in repr(answer)


async def test_a_vault_locked_or_a_program_changed_after_the_yes_gives_nothing(
    tmp_path: Path,
) -> None:
    vault = FakeVault([MARIO])
    at = program(tmp_path)
    made = await door(vault, at)
    vault.state = VAULT_LOCKED

    assert code_of(await made.take(SITE, MARIO.id)) == "vault.locked"

    vault.state = "unlocked"
    program(tmp_path, b"\xcf\xfa\xed\xfe changed")
    before = list(vault.calls)

    assert code_of(await made.take(SITE, MARIO.id)) == "vault.program_changed"
    assert vault.calls == before, "the identity is compared before the launch, after the yes too"


def test_every_code_of_the_vault_is_in_the_closed_set() -> None:
    from ela.tools import vault

    assert (
        frozenset(
            {
                "vault.undeclared",
                "vault.no_program",
                "vault.program_changed",
                "vault.program_gone",
                "vault.program_is_a_script",
                "vault.unauthenticated",
                "vault.locked",
                "vault.timeout",
                "vault.failed",
                "vault.key_refused",
                "vault.no_entry",
                "vault.entry_ambiguous",
                "vault.entry_not_for_site",
                "vault.no_password",
            }
        )
        == vault.VAULT_CODES
    )
    assert vault.VAULT_TIMEOUT_SECONDS == 15


# ----------------------------------------------------------------------------------------
# A vault that fails, at each door
# ----------------------------------------------------------------------------------------


async def test_a_vault_that_fails_while_it_is_opened_closed_or_asked_its_state(
    tmp_path: Path,
) -> None:
    vault = FakeVault([MARIO], state=VAULT_LOCKED)
    made = await door(vault, program(tmp_path))
    failure = VaultFailed("bw status failed")

    vault.raising["unlock"] = failure
    assert code_of(await made.open(Secret(KEY))) == "vault.failed"
    del vault.raising["unlock"]

    vault.raising["status"] = VaultTimeout("bw status did not answer within 15 s")
    assert (await made.state()).name == "timeout"
    del vault.raising["status"]

    assert await made.open(Secret(KEY)) is None
    vault.raising["lock"] = failure
    assert code_of(await made.close()) == "vault.failed"
    assert vault.calls[-2:] == ["lock", "forget"], "a lock that failed still leaves no key held"
    assert (await made.state()).forgets_at is None


async def test_closing_a_vault_nobody_declared_says_so() -> None:
    made = await door(None, None)

    assert code_of(await made.close()) == "vault.undeclared"
    assert await made.expire() is False


async def test_a_key_ended_elsewhere_is_forgotten_when_the_state_is_asked(tmp_path: Path) -> None:
    """Measured (K2): a new unlock in the owner's terminal ends the key ELA holds, and so does a
    lock. ELA learns it when it asks, and holds a dead key no longer."""
    vault = FakeVault([MARIO], state=VAULT_LOCKED)
    made = await door(vault, program(tmp_path))
    assert await made.open(Secret(KEY)) is None
    vault.state = VAULT_LOCKED

    state = await made.state()

    assert state.name == "locked" and state.forgets_at is None
    assert vault.calls[-1] == "forget"
    assert await made.expire() is False, "there is no hour left to run out"


async def test_a_program_that_cannot_be_read_now_is_not_called_a_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ela.tools import vault as module

    vault = FakeVault([MARIO])
    made = await door(vault, program(tmp_path))

    def unreadable(*args: Any, **kwargs: Any) -> Any:
        raise PermissionError("not for this test to read")

    monkeypatch.setattr(module, "open", unreadable, raising=False)

    assert isinstance(await made.find(SITE), VaultEntry), "the launch says what became of it"


# ----------------------------------------------------------------------------------------
# The keeper of the key: every closing is told, with why, and one comes by itself
# ----------------------------------------------------------------------------------------

TOMMASO = Actor(kind=ActorKind.USER, id="the-user-of-the-test")


class Told:
    """Whoever is told of a closing — in ELA, the audit: what it received, in order."""

    def __init__(self) -> None:
        self.closings: list[Any] = []
        self.heard = asyncio.Event()

    async def __call__(self, closing: Any) -> None:
        self.closings.append(closing)
        self.heard.set()

    async def hears(self) -> None:
        """Wait for a closing: the keeper looks at its program in a thread, so «a few turns of
        the loop» is not when it is told."""
        await asyncio.wait_for(self.heard.wait(), 5)

    @property
    def said(self) -> list[tuple[str, Actor | None, bool, str | None]]:
        return [(one.reason, one.by, one.locked, one.code) for one in self.closings]


class Hour:
    """The hour of the key, held by the test: every wait the keeper begins, and the event that
    ends it."""

    def __init__(self) -> None:
        self.asked: list[float] = []
        self.over = asyncio.Event()
        self.cancelled = 0

    async def __call__(self, seconds: float) -> None:
        self.asked.append(seconds)
        try:
            await self.over.wait()
        except asyncio.CancelledError:
            self.cancelled += 1
            raise


async def turns(times: int = 5) -> None:
    for _ in range(times):
        await asyncio.sleep(0)


async def test_a_command_that_closes_is_told_with_who_asked_and_that_the_vault_locked(
    tmp_path: Path,
) -> None:
    told = Told()
    vault = FakeVault([MARIO], state=VAULT_LOCKED)
    made = await door(vault, program(tmp_path), closed=told)
    assert await made.open(Secret(KEY)) is None
    assert told.said == [], "an opening is not a closing: the route that receives it writes it"

    assert await made.close(TOMMASO) is None

    assert told.said == [("command", TOMMASO, True, None)]


async def test_a_command_that_could_not_lock_is_told_with_the_code_and_that_it_did_not(
    tmp_path: Path,
) -> None:
    """«Forgets it and launches nothing, and says so»: the row carries why the vault's program
    was not asked."""
    told = Told()
    vault = FakeVault([MARIO], state=VAULT_LOCKED)
    made = await door(vault, program(tmp_path), closed=told)
    assert await made.open(Secret(KEY)) is None
    program(tmp_path, b"\xcf\xfa\xed\xfe changed")

    assert code_of(await made.close(TOMMASO)) == "vault.program_changed"

    assert told.said == [("command", TOMMASO, False, "vault.program_changed")]


async def test_a_command_that_locks_a_vault_ela_held_no_key_of_is_told_too(
    tmp_path: Path,
) -> None:
    """``bw lock`` is the whole machine's: ELA closed what the owner had open in a terminal, on
    their command, and the row says who asked."""
    told = Told()
    vault = FakeVault([MARIO])
    made = await door(vault, program(tmp_path), closed=told)

    assert await made.close(TOMMASO) is None

    assert vault.calls[-1] == "lock"
    assert told.said == [("command", TOMMASO, True, None)]


async def test_a_command_that_held_nothing_and_ran_nothing_tells_nobody(tmp_path: Path) -> None:
    told = Told()
    undeclared = await door(None, None, closed=told)
    gone = await door(FakeVault([MARIO]), tmp_path / "never-there", closed=told)

    assert code_of(await undeclared.close(TOMMASO)) == "vault.undeclared"
    assert code_of(await gone.close(TOMMASO)) == "vault.no_program"

    assert told.said == []


async def test_the_hour_running_out_at_a_use_is_told_as_the_time_and_by_nobody(
    tmp_path: Path,
) -> None:
    told, hour, clock = Told(), Hour(), FakeClock()
    vault = FakeVault([MARIO], state=VAULT_LOCKED)
    made = await door(vault, program(tmp_path), clock=clock, closed=told, wait=hour)
    assert await made.open(Secret(KEY)) is None
    await turns()
    clock.advance(timedelta(hours=1))

    assert code_of(await made.find(SITE)) == "vault.locked"
    await turns()

    assert told.said == [("expired", None, True, None)]
    assert hour.cancelled == 1, "the wait is ended: the hour does not run out a second time"


async def test_at_its_time_the_keeper_closes_the_vault_with_nobody_calling(tmp_path: Path) -> None:
    """Decision 33: «a task of the keeper of the key — not a route: nobody is calling it»."""
    from ela.tools.vault import VAULT_OPEN_SECONDS

    told, hour = Told(), Hour()
    vault = FakeVault([MARIO], state=VAULT_LOCKED)
    made = await door(vault, program(tmp_path), closed=told, wait=hour)

    assert await made.open(Secret(KEY)) is None
    await turns()
    assert hour.asked == [float(VAULT_OPEN_SECONDS)], (
        "one wait, of the whole hour, from the opening"
    )
    assert told.said == [] and "lock" not in vault.calls

    hour.over.set()
    await told.hears()

    assert vault.calls[-1] == "lock"
    assert told.said == [("expired", None, True, None)]
    assert made.forgets_at is None


async def test_at_its_time_with_a_program_that_changed_the_keeper_forgets_and_runs_nothing(
    tmp_path: Path,
) -> None:
    told, hour = Told(), Hour()
    vault = FakeVault([MARIO], state=VAULT_LOCKED)
    made = await door(vault, program(tmp_path), closed=told, wait=hour)
    assert await made.open(Secret(KEY)) is None
    program(tmp_path, b"\xcf\xfa\xed\xfe changed")

    hour.over.set()
    await told.hears()

    assert vault.calls[-1] == "forget" and "lock" not in vault.calls
    assert told.said == [("expired", None, False, "vault.program_changed")]


async def test_a_close_before_the_time_ends_the_wait_and_the_time_closes_nothing_twice(
    tmp_path: Path,
) -> None:
    told, hour = Told(), Hour()
    vault = FakeVault([MARIO], state=VAULT_LOCKED)
    made = await door(vault, program(tmp_path), closed=told, wait=hour)
    assert await made.open(Secret(KEY)) is None
    await turns()

    assert await made.close(TOMMASO) is None
    await turns()
    assert hour.cancelled == 1

    hour.over.set()
    await turns()

    assert told.said == [("command", TOMMASO, True, None)]
    assert vault.calls.count("lock") == 1


async def test_a_second_opening_starts_the_hour_again_and_ends_the_first_wait(
    tmp_path: Path,
) -> None:
    hour, clock = Hour(), FakeClock()
    vault = FakeVault([MARIO], state=VAULT_LOCKED)
    made = await door(vault, program(tmp_path), clock=clock, wait=hour)
    assert await made.open(Secret(KEY)) is None
    await turns()
    first = made.forgets_at
    clock.advance(timedelta(minutes=10))

    assert await made.open(Secret(KEY)) is None
    await turns()

    assert made.forgets_at == first + timedelta(minutes=10)
    assert len(hour.asked) == 2 and hour.cancelled == 1


async def test_a_key_that_did_not_open_starts_no_wait(tmp_path: Path) -> None:
    hour = Hour()
    made = await door(FakeVault([MARIO], state=VAULT_LOCKED), program(tmp_path), wait=hour)

    assert code_of(await made.open(Secret("another key"))) == "vault.key_refused"
    await turns()

    assert hour.asked == [] and made.forgets_at is None


async def test_when_ela_stops_the_key_is_forgotten_and_nothing_is_launched(tmp_path: Path) -> None:
    """«The stop of ELA forgets it»: no ``bw lock`` — a process started while ELA closes is one
    more thing to wait for —, the wait of the hour ended, and the row that says why."""
    told, hour = Told(), Hour()
    vault = FakeVault([MARIO], state=VAULT_LOCKED)
    made = await door(vault, program(tmp_path), closed=told, wait=hour)
    assert await made.open(Secret(KEY)) is None
    await turns()

    await made.stopped()

    assert vault.calls[-1] == "forget" and "lock" not in vault.calls
    assert told.said == [("stopped", None, False, None)]
    assert made.forgets_at is None
    assert hour.cancelled == 1
    assert [task for task in asyncio.all_tasks() if task is not asyncio.current_task()] == []

    await made.stopped()
    assert told.said == [("stopped", None, False, None)], "once"


async def test_a_stop_with_no_key_held_tells_nobody_and_a_vault_nobody_declared_stops_too(
    tmp_path: Path,
) -> None:
    told = Told()
    vault = FakeVault([MARIO])
    made = await door(vault, program(tmp_path), closed=told)
    undeclared = await door(None, None, closed=told)

    await made.stopped()
    await undeclared.stopped()

    assert told.said == [] and "lock" not in vault.calls


async def test_a_stop_while_the_keeper_is_closing_waits_for_it_to_be_over(tmp_path: Path) -> None:
    """The loop is never torn down with a launch of the vault's program in flight: the stop ends
    the keeper's own closing and returns only when it is over."""
    hour = Hour()
    vault = FakeVault([MARIO], state=VAULT_LOCKED)
    made = await door(vault, program(tmp_path), wait=hour)
    assert await made.open(Secret(KEY)) is None
    locking, ended = asyncio.Event(), asyncio.Event()

    async def lock_that_hangs() -> None:
        locking.set()
        try:
            await asyncio.Event().wait()
        finally:
            ended.set()

    vault.lock = lock_that_hangs  # type: ignore[method-assign]
    hour.over.set()
    await locking.wait()

    await made.stopped()

    assert ended.is_set()
    assert [task for task in asyncio.all_tasks() if task is not asyncio.current_task()] == []


async def test_the_key_is_forgotten_before_anybody_is_told(tmp_path: Path) -> None:
    """A closing that cannot be written — a database that is gone — is still a key not held."""
    vault = FakeVault([MARIO], state=VAULT_LOCKED)

    async def cannot_write(closing: Any) -> None:
        raise OSError("the trail cannot be written")

    made = await door(vault, program(tmp_path), closed=cannot_write, wait=Hour())
    assert await made.open(Secret(KEY)) is None

    with pytest.raises(OSError, match="cannot be written"):
        await made.stopped()

    assert vault.calls[-1] == "forget" and made.forgets_at is None


async def test_a_key_ended_elsewhere_is_told_when_ela_learns_it(tmp_path: Path) -> None:
    told, hour = Told(), Hour()
    vault = FakeVault([MARIO], state=VAULT_LOCKED)
    made = await door(vault, program(tmp_path), closed=told, wait=hour)
    assert await made.open(Secret(KEY)) is None
    await turns()
    vault.state = VAULT_LOCKED

    await made.state()
    await turns()

    assert told.said == [("ended_elsewhere", None, False, None)]
    assert hour.cancelled == 1


def test_the_reasons_of_a_closing_are_a_closed_set() -> None:
    from ela.tools import vault as module

    assert set(module.CLOSING_REASONS) == {"command", "expired", "stopped", "ended_elsewhere"}


# ----------------------------------------------------------------------------------------
# The line to paste (decision 32)
# ----------------------------------------------------------------------------------------


async def test_a_locked_vault_says_the_whole_line_to_paste_with_the_declared_program(
    tmp_path: Path,
) -> None:
    at = program(tmp_path)
    made = await door(FakeVault([MARIO], state=VAULT_LOCKED), at)

    state = await made.state()

    assert state.name == "locked"
    assert state.opens_with == f"{at} unlock --raw | ela vault open"
    assert state.opens_with in state.message
    assert made.program == str(at)


async def test_a_program_whose_path_has_a_space_is_quoted_in_the_line(tmp_path: Path) -> None:
    """The line is pasted into a shell: a path that would split into two words is one word."""
    folder = tmp_path / "Application Support"
    folder.mkdir()
    at = program(folder)
    made = await door(FakeVault([MARIO], state=VAULT_LOCKED), at)

    state = await made.state()

    assert state.opens_with == f"'{at}' unlock --raw | ela vault open"
    assert shlex.split(state.opens_with)[0] == str(at)


@pytest.mark.parametrize(
    ("vault_state", "name", "said"),
    [
        (VAULT_UNAUTHENTICATED, "unauthenticated", " login"),
        ("unlocked", "unlocked", ""),
    ],
)
async def test_only_a_locked_vault_has_a_line_to_paste(
    tmp_path: Path, vault_state: str, name: str, said: str
) -> None:
    made = await door(FakeVault([MARIO], state=vault_state), program(tmp_path))

    state = await made.state()

    assert state.name == name and state.opens_with is None
    assert said in state.message and bool(state.message) == bool(said)


async def test_without_a_program_there_is_no_line_and_the_state_says_what_is_missing() -> None:
    made = await door(None, None)

    state = await made.state()

    assert state.name == "undeclared" and state.opens_with is None
    assert "ELA_VAULT_PROGRAM" in state.message
    assert made.program is None
