"""The adapter of the vault: the process of ``bw``, and nothing of a password that leaves it
before a yes (M13.9, ADR 0063; decisions 16, 28 and 64).

What is asserted, on a ``bw`` of the tests (``fake_bw.py``) that prints what the real one prints:

* **the commands the adapter composes are a closed list** — ``status``, ``list items --url``,
  ``get item``, ``lock`` —, and the session key is never among their arguments;
* **what the child receives**: the closed environment, the key in ``BW_SESSION`` and
  ``BW_NOINTERACTION``, a stdin that is the end of a file — and ELA's own environment never
  holds the key;
* **before the yes** the adapter asks the status and the listing for an address, and gives back
  the id, the name, the addresses, **the username masked** and whether there is a password:
  never a value. A sentinel the ``bw`` of the tests prints as the password, as the seed of a
  one-time code, in the notes, in a custom field and in the history of the passwords is in no
  result, in no exception — whatever became of the output — and in no log;
* **after the yes** one launch, ``get item``: the addresses, and the username and the password
  inside a ``Secret``; everything else of the entry is thrown away, the same sentinel with it;
* a ``bw`` that does not answer is killed with its group at the deadline.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import stat
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.browser_leftovers import running

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="a process group is POSIX's")

SOURCE = Path(__file__).with_name("fake_bw.py")
KEY = "the-session-key-of-the-test-7c1d"
SENTINEL = "SENTINEL-of-the-test-0f3a9c"
SITE = "https://posta.example"
ENVIRONMENT = {"PATH": "/usr/bin:/bin", "HOME": "/nowhere", "TMPDIR": "/tmp", "LANG": "C.UTF-8"}  # noqa: S108
ITEM: dict[str, Any] = {
    "id": "11111111-2222-4333-8444-555555555555",
    "name": "La posta",
    "type": 1,
    "notes": f"note con {SENTINEL}",
    "fields": [{"name": "pin", "value": SENTINEL, "type": 1}],
    "passwordHistory": [{"lastUsedDate": "2026-01-01T00:00:00Z", "password": SENTINEL}],
    "login": {
        "uris": [
            {"uri": "https://posta.example/login", "match": None},
            {"uri": "https://mai.example", "match": 5},
        ],
        "username": "mario.rossi@example.com",
        "password": SENTINEL,
        "totp": SENTINEL,
    },
}


class Bw:
    """The ``bw`` of one test: its folder, its state, and what it was called with."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.program = folder / "bw"
        source = SOURCE.read_text(encoding="utf-8")
        self.program.write_text(f"#!{sys.executable}\n{source}", encoding="utf-8")
        self.program.chmod(self.program.stat().st_mode | stat.S_IXUSR)
        self.set(status="unlocked", key=KEY, items=[ITEM])

    def set(self, **state: Any) -> None:
        current = self.state() if (self.folder / "state.json").exists() else {}
        (self.folder / "state.json").write_text(json.dumps(current | state), encoding="utf-8")

    def state(self) -> dict[str, Any]:
        return dict(json.loads((self.folder / "state.json").read_text(encoding="utf-8")))

    def calls(self) -> list[dict[str, Any]]:
        file = self.folder / "calls.jsonl"
        if not file.exists():
            return []
        return [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines()]

    def commands(self) -> list[list[str]]:
        return [call["argv"] for call in self.calls()]


@pytest.fixture
def bw(tmp_path: Path) -> Bw:
    return Bw(tmp_path)


def vault(bw: Bw, **options: Any) -> Any:
    from ela.infrastructure.machine.vault import BitwardenVault

    return BitwardenVault(str(bw.program), environment=ENVIRONMENT, **options)


def secret(value: str) -> Any:
    from ela.ports import Secret

    return Secret(value)


async def opened(bw: Bw, **options: Any) -> Any:
    made = vault(bw, **options)
    assert await made.unlock(secret(KEY)) is True
    return made


def everything_said(error: BaseException) -> str:
    """Whatever an exception carries, and whatever it is chained to: the place a value hides."""
    said, seen = [], set()
    todo: list[BaseException | None] = [error]
    while todo:
        one = todo.pop()
        if one is None or id(one) in seen:
            continue
        seen.add(id(one))
        said.append(f"{one!r} {one} {one.args!r} {vars(one)!r}")
        todo.extend([one.__cause__, one.__context__])
    return "\n".join(said)


