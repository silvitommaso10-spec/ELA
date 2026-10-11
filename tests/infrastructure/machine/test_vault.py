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
import signal
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

    def grandchild(self) -> int | None:
        """The pid of the child a ``bw`` that hangs started for itself, once it has said it."""
        file = self.folder / "grandchild"
        said = file.read_text(encoding="utf-8") if file.exists() else ""
        return int(said) if said else None


@pytest.fixture
def bw(tmp_path: Path) -> Iterator[Bw]:
    """The ``bw`` of one test — and, when the test is over, nothing of what it started: a test
    that fails leaves no process either (decision 71)."""
    made = Bw(tmp_path)
    try:
        yield made
    finally:
        for pid in (made.grandchild(), *(call["pid"] for call in made.calls())):
            if pid is not None and running(pid):
                os.kill(pid, signal.SIGKILL)


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
    assert "BW_SESSION" not in os.environ and KEY not in json.dumps(dict(os.environ))


@pytest.fixture
def something_typed() -> Iterator[bytes]:
    """The stdin of this process holding a line somebody typed, for one test — under pytest it is
    already the end of a file, and a child that inherited it would read nothing all the same."""
    typed = b"a line somebody typed\n"
    read, write = os.pipe()
    os.write(write, typed)
    os.close(write)
    kept = os.dup(0)
    os.dup2(read, 0)
    os.close(read)
    try:
        yield typed
    finally:
        os.dup2(kept, 0)
        os.close(kept)


async def test_the_child_s_stdin_is_the_end_of_a_file_whatever_ela_s_own_is(
    bw: Bw, something_typed: bytes
) -> None:
    """ADR 0063 §2: nothing can be asked on it, and nothing ELA was handed on its own stdin — the
    key, by ``ela vault open`` — is there for ``bw`` to read."""
    made = await opened(bw)
    await made.find(SITE)
    await made.take(ITEM["id"])
    await made.lock()

    assert [call["stdin"] for call in bw.calls()] == [0] * len(bw.calls())
    assert os.read(0, 64) == something_typed, "the control: there was a line, and nobody read it"


