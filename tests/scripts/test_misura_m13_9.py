"""``scripts/misura_m13_9.py`` before Tommaso runs it: what it writes, what it hands a child, what
it leaves (SPEC of M13.9, decision 4).

The measure runs once, on Tommaso's Mac, with his account of Bitwarden and his account of Google,
and its file goes into a chat. So what it decides on the way is tested here first, each with its
negative: **no line of the file carries a value it keeps to itself or an address**; the session key
reaches ``bw`` in the environment and never in ``argv``, and ``bw`` is launched only with the words
of a closed list; the test entry goes round and is deleted; what the world did not give is SALTATO
and not FALLITO; and at the end — also after an interrupt, also after an error — the vault is
closed, the account left and every folder gone, **each asked of bw and not remembered**.

``bw`` here is ``tests/scripts/fake_bw.py``, held to what the real CLI was recorded answering
without an account (``tests/scripts/data/bw-2026.9.1/``); the browser is a class of this file that
launches nothing. The dry run on the real Chrome for Testing of the lock opens windows and lets the
browser talk to Google, so it runs only when asked for: its ``skipif`` says how.
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parents[1] / "scripts" / "misura_m13_9.py"
RECORDED = HERE / "data" / "bw-2026.9.1"
ADDRESS_OF_THE_FAKE = "finto@example.invalid"
KEY_OF_THE_FAKE = "chiave-finta-di-sessione"
NEVER_IN_THE_FILE = (
    KEY_OF_THE_FAKE,
    ADDRESS_OF_THE_FAKE,
    "parola-inventata",
    "utente-inventato",
    "voce-di-prova",
    "inventato-a-secco",
    "@",
)
"""What no file of the measure may hold: the keys and the address the fake prints, the invented
value, user and name of the test entry, the cookie of the local pages, any address at all."""


@cache
def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("misura_m13_9_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def recorded(name: str) -> str:
    return (RECORDED / f"{name}.txt").read_text(encoding="utf-8")


@pytest.fixture
def bw(tmp_path: Path) -> Path:
    """The fake ``bw``, in a folder of the test's: run by this interpreter, whatever the PATH."""
    folder = tmp_path / "bw-finto"
    folder.mkdir()
    made = folder / "bw"
    body = (HERE / "fake_bw.py").read_text(encoding="utf-8").split("\n", 1)[1]
    made.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
    made.chmod(0o755)
    return made


def calls(bw: Path) -> list[dict[str, Any]]:
    log = bw.with_name("fake-bw-calls.jsonl")
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def commands(bw: Path) -> list[str]:
    return [call["argv"][0] for call in calls(bw)]


def turn_down(bw: Path, **what: str) -> None:
    bw.with_name("fake-bw.json").write_text(json.dumps(what), encoding="utf-8")


class Tommaso:
    """Tommaso, for a test: a region, and his yes and no in the order the measure asks them — a
    ``Callable`` among them is called instead, to interrupt. Every question is kept."""

    def __init__(self, *answers: Any, region: str = "com") -> None:
        self.region = region
        self._answers = iter(answers)
        self.asked: list[str] = []

    def __call__(self, question: str) -> str:
        self.asked.append(question)
        if "(com/eu)" in question:
            return self.region
        if "Premi Invio" in question:
            return ""
        answer = next(self._answers, "n")
        return str(answer() if callable(answer) else answer)


class NoBrowser:
    """A browser that launches nothing and remembers: the port ``Browsers`` of the script."""

    def __init__(
        self,
        work: Path,
        *,
        installed: bool = True,
        lets_in: frozenset[str] = frozenset({"cft", "chrome"}),
        sees: frozenset[bool] = frozenset({True, False}),
        logout_works: bool = True,
        breaks: str = "",
        offered: int = 0,
    ) -> None:
        self.offered = offered
        self.folder = work / "profili"
        self.folder.mkdir()
        self.installed = installed
        self.lets_in = lets_in
        self.sees = sees
        self.logout_works = logout_works
        self.breaks = breaks
        self.inside: set[Path] = set()
        self.windows: list[tuple[str, str, bool]] = []
        self.visits: list[tuple[str, bool, bool]] = []
        self.removed: list[Path] = []
        self.profiles: list[tuple[str, bool]] = []
        self.busy = False

    def binary(self, kind: str) -> Path | None:
        return Path("/a/browser/of/the/test") if self.installed else None

    def profile(self, name: str, *, preferences: bool) -> Path:
        self.profiles.append((name, preferences))
        made = self.folder / name
        made.mkdir()
        return made

    def occupied(self, profile: Path) -> bool:
        return self.busy

    def guided_window(
        self, kind: str, profile: Path, address: str, person: Callable[[], None]
    ) -> Any:
        self.windows.append(("guided", kind, False))
        person()
        if self.breaks == "guided":
            raise RuntimeError("https://accounts.google.com/?Email=qualcuno@example.org closed")
        return script().Seen(ended_on=address + "?hl=it&continue=segreto", cookie=False)

    def plain_window(
        self, kind: str, profile: Path, address: str, person: Callable[[], None], *, bare: bool
    ) -> Any:
        self.windows.append(("plain", kind, bare))
        person()
        if kind in self.lets_in:
            self.inside.add(profile)
        return script().Seen(ended_on="", cookie=False, exit=0)

    def visit(
        self, kind: str, profile: Path, address: str, *, window: bool, gated: bool = False
    ) -> Any:
        self.visits.append((address.rsplit("/", 1)[-1] or "account", window, gated))
        if self.breaks == "visit":
            raise TimeoutError(
                "page.goto: https://myaccount.google.com/?authuser=qualcuno@example.org"
            )
        if "ogout" in address and self.logout_works:
            self.inside.discard(profile)
        inside = profile in self.inside and window in self.sees
        where = address if inside or "ogout" in address else "https://accounts.google.com/signin"
        return script().Seen(ended_on=where, cookie=inside)

    def linked(self, profile: Path) -> dict[str, object] | None:
        return dict(script().linked_from({"signin": {"allowed": False}}))

    def saved(self, profile: Path) -> dict[str, int | None]:
        return {"logins": 0, "stats": self.offered, "autofill": 0}

    def remove(self, profile: Path) -> bool:
        self.removed.append(profile)
        shutil.rmtree(profile)
        return not profile.exists()