# ----------------------------------------------------------------------------------------
# The state, and the key
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["unauthenticated", "locked"])
async def test_the_state_is_what_bw_says_and_the_account_s_address_is_thrown_away(
    bw: Bw, status: str
) -> None:
    bw.set(status=status)

    said = await vault(bw).status()

    assert said == status
    assert bw.commands() == [["status"]]


async def test_a_key_that_opens_the_vault_is_kept_and_one_that_does_not_is_forgotten(
    bw: Bw,
) -> None:
    made = vault(bw)

    assert await made.unlock(secret("a key that opens nothing")) is False
    assert await made.status() == "locked", "asked again, with no key: it was not kept"
    assert await made.unlock(secret(KEY)) is True
    assert await made.status() == "unlocked"

    sessions = [call["environment"].get("BW_SESSION") for call in bw.calls()]
    assert sessions == ["a key that opens nothing", None, KEY, KEY]
    assert bw.commands() == [["status"]] * 4, "the key is asked of bw with status, and no unlock"


async def test_the_key_is_in_the_child_s_environment_and_nowhere_else(bw: Bw) -> None:
    """Never in ``argv`` — ``--session`` is not an argument the adapter composes —, never in
    ELA's own environment, which the browser's driver inherits."""
    made = await opened(bw)
    await made.find(SITE)
    await made.take(ITEM["id"])
    await made.lock()

    for call in bw.calls():
        assert KEY not in " ".join(call["argv"]) and "--session" not in call["argv"]
        assert set(call["environment"]) - {"__CF_USER_TEXT_ENCODING", "__CFBundleIdentifier"} <= {
            *ENVIRONMENT,
            "BW_SESSION",
            "BW_NOINTERACTION",
        }, "the closed environment, and the two of bw"
        assert call["environment"]["BW_NOINTERACTION"] == "true"
        assert call["stdin"] == 0, "its stdin is the end of a file: nothing can be asked on it"
    assert "BW_SESSION" not in os.environ and KEY not in json.dumps(dict(os.environ))


async def test_locking_asks_bw_to_lock_and_forgets_the_key(bw: Bw) -> None:
    made = await opened(bw)

    await made.lock()

    assert bw.commands()[-1] == ["lock"]
    assert bw.state()["status"] == "locked"
    assert await made.status() == "locked"
    assert bw.calls()[-1]["environment"].get("BW_SESSION") is None, "the key was forgotten"


async def test_forgetting_launches_nothing(bw: Bw) -> None:
    """For the day the program changed or went away: the key is dropped, and nothing is run."""
    made = await opened(bw)
    before = len(bw.calls())

    await made.forget()

    assert len(bw.calls()) == before
    assert await made.status() == "locked"
    assert bw.calls()[-1]["environment"].get("BW_SESSION") is None


# ----------------------------------------------------------------------------------------
# Before the yes: no value leaves the adapter (decision 28)
# ----------------------------------------------------------------------------------------


async def test_before_the_yes_the_adapter_asks_the_status_and_the_listing_and_gives_no_value(
    bw: Bw, caplog: pytest.LogCaptureFixture
) -> None:
    from ela.ports import VaultEntry

    made = await opened(bw)
    with caplog.at_level(logging.DEBUG):
        found = await made.find(SITE)

    assert bw.commands()[-2:] == [["status"], ["list", "items", "--url", SITE]]
    assert found == (
        VaultEntry(
            id=ITEM["id"],
            name="La posta",
            addresses=("https://posta.example/login",),
            username="m…@example.com",
            has_password=True,
        ),
    ), "the address bw marks «never» does not count, and the username is masked"
    assert SENTINEL not in repr(found) and "mario.rossi" not in repr(found)
    assert SENTINEL not in caplog.text and "mario.rossi" not in caplog.text


@pytest.mark.parametrize("status", ["unauthenticated", "locked"])
async def test_a_vault_that_is_not_open_is_said_before_any_listing(bw: Bw, status: str) -> None:
    from ela.ports import VaultNotOpen

    bw.set(status=status)
    made = vault(bw)

    with pytest.raises(VaultNotOpen) as caught:
        await made.find(SITE)

    assert caught.value.state == status
    assert bw.commands() == [["status"]], "no listing was asked of a vault that is not open"