async def test_what_bw_writes_on_its_stderr_goes_nowhere(
    bw: Bw, capfd: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    """ADR 0063 §2: an error of ``bw`` can name the entry it could not read, or the account. It
    does not reach ELA's own stderr, which is its log."""
    made = await opened(bw)
    bw.set(mutter=f"error: {SENTINEL} of the-account@example.invalid")
    with caplog.at_level(logging.DEBUG):
        await made.find(SITE)
        await made.take(ITEM["id"])
        await made.lock()

    written = capfd.readouterr()
    assert SENTINEL not in written.err and SENTINEL not in written.out
    assert SENTINEL not in caplog.text


async def test_locking_asks_bw_to_lock_and_forgets_the_key(bw: Bw) -> None:
    made = await opened(bw)

    await made.lock()

    assert bw.commands()[-1] == ["lock"]
    assert bw.state()["status"] == "locked"
    assert await made.status() == "locked"
    assert bw.calls()[-1]["environment"].get("BW_SESSION") is None, "the key was forgotten"


async def test_a_lock_bw_refused_is_said_and_the_key_is_forgotten_all_the_same(bw: Bw) -> None:
    """A vault that stayed open is not written down as locked: the adapter says the lock failed."""
    from ela.ports import VaultFailed

    made = await opened(bw)
    bw.set(fail=["lock"])

    with pytest.raises(VaultFailed, match="^bw lock failed$"):
        await made.lock()

    assert bw.state()["status"] == "unlocked", "the control: bw did not lock"
    bw.set(fail=[])
    assert await made.status() == "locked"
    assert bw.calls()[-1]["environment"].get("BW_SESSION") is None, "the key was forgotten"


async def test_a_status_bw_could_not_give_is_not_believed(bw: Bw) -> None:
    from ela.ports import VaultFailed

    bw.set(fail=["status"])

    with pytest.raises(VaultFailed, match="^bw status failed$"):
        await vault(bw).status()


@pytest.mark.parametrize(
    "said",
    ['{"status": "half-open"}', '{"status": ["unlocked"]}', '{"status": {"is": "unlocked"}}', "[]"],
    ids=["a-word-nobody-knows", "a-list", "an-object", "not-an-object"],
)
async def test_a_status_that_is_not_one_of_the_three_words_is_an_error_of_the_vault(
    bw: Bw, said: str
) -> None:
    """Whatever ``bw`` printed in the place of the word — a list is not hashable, and looking it
    up among the three words is a ``TypeError`` —: the adapter's own error, and no state."""
    from ela.ports import VaultFailed

    bw.set(raw={"status": said})

    with pytest.raises(VaultFailed, match="did not say whether the vault is open"):
        await vault(bw).status()


async def test_a_key_no_environment_can_carry_is_an_error_of_the_vault_and_is_not_said(
    bw: Bw,
) -> None:
    """A NUL cannot be in the environment of a process: the launch is refused by Python with a
    ``ValueError``, before ``bw`` exists. The adapter's own error, with nothing of the key."""
    from ela.ports import VaultFailed

    made = vault(bw)
    key = "a-key-with-a-nul-\x00-and-the-SENTINEL-in-it"

    with pytest.raises(VaultFailed, match="could not be started") as caught:
        await made.unlock(secret(key))

    assert "SENTINEL" not in everything_said(caught.value)
    assert bw.calls() == [], "nothing was launched"
    assert await made.status() == "locked", "and the key was not kept"


async def test_an_address_no_argument_can_carry_is_an_error_of_the_vault(bw: Bw) -> None:
    from ela.ports import VaultFailed

    made = await opened(bw)

    with pytest.raises(VaultFailed, match="could not be started"):
        await made.find("https://posta.example/\x00")


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


@pytest.mark.parametrize(
    "items",
    [{"id": "not a list", "password": SENTINEL}, [ITEM, f"a line with {SENTINEL}"], [ITEM, [ITEM]]],
    ids=["an-object", "a-text-among-the-entries", "a-list-among-the-entries"],
)
async def test_a_listing_that_is_not_a_list_of_entries_is_an_error_and_not_a_guess(
    bw: Bw, items: Any
) -> None:
    from ela.ports import VaultFailed

    made = await opened(bw)
    bw.set(items=items)

    with pytest.raises(VaultFailed, match="did not print a list of entries") as caught:
        await made.find(SITE)

    assert SENTINEL not in everything_said(caught.value)


async def test_an_entry_whose_id_is_not_a_text_is_no_entry_to_ask_for(bw: Bw) -> None:
    """The id is what ``get item`` is launched with after the yes: one that is not a text is not
    one ELA can name, and is left out and not guessed."""
    numbered = json.loads(json.dumps(ITEM)) | {"id": 7, "name": "Senza un id"}
    bw.set(items=[numbered, ITEM])
    made = await opened(bw)

    found = await made.find(SITE)

    assert [entry.name for entry in found] == ["La posta"]


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

    with pytest.raises(VaultFailed, match="^bw list items failed$"):
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


@pytest.mark.parametrize("password", [None, "", 7], ids=["none", "empty", "not-a-text"])
async def test_an_entry_without_a_password_gives_none_and_says_so(bw: Bw, password: Any) -> None:
    from ela.ports import VaultFailed

    bare = json.loads(json.dumps(ITEM))
    bare["login"]["password"] = password
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


async def test_a_group_that_has_ended_and_is_not_collected_yet_is_a_group_with_nothing_to_kill(
    bw: Bw, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The time of a ``bw`` runs out the moment it ends, before the loop has collected it. Asked
    to kill such a group, macOS answers «not permitted» — measured on 2026-10-11, where Linux
    answers nothing. **The test gives that answer on every system**, once the group has been
    ended for real: what leaves is the adapter's own «did not answer», and not the system's
    error."""
    from ela.ports import VaultTimeout

    bw.set(hang=["status"])
    made = vault(bw, timeout_seconds=2.0)
    killpg = os.killpg

    def not_permitted(group: int, sent: int) -> None:
        killpg(group, sent)
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "killpg", not_permitted)

    with pytest.raises(VaultTimeout):
        await made.status()

    (hung,) = bw.calls()
    deadline = asyncio.get_running_loop().time() + 10
    while running(hung["pid"]) and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.02)
    assert not running(hung["pid"])


async def test_a_wait_that_is_cancelled_does_not_leave_bw_running_nor_what_it_started(
    bw: Bw,
) -> None:
    """«Killed with its group»: the ``bw`` of the tests that hangs has started a child of its own
    by then, and the child goes with it — a kill of the one process would leave it."""
    made = await opened(bw)
    bw.set(hang=["list"])
    finding = asyncio.create_task(made.find(SITE))
    while bw.grandchild() is None:  # the listing hangs once its own child is started
        await asyncio.sleep(0.02)

    finding.cancel()
    with pytest.raises(asyncio.CancelledError):
        await finding

    hung, child = bw.calls()[-1]["pid"], bw.grandchild()
    assert child is not None
    deadline = asyncio.get_running_loop().time() + 10
    while (running(hung) or running(child)) and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.02)
    assert not running(hung)
    assert not running(child), "the child bw started is in its group, and went with it"


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
        ("@example.com", "@…"),
        ("@mario_rossi", "@…"),
        ("@", "…"),
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