def run(
    tmp_path: Path, *arguments: str, ask: Callable[[str], str] | None = None, **browser: Any
) -> tuple[int, str, list[NoBrowser]]:
    out = tmp_path / "misura.txt"
    made: list[NoBrowser] = []

    def browsers(work: Path, reached: Callable[[], bool]) -> NoBrowser:
        made.append(NoBrowser(work, **browser))
        return made[0]

    code = script().main([*arguments, "--out", str(out)], ask=ask or Tommaso(), browsers=browsers)
    return code, out.read_text(encoding="utf-8"), made


def clean(text: str) -> None:
    for kept in NEVER_IN_THE_FILE:
        assert kept not in text, kept
    assert str(Path.home()) not in text


# ----------------------------------------------------------------------------------------
# The file: every line through the filter
# ----------------------------------------------------------------------------------------


def report(tmp_path: Path) -> Any:
    return script().Report(tmp_path / "file.txt", echo=lambda line: None)


def test_a_line_that_carries_a_registered_value_is_not_written_and_one_that_does_not_is(
    tmp_path: Path,
) -> None:
    made = report(tmp_path)
    made.secret("un-valore-che-resta-qui")
    made.say("la chiave è un-valore-che-resta-qui, tutta")
    made.say("la chiave ha 23 caratteri")
    made.close()
    text = made.path.read_text(encoding="utf-8")

    assert "un-valore-che-resta-qui" not in text
    assert "una riga trattenuta" in text and "la chiave ha 23 caratteri" in text
    assert made.withheld_lines == 1


def test_an_output_of_several_lines_does_not_get_through_one_line_at_a_time(tmp_path: Path) -> None:
    """A ``bw`` that ignored ``--raw`` would print a message around the key: registered whole, one
    of its lines alone would pass — so each of its long words is registered too."""
    made = report(tmp_path)
    made.secret(
        'You are logged in!\n\n$ export BW_SESSION="una-chiave-lunga-abbastanza-da-contare"'
    )
    made.say('$ export BW_SESSION="una-chiave-lunga-abbastanza-da-contare"')
    made.say("You are logged in!")
    made.close()
    text = made.path.read_text(encoding="utf-8")

    assert "una-chiave-lunga" not in text
    assert "You are logged in!" in text, "a short word of the message is not a secret"


@pytest.mark.parametrize("address", ["qualcuno@example.org", "qualcuno%40example.org"])
def test_a_line_with_an_address_is_not_written_and_a_host_alone_is(
    tmp_path: Path, address: str
) -> None:
    made = report(tmp_path)
    made.say(f"l'account è {address}")
    made.say("il server di bw: vault.bitwarden.eu")
    made.close()
    text = made.path.read_text(encoding="utf-8")

    assert "example.org" not in text
    assert "vault.bitwarden.eu" in text


def test_a_value_too_short_to_be_a_secret_does_not_swallow_the_file(tmp_path: Path) -> None:
    made = report(tmp_path)
    made.secret("s")
    made.say("PASSATO: sì")
    made.close()

    assert "PASSATO: sì" in made.path.read_text(encoding="utf-8")


def test_the_file_read_back_says_what_it_holds_and_nothing_when_it_holds_nothing(
    tmp_path: Path,
) -> None:
    """The last check of the measure reads the disk, not its own memory: a value that reached the
    file by another road — the negative case, built here — is found."""
    made = report(tmp_path)
    made.secret("un-valore-che-resta-qui")
    made.say("una riga qualunque")
    assert made.found_in_the_file() == []

    with made.path.open("a", encoding="utf-8") as beside:
        beside.write("un-valore-che-resta-qui\nqualcuno@example.org\n")

    assert made.found_in_the_file() == ["un valore che la misura tiene per sé", "un indirizzo"]
    made.close()


def test_an_address_is_shown_as_its_host_and_path_and_nothing_else() -> None:
    shown = script().shown

    assert shown("https://accounts.google.com/v3/signin?Email=x&continue=y") == (
        "accounts.google.com/v3/signin"
    )
    before_the_host = "qualcuno" + ":" + "una-parola" + "@"
    assert shown(f"https://{before_the_host}accounts.google.com/") == "accounts.google.com/"
    assert shown("http://127.0.0.1:8080/account") == "127.0.0.1:8080/account"


def test_the_place_of_the_file_is_said_without_the_home() -> None:
    at = script().at

    assert at(Path.home() / "Downloads" / "misura.txt") == "~/Downloads/misura.txt"
    assert at(Path("/tmp/misura.txt")) == "/tmp/misura.txt"
    assert at(Path(str(Path.home()) + "2") / "misura.txt") == str(
        Path(str(Path.home()) + "2") / "misura.txt"
    )


# ----------------------------------------------------------------------------------------
# bw: what a child receives
# ----------------------------------------------------------------------------------------


def test_the_key_reaches_bw_in_its_environment_and_never_in_argv(bw: Path, tmp_path: Path) -> None:
    made = script().Bw(bw, tmp_path / "dati")
    made.run("status", session="una-chiave-di-sessione-di-prova")
    (call,) = calls(bw)

    assert call["session_in_the_environment"] is True
    assert "una-chiave-di-sessione-di-prova" not in " ".join(call["argv"])
    with pytest.raises(ValueError, match="never goes in argv"):
        made.run("status", "--session", "una-chiave-di-sessione-di-prova")
    with pytest.raises(ValueError, match="never goes in argv"):
        made.run(
            "get",
            "item",
            "una-chiave-di-sessione-di-prova",
            session="una-chiave-di-sessione-di-prova",
        )
    assert len(calls(bw)) == 1