@pytest.mark.parametrize("word", ["status", "list"])
async def test_an_output_that_cannot_be_read_gives_an_error_that_carries_none_of_it(
    bw: Bw, word: str, caplog: pytest.LogCaptureFixture
) -> None:
    """The output of ``bw`` holds every password of the listing. An error raised while reading it
    would carry it in its own text, or in the text of what it is chained to."""
    from ela.ports import VaultFailed

    made = await opened(bw)
    bw.set(garbage=[word])

    with caplog.at_level(logging.DEBUG), pytest.raises(VaultFailed) as caught:
        await made.find(SITE)

    assert SENTINEL not in everything_said(caught.value)
    assert SENTINEL not in caplog.text


async def test_a_listing_that_is_not_a_list_of_entries_is_an_error_and_not_a_guess(bw: Bw) -> None:
    from ela.ports import VaultFailed

    made = await opened(bw)
    bw.set(items={"id": "not a list", "password": SENTINEL})

    with pytest.raises(VaultFailed) as caught:
        await made.find(SITE)

    assert SENTINEL not in everything_said(caught.value)


async def test_an_entry_without_a_login_is_no_entry_for_a_site(bw: Bw) -> None:
    note = {"id": "99999999-2222-4333-8444-555555555555", "name": "Una nota", "notes": SENTINEL}
    bw.set(items=[note, ITEM])
    made = await opened(bw)

    found = await made.find(SITE)

    assert [entry.name for entry in found] == ["La posta"]


async def test_a_command_that_fails_is_an_error_that_says_which_and_nothing_else(bw: Bw) -> None:
    from ela.ports import VaultFailed

    made = await opened(bw)
    bw.set(fail=["list"])

    with pytest.raises(VaultFailed, match="list items"):
        await made.find(SITE)


async def test_a_program_that_is_not_there_is_an_error_and_not_a_traceback(tmp_path: Path) -> None:
    from ela.infrastructure.machine.vault import BitwardenVault
    from ela.ports import VaultFailed

    made = BitwardenVault(str(tmp_path / "no-bw-here"), environment=ENVIRONMENT)

    with pytest.raises(VaultFailed, match="could not be started"):
        await made.status()


# ----------------------------------------------------------------------------------------
# After the yes: one launch, and only what is named (decision 64)
# ----------------------------------------------------------------------------------------


async def test_after_the_yes_the_entry_is_read_once_and_only_what_is_named_comes_out(
    bw: Bw, caplog: pytest.LogCaptureFixture
) -> None:
    from ela.ports import Secret, VaultTaken

    made = await opened(bw)
    before = len(bw.calls())
    with caplog.at_level(logging.DEBUG):
        taken = await made.take(ITEM["id"])

    assert bw.commands()[before:] == [["get", "item", ITEM["id"]]], "one launch, and no status"
    assert isinstance(taken, VaultTaken)
    assert taken.addresses == ("https://posta.example/login",)
    assert isinstance(taken.username, Secret) and isinstance(taken.password, Secret)
    assert taken.username.reveal() == "mario.rossi@example.com"
    assert taken.password.reveal() == SENTINEL, "the control: the password is the sentinel"
    assert SENTINEL not in repr(taken) and SENTINEL not in caplog.text
    assert {field.name for field in __import__("dataclasses").fields(taken)} == {
        "addresses",
        "username",
        "password",
    }, "the seed of a one-time code, the notes, the fields, the history: none has a place here"


async def test_an_entry_that_is_not_there_any_more_is_said_and_the_vault_is_asked_why(
    bw: Bw,
) -> None:
    from ela.ports import VaultFailed

    made = await opened(bw)

    with pytest.raises(VaultFailed, match="get item"):
        await made.take("00000000-0000-4000-8000-000000000000")

    assert bw.commands()[-1] == ["status"], "asked only when the reading failed"


async def test_a_vault_locked_between_the_question_and_the_yes_is_said_locked(bw: Bw) -> None:
    from ela.ports import VaultNotOpen

    made = await opened(bw)
    bw.set(status="locked")

    with pytest.raises(VaultNotOpen) as caught:
        await made.take(ITEM["id"])

    assert caught.value.state == "locked"