@pytest.mark.parametrize(
    "arguments",
    [
        ("export",),
        ("serve",),
        ("import", "chromecsv", "file.csv"),
        ("--raw", "export"),
        ("get", "totp", "una-voce"),
        ("get", "notes", "una-voce"),
        ("unlock", "la-password-principale"),
        ("unlock", "--passwordenv", "NOME"),
        ("login", "qualcuno", "la-password-principale"),
        ("login", "--apikey"),
        ("status", "--pretty"),
        ("list", "folders"),
        ("delete", "item", "una-voce", "un'altra"),
        ("create", "item", "eyJ0eXBlIjoxfQ"),
    ],
)
def test_bw_is_launched_only_with_the_words_of_the_closed_list(
    bw: Path, tmp_path: Path, arguments: tuple[str, ...]
) -> None:
    """Word by word, not only the first: nothing that would take the master password as an
    argument, a code, an export, or the entry's JSON in ``argv``."""
    assert script().refused(arguments) is not None
    with pytest.raises(ValueError, match="bw "):
        script().Bw(bw, tmp_path / "dati").run(*arguments)

    assert calls(bw) == []


@pytest.mark.parametrize(
    "arguments",
    [
        ("--version",),
        ("status",),
        ("config", "server"),
        ("config", "server", "https://vault.bitwarden.eu"),
        ("login", "--raw"),
        ("unlock", "--raw"),
        ("lock",),
        ("logout",),
        ("create", "item"),
        ("list", "items", "--url", "http://127.0.0.1:1/login"),
        ("list", "items", "--search", "un nome"),
        ("get", "password", "una-voce"),
        ("delete", "item", "una-voce", "--permanent"),
    ],
)
def test_every_launch_the_measure_composes_is_in_the_closed_list(
    arguments: tuple[str, ...],
) -> None:
    assert script().refused(arguments) is None


def test_every_word_of_the_closed_list_is_in_the_help_of_the_real_cli() -> None:
    """Held against the help of ``bw`` 2026.9.1, recorded without an account: a command or a word
    the real CLI does not have would be found by Tommaso, at his terminal, with his account."""
    everything = recorded("help")
    for command, words in script().BW_COMMANDS.items():
        its_help = recorded(f"{command}-help")
        assert f"\n  {command}" in everything, command
        for word in (*words.objects, *words.options):
            assert word in its_help or word in everything.split("Commands:")[0], (command, word)

    assert "--raw" in everything.split("Commands:")[0]
    assert "piped into stdin" in recorded("create-help")
    assert "--permanent" in recorded("delete-help")


def test_an_interactive_bw_keeps_the_terminal_and_writes_its_answer_on_a_pipe(
    bw: Path, tmp_path: Path
) -> None:
    """**The script never receives a password**: an interactive ``bw`` reads the standard input the
    script itself was given — Tommaso's terminal —, not a pipe of the script's; and only its stdout
    comes back. A ``bw`` that asks nothing reads the null device."""
    made = script().Bw(bw, tmp_path / "dati")
    made.run("login", "--raw", interactive=True)
    made.run("status")
    with_tommaso, quiet = calls(bw)
    ours = os.fstat(0)

    assert with_tommaso["stdin"] == [ours.st_dev, ours.st_ino]
    assert with_tommaso["stdout_is_a_pipe"] is True
    assert quiet["stdin_is_the_null_device"] is True and quiet["stdout_is_a_pipe"] is True


@pytest.mark.skipif(os.name == "nt", reason="a pseudo-terminal and its echo are POSIX's")
def test_the_terminal_does_not_echo_while_bw_starts_and_is_given_back_as_it_was(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What Tommaso types before ``bw`` has shown its prompt is not written on the screen: the
    echo is off for the launch, and back after it — also when the launch raises."""
    import pty
    import termios

    master, slave = pty.openpty()
    try:
        with os.fdopen(slave, "r", closefd=False) as terminal:
            monkeypatch.setattr(sys, "stdin", terminal)
            assert termios.tcgetattr(slave)[3] & termios.ECHO
            with pytest.raises(RuntimeError), script().quiet_terminal():
                assert not termios.tcgetattr(slave)[3] & termios.ECHO
                raise RuntimeError
            assert termios.tcgetattr(slave)[3] & termios.ECHO
    finally:
        os.close(master)
        os.close(slave)


def test_where_there_is_no_terminal_there_is_nothing_to_quieten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The defect the dry run of 2026-10-10 found: a standard input that is the null device made
    the launch of ``bw`` raise. It is a launch like any other."""
    with open(os.devnull) as nothing:
        monkeypatch.setattr(sys, "stdin", nothing)
        with script().quiet_terminal():
            pass


def test_bw_gets_a_closed_environment_and_is_told_not_to_ask_unless_tommaso_is_there(
    bw: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ELA_API_TOKEN", "x" * 40)
    monkeypatch.setenv("BW_SESSION", "una-chiave-rimasta-nella-shell")
    made = script().Bw(bw, tmp_path / "dati")
    made.run("status")
    made.run("login", "--raw", interactive=True)
    quiet, with_tommaso = calls(bw)

    assert not any(name.startswith("ELA_") for name in quiet["environment_names"])
    assert quiet["session_in_the_environment"] is False, "a key left in the shell is not handed on"
    assert quiet["no_interaction"] == "true"
    assert with_tommaso["no_interaction"] is None
    assert "TERM" in with_tommaso["environment_names"] and "TERM" not in quiet["environment_names"]


def test_the_status_keeps_the_state_and_drops_the_address_of_the_account(
    bw: Path, tmp_path: Path
) -> None:
    made = script().Bw(bw, tmp_path / "dati")
    key = made.run("login", "--raw", interactive=True).out

    assert ADDRESS_OF_THE_FAKE in made.run("status", session=key).out, (
        "the fake prints it, as bw does"
    )
    assert made.status(key) == "unlocked"
    assert made.status() == "locked"


def test_what_bw_says_when_it_fails_reaches_the_file_as_a_code_never_as_its_words() -> None:
    ran = script().Ran

    assert ran(1, "", "Vault is locked.", 5).said == "uscita 1, vault chiuso"
    assert (
        ran(1, "", "qualcuno@example.org is not allowed", 5).said == "uscita 1, altro, 35 caratteri"
    )
    assert ran(0, "", "", 5).said == "uscita 0"


def test_the_fake_answers_without_an_account_what_the_real_cli_was_recorded_answering(
    bw: Path, tmp_path: Path
) -> None:
    made = script().Bw(bw, tmp_path / "dati")

    assert made.run("status").out == recorded("status-no-account")
    assert made.run("--version").out == recorded("version").strip()
    for name, arguments in (
        ("list-items-no-account", ("list", "items")),
        ("get-password-no-account", ("get", "password", "niente")),
        ("lock-no-account", ("lock",)),
    ):
        ran = made.run(*arguments)
        assert f"exit {ran.code}\n{ran.err}" == recorded(name), name


def test_a_bw_that_is_named_is_that_one_or_none_and_a_dry_run_never_looks_for_one(
    tmp_path: Path, bw: Path
) -> None:
    """A dry run that named a fake which cannot be launched must not fall back to the real ``bw``
    and log in with it."""
    find = script().find_bw
    not_executable = tmp_path / "bw-senza-permesso"
    not_executable.write_text("#!/bin/sh\n", encoding="utf-8")

    assert find(bw, search=True) == bw
    assert find(not_executable, search=True) is None
    assert find(tmp_path / "non-c-è", search=True) is None
    assert find(None, search=False) is None


# ----------------------------------------------------------------------------------------
# The whole measure, dry
# ----------------------------------------------------------------------------------------


def test_the_dry_run_goes_through_and_its_file_holds_no_value_and_no_address(
    bw: Path, tmp_path: Path
) -> None:
    code, text, (browser,) = run(tmp_path, "--a-secco", "--bw", str(bw))

    assert code == 0, text
    assert "0 FALLITO" in text and "0 RIAPRE" in text and "INTERROTTA" not in text
    assert "la voce ha fatto il giro, è cancellata, e il suo valore non è nel file" in text
    assert "V1: bw get item porta login.password: sì" in text
    assert "K2: con la chiave nuova: unlocked; con quella di prima: locked" in text
    assert "il vault è chiuso, l'account è lasciato" in text
    assert "la misura non lascia niente sul disco, e il file si può mandare" in text
    clean(text)
    assert "segreto" not in text, "the query of an address is not written"


def test_the_dry_run_hands_no_key_and_no_invented_value_to_argv(bw: Path, tmp_path: Path) -> None:
    run(tmp_path, "--a-secco", "--bw", str(bw))
    made = calls(bw)
    every_argument = " ".join(word for call in made for word in call["argv"])
    (created,) = [call for call in made if call["argv"][:2] == ["create", "item"]]

    assert KEY_OF_THE_FAKE not in every_argument and "--session" not in every_argument
    assert "parola-inventata" not in every_argument
    assert created["argv"] == ["create", "item"] and created["stdin_bytes"] > 0
    assert any(call["session_in_the_environment"] for call in made)


def test_at_the_end_the_vault_is_locked_the_account_left_and_every_folder_gone(
    bw: Path, tmp_path: Path
) -> None:
    code, text, (browser,) = run(tmp_path, "--a-secco", "--bw", str(bw))
    order = commands(bw)

    assert code == 0
    assert order.index("logout") > max(i for i, name in enumerate(order) if name == "lock")
    assert order[-1] == "status", "the last word asked of bw is whether the account is left"
    assert "alla fine bw dice: unauthenticated" in text
    assert browser.removed and not any(folder.exists() for folder in browser.removed)
    assert not browser.folder.parent.exists(), "the temporary folder of the measure is gone"


def test_a_logout_that_does_not_happen_is_a_failure_and_the_file_says_what_to_do(
    bw: Path, tmp_path: Path
) -> None:
    """The negative of the closing: it is verified by asking ``bw``, so a logout the server did
    not take is not written as done."""
    turn_down(bw, logout="refuse")
    code, text, _ = run(tmp_path, "--a-secco", "--bw", str(bw))

    assert code == 1
    assert "alla fine bw dice: locked" in text
    assert "FALLITO: la chiusura non è verificata" in text
    assert "il vault è chiuso, l'account è lasciato" not in text


def test_an_entry_that_cannot_be_deleted_is_a_failure_at_the_entry_and_at_the_end(
    bw: Path, tmp_path: Path
) -> None:
    turn_down(bw, delete="refuse")
    code, text, _ = run(tmp_path, "--a-secco", "--bw", str(bw))

    assert code == 1
    assert "FALLITO: la voce di prova non risulta cancellata" in text
    assert "voci di prova nel vault: UNA È RIMASTA" in text
    assert "FALLITO: una voce di prova può essere rimasta nel vault" in text
    clean(text)


def test_an_entry_left_by_an_interrupted_run_is_taken_away_by_the_next(
    bw: Path, tmp_path: Path
) -> None:
    turn_down(bw, delete="refuse")
    first = script().Bw(bw, tmp_path / "dati")
    key = first.run("login", "--raw", interactive=True).out
    first.run(
        "create", "item", session=key, stdin=script().invented_item("un-valore", ("http://a/",))
    )
    vault = script().Vault(first, keys=[key])
    assert script().none_left(vault) is False
    assert script().swept(vault) == 1 and script().none_left(vault) is False, (
        "the delete is refused"
    )

    turn_down(bw)
    assert script().swept(vault) == 1
    assert script().none_left(vault) is True


def test_a_login_bw_turns_down_is_skipped_and_the_rest_goes_on(bw: Path, tmp_path: Path) -> None:
    """What the world did not give is SALTATO, not FALLITO: a wrong password, a server that does
    not answer, are not a defect of the measure."""
    turn_down(bw, login="refuse")
    code, text, _ = run(tmp_path, "--a-secco", "--bw", str(bw))

    assert code == 0, text
    assert "SALTATO: bw login non ha dato una chiave" in text
    assert (
        "una voce di prova" not in text
        and "K3" not in text.split("# La fine")[1].split("SALTATO")[0]
    )
    assert "G1: nella finestra senza automazione il login passa" in text
    assert "alla fine bw dice: unauthenticated" in text
    assert "la cartella dei dati della misura non c'è più: sì" in text


def test_a_mistyped_password_is_asked_again_and_an_unlock_given_up_skips_what_needs_it(
    bw: Path, tmp_path: Path
) -> None:
    turn_down(bw, unlock="refuse")
    tommaso = Tommaso("n", "s", "n")
    code, text, _ = run(tmp_path, "--bw", str(bw), ask=tommaso)

    assert code == 0, text
    assert (
        sum("bw unlock non è riuscito: riprovare?" in question for question in tommaso.asked) == 2
    )
    assert commands(bw).count("unlock") == 2
    assert "SALTATO: bw unlock non ha dato una chiave" in text
    assert "SALTATO: il vault non è rimasto aperto con una chiave buona: K3 non misurato" in text
    assert "alla fine bw dice: unauthenticated" in text


def test_without_a_bw_the_steps_of_bitwarden_are_skipped(tmp_path: Path) -> None:
    code, text, _ = run(tmp_path, "--a-secco")

    assert code == 0
    assert "SALTATO: nessun bw" in text
    assert "0 FALLITO" in text


def test_without_chrome_for_testing_the_steps_of_google_are_skipped(
    bw: Path, tmp_path: Path
) -> None:
    code, text, (browser,) = run(tmp_path, "--a-secco", "--bw", str(bw), installed=False)

    assert code == 0
    assert "SALTATO: Chrome for Testing non è installato" in text
    assert browser.windows == []


# ----------------------------------------------------------------------------------------
# An interrupt, an error: the closing still happens, and the file does not lie
# ----------------------------------------------------------------------------------------


def interrupt() -> str:
    raise KeyboardInterrupt


def test_an_interrupt_after_the_login_still_locks_logs_out_and_says_it_was_interrupted(
    bw: Path, tmp_path: Path
) -> None:
    """Ctrl-C at the first question after ``bw login``: the vault exists for the closing before
    the login, so it is locked, the account is left, and both are asked of ``bw``."""
    code, text, _ = run(tmp_path, "--bw", str(bw), ask=Tommaso(interrupt))
    order = commands(bw)

    assert code == 1
    assert "INTERROTTA (KeyboardInterrupt) al passo 3" in text
    assert "L'esito: INTERROTTA prima della fine" in text
    assert order[-4:] == ["lock", "status", "logout", "status"]
    assert "alla fine bw dice: unauthenticated" in text
    assert "il vault è chiuso, l'account è lasciato" in text
    clean(text)


def test_an_interrupt_while_the_entry_is_in_the_vault_does_not_leave_it_there(
    bw: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = script()
    plain = module.carries_a_password
    monkeypatch.setattr(module, "carries_a_password", lambda listed: interrupt())
    code, text, _ = run(tmp_path, "--a-secco", "--bw", str(bw))
    monkeypatch.setattr(module, "carries_a_password", plain)

    assert code == 1 and "INTERROTTA" in text
    assert "delete" in commands(bw)
    assert "voci di prova nel vault: nessuna rimasta" in text
    assert "alla fine bw dice: unauthenticated" in text


def test_a_browser_that_breaks_is_a_step_not_measured_and_the_file_says_which(
    bw: Path, tmp_path: Path
) -> None:
    """Nothing a browser raises ends the measure with a traceback behind a file that says «0
    FALLITO»: the step is SALTATO, with the type of the error and never its message."""
    code, text, (browser,) = run(tmp_path, "--bw", str(bw), ask=Tommaso("n", "s"), breaks="visit")

    assert code == 0, text
    assert "SALTATO: G3 con la finestra: non misurato, il browser ha sollevato TimeoutError" in text
    assert "SALTATO: G6: nessun lancio di Playwright ha visto il login" not in text
    assert "nessun lancio di Playwright ha visto il login" in text
    assert "alla fine bw dice: unauthenticated" in text
    assert len(browser.removed) == len(browser.profiles)
    clean(text)


def test_a_defect_of_the_measure_is_a_failure_with_its_line_and_the_closing_follows(
    bw: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = script()

    def broken(*arguments: Any, **named: Any) -> None:
        raise ZeroDivisionError("qualcuno@example.org")

    monkeypatch.setattr(module, "google", broken)
    code, text, _ = run(tmp_path, "--a-secco", "--bw", str(bw))

    assert code == 1
    assert "FALLITO: la misura si è rotta: ZeroDivisionError alla riga" in text
    assert "alla fine bw dice: unauthenticated" in text
    clean(text)


def test_without_a_terminal_the_real_measure_does_not_start(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "misura.txt"

    assert script().main(["--out", str(out)]) == 2
    assert "vuole un terminale" in capsys.readouterr().err
    assert not out.exists()


# ----------------------------------------------------------------------------------------
# The measure with Tommaso there
# ----------------------------------------------------------------------------------------


def test_the_one_thing_asked_of_tommaso_in_words_is_where_the_account_is(
    bw: Path, tmp_path: Path
) -> None:
    tommaso = Tommaso("n", "s", "n", "n", region="eu")
    code, text, _ = run(tmp_path, "--bw", str(bw), ask=tommaso)
    in_words = [q for q in tommaso.asked if "(s/n)" not in q and "Premi Invio" not in q]

    assert code == 0, text
    assert in_words == ["L'account sta su bitwarden.com o su bitwarden.eu? (com/eu) "]
    assert "il server di bw: vault.bitwarden.eu (risposta: eu)" in text
    assert ["config", "server", "https://vault.bitwarden.eu"] in [
        call["argv"] for call in calls(bw)
    ]


def test_an_answer_that_is_neither_is_asked_again(bw: Path, tmp_path: Path) -> None:
    answers = iter(["boh", "COM"])
    asked: list[str] = []

    def tommaso(question: str) -> str:
        asked.append(question)
        return next(answers) if "(com/eu)" in question else "n"

    run(tmp_path, "--bw", str(bw), ask=tommaso)

    assert len([question for question in asked if "(com/eu)" in question]) == 2
    assert not any(
        call["argv"][:2] == ["config", "server"] and len(call["argv"]) == 3 for call in calls(bw)
    )


def test_the_window_without_automation_comes_first_on_a_clean_folder_and_the_guided_one_after(
    bw: Path, tmp_path: Path
) -> None:
    """G1 decides the binary, so nothing signs the folder in before it: the plain window first, then
    the launches of Playwright (with the window before without), the adapter's road, the way out —
    and only then the guided window, on the same folder, out of the account."""
    code, text, (browser,) = run(tmp_path, "--bw", str(bw), ask=Tommaso("n", "s", "n", "n"))

    assert code == 0, text
    assert browser.windows == [
        ("plain", "cft", False),
        ("guided", "cft", False),
        ("plain", "cft", True),
    ]
    assert browser.visits[:3] == [
        ("account", True, False),
        ("account", False, False),
        ("account", False, True),
    ]
    assert text.index("G1: il login in una finestra") < text.index("G3: il login della finestra")
    assert text.index("fuori dall'account") < text.index("G2: il login in una finestra")
    assert "G6: per la strada dell'adapter il login si ritrova" in text
    assert "G2, un fatto: in una finestra guidata Google fa entrare: no" in text


def test_a_site_that_turns_chrome_for_testing_down_is_tried_in_the_installed_chrome(
    bw: Path, tmp_path: Path
) -> None:
    """G1 of the rule written before the numbers: the same login, in the same conditions, in the
    other binary — a new test folder, the same preferences, the same round."""
    tommaso = Tommaso("s", "n", "s", "n", "n")
    code, text, (browser,) = run(
        tmp_path, "--bw", str(bw), ask=tommaso, lets_in=frozenset({"chrome"})
    )

    assert code == 0, text
    assert browser.windows[:2] == [("plain", "cft", False), ("plain", "chrome", False)]
    assert browser.profiles[:2] == [("google-cft", True), ("google-chrome", True)]
    assert "RIAPRE: G1 — nella finestra senza automazione di Chrome for Testing" in text
    assert "l'altra metà di G1 e G4: il Chrome installato, nelle stesse condizioni" in text
    assert "non è la tua, e la chiude lo script" in text
    assert "G3: si ritrova, con la finestra e senza" in text
    assert len(browser.removed) == len(browser.profiles) == 3


def test_what_the_binary_does_with_nothing_to_stop_it_is_measured_in_a_bare_window(
    bw: Path, tmp_path: Path
) -> None:
    """G5 (decision 20): a folder without ELA's preferences, in a window without the flags that
    switch the browser's own sign-in off — and Tommaso left out of that account too."""
    code, text, (browser,) = run(tmp_path, "--bw", str(bw), ask=Tommaso("n", "s", "n", "s"))

    assert code == 0, text
    assert ("plain", "cft", True) in browser.windows
    assert ("google-cft-senza-preferenze", False) in browser.profiles
    assert "G5, un fatto: senza niente che lo spenga, collegato: no" in text
    assert text.count("fuori dall'account: la pagina dell'account non si apre più") == 2
    assert script().BARE_WINDOW == (
        "--use-mock-keychain",
        "--no-first-run",
        "--no-default-browser-check",
    )


def test_a_login_found_only_with_the_window_reopens_g3_and_is_left_through_the_window(
    bw: Path, tmp_path: Path
) -> None:
    code, text, (browser,) = run(
        tmp_path, "--bw", str(bw), ask=Tommaso("n", "s", "n", "n"), sees=frozenset({True})
    )

    assert code == 0, text
    assert "RIAPRE: G3 — si ritrova solo con la finestra" in text
    assert ("Logout", True, False) in browser.visits
    assert "fuori dall'account: la pagina dell'account non si apre più" in text


def test_a_way_out_that_cannot_be_seen_is_not_said_to_be_done(bw: Path, tmp_path: Path) -> None:
    """No launch of Playwright saw the login: a logout from one would do nothing and «the account
    page does not open» would be true before it. Not verified is not PASSATO."""
    code, text, _ = run(
        tmp_path, "--bw", str(bw), ask=Tommaso("n", "s", "n", "n"), sees=frozenset()
    )

    assert code == 0, text
    assert "RIAPRE: G3 — non si ritrova in nessuno dei due lanci" in text
    assert (
        "SALTATO: nessun lancio di Playwright ha visto il login: l'uscita non si può fare" in text
    )
    assert "fuori dall'account: la pagina" not in text
    assert "SALTATO: la cartella non è fuori dall'account" in text


def test_a_logout_that_leaves_the_session_alive_is_a_failure(bw: Path, tmp_path: Path) -> None:
    code, text, _ = run(
        tmp_path, "--bw", str(bw), ask=Tommaso("n", "s", "n", "n"), logout_works=False
    )

    assert code == 1
    assert "FALLITO: l'uscita non è verificata" in text


def test_a_browser_that_kept_something_of_a_login_made_by_hand_reopens_the_preferences(
    bw: Path, tmp_path: Path
) -> None:
    """P1: after Tommaso's own login in the window, the counts of what the browser's password
    manager wrote — a row of an offer to save is enough to reopen proposal 3."""
    answers = ("n", "s", "n", "n")
    _, clean_run, _ = run(tmp_path, "--bw", str(bw), ask=Tommaso(*answers))
    _, kept, _ = run(tmp_path, "--bw", str(bw), ask=Tommaso(*answers), offered=1)

    assert "PASSATO: P1: niente salvato, niente offerto, niente ricordato" in clean_run
    assert "righe di stats: 1" in kept
    assert "RIAPRE: P1 — il browser ha tenuto qualcosa del login nonostante le preferenze" in kept


def test_the_counts_of_what_a_browser_saved_are_read_from_its_tables_and_never_a_row(
    tmp_path: Path,
) -> None:
    import sqlite3

    chrome = script().Chrome(tmp_path, simulated=True)
    profile = chrome.profile("una", preferences=True)
    with sqlite3.connect(profile / "Default" / "Login Data") as made:
        made.execute("create table logins (username_value text)")
        made.execute("create table stats (username_value text)")
        made.execute("insert into stats values ('qualcuno@example.org')")

    assert chrome.saved(profile) == {"logins": 0, "stats": 1, "autofill": None}


def test_a_folder_somebody_else_holds_is_not_given_a_second_browser(
    bw: Path, tmp_path: Path
) -> None:
    out = tmp_path / "misura.txt"
    made: list[NoBrowser] = []

    def browsers(work: Path, reached: Callable[[], bool]) -> NoBrowser:
        made.append(NoBrowser(work))
        return made[0]

    plain = NoBrowser.visit

    def then_busy(self: NoBrowser, *arguments: Any, **named: Any) -> Any:
        self.busy = "ogout" in arguments[2] or self.busy
        return plain(self, *arguments, **named)

    NoBrowser.visit = then_busy  # type: ignore[method-assign]
    try:
        script().main(
            ["--bw", str(bw), "--out", str(out)], ask=Tommaso("n", "s"), browsers=browsers
        )
    finally:
        NoBrowser.visit = plain  # type: ignore[method-assign]

    assert "SALTATO: la cartella di prova è occupata da un altro processo" in out.read_text("utf-8")
    assert ("guided", "cft", False) not in made[0].windows


def test_a_guided_window_tommaso_closed_is_not_measured_and_says_no_address(
    bw: Path, tmp_path: Path
) -> None:
    code, text, _ = run(tmp_path, "--bw", str(bw), ask=Tommaso("n", "s", "s"), breaks="guided")

    assert code == 0, text
    assert "SALTATO: G2: non misurato, il browser ha sollevato RuntimeError" in text
    clean(text)


# ----------------------------------------------------------------------------------------
# What is read of the profile, and the fences
# ----------------------------------------------------------------------------------------


def test_what_says_the_browser_is_linked_is_read_as_presence_never_as_a_value() -> None:
    preferences = {
        "account_info": [{"email": "qualcuno@example.org", "gaia": "1234567890"}],
        "google": {
            "services": {"account_id": "1234567890", "last_username": "qualcuno@example.org"}
        },
        "sync": {"has_setup_completed": True},
        "signin": {"allowed": True},
    }
    read = script().linked_from(preferences)

    assert read == {
        "account_info": 1,
        "google.services.account_id": True,
        "google.services.last_username": True,
        "google.services.consented_to_sync": None,
        "sync.has_setup_completed": True,
        "signin.allowed": True,
    }
    assert "example.org" not in str(read) and "1234567890" not in str(read)
    assert script().is_linked(read) is True
    assert script().is_linked(script().linked_from({"signin": {"allowed": False}})) is False


def test_preferences_that_cannot_be_read_are_not_read_as_a_browser_that_is_not_linked(
    tmp_path: Path,
) -> None:
    """G4 does not pass on a folder no browser ever wrote: not read is not «not linked»."""
    chrome = script().Chrome(tmp_path, simulated=True)
    never_opened = chrome.profile("mai-aperta", preferences=False)
    broken = chrome.profile("rotta", preferences=True)
    (broken / "Default" / "Preferences").write_text("{non è JSON", encoding="utf-8")
    made = report(tmp_path)

    assert chrome.linked(never_opened) is None and chrome.linked(broken) is None
    script().linked(made, chrome, never_opened, "G4", script().Outcome())
    made.close()
    text = made.path.read_text(encoding="utf-8")
    assert "SALTATO: Default/Preferences non si legge" in text and "PASSATO" not in text


def test_a_window_without_automation_has_nothing_attached_and_never_the_keychain() -> None:
    module = script()

    assert module.attaches_nothing(module.WINDOW_ARGUMENTS) and module.attaches_nothing(
        module.BARE_WINDOW
    )
    assert (
        module.MOCK_KEYCHAIN in module.WINDOW_ARGUMENTS
        and module.MOCK_KEYCHAIN in module.BARE_WINDOW
    )
    for attached in ("--remote-debugging-port=0", "--remote-debugging-pipe", "--headless=new"):
        assert module.attaches_nothing((*module.WINDOW_ARGUMENTS, attached)) is False


def test_a_browser_whose_own_arguments_are_not_the_measure_s_is_outside_the_fence(
    tmp_path: Path,
) -> None:
    keeps = script().keeps_the_fence
    folder = tmp_path / "profili" / "una"

    assert keeps(f"/bin/chrome --user-data-dir={folder} --use-mock-keychain about:blank", folder)
    assert not keeps(f"/bin/chrome --user-data-dir={folder} about:blank", folder)
    assert not keeps("/bin/chrome --user-data-dir=/altrove --use-mock-keychain", folder)
    assert not keeps("", folder), "a browser the kernel does not show is not vouched for"


def test_a_folder_that_is_not_the_measure_s_is_never_a_profile(tmp_path: Path) -> None:
    chrome = script().Chrome(tmp_path, simulated=True)
    of_the_user = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"

    with pytest.raises(RuntimeError, match="the profile of the installed Chrome"):
        chrome.occupied(of_the_user)
    with pytest.raises(RuntimeError, match="the fence holds"):
        chrome.remove(tmp_path)
    assert chrome.profile("una", preferences=True).is_relative_to(tmp_path.resolve())


@pytest.mark.skipif(
    os.name == "nt", reason="a symbolic link to host-pid is how Chrome locks on POSIX"
)
def test_who_holds_a_profile_is_read_from_its_lock_without_launching(tmp_path: Path) -> None:
    chrome = script().Chrome(tmp_path, simulated=True)
    profile = chrome.profile("una", preferences=False)
    assert chrome.occupied(profile) is False

    (profile / "SingletonLock").symlink_to(f"questa-macchina-{os.getpid()}")
    assert chrome.occupied(profile) is True

    (profile / "SingletonLock").unlink()
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    (profile / "SingletonLock").symlink_to(f"questa-macchina-{gone.pid}")
    assert chrome.occupied(profile) is False, "a lock whose process is dead holds nothing"


def test_the_preferences_written_first_are_the_ones_the_spec_proposes(tmp_path: Path) -> None:
    profile = script().Chrome(tmp_path, simulated=True).profile("una", preferences=True)
    written = json.loads((profile / "Default" / "Preferences").read_text(encoding="utf-8"))

    assert written["credentials_enable_service"] is False
    assert written["signin"] == {"allowed": False, "allowed_on_next_startup": False}
    assert written["autofill"] == {"profile_enabled": False, "credit_card_enabled": False}


@pytest.mark.skipif(os.name == "nt", reason="the bits of a folder's mode are POSIX's")
def test_a_test_folder_is_made_for_its_owner_alone(tmp_path: Path) -> None:
    profile = script().Chrome(tmp_path, simulated=True).profile("una", preferences=True)

    assert oct(profile.stat().st_mode & 0o777) == "0o700"


# ----------------------------------------------------------------------------------------
# The dry run on the real browser
# ----------------------------------------------------------------------------------------


def chrome_for_testing_of_the_lock() -> bool:
    """Whether the Chrome for Testing **of the revision the lock names** is where Playwright would
    launch it from — read from the registry's folder, without starting anything."""
    import playwright

    package = Path(playwright.__file__).parent / "driver" / "package"
    browsers = json.loads((package / "browsers.json").read_text(encoding="utf-8"))["browsers"]
    (revision,) = [entry["revision"] for entry in browsers if entry["name"] == "chromium"]
    registry = Path(
        os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or Path.home() / "Library/Caches/ms-playwright"
    )
    return any((registry / f"chromium-{revision}").glob("chrome-mac*/*.app/Contents/MacOS/*"))


ASKED_FOR = os.environ.get("MISURA_M13_9_BROWSER") == "1"
ON_THE_REAL_BROWSER = (
    ASKED_FOR and platform.system() == "Darwin" and chrome_for_testing_of_the_lock()
)
NOT_ASKED_FOR = (
    "the dry run on the real Chrome for Testing opens windows and lets the browser talk to Google: "
    "it runs with MISURA_M13_9_BROWSER=1, on a Mac, after `uv run playwright install chromium`"
)


@pytest.fixture
def no_browser_left() -> Iterator[None]:
    yield
    listing = subprocess.run(
        ["/bin/ps", "-A", "-o", "pid=,args="], capture_output=True, text=True, check=False
    )
    left = [
        line.split(None, 1)[0] for line in listing.stdout.splitlines() if "ela-misura-m139-" in line
    ]
    for pid in left:
        subprocess.run(["/bin/kill", "-9", pid], check=False)
    assert left == [], "a browser of the measure was still running, and has been killed"


@pytest.mark.skipif(not ON_THE_REAL_BROWSER, reason=NOT_ASKED_FOR)
def test_the_dry_run_on_the_real_chrome_for_testing_finds_the_login_of_the_window_again(
    bw: Path, tmp_path: Path, no_browser_left: None
) -> None:
    """The whole measure with nobody there: local pages, the window of the binary launched with no
    automation, the launches of Playwright after it — the adapter's road among them —, the way
    out, and the guided window: on the browser of the lock."""
    out = tmp_path / "misura.txt"
    code = script().main(["--a-secco", "--bw", str(bw), "--out", str(out)])
    text = out.read_text(encoding="utf-8")

    assert code == 0, text
    assert "G1: nella finestra senza automazione il login passa" in text
    assert "G3: si ritrova, con la finestra e senza: la stessa chiave nei due lanci" in text
    assert "G6: per la strada dell'adapter il login si ritrova" in text
    assert "G4: il browser non è collegato a nessun account, e la sincronizzazione è spenta" in text
    assert text.count("fuori dall'account: la pagina dell'account non si apre più") == 2
    assert "G2, un fatto: in una finestra guidata Google fa entrare: sì" in text
    assert "cancellate: 1, e nessuna c'è più" in text
    assert "0 FALLITO" in text and "0 RIAPRE" in text
    clean(text)