async def test_an_entry_read_after_the_yes_that_cannot_be_read_carries_none_of_it(bw: Bw) -> None:
    from ela.ports import VaultFailed

    made = await opened(bw)
    bw.set(garbage=["get"])

    with pytest.raises(VaultFailed) as caught:
        await made.take(ITEM["id"])

    assert SENTINEL not in everything_said(caught.value)


async def test_an_entry_without_a_password_gives_none_and_says_so(bw: Bw) -> None:
    from ela.ports import VaultFailed

    bare = json.loads(json.dumps(ITEM))
    bare["login"]["password"] = None
    bw.set(items=[bare])
    made = await opened(bw)

    (found,) = await made.find(SITE)
    assert found.has_password is False

    with pytest.raises(VaultFailed, match="no password"):
        await made.take(ITEM["id"])


# ----------------------------------------------------------------------------------------
# A bw that does not answer
# ----------------------------------------------------------------------------------------


async def test_a_bw_that_does_not_answer_is_killed_with_its_group_at_the_deadline(bw: Bw) -> None:
    """One launch, which never answers: the deadline is the only thing that ends it — and it is
    short for this launch alone, so that no other launch of the test can run out of time on a
    machine that is busy."""
    from ela.ports import VaultTimeout

    bw.set(hang=["status"])
    made = vault(bw, timeout_seconds=2.0)

    with pytest.raises(VaultTimeout, match="bw status did not answer within 2 s"):
        await made.status()

    (hung,) = bw.calls()
    assert hung["group"] == hung["pid"], "in a group of its own"
    deadline = asyncio.get_running_loop().time() + 10
    while running(hung["pid"]) and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.02)
    assert not running(hung["pid"]), "and not left behind"


async def test_a_wait_that_is_cancelled_does_not_leave_bw_running(bw: Bw) -> None:
    made = await opened(bw)
    bw.set(hang=["list"])
    finding = asyncio.create_task(made.find(SITE))
    while len(bw.calls()) < 3:  # the unlock's status, find's status, and the listing that hangs
        await asyncio.sleep(0.02)

    finding.cancel()
    with pytest.raises(asyncio.CancelledError):
        await finding

    hung = bw.calls()[-1]
    deadline = asyncio.get_running_loop().time() + 10
    while running(hung["pid"]) and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.02)
    assert not running(hung["pid"])


# ----------------------------------------------------------------------------------------
# The closed list, and the mask
# ----------------------------------------------------------------------------------------


def test_the_commands_the_adapter_composes_are_a_closed_list() -> None:
    """Decision 64: ``get item`` in place of ``get username`` and ``get password``. Never
    ``unlock``, ``login``, ``export``, ``get totp``, ``get uri``, ``serve``, ``sync``."""
    from ela.infrastructure.machine import vault

    assert vault.COMMANDS == (
        ("status",),
        ("list", "items", "--url"),
        ("get", "item"),
        ("lock",),
    )


async def test_everything_the_adapter_launched_in_these_tests_is_on_the_closed_list(
    bw: Bw,
) -> None:
    from ela.infrastructure.machine import vault

    made = await opened(bw)
    await made.find(SITE)
    await made.take(ITEM["id"])
    await made.lock()

    for argv in bw.commands():
        assert any(tuple(argv[: len(command)]) == command for command in vault.COMMANDS), argv
        assert len(argv) <= 4


@pytest.mark.parametrize(
    ("username", "shown"),
    [
        ("mario.rossi@example.com", "m…@example.com"),
        ("mario", "m…"),
        ("m", "…"),
        ("m@example.com", "…@example.com"),
        ("", ""),
        ("@example.com", "…@example.com"),
        ("a@b@c.example", "a…@c.example"),
    ],
)
def test_a_username_is_shown_by_its_first_character_and_what_follows_the_at(
    username: str, shown: str
) -> None:
    """Decision 31: the first character, and for an address the part from the at sign. A name of
    one character does not show even that."""
    from ela.infrastructure.machine.vault import masked

    assert masked(username) == shown


@pytest.fixture(autouse=True)
def _no_key_in_this_process() -> Iterator[None]:
    assert "BW_SESSION" not in os.environ
    yield
    assert "BW_SESSION" not in os.environ
