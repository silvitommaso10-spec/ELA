"""La misura di M13.11, sul PC: che cosa parte sotto lo Smart App Control, e il vault del PC.

    uv run python scripts/misura_m13_11.py A              # senza account
    uv run python scripts/misura_m13_11.py B              # con Tommaso: il vault
    uv run python scripts/misura_m13_11.py A --a-secco    # nessun browser lanciato, nessuna domanda
    uv run python scripts/misura_m13_11.py B --a-secco    # nessun account: un vault finto, suo

**La lancia Tommaso sul PC, dal repository, in PowerShell, con l'interprete e mai con ``ela.exe``**
(SPEC di M13.11, parte prima, «La misura»; decisione 17). Scrive tutto in un file nei Downloads,
``misura-m13.11-<parte>-<AAAAMMGG-HHMMSS>.txt`` — a secco ``misura-m13.11-a-secco-<parte>-…``, che
il passo 7 della guida non scambia per una misura —, e lo stampa anche qui. Risponde alle righe di
«La regola della misura, riga per riga», **con le righe A3.3 e A5 (ii) e la tabella degli strati
che valgono dal 2026-11-20** (decisioni 44 e 45, «Le risposte 40–43 e le decisioni 44–48»).

**Il file va sul Mac per posta**, e non porta password, chiavi, cookie, nomi utente, nomi di voci,
indirizzi, la casa del PC — che si scrive ``~`` —, il nome della macchina né un SID: ogni riga passa
da un filtro prima di essere scritta (:class:`Filter`), e alla fine lo script rilegge il file e lo
dice. **Un file la cui rilettura è FALLITO non lascia il PC.**

Le parole dell'esito, una per significato, come in ``misura_m13_9.py``: **PASSATO** — misurato, e
la risposta lascia la premessa com'è —; **RIAPRE** — misurato, e la risposta riapre la riga che
nomina; e dice **se ferma lo strato** che la vuole o **se non lo ferma** —; **SALTATO** — non
misurato, perché il mondo non l'ha dato —; **FALLITO** — un dovere dello script non verificato: la
pulizia, il file, una recinzione che non ha tenuto. Alla fine, **la tabella degli strati S1–S4**:
quali cominciano secondo la regola recepita.

* **Parte A**, senza account: la macchina (A1); che cosa c'è, con la firma di ogni file (A2); gli
  adapter di oggi, senza lanciare niente (A3.0); che cosa parte da solo (A3.1) e come lo lancia ELA
  (A3.2); il Chrome installato, lanciato solo se Chrome for Testing non è partito (A3.3); il profilo
  che dura (A4); la chiusura sana e che cosa resta quando il driver solo è terminato (A5).
* **Parte B**, con Tommaso: ``bw.exe`` solo in ``~\\.ela\\bin``, **e firmato da Bitwarden prima
  di lanciarlo** (B1); il login e lo sblocco come K1–K3 di M13.9, con la chiave **solo in memoria**
  e ai figli **solo come** ``BW_SESSION``, mai in ``argv`` (B2); il tubo di PowerShell 5.1 e 7, con
  due programmi dello script e mai la chiave vera (B3).

**Le recinzioni**: nessun sito vero — le pagine le serve lo script su ``127.0.0.1`` —; ogni cartella
di profilo sotto una cartella temporanea dello script, cancellata alla fine e verificata; **del
Chrome installato solo il file del programma, ai percorsi esatti di ``INSTALLED_CHROME``**, e
niente altro sotto ``%LOCALAPPDATA%\\Google\\Chrome``; **né ``_killing`` né ``_alive`` di ELA
girano sul PC** (decisione 44): dove una chiusura di ELA passasse il suo limite, l'albero lo toglie
lo script con ``taskkill``, e lo dice. Il codice di ELA lo importa, non lo ricopia: gli argomenti e
le opzioni dei due adapter, le costanti, la lettura di PowerShell di
``infrastructure/machine/windows.py``.

**I suoi test usano solo finti** (``tests/scripts/test_misura_m13_11.py``): tutto ciò che legge
Windows passa da un oggetto «macchina» (:class:`Pc`), e un test ne passa uno suo.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import getpass
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
    Iterable,
    Iterator,
    Mapping,
    Sequence,
)
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Final, Protocol, TextIO
from urllib.parse import unquote, urlsplit

from ela.composition.root import BROWSER_CLOSE_GRACE_SECONDS
from ela.infrastructure.machine.account import LAUNCH_ARGUMENTS, AccountChrome, reports_in
from ela.infrastructure.machine.browser import GONE_SECONDS, PlaywrightBrowser, _process_of
from ela.infrastructure.machine.windows import POWERSHELL, encoded, without_module_path
from ela.tools.terminal import CLOSED_PATH, LANGUAGE

ROOT: Final = Path(__file__).resolve().parents[1]
EMAIL: Final = re.compile(r"[A-Za-z0-9._%+-]+(?:@|%40)[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SID: Final = re.compile(r"S-1-5-21(?:-\d+)+")
"""A security identifier of a user or a machine of a domain: never written (decision 18, A4)."""
USERS_FOLDER: Final = re.compile(r"[A-Za-z]:(?:\\+|/+)Users(?:\\+|/+)[^\\/\s:*?\"<>|']+", re.I)
"""Any folder of a user of Windows — the home, and its short name of 8.3 too (``TOMMAS~1``): written
``~``, whoever's it is."""
YES: Final = frozenset({"s", "si", "sì"})
NO: Final = frozenset({"n", "no"})
WORDS: Final = ("PASSATO", "RIAPRE", "SALTATO", "FALLITO")

TITLE: Final = "ELA misura M13.11"
"""The title of the script's page on 127.0.0.1: a browser that reads it has read the page."""
COOKIE: Final = "ela_misura_m1311"
"""The name of the cookie of A4 (i): looked for by name, its value never kept."""
KEY_LINE: Final = base64.b64encode(bytes(range(64))).decode("ascii")
"""A line of the shape of a session key of ``bw`` (K1: 88 characters of base64), invented here and
the same at every run: what the first program of B3 prints in place of a key."""
NON_ASCII: Final = "àèìòù €—ß"
TIMES: Final = 10
"""How many openings and closings of each browser A5 (i) times."""
HALF: Final = BROWSER_CLOSE_GRACE_SECONDS / 2
"""Half the limit of a closing: the criterion of ADR 0072 §7 — 2,5 s."""
NAVIGATION_MS: Final = 30_000
CLOSE_WITHIN: Final = 30.0
"""How long a closing of the script's own may take before the script takes the tree away."""
BLOCKED: Final = 4551
"""What Windows says of a file an application control policy blocked (os error 4551)."""
BLOCKED_SAID: Final = re.compile(r"4551|controllo dell.applicazione|Application Control", re.I)
TASKKILL: Final = r"C:\Windows\System32\taskkill.exe"
"""At a literal path, like ``POWERSHELL``: a binary of the system, never one the ``PATH`` chose."""
SAC_KEY: Final = r"SYSTEM\CurrentControlSet\Control\CI\Policy"
SAC_VALUE: Final = "VerifiedAndReputablePolicyState"
SHELL_NAMES: Final = frozenset({"powershell.exe", "pwsh.exe", "cmd.exe"})
PWSH: Final = ("PowerShell", "7", "pwsh.exe")
"""Where PowerShell 7 is, under ``%ProgramFiles%``: looked at there, and only then in the PATH."""
INSTALLED_CHROME: Final = (
    ("ProgramFiles", "Google", "Chrome", "Application", "chrome.exe"),
    ("ProgramFiles(x86)", "Google", "Chrome", "Application", "chrome.exe"),
    ("LOCALAPPDATA", "Google", "Chrome", "Application", "chrome.exe"),
)
"""The only places the installed Chrome is looked for, each with one «is it a file?»."""
CHROME_DATA: Final = ("Google", "Chrome")
"""Under ``%LOCALAPPDATA%``: the installed Chrome's own folder, where ``User Data`` — the profile —
is. Nothing in it is opened, read or listed but the program, at its exact path."""
PROTECTED: Final = frozenset({"(A;OICI;FA;;;SY)", "(A;OICI;FA;;;BA)", "(A;OICI;FA;;;OW)"})
"""The DACL ``mkdir(0o700)`` gives from Python 3.12.4 (ADR 0040 §2), read as
``tests/infrastructure/machine/test_acl_smoke.py`` reads it."""
EXPECTED_ADAPTERS: Final = ("BrowserUnsupported", "BrowserUnsupported", "False")
"""What A3.0 expects the code of today to answer on Windows (difference 7 of the SPEC)."""
OPENJS: Final = "OpenJS Foundation"
M8: Final[Mapping[str, tuple[str, str | None]]] = {
    "node.exe": ("Valid", OPENJS),
    "chrome-headless-shell.exe": ("NotSigned", None),
    "libEGL.dll": ("NotSigned", None),
    "libGLESv2.dll": ("NotSigned", None),
    "vk_swiftshader.dll": ("NotSigned", None),
    "vulkan-1.dll": ("NotSigned", None),
    "ffmpeg-win64.exe": ("NotSigned", None),
}
"""The rows of M8 of M13.4, read on the Mac: the status a file should have, and the organization of
who signed it. The DLLs are those beside the shell."""
SHELL_EXE: Final = "chrome-headless-shell.exe"
CFT_EXE: Final = "chrome.exe"
STRATA: Final[Mapping[str, tuple[str, ...]]] = {
    "S1": (
        "A1",
        "A2 node.exe",
        "A2 lo shell",
        "A3.1 node.exe",
        "A3.1 lo shell",
        "A3.2 lo shell",
    ),
    "S2": (
        "S1",
        "A2 Chrome for Testing",
        "A3.1 Chrome for Testing",
        "A3.2 (c) senza finestra",
        "A3.2 (c) con la finestra",
        "A4 (i)",
    ),
    "S3": ("S2", "B1", "B2", "B3"),
}
"""The table of the strata that holds from 2026-11-20 (decision 45): the rows each one wants. «A3.2
lo shell» is (a) or (b); S4 wants S1 or S2, and no row more."""
STARTS: Final = "comincia"
STOPPED: Final = "non comincia"
ELSEWHERE: Final = "si legge con il file dell'altra parte"

BITWARDEN: Final = "Bitwarden Inc."
"""The organization a ``bw.exe`` must be signed by before it is launched at all (B1). *From the
SPEC's knowledge, not verified*: a value that differs launches nothing, and the reviewer reads
it."""
INVENTED_NAME: Final = "ELA-misura-M13.11-voce-di-prova"
INVENTED_USER: Final = "utente-inventato-m1311"
SERVERS: Final = {
    "com": (None, "bitwarden.com"),
    "eu": ("https://vault.bitwarden.eu", "vault.bitwarden.eu"),
}
KNOWN: Final = {
    "You are not logged in.": "non autenticato",
    "Vault is locked.": "vault chiuso",
    "Not found.": "non trovato",
}
BW_TIMEOUT_SECONDS: Final = 60
WINDOWS_KEPT: Final = frozenset(
    {
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "PATHEXT",
        "COMSPEC",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
        "OS",
    }
)
"""What a child of the vault gets of this process's environment on Windows, by name: what a program
of the system needs, and nothing of the user's — no key, no ``ELA_``, no token."""


@dataclass(frozen=True)
class Words:
    """The words of one command of ``bw`` this script uses (as in ``misura_m13_9.py``)."""

    objects: tuple[str, ...] = ()
    options: tuple[str, ...] = ()
    values: int = 0


BW_COMMANDS: Final[Mapping[str, Words]] = {
    "status": Words(),
    "config": Words(objects=("server",), values=1),
    "login": Words(options=("--raw",)),
    "unlock": Words(options=("--raw",)),
    "lock": Words(),
    "logout": Words(),
    "get": Words(objects=("item", "uri", "username", "password"), values=1),
    "create": Words(objects=("item",)),
    "list": Words(objects=("items",), options=("--url", "--search")),
    "delete": Words(objects=("item",), options=("--permanent",), values=1),
}
"""Every command of ``bw`` this script composes, with its words: a closed list. ``login`` and
``unlock`` take **no** value: the master password is never an argument."""
VALUED: Final = frozenset({"--url", "--search"})


class Interrupted(BaseException):
    """The terminal was closed or the process told to end: cleaned up after, like a Ctrl-C."""


class FenceBroken(RuntimeError):
    """A fence of the measure did not hold: a folder that is not one of the measure's, a path under
    the installed Chrome's own folder. FALLITO, and the part stops there."""


@dataclass(frozen=True)
class Failure:
    """What a reading of the machine could not give, and why: a sentence of the script's or the
    first line of the system's."""

    said: str


@dataclass(frozen=True)
class Verdict:
    word: str
    stops: bool = False


def fine(verdict: Verdict | None) -> bool:
    """Whether a row lets a stratum start: PASSATO, or RIAPRE without stopping it."""
    return verdict is not None and (
        verdict.word == "PASSATO" or (verdict.word == "RIAPRE" and not verdict.stops)
    )


def on_signal(number: int, handler: Any) -> Any:
    try:
        return signal.signal(number, handler)
    except ValueError:
        return None


def first_line(text: str, limit: int = 300) -> str:
    lines = text.strip().splitlines()
    return lines[0][:limit] if lines else ""


# ---------------------------------------------------------------------------------------------
# Il filtro, e il rapporto
# ---------------------------------------------------------------------------------------------


def _home_pattern(home: str) -> re.Pattern[str] | None:
    parts = [part for part in re.split(r"[\\/]+", home) if part]
    if not parts:
        return None
    lead = r"[\\/]+" if home[:1] in "\\/" else ""
    return re.compile(
        lead + r"[\\/]+".join(re.escape(part) for part in parts) + r"(?![\w.-])", re.I
    )


def _word(name: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", re.I)


class Filter:
    """What a line may carry: the home is written ``~``; a line with a value the measure keeps to
    itself, an address, a name of the user, the name of the machine or a SID is withheld."""

    def __init__(self, *, home: str, users: Iterable[str], machines: Iterable[str]) -> None:
        self.home = _home_pattern(home)
        self.users = [_word(one) for one in users if len(one) >= 2]
        self.machines = [_word(one) for one in machines if len(one) >= 2]
        self.secrets: set[str] = set()

    def secret(self, value: str) -> None:
        """A value no line may carry from now on — whole, and each of its long words."""
        if len(value) >= 6:
            self.secrets.add(value)
        self.secrets.update(word for word in value.split() if len(word) >= 16)

    def shown(self, line: str) -> str:
        if self.home is not None:
            line = self.home.sub("~", line)
        return USERS_FOLDER.sub("~", line)

    def withheld(self, line: str) -> str | None:
        """Why ``line``, as :meth:`shown` writes it, may not be written — or ``None``."""
        if any(secret in line for secret in self.secrets):
            return "un valore che la misura tiene per sé"
        if EMAIL.search(line) is not None:
            return "un indirizzo"
        if any(one.search(line) for one in self.users):
            return "un nome utente"
        if any(one.search(line) for one in self.machines):
            return "il nome della macchina"
        if SID.search(line) is not None:
            return "un SID"
        return None

    def found(self, text: str) -> list[str]:
        """What ``text`` — the file, read back — carries that it must not."""
        found = [
            reason
            for reason, there in (
                ("un valore che la misura tiene per sé", any(s in text for s in self.secrets)),
                ("un indirizzo", EMAIL.search(text) is not None),
                ("un nome utente", any(one.search(text) for one in self.users)),
                ("il nome della macchina", any(one.search(text) for one in self.machines)),
                ("un SID", SID.search(text) is not None),
                (
                    "la casa del PC",
                    (self.home is not None and self.home.search(text) is not None)
                    or USERS_FOLDER.search(text) is not None,
                ),
            )
            if there
        ]
        return found


class Report:
    """What goes on the screen and in the file: the same lines, each through the filter."""

    def __init__(self, path: Path, screen: Callable[[str], None], filtered: Filter) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file: TextIO = path.open("w", encoding="utf-8")
        self._screen = screen
        self.filter = filtered
        self.number = 0
        self.counts = dict.fromkeys(WORDS, 0)
        self.rows: dict[str, Verdict] = {}
        self.withheld_lines = 0
        self.interrupted = False

    def secret(self, value: str) -> None:
        self.filter.secret(value)

    def say(self, line: str = "") -> None:
        line = self.filter.shown(line)
        reason = self.filter.withheld(line)
        if reason is not None:
            self.withheld_lines += 1
            line = f"[una riga trattenuta: portava {reason}]"
        self._screen(line)
        self._file.write(line + "\n")
        self._file.flush()

    def step(self, title: str) -> None:
        self.number += 1
        self.say(f"\n—— passo {self.number}: {title} ——")

    def _mark(self, word: str, text: str) -> None:
        self.counts[word] += 1
        self.say(f"[{self.number}] {word}: {text}")

    def row(self, name: str, word: str, text: str, *, stops: bool = False) -> None:
        """The answer to a row of the rule: its word, and — for a RIAPRE — whether it stops the
        stratum that wants that row."""
        self.rows[name] = Verdict(word, stops)
        tail = ""
        if word == "RIAPRE":
            tail = " — ferma lo strato che la vuole" if stops else " — non ferma"
        self._mark(word, f"{name} — {text}{tail}")

    def passed(self, text: str) -> None:
        self._mark("PASSATO", text)

    def skipped(self, text: str) -> None:
        self._mark("SALTATO", text)

    def failed(self, text: str) -> None:
        self._mark("FALLITO", text)

    def fact(self, text: str) -> None:
        self.say(f"    {text}")

    def looked(self, question: str, answer: bool) -> None:
        self.say(f"[{self.number}] GUARDATO: {question} — {'sì' if answer else 'no'}")

    def found_in_the_file(self) -> list[str]:
        self._file.flush()
        return self.filter.found(self.path.read_text(encoding="utf-8"))

    def verdict(self) -> None:
        counts = ", ".join(f"{count} {word}" for word, count in self.counts.items())
        ended = "INTERROTTA prima della fine; " if self.interrupted else ""
        self.say(
            f"\n## L'esito: {ended}{counts}; righe trattenute dal filtro: {self.withheld_lines}"
        )

    @property
    def ok(self) -> bool:
        return self.counts["FALLITO"] == 0 and not self.interrupted

    def close(self) -> None:
        self._file.close()


def yes_or_no(ask: Callable[[str], str], report: Report, question: str) -> bool:
    while True:
        answer = ask(f"{question} (s/n) ").strip().lower()
        if answer in YES or answer in NO:
            report.looked(question, answer in YES)
            return answer in YES


def screen(line: str) -> None:
    """A line on the terminal of the PC: one its code page cannot write is written with ``?``."""
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode("ascii"), flush=True)


# ---------------------------------------------------------------------------------------------
# Ciò che la macchina dice
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Ran:
    """A child that ran: its exit, what it printed, how long it took."""

    code: int
    out: str
    err: str
    ms: int
    timed_out: bool = False

    @property
    def said(self) -> str:
        """What ``bw`` said on its stderr, as a code of this script's — never its text."""
        if self.code == 0:
            return "uscita 0"
        return f"uscita {self.code}, {KNOWN.get(self.err, f'altro, {len(self.err)} caratteri')}"


@dataclass(frozen=True)
class FileFacts:
    size: int
    sha256: str
    status: str
    subject: str
    version: str = ""


@dataclass(frozen=True)
class Attempt:
    """A page asked of a browser: the title it read, or the type of what it raised and the first
    line of its message."""

    title: str | None
    error: str = ""
    said: str = ""


def reads(attempt: Attempt) -> bool:
    return attempt.title == TITLE


def is_blocked(attempt: Attempt) -> bool:
    return BLOCKED_SAID.search(attempt.said) is not None


def shown_attempt(attempt: Attempt) -> str:
    if reads(attempt):
        return "ha letto la pagina"
    if attempt.title is not None:
        return f"ha letto un altro titolo, di {len(attempt.title)} caratteri"
    return f"ha sollevato {attempt.error}: {attempt.said}"


def attempted(work: Callable[[], Awaitable[str]]) -> Attempt:
    try:
        return Attempt(title=asyncio.run(work()))  # type: ignore[arg-type]
    except Exception as error:  # noqa: BLE001 — whatever a browser raises is the answer
        return Attempt(None, type(error).__name__, first_line(str(error)))


@dataclass(frozen=True)
class Launched:
    """A program launched by its path (A3.1, A3.3): it started — with its exit and its first line —
    or the system's error as it is, its number and its sentence."""

    started: bool
    code: int | None = None
    first: str = ""
    error: int | None = None
    sentence: str = ""
    timed_out: bool = False

    @property
    def blocked(self) -> bool:
        return self.error == BLOCKED


@dataclass(frozen=True)
class Cookie:
    """A4 (i) and (ii): whether the cookie of a first launch is there in a second one, by name; the
    names of what is in the folder while the browser runs and after it closed."""

    found: bool | None
    running: tuple[str, ...] = ()
    after: tuple[str, ...] = ()
    error: Attempt | None = None


@dataclass(frozen=True)
class Closings:
    """A5 (i): how long each closing took, in seconds; what broke, if something did; and how many
    times a closing of ELA's adapter passed its limit."""

    seconds: tuple[float, ...] = ()
    error: str = ""
    limit: int = 0


@dataclass(frozen=True)
class Orphans:
    """A5 (ii): the tree of the driver before, what of it was alive ``GONE_SECONDS`` after the
    driver alone was terminated, and what was still alive after the script's own cleanup."""

    tree: tuple[tuple[int, str], ...] = ()
    left: tuple[tuple[int, str], ...] = ()
    remaining: tuple[tuple[int, str], ...] = ()
    error: str = ""


class Machine(Protocol):
    """What the measure asks of the PC. The real one is :class:`Pc`; a test passes its own."""

    environ: Mapping[str, str]

    def system(self) -> str: ...
    def pid(self) -> int: ...
    def home(self) -> str: ...
    def who(self) -> tuple[tuple[str, ...], tuple[str, ...]]: ...
    def commit(self) -> str: ...
    def python(self) -> tuple[int, int, int]: ...
    def windows(self) -> list[str]: ...
    def registry_sac(self) -> int | Failure: ...
    def defender_sac(self) -> str | Failure: ...
    def shells(self) -> dict[str, Path | None]: ...
    def processes(self) -> dict[int, tuple[int, str]] | Failure: ...
    def is_file(self, path: Path) -> bool: ...
    def registry(self) -> tuple[Path, str]: ...
    def lock(self) -> list[tuple[str, str]]: ...
    def node(self) -> Path: ...
    def pe_files(self, folder: Path) -> list[Path]: ...
    def file_facts(self, paths: Sequence[Path]) -> dict[Path, FileFacts] | Failure: ...
    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        stdin: bytes | None = None,
        interactive: bool = False,
        timeout: float | None = 60.0,
    ) -> Ran: ...
    def kill_tree(self, pid: int) -> Ran | Failure: ...
    def adapters_installed(self, registry: Path) -> tuple[str, str, str]: ...
    def adapter_title(self, url: str) -> Attempt: ...
    def shell_title(self, url: str, *, whole: bool) -> Attempt: ...
    def cft_title(self, url: str, folder: Path, *, window: bool, whole: bool) -> Attempt: ...
    def cookie_twice(self, origin: str, folder: Path, *, whole: bool) -> Cookie: ...
    def folder_check(self, folder: Path) -> tuple[str, str]: ...
    def sddl(self, folder: Path) -> str | Failure: ...
    def closings(self, kind: str, url: str, folder: Path, *, how: str) -> Closings: ...
    def orphans(self, kind: str, url: str, folder: Path, *, how: str) -> Orphans: ...


# ---------------------------------------------------------------------------------------------
# PowerShell: ogni script è una costante in chiaro, nella forma di P3-bis
# ---------------------------------------------------------------------------------------------

DEFENDER_SAC: Final = """$ProgressPreference = 'SilentlyContinue'
$ErrorActionPreference = 'Stop'
try {
  $state = (Get-MpComputerStatus).SmartAppControlState
  [Console]::Out.WriteLine([System.Uri]::EscapeDataString([string]$state))
} catch {
  [Console]::Error.WriteLine($_.Exception.Message)
  exit 1
}
"""
"""``SmartAppControlState`` as ``Get-MpComputerStatus`` says it, raw."""

PROCESSES: Final = """$ProgressPreference = 'SilentlyContinue'
$ErrorActionPreference = 'Stop'
try {
  [Console]::Out.WriteLine($PID)
  foreach ($p in Get-CimInstance Win32_Process) {
    $name = [System.Uri]::EscapeDataString([string]$p.Name)
    [Console]::Out.WriteLine(('{0} {1} {2}' -f $p.ProcessId, $p.ParentProcessId, $name))
  }
} catch {
  [Console]::Error.WriteLine($_.Exception.Message)
  exit 1
}
"""
"""Every process of ``Win32_Process``: its number, its parent's and its name — never a command line.
The first line is this PowerShell's own number, which the listing leaves out."""

FILE_FACTS: Final = """$ProgressPreference = 'SilentlyContinue'
$ErrorActionPreference = 'Stop'
try {
  $ms = New-Object System.IO.MemoryStream
  [Console]::OpenStandardInput().CopyTo($ms)
  $all = [System.Text.Encoding]::UTF8.GetString($ms.ToArray())
  foreach ($line in $all.Split("`n")) {
    $path = $line.TrimEnd("`r")
    if (-not $path) { continue }
    $status = 'Illeggibile'
    $subject = ''
    $version = ''
    try {
      $s = Get-AuthenticodeSignature -LiteralPath $path
      $status = [string]$s.Status
      if ($s.SignerCertificate) { $subject = $s.SignerCertificate.Subject }
    } catch { $status = 'Illeggibile' }
    try {
      $v = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($path).ProductVersion
      if ($v) { $version = $v }
    } catch { $version = '' }
    $a = [System.Uri]::EscapeDataString($path)
    $b = [System.Uri]::EscapeDataString($subject)
    $c = [System.Uri]::EscapeDataString($version)
    [Console]::Out.WriteLine($a + ' ' + $status + ' ' + $b + ' ' + $c)
  }
} catch {
  [Console]::Error.WriteLine($_.Exception.Message)
  exit 1
}
"""
"""For each path on stdin: ``Get-AuthenticodeSignature`` — ``Status`` and
``SignerCertificate.Subject`` — and the version of the file (``VersionInfo``), nothing launched."""

READ_SDDL: Final = """$ProgressPreference = 'SilentlyContinue'
$ErrorActionPreference = 'Stop'
try {
  $ms = New-Object System.IO.MemoryStream
  [Console]::OpenStandardInput().CopyTo($ms)
  $path = [System.Text.Encoding]::UTF8.GetString($ms.ToArray())
  [Console]::Out.WriteLine((Get-Acl -LiteralPath $path).Sddl)
} catch {
  [Console]::Error.WriteLine($_.Exception.Message)
  exit 1
}
"""
"""The script of ``tests/infrastructure/machine/test_acl_smoke.py``, as it is: the path on stdin."""


def processes_from(said: str) -> dict[int, tuple[int, str]]:
    """What :data:`PROCESSES` printed, by number: the parent and the name — without the
    PowerShell that listed them."""
    lines = said.splitlines()
    if not lines or not lines[0].strip().isdigit():
        return {}
    itself = int(lines[0])
    table: dict[int, tuple[int, str]] = {}
    for line in lines[1:]:
        parts = line.strip().split(" ")
        if len(parts) != 3 or not (parts[0].isdigit() and parts[1].isdigit()):
            continue
        if int(parts[0]) != itself:
            table[int(parts[0])] = (int(parts[1]), unquote(parts[2]))
    return table


def facts_from(said: str) -> dict[str, tuple[str, str, str]]:
    """What :data:`FILE_FACTS` printed: by path, the status, the subject and the version."""
    found: dict[str, tuple[str, str, str]] = {}
    for line in said.splitlines():
        parts = line.strip().split(" ")
        if len(parts) == 4:
            found[unquote(parts[0])] = (parts[1], unquote(parts[2]), unquote(parts[3]))
    return found


def dacl(descriptor: str) -> tuple[str, list[str]]:
    """The DACL's flags and its entries, as ``dacl()`` of ``test_acl_smoke.py`` reads them."""
    body = descriptor.partition("D:")[2].partition("S:")[0]
    return body.partition("(")[0], re.findall(r"\([^)]*\)", body)


def protected(descriptor: str) -> bool:
    flags, entries = dacl(descriptor)
    return "P" in flags and len(entries) == len(PROTECTED) and set(entries) == PROTECTED


def dacl_shown(descriptor: str) -> str:
    """Only the ``D:`` part, and a SID in it masked: the owner and the group are the user's."""
    body = descriptor.partition("D:")[2].partition("S:")[0]
    return "D:" + SID.sub("S-1-5-21-…", body)


def split_dn(subject: str) -> list[str]:
    """The parts of a distinguished name, split at the commas that are not inside quotes."""
    parts: list[str] = []
    current: list[str] = []
    quoted = False
    for character in subject:
        if character == '"':
            quoted = not quoted
        if character == "," and not quoted:
            parts.append("".join(current))
            current = []
        else:
            current.append(character)
    parts.append("".join(current))
    return parts


def organization(subject: str) -> str | None:
    """The value of ``O=`` of a certificate's subject, its quotes taken away; ``None`` if none."""
    for part in split_dn(subject):
        key, equal, value = part.partition("=")
        if equal and key.strip().upper() == "O":
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] == '"':
                value = value[1:-1].replace('""', '"')
            return value
    return None


def agrees(facts: FileFacts, expected: tuple[str, str | None]) -> bool:
    status, signer = expected
    return facts.status == status and (signer is None or organization(facts.subject) == signer)


def not_of_bitwarden(facts: FileFacts) -> str | None:
    """Why a ``bw.exe`` is not launched as the CLI of Bitwarden, or ``None``: ``Status`` must be
    ``Valid`` and the organization of the signer exactly :data:`BITWARDEN`."""
    if facts.status != "Valid":
        return f"Status è {facts.status}, non Valid"
    signer = organization(facts.subject)
    if signer != BITWARDEN:
        return f"l'organizzazione di chi ha firmato è {signer!r}, non {BITWARDEN!r}"
    return None


def descendants(root: int, table: Mapping[int, tuple[int, str]]) -> list[tuple[int, str]]:
    """Every process whose parentage leads to ``root``, as ``table`` says it: number and name."""
    found: list[tuple[int, str]] = []
    seen = {root}
    frontier = [root]
    while frontier:
        parent = frontier.pop()
        for pid, (ppid, name) in sorted(table.items()):
            if ppid == parent and pid not in seen:
                seen.add(pid)
                found.append((pid, name))
                frontier.append(pid)
    return found


def ancestry(pid: int, table: Mapping[int, tuple[int, str]], depth: int = 8) -> list[str]:
    """The names from ``pid`` up through its parents: who launched whom."""
    chain: list[str] = []
    seen: set[int] = set()
    while pid in table and pid not in seen and len(chain) < depth:
        seen.add(pid)
        parent, name = table[pid]
        chain.append(name)
        pid = parent
    return chain


def still(
    tree: Iterable[tuple[int, str]], table: Mapping[int, tuple[int, str]]
) -> tuple[tuple[int, str], ...]:
    """What of ``tree`` is still in ``table``: the same number with the same name."""
    return tuple((pid, name) for pid, name in tree if pid in table and table[pid][1] == name)


def counted(processes: Iterable[tuple[int, str]]) -> str:
    """Names with how many of each — never a number of a process, never a command line."""
    counts: dict[str, int] = {}
    for _, name in processes:
        counts[name] = counts.get(name, 0) + 1
    return ", ".join(f"{name} ×{count}" for name, count in sorted(counts.items())) or "nessuno"


# ---------------------------------------------------------------------------------------------
# Il PC vero: nessuna di queste righe gira in un test
# ---------------------------------------------------------------------------------------------


async def _nothing() -> None:
    return None


def _anything(_: str) -> bool:
    return True


class _NeverStopped:
    """The stop of a task that is never raised: what a step of the measure hands the adapter."""

    def listen(self, where: str) -> None:
        del where

    def is_set(self) -> bool:
        return False

    def stopped(self) -> Awaitable[object]:
        return asyncio.Event().wait()


NEVER: Final = _NeverStopped()


async def _within(close: Callable[[], Awaitable[object]], seconds: float) -> bool:
    try:
        await asyncio.wait_for(close(), seconds)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001 — what cannot be closed any more is closed
        return False
    return True


@contextlib.contextmanager
def variable(name: str, value: str | None) -> Iterator[None]:
    """``os.environ[name]`` set — or taken away — for the time of the block, then as it was."""
    before = os.environ.get(name)
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
    try:
        yield
    finally:
        if before is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = before


def names_in(folder: Path) -> tuple[str, ...]:
    return tuple(sorted(one.name for one in folder.iterdir()))


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def head_of(root: Path) -> str:
    """The commit the clone at ``root`` is at, read from its files — no ``git`` launched, so none
    the ``PATH`` chose: ``.git/HEAD``, the branch's ref, or ``packed-refs``. ``illeggibile``
    when one of them is not there or not what it should be."""
    folder = root / ".git"
    try:
        head = (folder / "HEAD").read_text(encoding="ascii").strip()
        if not head.startswith("ref: "):
            commit = head
        else:
            ref = head.removeprefix("ref: ")
            loose = folder / ref
            if loose.is_file():
                commit = loose.read_text(encoding="ascii").strip()
            else:
                packed = (folder / "packed-refs").read_text(encoding="ascii").splitlines()
                commit = next(line.split()[0] for line in packed if line.split()[1:] == [ref])
    except (OSError, UnicodeDecodeError, StopIteration, IndexError):
        return "illeggibile"
    return commit[:7] if re.fullmatch(r"[0-9a-f]{40}", commit) else "illeggibile"


class Pc:
    """The PC: Windows read through ``winreg`` and ``powershell.exe``, programs launched by their
    path, the browsers through Playwright with the options ELA's adapters compose."""

    def __init__(self) -> None:
        self.environ: Mapping[str, str] = os.environ

    # Who and where ------------------------------------------------------------------------

    def system(self) -> str:
        return platform.system()

    def pid(self) -> int:
        return os.getpid()

    def home(self) -> str:
        return str(Path.home())

    def who(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        users = {os.environ.get("USERNAME", ""), Path.home().name}
        with contextlib.suppress(Exception):
            users.add(getpass.getuser())
        machines = {platform.node(), os.environ.get("COMPUTERNAME", "")}
        return tuple(sorted(one for one in users if one)), tuple(
            sorted(one for one in machines if one)
        )

    def commit(self) -> str:
        return head_of(ROOT)

    def python(self) -> tuple[int, int, int]:
        return (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)

    def windows(self) -> list[str]:
        lines = [
            f"sistema: {platform.system()} {platform.release()}, versione {platform.version()}, "
            f"{platform.machine()}"
        ]
        edition = getattr(platform, "win32_edition", lambda: None)()
        if edition:
            lines.append(f"edizione: {edition}")
        try:
            import winreg

            with winreg.OpenKey(  # type: ignore[attr-defined]
                winreg.HKEY_LOCAL_MACHINE,  # type: ignore[attr-defined]
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            ) as key:
                read = {}
                for name in ("DisplayVersion", "CurrentBuild", "UBR"):
                    with contextlib.suppress(OSError):
                        read[name] = winreg.QueryValueEx(key, name)[0]  # type: ignore[attr-defined]
            lines.append(
                f"build: {read.get('CurrentBuild', '?')}.{read.get('UBR', '?')}, "
                f"{read.get('DisplayVersion', '?')}"
            )
        except (ImportError, OSError) as error:
            lines.append(f"build: non letta dal registro ({type(error).__name__})")
        return lines

    # Lo Smart App Control -----------------------------------------------------------------

    def registry_sac(self) -> int | Failure:
        try:
            import winreg

            with winreg.OpenKey(  # type: ignore[attr-defined]
                winreg.HKEY_LOCAL_MACHINE,  # type: ignore[attr-defined]
                SAC_KEY,
                0,
                winreg.KEY_READ,  # type: ignore[attr-defined]
            ) as key:
                value, _ = winreg.QueryValueEx(key, SAC_VALUE)  # type: ignore[attr-defined]
        except ImportError:
            return Failure("winreg non c'è: questa macchina non è Windows")
        except OSError as error:
            return Failure(f"{type(error).__name__}: {error.strerror or error}")
        if isinstance(value, int):
            return value
        return Failure(f"un valore di un altro tipo ({type(value).__name__})")

    def defender_sac(self) -> str | Failure:
        ran = self.powershell(DEFENDER_SAC)
        if isinstance(ran, Failure):
            return ran
        if ran.code != 0:
            return Failure(f"uscita {ran.code}: {first_line(ran.err)}")
        return unquote(ran.out.strip())

    # PowerShell e i processi -------------------------------------------------------------

    def shells(self) -> dict[str, Path | None]:
        found: dict[str, Path | None] = {
            "powershell.exe": Path(POWERSHELL) if Path(POWERSHELL).is_file() else None
        }
        programs = env_get(os.environ, "ProgramFiles")
        seven = Path(programs, *PWSH) if programs else None
        if seven is not None and seven.is_file():
            found["pwsh.exe"] = seven
        else:
            elsewhere = shutil.which("pwsh.exe") or shutil.which("pwsh")
            found["pwsh.exe"] = Path(elsewhere) if elsewhere else None
        return found

    def powershell(
        self, script: str, stdin: bytes = b"", *, shell: str = POWERSHELL, timeout: float = 300.0
    ) -> Ran | Failure:
        """``script`` through ``powershell.exe`` started as ELA starts its own: no profile, no
        interaction, the script in ``-EncodedCommand``, and no ``PSModulePath`` (M12.3d)."""
        if not Path(shell).is_file():
            return Failure(f"{Path(shell).name} non c'è al suo percorso")
        try:
            return self.run(
                [shell, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded(script)],
                env=without_module_path(os.environ),
                stdin=stdin,
                timeout=timeout,
            )
        except OSError as error:
            return Failure(f"{Path(shell).name} non parte: {error.strerror or error}")

    def processes(self) -> dict[int, tuple[int, str]] | Failure:
        ran = self.powershell(PROCESSES)
        if isinstance(ran, Failure):
            return ran
        if ran.code != 0:
            return Failure(f"uscita {ran.code}: {first_line(ran.err)}")
        table = processes_from(ran.out)
        return table or Failure("Win32_Process non ha dato una tabella che lo script legge")

    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        stdin: bytes | None = None,
        interactive: bool = False,
        timeout: float | None = 60.0,
    ) -> Ran:
        """A program by its path. **What does not start raises** ``OSError`` as the system said it
        — the caller reads it. An interactive one has the terminal: stdin and stderr inherited,
        stdout read. One that overstays is ended with its tree."""
        started = time.monotonic()
        process = subprocess.Popen(
            list(argv),
            env=None if env is None else dict(env),
            stdin=None
            if interactive
            else (subprocess.PIPE if stdin is not None else subprocess.DEVNULL),
            stdout=subprocess.PIPE,
            stderr=None if interactive else subprocess.PIPE,
        )
        timed_out = False
        try:
            out, err = process.communicate(
                input=None if interactive else stdin, timeout=None if interactive else timeout
            )
        except subprocess.TimeoutExpired:
            timed_out = True
            self._end(process)
            out, err = process.communicate()
        except BaseException:
            self._end(process)
            process.wait()
            raise
        return Ran(
            code=-1 if timed_out else process.returncode,
            out=(out or b"").decode("utf-8", "replace").strip(),
            err=(err or b"").decode("utf-8", "replace").strip(),
            ms=round((time.monotonic() - started) * 1000),
            timed_out=timed_out,
        )

    def _end(self, process: subprocess.Popen[bytes]) -> None:
        if os.name == "nt":
            self.kill_tree(process.pid)
        with contextlib.suppress(OSError):
            process.kill()

    def kill_tree(self, pid: int) -> Ran | Failure:
        """``taskkill /T /F`` on ``pid``: the script's own cleanup, never ELA's kill."""
        if not Path(TASKKILL).is_file():
            return Failure("taskkill.exe non c'è al suo percorso")
        try:
            done = subprocess.run(
                [TASKKILL, "/T", "/F", "/PID", str(pid)],
                capture_output=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            return Failure(type(error).__name__)
        return Ran(done.returncode, "", "", 0)

    # I file ---------------------------------------------------------------------------------

    def is_file(self, path: Path) -> bool:
        return path.is_file()

    def registry(self) -> tuple[Path, str]:
        """Where Playwright installs its browsers on this PC, as its own code says it:
        ``PLAYWRIGHT_BROWSERS_PATH``, then ``%LOCALAPPDATA%\\ms-playwright``."""
        import playwright

        declared = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
        if declared == "0":
            package = Path(playwright.__file__).parent / "driver" / "package"
            return package / ".local-browsers", "PLAYWRIGHT_BROWSERS_PATH=0: dentro il pacchetto"
        if declared:
            return Path(declared), "da PLAYWRIGHT_BROWSERS_PATH"
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local) / "ms-playwright", "la cartella di Windows, %LOCALAPPDATA%"
        return Path.home() / "AppData" / "Local" / "ms-playwright", "LOCALAPPDATA non c'è"

    def lock(self) -> list[tuple[str, str]]:
        import playwright

        listed = Path(playwright.__file__).parent / "driver" / "package" / "browsers.json"
        browsers = json.loads(listed.read_text(encoding="utf-8"))["browsers"]
        return [(str(one["name"]), str(one["revision"])) for one in browsers]

    def node(self) -> Path:
        import playwright

        driver = Path(playwright.__file__).parent / "driver"
        return driver / ("node.exe" if os.name == "nt" else "node")

    def pe_files(self, folder: Path) -> list[Path]:
        if not folder.is_dir():
            return []
        return sorted(
            one
            for one in folder.rglob("*")
            if one.suffix.lower() in (".exe", ".dll") and one.is_file()
        )

    def file_facts(self, paths: Sequence[Path]) -> dict[Path, FileFacts] | Failure:
        if not paths:
            return {}
        stdin = "\n".join(str(one) for one in paths).encode("utf-8")
        ran = self.powershell(FILE_FACTS, stdin)
        if isinstance(ran, Failure):
            return ran
        if ran.code != 0:
            return Failure(f"uscita {ran.code}: {first_line(ran.err)}")
        signed = facts_from(ran.out)
        found: dict[Path, FileFacts] = {}
        for one in paths:
            status, subject, version = signed.get(str(one), ("NonLetta", "", ""))
            try:
                size, digest = one.stat().st_size, sha256_of(one)
            except OSError as error:
                size, digest = -1, f"illeggibile ({type(error).__name__})"
            found[one] = FileFacts(size, digest, status, subject, version)
        return found

    # I browser ------------------------------------------------------------------------------

    def _closed(self) -> dict[str, str]:
        """The closed environment of the browser **as root.py:992-997 composes it**: its keys,
        with the values that code gives on this PC — ``PATH`` the POSIX string, as it is."""
        return {
            "PATH": CLOSED_PATH,
            "HOME": str(Path.home()),
            "TMPDIR": tempfile.gettempdir(),
            "LANG": LANGUAGE,
        }

    def _empty(self) -> tuple[PlaywrightBrowser, list[str]]:
        adapter = PlaywrightBrowser(
            asyncio.Event(),
            environment=self._closed(),
            kept=_nothing,
            system=platform.system(),
            closing=BROWSER_CLOSE_GRACE_SECONDS,
        )
        return adapter, self._without_ela_s_kill(adapter)

    def _without_ela_s_kill(self, adapter: PlaywrightBrowser) -> list[str]:
        """**Neither ``_killing`` nor ``_alive`` runs on the PC** (decision 44): if a closing of the
        adapter passes its limit, in place of ELA's kill the script takes the driver's tree away
        with ``taskkill``, and the returned list says each time it happened."""
        passed: list[str] = []

        async def instead(drivers: Sequence[asyncio.subprocess.Process]) -> tuple[str, ...]:
            passed.append("il limite di chiusura è passato")
            for driver in drivers:
                await asyncio.to_thread(self.kill_tree, driver.pid)
                await _within(driver.wait, 10.0)
            return ()

        adapter._killing = instead  # type: ignore[method-assign]
        return passed

    def _shell_options(self, *, whole: bool) -> dict[str, Any]:
        options = PlaywrightBrowser(
            asyncio.Event(),
            environment=self._closed(),
            kept=_nothing,
            system=platform.system(),
            closing=BROWSER_CLOSE_GRACE_SECONDS,
        )._launch()
        if whole:
            options["env"] = dict(os.environ)
        return options

    def _profile_options(self, folder: Path, *, window: bool, whole: bool) -> dict[str, Any]:
        """The options and the arguments of the adapter of the profile, from its code: Chrome for
        Testing, ``LAUNCH_ARGUMENTS``, the folder of the crashes, ``chromium_sandbox``."""
        options = AccountChrome(
            asyncio.Event(),
            environment=self._closed(),
            kept=_nothing,
            system=platform.system(),
            profile=folder,
            shown=lambda: window,
            closing=BROWSER_CLOSE_GRACE_SECONDS,
        )._launch()
        if whole:
            options["env"] = dict(os.environ)
        return options

    async def _launched(
        self, playwright: Any, kind: str, folder: Path, how: str
    ) -> tuple[Any, Any]:
        whole = how == "intero"
        if kind == "shell":
            browser = await playwright.chromium.launch(**self._shell_options(whole=whole))
            return browser, await browser.new_context()
        options = self._profile_options(folder, window=False, whole=whole)
        return None, await playwright.chromium.launch_persistent_context(str(folder), **options)

    async def _down(self, manager: Any, playwright: Any) -> None:
        """The driver stopped within its time, and its tree taken away if it is still there."""
        await _within(playwright.stop, CLOSE_WITHIN)
        process = _process_of(manager)
        if process is not None and process.returncode is None:
            await asyncio.to_thread(self.kill_tree, process.pid)

    @contextlib.asynccontextmanager
    async def _driver(self) -> AsyncIterator[tuple[Any, Any]]:
        from playwright.async_api import async_playwright

        manager = async_playwright()
        playwright = await manager.start()
        try:
            yield manager, playwright
        finally:
            await self._down(manager, playwright)

    def adapters_installed(self, registry: Path) -> tuple[str, str, str]:
        async def asked(adapter: Any) -> str:
            try:
                return str(await adapter.installed())
            except Exception as error:  # noqa: BLE001 — the type is the answer
                return type(error).__name__

        async def work() -> tuple[str, str, str]:
            profile = AccountChrome(
                asyncio.Event(),
                environment=self._closed(),
                kept=_nothing,
                system=platform.system(),
                profile=None,
                shown=lambda: False,
                closing=BROWSER_CLOSE_GRACE_SECONDS,
            )
            empty, _ = self._empty()
            first = await asked(profile)
            with variable("PLAYWRIGHT_BROWSERS_PATH", None):
                second = await asked(empty)
            with variable("PLAYWRIGHT_BROWSERS_PATH", str(registry)):
                third = await asked(empty)
            return first, second, third

        return asyncio.run(work())

    def adapter_title(self, url: str) -> Attempt:
        async def work() -> str:
            adapter, _ = self._empty()
            opened = await adapter.open(url, _anything, NEVER)
            try:
                return await adapter.title(opened.page)
            finally:
                await adapter.close(opened.page)

        return attempted(work)

    def shell_title(self, url: str, *, whole: bool) -> Attempt:
        async def work() -> str:
            async with self._driver() as (_, playwright):
                browser = await playwright.chromium.launch(**self._shell_options(whole=whole))
                try:
                    page = await (await browser.new_context()).new_page()
                    await page.goto(url, timeout=NAVIGATION_MS)
                    return str(await page.title())
                finally:
                    await _within(browser.close, CLOSE_WITHIN)

        return attempted(work)

    def cft_title(self, url: str, folder: Path, *, window: bool, whole: bool) -> Attempt:
        async def work() -> str:
            options = self._profile_options(folder, window=window, whole=whole)
            async with self._driver() as (_, playwright):
                context = await playwright.chromium.launch_persistent_context(
                    str(folder), **options
                )
                try:
                    page = context.pages[0] if context.pages else await context.new_page()
                    await page.goto(url, timeout=NAVIGATION_MS)
                    return str(await page.title())
                finally:
                    await _within(context.close, CLOSE_WITHIN)

        return attempted(work)

    def cookie_twice(self, origin: str, folder: Path, *, whole: bool) -> Cookie:
        async def work() -> Cookie:
            options = self._profile_options(folder, window=False, whole=whole)
            async with self._driver() as (_, playwright):
                context = await playwright.chromium.launch_persistent_context(
                    str(folder), **options
                )
                try:
                    page = context.pages[0] if context.pages else await context.new_page()
                    await page.goto(origin + "/cookie", timeout=NAVIGATION_MS)
                    running = names_in(folder)
                finally:
                    await _within(context.close, CLOSE_WITHIN)
            after = names_in(folder)
            async with self._driver() as (_, playwright):
                context = await playwright.chromium.launch_persistent_context(
                    str(folder), **options
                )
                try:
                    cookies = await context.cookies(origin)
                finally:
                    await _within(context.close, CLOSE_WITHIN)
            found = any(one.get("name") == COOKIE for one in cookies)
            return Cookie(found, running, after)

        try:
            return asyncio.run(work())
        except Exception as error:  # noqa: BLE001 — whatever a browser raises is the answer
            return Cookie(None, error=Attempt(None, type(error).__name__, first_line(str(error))))

    def folder_check(self, folder: Path) -> tuple[str, str]:
        """The bits of ``st_mode``, and what the check of the folder of the adapter of the profile
        (``account.py:925-934``) says of it — run, not copied."""
        mode = f"{stat.S_IMODE(folder.stat().st_mode):04o}"
        adapter = AccountChrome(
            asyncio.Event(),
            environment=self._closed(),
            kept=_nothing,
            system=platform.system(),
            profile=folder,
            shown=lambda: False,
            closing=BROWSER_CLOSE_GRACE_SECONDS,
        )
        try:
            adapter._checked(folder)
        except Exception as error:  # noqa: BLE001 — what it raises is the answer
            return mode, f"{type(error).__name__}: {first_line(str(error))}"
        return mode, "accetta"

    def sddl(self, folder: Path) -> str | Failure:
        ran = self.powershell(READ_SDDL, str(folder).encode("utf-8"))
        if isinstance(ran, Failure):
            return ran
        if ran.code != 0:
            return Failure(f"uscita {ran.code}: {first_line(ran.err)}")
        return ran.out.strip()

    def closings(self, kind: str, url: str, folder: Path, *, how: str) -> Closings:
        async def with_the_adapter() -> Closings:
            adapter, passed = self._empty()
            seconds: list[float] = []
            for _ in range(TIMES):
                opened = await adapter.open(url, _anything, NEVER)
                await adapter.title(opened.page)
                started = time.monotonic()
                await adapter.close(opened.page)
                seconds.append(time.monotonic() - started)
            return Closings(tuple(seconds), limit=len(passed))

        async def with_its_options() -> Closings:
            from playwright.async_api import async_playwright

            seconds: list[float] = []
            for _ in range(TIMES):
                manager = async_playwright()
                playwright = await manager.start()
                try:
                    browser, context = await self._launched(playwright, kind, folder, how)
                    page = context.pages[0] if context.pages else await context.new_page()
                    await page.goto(url, timeout=NAVIGATION_MS)
                    await page.title()
                    started = time.monotonic()
                    await context.close()
                    if browser is not None:
                        await browser.close()
                    await playwright.stop()
                    seconds.append(time.monotonic() - started)
                finally:
                    await self._down(manager, playwright)
            return Closings(tuple(seconds))

        work = with_the_adapter if kind == "shell" and how == "adapter" else with_its_options
        try:
            return asyncio.run(work())
        except Exception as error:  # noqa: BLE001 — whatever a browser raises is the answer
            return Closings(error=f"{type(error).__name__}: {first_line(str(error))}")

    def orphans(self, kind: str, url: str, folder: Path, *, how: str) -> Orphans:
        """A5 (ii), the row of decision 44: the tree of the driver read from ``Win32_Process``
        with the page open; **the driver alone terminated** — ``Process.kill()``, which on Windows
        is ``TerminateProcess``; after ``GONE_SECONDS`` what is left of that tree; then the
        script's own ``taskkill /T /F`` on each, and what is left after it."""

        async def work() -> Orphans:
            from playwright.async_api import async_playwright

            manager = async_playwright()
            playwright = await manager.start()
            try:
                _, context = await self._launched(playwright, kind, folder, how)
                page = context.pages[0] if context.pages else await context.new_page()
                await page.goto(url, timeout=NAVIGATION_MS)
                driver = _process_of(manager)
                if driver is None:
                    return Orphans(
                        error="il processo del driver non si legge dove Playwright lo tiene"
                    )
                table = await asyncio.to_thread(self.processes)
                if isinstance(table, Failure):
                    return Orphans(error=f"i processi non si leggono: {table.said}")
                tree = ((driver.pid, table.get(driver.pid, (0, "?"))[1]),)
                tree += tuple(descendants(driver.pid, table))
                driver.kill()
                await asyncio.sleep(GONE_SECONDS)
                after = await asyncio.to_thread(self.processes)
                left = still(tree, after) if not isinstance(after, Failure) else tree
                for pid, _ in left:
                    await asyncio.to_thread(self.kill_tree, pid)
                remaining = left
                for _ in range(10):
                    final = await asyncio.to_thread(self.processes)
                    remaining = still(tree, final) if not isinstance(final, Failure) else left
                    if not remaining:
                        break
                    await asyncio.sleep(0.5)
                return Orphans(tree, left, remaining)
            finally:
                await self._down(manager, playwright)

        try:
            return asyncio.run(work())
        except Exception as error:  # noqa: BLE001 — whatever a browser raises is the answer
            return Orphans(error=f"{type(error).__name__}: {first_line(str(error))}")


# ---------------------------------------------------------------------------------------------
# Le cartelle dello script, e le sue pagine
# ---------------------------------------------------------------------------------------------


def _normal(path: Path | str) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def env_get(environ: Mapping[str, str], name: str) -> str | None:
    """A variable of the environment by its name in any spelling, as Windows keeps them."""
    return next((value for key, value in environ.items() if key.upper() == name.upper()), None)


def chrome_places(environ: Mapping[str, str]) -> list[tuple[str, Path | None]]:
    """The exact paths of the installed Chrome, built from the environment — ``None`` for
    a variable this PC does not have."""
    places: list[tuple[str, Path | None]] = []
    for variable_name, *rest in INSTALLED_CHROME:
        base = env_get(environ, variable_name)
        places.append((variable_name, Path(base, *rest) if base else None))
    return places


def chrome_data(environ: Mapping[str, str]) -> str | None:
    local = env_get(environ, "LOCALAPPDATA")
    return _normal(Path(local, *CHROME_DATA)) if local else None


def fenced(path: Path, environ: Mapping[str, str]) -> bool:
    """Whether ``path`` is under the installed Chrome's own folder and is not its program at the
    exact path: what the measure never opens, reads or lists."""
    forbidden = chrome_data(environ)
    if forbidden is None:
        return False
    here = _normal(path)
    exact = {_normal(place) for _, place in chrome_places(environ) if place is not None}
    return (here == forbidden or here.startswith(forbidden + os.sep)) and here not in exact


class Work:
    """The temporary folder of the measure: every folder of a profile is made here, and nowhere
    else — and the whole of it is taken away at the end, and verified."""

    def __init__(self, root: Path, environ: Mapping[str, str]) -> None:
        self.root = root
        self.environ = environ
        self.profiles = root / "profili"
        self.profiles.mkdir(mode=0o700)

    def profile(self, name: str) -> Path:
        made = self.profiles / name
        if fenced(made, self.environ) or not _normal(made).startswith(
            _normal(self.profiles) + os.sep
        ):
            raise FenceBroken("una cartella di profilo che non è una cartella della misura")
        made.mkdir(mode=0o700)
        return made


class Pages:
    """The pages of the measure, served by the script on 127.0.0.1: a title, and a cookie that
    lasts an hour — its value invented here and never written."""

    def __init__(self) -> None:
        self.requests: list[str] = []
        pages = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 — the name http.server calls
                pages.requests.append(self.path)
                body = f"<!doctype html><title>{TITLE}</title><h1>{TITLE}</h1>".encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                if self.path == "/cookie":
                    value = secrets.token_hex(8)
                    self.send_header("Set-Cookie", f"{COOKIE}={value}; Max-Age=3600; Path=/")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.origin = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def url(self, path: str = "/") -> str:
        return self.origin + path

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


# ---------------------------------------------------------------------------------------------
# Parte A
# ---------------------------------------------------------------------------------------------


@dataclass
class Found:
    """What part A found on its way, for the rows after."""

    registry: Path | None = None
    node: Path | None = None
    shell: Path | None = None
    cft: Path | None = None
    ffmpeg: Path | None = None
    installed: list[Path] = field(default_factory=list)
    started: dict[str, bool] = field(default_factory=dict)
    blocked: dict[str, bool] = field(default_factory=dict)
    shell_how: str | None = None
    cft_how: str | None = None
    cft_read: dict[bool, bool] = field(default_factory=dict)


def sac_on(reading: int | str | Failure) -> bool | None:
    """Whether a source says the Smart App Control is on — ``None`` when it was not read."""
    if isinstance(reading, Failure):
        return None
    text = str(reading).strip()
    if not text:
        return None
    return text.lower() in ("1", "on")


def sac_shown(reading: int | str | Failure) -> str:
    if isinstance(reading, Failure):
        return f"non letto — {reading.said}"
    return f"{reading!r}"


def a1_verdict(
    registry: int | Failure, defender: str | Failure, version: Sequence[int]
) -> tuple[str, bool, str]:
    """The rule of A1: Python from 3.12.4; at least one source read, and every source read says
    on. Anything else stops S1, and with it everything — but nothing read at all is SALTATO."""
    if tuple(version) < (3, 12, 4):
        shown = ".".join(str(one) for one in version)
        return "RIAPRE", True, f"Python {shown} è prima della 3.12.4: ADR 0040 §2, il nodo rifiuta"
    read = [one for one in (sac_on(registry), sac_on(defender)) if one is not None]
    if not read:
        return "SALTATO", False, "nessuna delle due fonti dello Smart App Control si legge"
    if not all(read):
        return (
            "RIAPRE",
            True,
            "una fonte dice che lo Smart App Control non è acceso, o le due non dicono la stessa "
            "cosa: la premessa della registrazione, e decide il revisore",
        )
    return "PASSATO", False, f"lo Smart App Control è acceso ({len(read)} fonti su 2 lette)"


def a1(report: Report, machine: Machine) -> None:
    report.step("A1 — la macchina: Windows, lo Smart App Control, Python, le shell")
    for line in machine.windows():
        report.fact(line)
    registry, defender = machine.registry_sac(), machine.defender_sac()
    report.fact(f"dal registro, HKLM\\{SAC_KEY}, {SAC_VALUE}: {sac_shown(registry)}")
    report.fact(f"da Get-MpComputerStatus, SmartAppControlState: {sac_shown(defender)}")
    version = machine.python()
    report.fact(f"Python: {'.'.join(str(one) for one in version)}")
    for name, where in machine.shells().items():
        report.fact(f"{name}: {where}" if where is not None else f"{name}: non c'è")
    table = machine.processes()
    if isinstance(table, Failure):
        report.fact(f"chi ha lanciato lo script: non letto — {table.said}")
    else:
        chain = ancestry(machine.pid(), table)
        report.fact("chi ha lanciato lo script, risalendo: " + " ← ".join(chain))
        shell = next((one for one in chain if one.lower() in SHELL_NAMES), "nessuna shell")
        report.fact(f"la shell che ha lanciato lo script: {shell}")
    word, stops, text = a1_verdict(registry, defender, version)
    report.row("A1", word, text, stops=stops)


def a2(report: Report, machine: Machine, found: Found) -> None:
    report.step("A2 — che cosa c'è: node.exe, i browser del lock, il Chrome installato")
    environ = machine.environ
    registry, how = machine.registry()
    if fenced(registry, environ):
        raise FenceBroken("il registro di Playwright è sotto la cartella del Chrome installato")
    found.registry = registry
    report.fact(f"il registro di Playwright: {registry} ({how})")
    node = machine.node()
    found.node = node if machine.is_file(node) else None
    folders: dict[str, Path] = {}
    files: dict[str, list[Path]] = {}
    for name, revision in machine.lock():
        folder = registry / f"{name.replace('-', '_')}-{revision}"
        folders[name] = folder
        files[name] = machine.pe_files(folder)
        report.fact(
            f"{name}, revisione {revision}: "
            + (f"{len(files[name])} file PE" if files[name] else "non c'è nel registro")
        )
    found.shell = next(
        (p for p in files.get("chromium-headless-shell", []) if p.name == SHELL_EXE), None
    )
    found.cft = next((p for p in files.get("chromium", []) if p.name == CFT_EXE), None)
    found.ffmpeg = next(
        (p for p in files.get("ffmpeg", []) if p.name.startswith("ffmpeg") and p.suffix == ".exe"),
        None,
    )
    for variable_name, place in chrome_places(environ):
        if place is None:
            report.fact(f"il Chrome installato, sotto %{variable_name}%: la variabile non c'è")
            continue
        there = machine.is_file(place)
        report.fact(f"il Chrome installato, {place}: " + ("c'è" if there else "non c'è"))
        if there:
            found.installed.append(place)
    every = [*([node] if found.node else []), *(p for f in files.values() for p in f)]
    every += found.installed
    facts = machine.file_facts(every)
    if isinstance(facts, Failure):
        report.fact(f"le firme non si leggono: {facts.said}")
        facts = {}
    for path in every:
        one = facts.get(path)
        if one is None:
            report.fact(f"{path}: non letto")
            continue
        version = f", versione {one.version}" if path in found.installed and one.version else ""
        report.fact(
            f"{path}: {one.size} byte, sha256 {one.sha256}, firma {one.status}, "
            f"{one.subject or 'nessun firmatario'}{version}"
        )
    a2_rows(report, found, files, facts)


def a2_rows(
    report: Report,
    found: Found,
    files: Mapping[str, list[Path]],
    facts: Mapping[Path, FileFacts],
) -> None:
    """The rows of A2: a file of M8 whose signature Windows says otherwise reopens the table of
    M8 without stopping; a browser of the lock that is not there is SALTATO, and stops the
    stratum that wants it until step 3 installs it."""

    def against_m8(label: str, paths: Iterable[Path]) -> None:
        compared = [(p, facts.get(p)) for p in paths if p.name in M8]
        unread = [p.name for p, one in compared if one is None]
        if unread:
            report.row(label, "SALTATO", f"le firme non si leggono: {', '.join(unread)}")
            return
        other = [p.name for p, one in compared if one is not None and not agrees(one, M8[p.name])]
        if other:
            report.row(
                label,
                "RIAPRE",
                "la firma che Windows dice è diversa dalla riga di M8 di M13.4: "
                + ", ".join(other),
            )
        else:
            report.row(label, "PASSATO", "ogni file è detto, e la firma concorda con M8")

    if found.node is None:
        report.row("A2 node.exe", "SALTATO", "node.exe della ruota non c'è")
    else:
        against_m8("A2 node.exe", [found.node])
    if found.shell is None:
        report.row("A2 lo shell", "SALTATO", "lo shell del lock non c'è: il passo 3 lo installa")
    else:
        against_m8("A2 lo shell", files.get("chromium-headless-shell", []))
    if found.cft is None:
        report.row("A2 Chrome for Testing", "SALTATO", "non c'è: il passo 3 lo installa")
    elif any(facts.get(p) is None for p in files.get("chromium", [])):
        report.row("A2 Chrome for Testing", "SALTATO", "le firme non si leggono")
    else:
        report.row("A2 Chrome for Testing", "PASSATO", "ogni file è detto, con la sua firma")
    if found.ffmpeg is None:
        report.row("A2 ffmpeg", "SALTATO", "ffmpeg del lock non c'è")
    else:
        against_m8("A2 ffmpeg", [found.ffmpeg])


def a3_0(report: Report, machine: Machine, found: Found) -> None:
    report.step("A3.0 — gli adapter di oggi, costruiti com'è il codice, senza lanciare niente")
    assert found.registry is not None  # noqa: S101 — A2 found it
    answers = machine.adapters_installed(found.registry)
    labels = (
        "installed() dell'adapter del profilo",
        "installed() dell'adapter vuoto, senza PLAYWRIGHT_BROWSERS_PATH",
        "installed() dell'adapter vuoto, con la variabile sul registro di A2",
    )
    for label, answer in zip(labels, answers, strict=True):
        report.fact(f"{label}: {answer}")
    if tuple(answers) == EXPECTED_ADAPTERS:
        report.row("A3.0", "PASSATO", "le risposte sono quelle che il codice dice")
    else:
        report.row(
            "A3.0",
            "RIAPRE",
            f"una risposta diversa da {', '.join(EXPECTED_ADAPTERS)}: la differenza 7",
        )


def launch(machine: Machine, argv: Sequence[str], *, timeout: float) -> Launched:
    try:
        ran = machine.run(argv, timeout=timeout)
    except OSError as error:
        number = getattr(error, "winerror", None) or error.errno
        return Launched(False, error=number, sentence=str(error.strerror or error))
    return Launched(True, ran.code, first_line(ran.out or ran.err, 120), timed_out=ran.timed_out)


def said_of(launched: Launched) -> str:
    if launched.started:
        stopped = ", fermato dallo script al suo tempo" if launched.timed_out else ""
        return f"è partito; uscita {launched.code}{stopped}; la prima riga: {launched.first!r}"
    return f"non è partito — errore {launched.error}: {launched.sentence}"


def a3_1(report: Report, machine: Machine, found: Found, work: Work) -> None:
    report.step("A3.1 — che cosa parte, da solo, con un argomento innocuo")
    programs: list[tuple[str, Path | None, list[str]]] = [
        ("node.exe", found.node, ["--version"]),
        ("ffmpeg", found.ffmpeg, ["-version"]),
    ]
    for name, path, folder in (
        ("lo shell", found.shell, "a31-shell"),
        ("Chrome for Testing", found.cft, "a31-cft"),
    ):
        arguments = []
        if path is not None:
            made = work.profile(folder)
            arguments = ["--headless", "--dump-dom", f"--user-data-dir={made}", "about:blank"]
        programs.append((name, path, arguments))
    for name, path, arguments in programs:
        row = f"A3.1 {name}"
        if path is None:
            report.row(row, "SALTATO", "non c'è (A2)")
            continue
        launched = launch(machine, [str(path), *arguments], timeout=60.0)
        found.started[name] = launched.started
        found.blocked[name] = launched.blocked
        report.fact(f"{name}: {said_of(launched)}")
        if launched.started:
            report.row(row, "PASSATO", "è partito")
        else:
            why = "bloccato" if launched.blocked else "non è partito"
            report.row(row, "RIAPRE", f"{why}, con l'errore del sistema com'è", stops=True)


def a3_2(report: Report, machine: Machine, found: Found, work: Work, pages: Pages) -> None:
    report.step("A3.2 (a) e (b) — lo shell, come lo lancia ELA")
    url = pages.url("/")
    if found.shell is None:
        report.row("A3.2 lo shell", "SALTATO", "lo shell non c'è (A2)")
    else:
        a = machine.adapter_title(url)
        report.fact(
            f"(a) l'adapter vuoto com'è, con l'ambiente chiuso di root.py: {shown_attempt(a)}"
        )
        if reads(a):
            found.shell_how = "adapter"
            report.row("A3.2 lo shell", "PASSATO", "(a) legge la pagina")
        else:
            b = machine.shell_title(url, whole=False)
            report.fact(f"(b) le opzioni dell'adapter vuoto, l'ambiente chiuso: {shown_attempt(b)}")
            if reads(b):
                found.shell_how = "chiuso"
                report.row(
                    "A3.2 lo shell",
                    "RIAPRE",
                    "(a) cade e (b) legge: il codice dell'adapter su Windows",
                )
            else:
                w = machine.shell_title(url, whole=True)
                report.fact(f"(b) di nuovo, con l'ambiente intero dello script: {shown_attempt(w)}")
                if reads(w):
                    found.shell_how = "intero"
                    report.row(
                        "A3.2 lo shell",
                        "RIAPRE",
                        "legge solo con l'ambiente intero: l'ambiente chiuso di ADR 0052 §10 su "
                        "Windows",
                    )
                elif is_blocked(b) or is_blocked(w) or found.blocked.get("lo shell"):
                    report.row(
                        "A3.2 lo shell",
                        "RIAPRE",
                        "lo shell bloccato dallo Smart App Control",
                        stops=True,
                    )
                else:
                    report.row(
                        "A3.2 lo shell",
                        "SALTATO",
                        "non misurato: lo shell non legge in nessun modo",
                    )
    report.step("A3.2 (c) — Chrome for Testing, con gli argomenti e le opzioni dell'adapter")
    report.fact(
        f"gli argomenti di ELA: {' '.join(LAUNCH_ARGUMENTS)} {reports_in(Path('<cartella>'))}; "
        "chromium_sandbox: sì"
    )
    for window in (False, True):
        row = "A3.2 (c) con la finestra" if window else "A3.2 (c) senza finestra"
        if found.cft is None:
            report.row(row, "SALTATO", "Chrome for Testing non c'è (A2)")
            continue
        mode = "con la finestra" if window else "senza finestra"
        label = "c-finestra" if window else "c-senza"
        closed = machine.cft_title(url, work.profile(f"a32-{label}"), window=window, whole=False)
        report.fact(f"(c) {mode}, l'ambiente chiuso: {shown_attempt(closed)}")
        if reads(closed):
            found.cft_read[window] = True
            if not window:
                found.cft_how = "chiuso"
            report.row(row, "PASSATO", "legge la pagina")
            continue
        whole = machine.cft_title(
            url, work.profile(f"a32-{label}-intero"), window=window, whole=True
        )
        report.fact(f"(c) {mode}, di nuovo con l'ambiente intero: {shown_attempt(whole)}")
        if reads(whole):
            found.cft_read[window] = True
            if not window:
                found.cft_how = "intero"
            report.row(
                row, "RIAPRE", "legge solo con l'ambiente intero: l'ambiente chiuso su Windows"
            )
        elif is_blocked(closed) or is_blocked(whole) or found.blocked.get("Chrome for Testing"):
            report.row(row, "RIAPRE", "Chrome for Testing bloccato", stops=True)
        else:
            report.row(row, "SALTATO", "non misurato: Chrome for Testing non legge la pagina")


def a3_3(report: Report, machine: Machine, found: Found, work: Work, pages: Pages) -> None:
    report.step("A3.3 — il Chrome installato (rivista: decisione 45)")
    if not found.installed:
        report.fact("A2 non l'ha trovato a nessuno dei suoi percorsi: niente da dire")
        return
    report.fact("la versione e la firma, lette dal file, sono in A2: nessun lancio per leggerle")
    if found.cft is None:
        report.row("A3.3", "SALTATO", "non lanciato: Chrome for Testing non c'è (A2)")
        return
    if found.started.get("Chrome for Testing") or any(found.cft_read.values()):
        report.fact("non lanciato: Chrome for Testing è partito, in A3.1 o in A3.2 (c)")
        return
    chrome = found.installed[0]
    folder = work.profile("a33-chrome-installato")
    argv = [
        str(chrome),
        "--headless",
        "--dump-dom",
        f"--user-data-dir={folder}",
        "--no-first-run",
        "--no-default-browser-check",
        pages.url("/"),
    ]
    launched = launch(machine, argv, timeout=60.0)
    report.fact(
        f"il Chrome installato, headless, su una cartella dello script: {said_of(launched)}"
    )
    if launched.started:
        report.row(
            "A3.3",
            "RIAPRE",
            "Chrome for Testing non parte in A3.1 né legge in A3.2 (c), e il Chrome installato "
            "parte: ADR 0063 §4, «mai il Chrome installato» — decide il revisore",
            stops=True,
        )
    else:
        report.row("A3.3", "PASSATO", "neanche il Chrome installato parte: ADR 0063 §4 resta")


def a4(
    report: Report, machine: Machine, found: Found, work: Work, pages: Pages | None, *, real: bool
) -> None:
    report.step("A4 (i) e (ii) — il cookie su due lanci, e i nomi dei file nella cartella")
    if not real or pages is None:
        report.skipped("A4 (i) e (ii): a secco, nessun browser lanciato")
    elif found.cft is None or found.cft_how is None:
        report.row("A4 (i)", "SALTATO", "Chrome for Testing non ha letto la pagina in A3.2 (c)")
    else:
        cookie = machine.cookie_twice(
            pages.origin, work.profile("a4-cookie"), whole=found.cft_how == "intero"
        )
        a4_cookie(report, cookie)
    report.step("A4 (iii) e (iv) — la cartella creata con mkdir(0o700): st_mode e il DACL")
    folder = work.profile("a4-modo")
    mode, said = machine.folder_check(folder)
    report.fact(f"(iii) i bit di st_mode: {mode}; il controllo di account.py:925-934: {said}")
    if said == "accetta":
        report.row("A4 (iii)", "PASSATO", "il controllo della cartella la accetta")
    else:
        report.row("A4 (iii)", "RIAPRE", "il controllo della cartella di ADR 0063 §4, su Windows")
    descriptor = machine.sddl(folder)
    if isinstance(descriptor, Failure):
        report.row("A4 (iv)", "SALTATO", f"il DACL non si legge: {descriptor.said}")
        return
    report.fact(f"(iv) il DACL: {dacl_shown(descriptor)}")
    if protected(descriptor):
        report.row("A4 (iv)", "PASSATO", "il DACL è quello di mkdir(0o700), protetto")
    else:
        report.row("A4 (iv)", "RIAPRE", "un DACL diverso: la protezione della cartella del profilo")


def a4_cookie(report: Report, cookie: Cookie) -> None:
    if cookie.error is not None or cookie.found is None:
        error = cookie.error or Attempt(None, "nessun errore", "")
        report.fact(f"(i) {shown_attempt(error)}")
        word, stops = ("RIAPRE", True) if is_blocked(error) else ("SALTATO", False)
        report.row("A4 (i)", word, "non misurato: il browser non ha fatto i due lanci", stops=stops)
        return
    there = "c'è" if cookie.found else "manca"
    report.fact(f"(i) il cookie {COOKIE}, per nome, nel secondo lancio: {there}")
    if cookie.found:
        report.row("A4 (i)", "PASSATO", "il cookie si ritrova")
    else:
        report.row(
            "A4 (i)",
            "RIAPRE",
            "il cookie non si ritrova: «ciò che dura è la cartella» di ADR 0063 §4",
            stops=True,
        )
    gone = sorted(set(cookie.running) - set(cookie.after))
    report.fact(f"(ii) mentre gira: {', '.join(cookie.running) or 'niente'}")
    report.fact(f"(ii) creati mentre gira e tolti alla chiusura: {', '.join(gone) or 'nessuno'}")
    if "SingletonLock" in cookie.running:
        report.row("A4 (ii)", "PASSATO", "la cartella è tenuta da SingletonLock, come sul Mac")
    else:
        report.row("A4 (ii)", "RIAPRE", "nessun SingletonLock: il lock letto per pid, su Windows")


def a5(
    report: Report, machine: Machine, found: Found, work: Work, pages: Pages | None, *, real: bool
) -> None:
    report.step(f"A5 (i) — la chiusura sana, {TIMES} volte per browser")
    if not real or pages is None:
        report.skipped("A5: a secco, nessun browser lanciato")
        return
    url = pages.url("/")
    for kind, label, how in (
        ("shell", "lo shell", found.shell_how),
        ("cft", "Chrome for Testing", found.cft_how),
    ):
        row = f"A5 (i) {label}"
        if how is None:
            report.row(row, "SALTATO", "non ha letto la pagina in A3.2: non misurato")
            continue
        closings = machine.closings(kind, url, work.profile(f"a5-{kind}"), how=how)
        a5_closings(report, row, label, how, closings)
    report.step("A5 (ii) — che cosa resta, per parentela, quando il driver solo è terminato")
    if found.shell_how is not None:
        kind, how = "shell", "chiuso" if found.shell_how == "adapter" else found.shell_how
    elif found.cft_how is not None:
        kind, how = "cft", found.cft_how
    else:
        report.row("A5 (ii)", "SALTATO", "nessun browser ha letto la pagina in A3.2")
        return
    orphans = machine.orphans(kind, url, work.profile("a5-orfani"), how=how)
    a5_orphans(report, orphans)


def a5_closings(report: Report, row: str, label: str, how: str, closings: Closings) -> None:
    if closings.error or not closings.seconds:
        report.row(row, "SALTATO", f"non misurato: {closings.error or 'nessuna chiusura'}")
        return
    longest = max(closings.seconds)
    ordered = sorted(closings.seconds)
    report.fact(
        f"{len(ordered)} chiusure di {label} ({how}): la più lunga {longest:.3f} s, la mediana "
        f"{ordered[len(ordered) // 2]:.3f} s; il limite, BROWSER_CLOSE_GRACE_SECONDS, "
        f"{BROWSER_CLOSE_GRACE_SECONDS} s, e la sua metà {HALF} s"
    )
    if closings.limit:
        report.fact(
            f"il limite di chiusura di ELA è passato {closings.limit} volte: l'uccisione di "
            "ELA non gira sul PC (decisione 44), e l'albero lo ha tolto lo script con taskkill"
        )
    if longest > HALF:
        report.row(
            row, "RIAPRE", "la più lunga è sopra la metà: il limite di ADR 0072 §1 su Windows"
        )
    else:
        report.row(row, "PASSATO", "la più lunga è sotto la metà del limite")


def a5_orphans(report: Report, orphans: Orphans) -> None:
    if orphans.error:
        report.row("A5 (ii)", "SALTATO", f"non misurato: {orphans.error}")
        return
    report.fact(f"l'albero del driver, prima: {counted(orphans.tree)}")
    report.fact(f"vivi {GONE_SECONDS} s dopo il driver solo terminato: {counted(orphans.left)}")
    report.fact(f"vivi dopo il taskkill /T /F dello script: {counted(orphans.remaining)}")
    if orphans.remaining:
        report.row("A5 (ii)", "FALLITO", "la pulizia dello script lascia dei vivi")
    elif orphans.left:
        report.row(
            "A5 (ii)",
            "RIAPRE",
            "restano dei vivi: l'uccisione per parentela su Windows vuole il Job Object (ADR 0047 "
            "§13) o l'albero intero",
        )
    else:
        report.row("A5 (ii)", "PASSATO", f"non resta niente dopo {GONE_SECONDS} s")


def part_a(
    report: Report, machine: Machine, *, real: bool, work: Work, pages: Pages | None
) -> None:
    report.say("\n# Parte A — senza account")
    found = Found()
    a1(report, machine)
    a2(report, machine, found)
    a3_0(report, machine, found)
    if real and pages is not None:
        a3_1(report, machine, found, work)
        a3_2(report, machine, found, work, pages)
        a3_3(report, machine, found, work, pages)
    else:
        report.step("A3.1, A3.2 e A3.3 — a secco")
        report.skipped("a secco: nessun programma del lock è lanciato, nessun browser")
    a4(report, machine, found, work, pages, real=real)
    a5(report, machine, found, work, pages, real=real)


# ---------------------------------------------------------------------------------------------
# Parte B: il vault
# ---------------------------------------------------------------------------------------------


def refused(arguments: Sequence[str], session: str | None = None) -> str | None:
    """Why ``bw`` is not launched with these arguments, or ``None``: every word is held to
    :data:`BW_COMMANDS`, and neither a session key nor anything that would take the master
    password is ever among them."""
    if list(arguments) == ["--version"]:
        return None
    if "--session" in arguments or (session is not None and session in arguments):
        return "the session key never goes in argv"
    command = arguments[0] if arguments else ""
    words = BW_COMMANDS.get(command)
    if words is None:
        return f"bw {command} is not a command this measure composes"
    positional: list[str] = []
    rest = iter(arguments[1:])
    for word in rest:
        if word.startswith("-"):
            if word not in words.options:
                return f"bw {command} {word} is not an option this measure composes"
            if word in VALUED:
                next(rest, None)
        else:
            positional.append(word)
    if not words.objects:
        return f"bw {command} takes no value here" if positional else None
    if not positional or positional[0] not in words.objects:
        return f"bw {command} {' '.join(positional[:1])} is not an object this measure composes"
    if len(positional) - 1 > words.values:
        return f"bw {command} {positional[0]} takes at most {words.values} value here"
    return None


def child_environment(environ: Mapping[str, str], system: str) -> dict[str, str]:
    """What a child of the vault gets, built from zero: on Windows what a program of the system
    needs by name (:data:`WINDOWS_KEPT`) and a ``PATH`` of the system; elsewhere the variables of
    M6."""
    if system == "Windows":
        made = {name: value for name, value in environ.items() if name.upper() in WINDOWS_KEPT}
        root = next(
            (value for name, value in environ.items() if name.upper() == "SYSTEMROOT"),
            r"C:\Windows",
        )
        made["PATH"] = f"{root}\\System32;{root}"
        return made
    return {
        "PATH": CLOSED_PATH,
        "HOME": str(Path.home()),
        "TMPDIR": tempfile.gettempdir(),
        "LANG": "C.UTF-8",
    }


@contextlib.contextmanager
def quiet_terminal() -> Iterator[None]:
    """The terminal without its own echo while ``bw`` starts, where there is a ``termios``; on
    Windows there is none, and nothing changes."""
    try:
        import termios
    except ImportError:
        yield
        return
    try:
        descriptor = sys.stdin.fileno()
        before = termios.tcgetattr(descriptor)
    except (termios.error, OSError, ValueError):
        yield
        return
    quiet = termios.tcgetattr(descriptor)
    quiet[3] &= ~termios.ECHO
    termios.tcsetattr(descriptor, termios.TCSADRAIN, quiet)
    try:
        yield
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, before)


class Bw:
    """The CLI of Bitwarden — or, a secco, the script's own fake —, launched by its path with a
    data folder of the measure's own. **The session key reaches the child in its environment and
    never in argv**; the master password never reaches this process: an interactive launch leaves
    the terminal to ``bw`` and reads only its stdout."""

    def __init__(self, machine: Machine, program: Sequence[str], data: Path) -> None:
        self.machine = machine
        self.program = tuple(program)
        self.data = data

    def environment(self, session: str | None, *, interactive: bool) -> dict[str, str]:
        made = child_environment(self.machine.environ, self.machine.system())
        made["BITWARDENCLI_APPDATA_DIR"] = str(self.data)
        if not interactive:
            made["BW_NOINTERACTION"] = "true"
        if session is not None:
            made["BW_SESSION"] = session
        return made

    def run(
        self,
        *arguments: str,
        session: str | None = None,
        stdin: bytes | None = None,
        interactive: bool = False,
    ) -> Ran:
        reason = refused(arguments, session)
        if reason is not None:
            raise ValueError(reason)
        with quiet_terminal() if interactive else contextlib.nullcontext():
            return self.machine.run(
                [*self.program, *arguments],
                env=self.environment(session, interactive=interactive),
                stdin=stdin,
                interactive=interactive,
                timeout=None if interactive else BW_TIMEOUT_SECONDS,
            )

    def status(self, session: str | None = None) -> str:
        """``unauthenticated``, ``locked`` or ``unlocked`` — and nothing else of what ``bw status``
        prints: the address and the id of the account stay in this function."""
        ran = self.run("status", session=session)
        try:
            return str(json.loads(ran.out)["status"])
        except (ValueError, KeyError, TypeError):
            return f"illeggibile ({ran.said})"

    def server(self) -> str:
        return urlsplit(self.run("config", "server").out).hostname or "illeggibile"


@dataclass
class Vault:
    """What the measure holds of the vault while it runs: in memory, and nowhere else."""

    bw: Bw
    keys: list[str] = field(default_factory=list)
    unlocked_at: float | None = None
    entries_made: int = 0
    entries_gone: int = 0

    @property
    def key(self) -> str | None:
        return self.keys[-1] if self.keys else None


def parsed(text: str) -> object:
    try:
        return json.loads(text)
    except ValueError:
        return None


def invented_item(value: str, addresses: Sequence[str]) -> bytes:
    """The test entry as ``bw create item`` wants it on its stdin: invented values, loopback."""
    login = {
        "uris": [{"match": None, "uri": address} for address in addresses],
        "username": INVENTED_USER,
        "password": value,
        "totp": None,
    }
    item = {
        "organizationId": None,
        "collectionIds": None,
        "folderId": None,
        "type": 1,
        "name": INVENTED_NAME,
        "notes": None,
        "favorite": False,
        "fields": [],
        "login": login,
        "reprompt": 0,
    }
    return base64.b64encode(json.dumps(item).encode("utf-8"))


def b1(report: Report, machine: Machine, work: Work, *, real: bool) -> Bw | None:
    report.step("B1 — il programma del vault, e che sia di Bitwarden prima di lanciarlo")
    if real:
        path = Path.home() / ".ela" / "bin" / "bw.exe"
        if not machine.is_file(path):
            report.row(
                "B1", "SALTATO", f"{path} non c'è: il passo 5 della guida; bw non è lanciato"
            )
            return None
        facts = machine.file_facts([path])
        one = None if isinstance(facts, Failure) else facts.get(path)
        if one is None:
            why = facts.said if isinstance(facts, Failure) else "nessuna risposta"
            report.row("B1", "SALTATO", f"la firma non si legge ({why}): bw non è lanciato")
            return None
        report.fact(f"firma: Status {one.status}; il soggetto: {one.subject or 'nessuno'}")
        why_not = not_of_bitwarden(one)
        if why_not is not None:
            report.row(
                "B1",
                "SALTATO",
                f"{why_not}: la password principale non si scrive in un programma che non è il "
                "suo, e bw non è lanciato",
            )
            return None
        report.fact(f"sha256: {one.sha256}; versione del file: {one.version or 'non detta'}")
        program: tuple[str, ...] = (str(path),)
    else:
        fake = work.root / "bw-finto.py"
        fake.write_text(FAKE_VAULT, encoding="utf-8")
        program = (sys.executable, str(fake))
        report.fact("a secco: un vault finto dello script, un programma Python al posto di bw")
    data = work.root / "bw-data"
    data.mkdir(mode=0o700)
    bw = Bw(machine, program, data)
    try:
        version = bw.run("--version")
    except OSError as error:
        number = getattr(error, "winerror", None) or error.errno
        report.fact(f"bw --version non parte — errore {number}: {error.strerror or error}")
        if real:
            report.row("B1", "RIAPRE", "firmato da Bitwarden, e bloccato", stops=True)
        else:
            report.failed("il vault finto dello script non parte")
        return None
    report.fact(f"bw --version: {first_line(version.out, 60)!r} ({version.said})")
    if version.code == 0 and version.out:
        report.row("B1", "PASSATO", "parte, e stampa una versione")
        return bw
    report.row("B1", "SALTATO", "è partito ma non ha stampato una versione: il resto non si fa")
    return None


def a_key(
    report: Report, ask: Callable[[str], str], bw: Bw, command: str, *, real: bool
) -> str | None:
    """``bw login --raw`` or ``bw unlock --raw`` with the terminal left to ``bw``: the key it wrote
    on its stdout — registered before anything else is said —, or ``None``."""
    for _ in range(3):
        report.say(
            f"    Parte bw {command}: aspetta che mostri la sua domanda, e scrivi lì. Lo script "
            "non legge ciò che scrivi."
        )
        started = time.monotonic()
        ran = bw.run(command, "--raw", interactive=True)
        seconds = round(time.monotonic() - started)
        if ran.code == 0 and ran.out:
            report.secret(ran.out)
            report.fact(
                f"K1: bw {command} --raw ha scritto sul suo stdout {len(ran.out)} caratteri, in "
                f"{len(ran.out.splitlines())} riga, in {seconds} s, il tempo di Tommaso compreso"
            )
            return ran.out
        report.fact(f"bw {command} è uscito con {ran.code}, senza una chiave")
        if not real or not yes_or_no(ask, report, f"bw {command} non è riuscito: riprovare?"):
            break
    return None


def swept(vault: Vault) -> int | None:
    bw, key = vault.bw, vault.key
    left = parsed(bw.run("list", "items", "--search", INVENTED_NAME, session=key).out)
    if not isinstance(left, list):
        return None
    ours = [item for item in left if isinstance(item, dict) and item.get("name") == INVENTED_NAME]
    for item in ours:
        bw.run("delete", "item", str(item.get("id")), "--permanent", session=key)
    return len(ours)


def none_left(vault: Vault) -> bool:
    bw, key = vault.bw, vault.key
    left = parsed(bw.run("list", "items", "--search", INVENTED_NAME, session=key).out)
    return isinstance(left, list) and not any(
        isinstance(item, dict) and item.get("name") == INVENTED_NAME for item in left
    )


def b2(
    report: Report,
    ask: Callable[[str], str],
    bw: Bw,
    made: list[Vault],
    *,
    real: bool,
) -> None:
    report.step("B2 — una cartella dei dati nuova, e il server")
    state = bw.status()
    if not (bw.data / "data.json").exists():
        report.failed("bw non scrive nella cartella dei dati della misura: il resto non si fa")
        return
    made.append(Vault(bw))
    vault = made[0]
    if state != "unauthenticated":
        report.failed(f"una cartella dei dati nuova dovrebbe dire unauthenticated, e dice {state}")
        return
    region = "" if real else "com"
    while region not in SERVERS:
        region = ask("L'account sta su bitwarden.com o su bitwarden.eu? (com/eu) ").strip().lower()
    address, host = SERVERS[region]
    if address is not None:
        bw.run("config", "server", address)
    read = bw.server()
    if read != host:
        report.failed(f"il server di bw dovrebbe essere {host}, ed è {read}: niente login")
        return
    report.passed(f"il server di bw: {read} (risposta: {region})")

    report.step("B2 — bw login: l'indirizzo e la password principale li chiede bw, sul terminale")
    if real:
        report.say(
            "    Al primo login da una cartella dei dati nuova Bitwarden può chiedere un codice "
            "arrivato per email: lo scrivi dentro bw, come la password."
        )
        ask("Premi Invio quando sei pronto a scrivere dentro bw: ")
    key = a_key(report, ask, bw, "login", real=real)
    if key is None:
        report.row("B2", "SALTATO", "bw login non ha dato una chiave: il vault non si è aperto")
        return
    vault.keys.append(key)
    vault.unlocked_at = time.monotonic()
    with_key, without = bw.status(key), bw.status()
    report.fact(f"bw status con la chiave nell'ambiente: {with_key}; senza: {without}")
    if with_key != "unlocked":
        vault.unlocked_at = None
        report.row(
            "B2",
            "RIAPRE",
            "la chiave scritta sullo stdout non apre il vault: la strada della chiave sul PC",
            stops=True,
        )
        return
    report.row(
        "B2", "PASSATO", "la chiave arriva sullo stdout, con la password chiesta sul terminale"
    )
    if real:
        yes_or_no(
            ask, report, "bw ti ha chiesto un codice arrivato per email, da dispositivo nuovo?"
        )
    entry(report, vault)
    keys(report, ask, vault, real=real)


def entry(report: Report, vault: Vault) -> None:
    """The round trip of one entry: invented here, created, read back, deleted."""
    report.step("B2 — una voce di prova: creata, riletta, cancellata")
    bw, key = vault.bw, vault.key
    invented = "parola-inventata-" + hashlib.sha256(os.urandom(16)).hexdigest()[:20]
    report.secret(invented)
    report.secret(INVENTED_NAME)
    report.secret(INVENTED_USER)
    before = swept(vault)
    if before:
        report.fact(f"voci di prova rimaste da una misura interrotta, cancellate prima: {before}")
    port = free_port()
    first, second = f"http://127.0.0.1:{port}/login", f"http://127.0.0.1:{port}/secondo"
    vault.entries_made += 1
    created = bw.run("create", "item", session=key, stdin=invented_item(invented, (first, second)))
    made = parsed(created.out)
    if created.code != 0 or not isinstance(made, dict) or "id" not in made:
        report.row("B2 voce", "SALTATO", f"bw create item non ha dato una voce ({created.said})")
        return
    identifier = str(made["id"])
    report.fact(f"creata in {created.ms} ms, con il JSON sullo stdin e mai in argv")
    round_trip = False
    try:
        listed = parsed(bw.run("list", "items", "--url", first, session=key).out)
        ours = isinstance(listed, list) and any(
            isinstance(i, dict) and i.get("id") == identifier for i in listed
        )
        user = bw.run("get", "username", identifier, session=key)
        word = bw.run("get", "password", identifier, session=key)
        report.fact(
            f"bw list items --url la trova: {'sì' if ours else 'no'}; bw get username rende il "
            f"nome inventato: {'sì' if user.out == INVENTED_USER else 'no'}; bw get password "
            f"rende il valore inventato: {'sì' if word.out == invented else 'no'}"
        )
        round_trip = ours and user.out == INVENTED_USER and word.out == invented
    finally:
        deleted = bw.run("delete", "item", identifier, "--permanent", session=key)
        after = bw.run("get", "item", identifier, session=key)
        gone = after.code != 0 and bw.status(key) == "unlocked"
        clean = none_left(vault)
        report.fact(
            f"cancellata per sempre ({deleted.said}); bw get item dopo: {after.said}; una ricerca "
            f"del suo nome non ne trova più: {'sì' if clean else 'no'}"
        )
    if gone and clean:
        vault.entries_gone += 1
    if not (gone and clean):
        report.row(
            "B2 voce",
            "FALLITO",
            "la voce di prova non risulta cancellata: è da togliere a mano (il suo nome è "
            "INVENTED_NAME in scripts/misura_m13_11.py)",
        )
    elif round_trip:
        report.row("B2 voce", "PASSATO", "la voce ha fatto il giro, ed è cancellata")
    else:
        report.row(
            "B2 voce", "RIAPRE", "la voce è cancellata, ma il giro non ha reso il suo valore"
        )


def keys(report: Report, ask: Callable[[str], str], vault: Vault, *, real: bool) -> None:
    """K2: what a new ``bw unlock`` does to the key before it, **asked while that key is alive**."""
    report.step("B2 — un nuovo bw unlock, con la prima chiave ancora viva")
    bw, first = vault.bw, vault.key
    before = bw.status(first)
    if before != "unlocked":
        vault.unlocked_at = None
        report.row("B2 K2", "SALTATO", f"la chiave di prima non apre più il vault ({before})")
        return
    if real:
        report.say("    Bw ti chiede di nuovo la password principale: è il nuovo sblocco.")
    key = a_key(report, ask, bw, "unlock", real=real)
    if key is None:
        report.row("B2 K2", "SALTATO", "bw unlock non ha dato una chiave")
        return
    old, new = bw.status(first), bw.status(key)
    report.fact(
        f"K2: subito dopo il nuovo unlock la chiave di prima dice: {old}; quella nuova: {new}"
    )
    if key != first:
        vault.keys.append(key)
    if new != "unlocked":
        if old != "unlocked":
            vault.unlocked_at = None
        report.row("B2 K2", "RIAPRE", "la chiave scritta da bw unlock --raw non apre il vault")
        return
    vault.unlocked_at = time.monotonic()
    if old == "unlocked":
        report.row(
            "B2 K2",
            "RIAPRE",
            "un nuovo unlock non chiude la chiave di prima, sul Mac sì: l'ora e la chiusura di "
            "ADR 0063 §3, sul PC",
        )
    else:
        report.row("B2 K2", "PASSATO", "un nuovo unlock chiude la chiave di prima, come sul Mac")


def still_open(report: Report, vault: Vault) -> None:
    """K3: whether the key still opens the vault after the time the rest of the measure took."""
    report.step("B2 — quanto dura la chiave senza essere usata, per il tempo di questa misura")
    if vault.key is None or vault.unlocked_at is None:
        report.row("B2 K3", "SALTATO", "il vault non è rimasto aperto con una chiave buona")
        return
    idle = round(time.monotonic() - vault.unlocked_at)
    state = vault.bw.status(vault.key)
    report.fact(f"K3: {idle} s dopo l'ultimo unlock, senza nessun uso, la chiave dice: {state}")
    if state == "unlocked":
        report.row("B2 K3", "PASSATO", f"la chiave vale ancora dopo {idle} s")
    else:
        report.row("B2 K3", "RIAPRE", f"la chiave è caduta da sola entro {idle} s: ADR 0063 §3")


def close_the_vault(report: Report, vault: Vault) -> None:
    """The end, whatever happened before: the test entry swept, ``bw lock`` read on every key the
    measure had, ``bw logout``, the data folder gone — **each asked of bw**, not remembered."""
    report.step("B2 — la fine: il vault chiuso, l'uscita dall'account, la cartella cancellata")
    bw = vault.bw
    state = bw.status(vault.key)
    report.fact(f"prima di chiudere, bw dice: {state}")
    entries = "nessuna creata"
    if vault.entries_made:
        if state == "unlocked":
            swept(vault)
            entries = "nessuna rimasta" if none_left(vault) else "UNA È RIMASTA"
        elif vault.entries_gone == vault.entries_made:
            entries = "nessuna rimasta (verificato quando è stata cancellata)"
        else:
            entries = "NON VERIFICABILE: il vault è chiuso"
    report.fact(f"voci di prova nel vault: {entries}")
    after: list[str] = []
    if state != "unauthenticated":
        lock = bw.run("lock", session=vault.key)
        after = [bw.status(key) for key in vault.keys] or [bw.status()]
        logout = bw.run("logout")
        report.fact(f"dopo bw lock ({lock.said}) le chiavi della misura dicono: {', '.join(after)}")
        report.fact(f"bw logout: {logout.said}")
    out = bw.status()
    report.fact(f"alla fine bw status dice: {out}")
    vault.keys.clear()
    shutil.rmtree(bw.data, ignore_errors=True)
    gone = not bw.data.exists()
    report.fact(f"la cartella dei dati della misura non c'è più: {'sì' if gone else 'no'}")
    if any(said != "locked" for said in after) or out != "unauthenticated" or not gone:
        report.failed(
            "la chiusura non è verificata: dal vault web, Impostazioni → Sicurezza, si chiudono "
            "le sessioni rimaste"
        )
    elif not entries.startswith(("nessuna creata", "nessuna rimasta")):
        report.failed("una voce di prova può essere rimasta nel vault: è da togliere a mano")
    else:
        report.passed("il vault è chiuso, l'account è lasciato, e la misura non tiene niente di bw")


FIRST: Final = f"""import sys

sys.stdout.buffer.write({KEY_LINE!r}.encode("ascii") + b"\\n")
sys.stdout.buffer.write({NON_ASCII!r}.encode("utf-8") + b"\\n")
sys.stdout.buffer.flush()
"""
"""The first program of B3, in place of ``bw``: a line of the shape of a key, and one that is not
ASCII, as bytes."""

SECOND: Final = """import sys
from pathlib import Path

Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())
"""
"""The second program of B3, in place of ELA: the bytes it received, in a file of the script's."""


def quoted(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def pipe_line(python: str, first: str, second: str, out: str) -> str:
    return (
        "$ProgressPreference = 'SilentlyContinue'\n"
        "[Console]::Out.WriteLine($PSVersionTable.PSVersion.ToString())\n"
        f"& {quoted(python)} {quoted(first)} | & {quoted(python)} {quoted(second)} {quoted(out)}\n"
    )


def pipe_argv(shell: str, python: str, first: str, second: str, out: str) -> list[str]:
    """The shell without its profile, the line in ``-EncodedCommand`` (B3)."""
    return [
        shell,
        "-NoProfile",
        "-NonInteractive",
        "-EncodedCommand",
        encoded(pipe_line(python, first, second, out)),
    ]


@dataclass(frozen=True)
class Piped:
    """What the second program of B3 received: whether the line of the shape of a key arrived
    whole, the end of its line, and what became of the line that is not ASCII."""

    size: int
    intact: bool
    ending: str
    other: str


def read_pipe(received: bytes | None) -> Piped:
    if received is None:
        return Piped(0, False, "nessuna", "niente è arrivato")
    lines = received.split(b"\n")
    head = lines[0]
    ending = "CRLF" if head.endswith(b"\r") else ("LF" if len(lines) > 1 else "nessuna")
    bom = head.startswith(b"\xef\xbb\xbf")
    intact = head.rstrip(b"\r") == KEY_LINE.encode("ascii")
    second = lines[1].rstrip(b"\r") if len(lines) > 1 else b""
    if second == NON_ASCII.encode("utf-8"):
        other = "arriva in UTF-8, intatta"
    else:
        other = f"arriva diversa — i suoi byte: {second.hex(' ') or 'nessuno'}"
    if bom:
        other += "; la prima riga comincia con un BOM"
    return Piped(len(received), intact, ending, other)


def b3(report: Report, machine: Machine, work: Work) -> None:
    report.step("B3 — il tubo: ciò che il primo programma stampa, come arriva al secondo")
    first, second = work.root / "primo.py", work.root / "secondo.py"
    first.write_text(FIRST, encoding="utf-8")
    second.write_text(SECOND, encoding="utf-8")
    report.fact(f"la riga della forma di una chiave: {len(KEY_LINE)} caratteri ASCII, inventata")
    shells = machine.shells()
    present = 0
    whole = 0
    for name in ("powershell.exe", "pwsh.exe"):
        row = f"B3 {name}"
        where = shells.get(name)
        if where is None:
            report.row(row, "SALTATO", "questa shell non c'è")
            continue
        present += 1
        out = work.root / f"tubo-{Path(name).stem}.bin"
        argv = pipe_argv(str(where), sys.executable, str(first), str(second), str(out))
        try:
            ran = machine.run(argv, env=without_module_path(machine.environ), timeout=120.0)
        except OSError as error:
            report.row(row, "SALTATO", f"non parte: {error.strerror or error}")
            continue
        piped = read_pipe(out.read_bytes() if out.exists() else None)
        report.fact(
            f"{name} {first_line(ran.out, 40) or '?'} ({ran.said}): {piped.size} byte; la riga "
            f"della forma di una chiave arriva intera: {'sì' if piped.intact else 'no'}; fine "
            f"riga {piped.ending}; la riga non ASCII {piped.other}"
        )
        if piped.intact:
            whole += 1
            report.row(row, "PASSATO", f"la riga arriva intera, con la fine {piped.ending}")
        else:
            report.row(row, "RIAPRE", "la riga non arriva intera in questa shell")
    if whole:
        report.row("B3", "PASSATO", f"in {whole} shell su {present} la riga arriva intera")
    elif present:
        report.row(
            "B3",
            "RIAPRE",
            "in nessuna shell la riga arriva intera: la strada della chiave sul PC",
            stops=True,
        )
    else:
        report.row("B3", "SALTATO", "nessuna delle due shell c'è")


def part_b(
    report: Report,
    machine: Machine,
    ask: Callable[[str], str],
    *,
    real: bool,
    work: Work,
    vaults: list[Vault],
) -> None:
    report.say("\n# Parte B — il vault del PC")
    bw = b1(report, machine, work, real=real)
    if bw is None:
        report.row("B2", "SALTATO", "B1 non ha dato un bw da lanciare: il login non si fa")
    else:
        b2(report, ask, bw, vaults, real=real)
    b3(report, machine, work)
    if vaults:
        still_open(report, vaults[0])


FAKE_VAULT: Final = '''"""Il vault finto della misura di M13.11, a secco: non è bw.

Risponde ai comandi che la misura compone, con lo stato in BITWARDENCLI_APPDATA_DIR; un nuovo
unlock chiude le chiavi di prima, come K2 ha misurato sul Mac.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

ADDRESS = "finto@example.invalid"


def host_of(address):
    return urlsplit(address).hostname or ""


def answer(arguments, environment, stdin):
    data = Path(environment["BITWARDENCLI_APPDATA_DIR"])
    data.mkdir(parents=True, exist_ok=True)
    file = data / "data.json"
    state = json.loads(file.read_text(encoding="utf-8")) if file.exists() else {}

    def save():
        file.write_text(json.dumps(state), encoding="utf-8")

    save()
    words = [word for word in arguments if word != "--raw"]
    if words == ["--version"]:
        return 0, "0.0.0-finto", ""
    command, rest = words[0], words[1:]
    account = state.get("account")
    open_ = account is not None and environment.get("BW_SESSION") in state.get("keys", [])
    if command == "status":
        if account is None:
            return 0, json.dumps({"serverUrl": None, "status": "unauthenticated"}), ""
        status = "unlocked" if open_ else "locked"
        said = {"serverUrl": state.get("server"), "userEmail": ADDRESS, "status": status}
        return 0, json.dumps(said), ""
    if command == "config":
        if len(rest) == 1:
            return 0, state.get("server") or "https://bitwarden.com", ""
        state["server"] = rest[1]
        save()
        return 0, "Saved setting config.", ""
    if command == "login":
        if account is not None:
            return 1, "", "You are already logged in."
        state["account"] = str(uuid.uuid4())
        key = base64.b64encode(secrets.token_bytes(64)).decode("ascii")
        state["keys"] = [key]
        save()
        return 0, key, ""
    if account is None:
        return 1, "", "You are not logged in."
    if command == "unlock":
        key = base64.b64encode(secrets.token_bytes(64)).decode("ascii")
        state["keys"] = [key]
        save()
        return 0, key, ""
    if command == "lock":
        state["keys"] = []
        save()
        return 0, "Your vault is locked.", ""
    if command == "logout":
        state.clear()
        save()
        return 0, "You have logged out.", ""
    if not open_:
        return 1, "", "Vault is locked."
    items = state.setdefault("items", {})
    if command == "create":
        item = json.loads(base64.b64decode(stdin))
        item["id"] = str(uuid.uuid4())
        items[item["id"]] = item
        save()
        return 0, json.dumps(item), ""
    if command == "list":
        found = list(items.values())
        if "--url" in rest:
            host = host_of(rest[rest.index("--url") + 1])
            found = [
                one for one in found
                if any(host_of(uri["uri"]) == host for uri in one["login"]["uris"])
            ]
        if "--search" in rest:
            term = rest[rest.index("--search") + 1].lower()
            found = [one for one in found if term in one["name"].lower()]
        return 0, json.dumps(found), ""
    if command == "get":
        item = items.get(rest[1])
        if item is None:
            return 1, "", "Not found."
        return 0, {
            "item": json.dumps(item),
            "uri": item["login"]["uris"][0]["uri"],
            "username": item["login"]["username"],
            "password": item["login"]["password"],
        }[rest[0]], ""
    if command == "delete":
        if items.pop(rest[1], None) is None:
            return 1, "", "Not found."
        save()
        return 0, "", ""
    return 1, "", "comando sconosciuto"


if __name__ == "__main__":
    arguments = sys.argv[1:]
    given = sys.stdin.buffer.read() if arguments[:1] == ["create"] else b""
    code, out, err = answer(arguments, dict(os.environ), given)
    sys.stdout.write(out)
    sys.stderr.write(err)
    raise SystemExit(code)
'''
"""The vault of the dry run: a program of the script's, launched with this interpreter in place of
``bw``, with the same environment and the same closed list of commands. Its key is invented at
every login and every unlock; its status carries an address, which the file must not."""


# ---------------------------------------------------------------------------------------------
# La fine: gli strati, i processi, la cartella, il file
# ---------------------------------------------------------------------------------------------


def describe(name: str, verdict: Verdict | None) -> str:
    if verdict is None:
        return f"{name} (non misurata)"
    if verdict.word == "RIAPRE":
        return f"{name} (RIAPRE, ferma)"
    return f"{name} ({verdict.word})"


def strata(rows: Mapping[str, Verdict], part: str) -> dict[str, tuple[str, list[str]]]:
    """Which stratum starts, with what this part's file says (decision 14, as received on
    2026-11-20): a stratum starts if every row it wants is PASSATO or RIAPRE without stopping it;
    a row of the other part is read with that part's file."""
    decided: dict[str, tuple[str, list[str]]] = {}
    for name, wanted in STRATA.items():
        stopping: list[str] = []
        elsewhere: list[str] = []
        for one in wanted:
            if one in decided:
                state, _ = decided[one]
                if state == STOPPED:
                    stopping.append(f"{one} non comincia")
                elif state == ELSEWHERE:
                    elsewhere.append(one)
            elif one[0] != part:
                elsewhere.append(one)
            elif not fine(rows.get(one)):
                stopping.append(describe(one, rows.get(one)))
        if stopping:
            decided[name] = (STOPPED, stopping)
        elif elsewhere:
            decided[name] = (ELSEWHERE, elsewhere)
        else:
            decided[name] = (STARTS, [])
    first, second = decided["S1"][0], decided["S2"][0]
    if STARTS in (first, second):
        decided["S4"] = (STARTS, ["con S1 o S2; nel taglio, con la fermata fino al nodo o dopo"])
    elif first == second == STOPPED:
        decided["S4"] = (STOPPED, ["né S1 né S2 cominciano"])
    else:
        decided["S4"] = (ELSEWHERE, ["S1", "S2"])
    return decided


def strata_table(report: Report, part: str) -> None:
    report.say("\n## Gli strati — la tabella che vale dal 2026-11-20 (decisione 45)")
    decided = strata(report.rows, part)
    for name, (state, why) in decided.items():
        report.say(f"- {name}: {state}" + (f" — {'; '.join(why)}" if why else ""))
    if decided["S1"][0] == decided["S2"][0] == STOPPED:
        report.say("Nessuno strato comincia: la milestone non comincia (decisione 14).")


def removed(folder: Path) -> bool:
    """The folder taken away — again, a few times, if a process that just ended still held a
    file —, and verified."""
    for _ in range(5):
        shutil.rmtree(folder, ignore_errors=True)
        if not folder.exists():
            return True
        time.sleep(1.0)
    return not folder.exists()


def the_end(report: Report, machine: Machine, work: Work) -> None:
    report.step("la fine: i processi dello script, la cartella temporanea, il file")
    problems: list[str] = []
    table = machine.processes()
    if isinstance(table, Failure):
        report.fact(f"i processi non si leggono: {table.said}")
        problems.append("i processi dello script non si verificano")
    else:
        alive = descendants(machine.pid(), table)
        report.fact(f"processi dello script vivi alla fine: {counted(alive)}")
        if alive:
            for pid, _ in alive:
                machine.kill_tree(pid)
            problems.append("dei processi dello script erano vivi alla fine")
    gone = removed(work.root)
    report.fact(
        f"la cartella temporanea della misura, con i profili, non c'è più: {'sì' if gone else 'no'}"
    )
    if not gone:
        problems.append("la cartella temporanea della misura è rimasta")
    for problem in problems:
        report.failed(problem)


def the_file(report: Report) -> None:
    """The file read back from the disk: nothing it must not carry — or FALLITO, and it does not
    leave the PC (step 7 of the guide)."""
    found = report.found_in_the_file()
    if found:
        report.fact("nel file: " + " e ".join(found))
        report.failed(
            "il file porta ciò che non deve: non lascia il PC — dillo al revisore (passo 7)"
        )
    else:
        report.fact(
            "nel file: niente di ciò che non deve — nessun valore trattenuto, nessun indirizzo, "
            "né la casa, né un nome utente, né il nome della macchina, né un SID"
        )
        report.passed("il file si rilegge pulito, e si può mandare")


# ---------------------------------------------------------------------------------------------
# La misura
# ---------------------------------------------------------------------------------------------


def duty(report: Report, what: str, call: Callable[[], None]) -> None:
    """A duty of the closing: one that breaks is FALLITO, and the closing goes on to the file."""
    try:
        call()
    except Exception as error:  # noqa: BLE001 — a duty not verified is said, never left silent
        report.failed(f"{what} si è rotta: {type(error).__name__} alla riga {line_of(error)}")


def line_of(error: BaseException) -> int:
    here, found, trace = str(Path(__file__).resolve()), 0, error.__traceback__
    while trace is not None:
        if str(Path(trace.tb_frame.f_code.co_filename).resolve()) == here:
            found = trace.tb_lineno
        trace = trace.tb_next
    return found


def measure(
    report: Report,
    part: str,
    mode: str,
    *,
    machine: Machine,
    ask: Callable[[str], str],
    temporary: Path | None = None,
) -> int:
    real = mode == "vera"
    report.say(
        f"Quando: {datetime.now():%Y-%m-%d %H:%M:%S}; il commit: {machine.commit()}; il "
        f"sistema: {machine.system()}"
    )
    if not real:
        report.say("A secco: niente di ciò che segue è una misura del PC; dice se lo script gira.")
    root = Path(tempfile.mkdtemp(prefix="ela-misura-m1311-", dir=temporary)).resolve()
    work = Work(root, machine.environ)
    vaults: list[Vault] = []
    pages = Pages() if part == "A" and real else None

    def ended(number: int, frame: object) -> None:
        raise Interrupted(signal.Signals(number).name)

    names = ("SIGHUP", "SIGTERM", "SIGBREAK")
    watched = [getattr(signal, one) for one in names if hasattr(signal, one)]
    before = {one: on_signal(one, ended) for one in watched}
    try:
        if part == "A":
            part_a(report, machine, real=real, work=work, pages=pages)
        else:
            part_b(report, machine, ask, real=real, work=work, vaults=vaults)
    except (KeyboardInterrupt, Interrupted) as stop:
        report.interrupted = True
        report.say(
            f"\nINTERROTTA ({type(stop).__name__}) al passo {report.number}: ciò che segue è la "
            "chiusura, e dice da sé che cosa ha verificato."
        )
    except FenceBroken as broken:
        report.step("una recinzione")
        report.failed(f"una recinzione non ha tenuto: {broken}; la parte si ferma qui")
    except Exception as error:  # noqa: BLE001 — a defect of the measure is said, then cleaned up
        report.step("un errore della misura")
        report.failed(
            f"la misura si è rotta: {type(error).__name__} alla riga {line_of(error)} di "
            "scripts/misura_m13_11.py; ciò che segue è la chiusura"
        )
    finally:
        quiet = on_signal(signal.SIGINT, signal.SIG_IGN)
        for one in watched:
            on_signal(one, signal.SIG_IGN)
        try:
            if vaults:
                duty(report, "la chiusura del vault", lambda: close_the_vault(report, vaults[0]))
            if pages is not None:
                pages.close()
            duty(report, "la fine", lambda: the_end(report, machine, work))
            strata_table(report, part)
            the_file(report)
            report.verdict()
        finally:
            if quiet is not None:
                on_signal(signal.SIGINT, quiet)
            for one, handler in before.items():
                if handler is not None:
                    on_signal(one, handler)
    return 0 if report.ok else 1


def default_out(part: str, mode: str) -> Path:
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}"
    tag = "" if mode == "vera" else "a-secco-"
    return Path.home() / "Downloads" / f"misura-m13.11-{tag}{part}-{stamp}.txt"


def main(
    argv: Sequence[str] | None = None,
    ask: Callable[[str], str] = input,
    machine: Machine | None = None,
    temporary: Path | None = None,
    echo: Callable[[str], None] = screen,
) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("parte", choices=("A", "B"), help="A senza account, B con il vault")
    parser.add_argument(
        "--a-secco",
        action="store_const",
        const="a-secco",
        dest="mode",
        help="nessun browser lanciato, nessuna domanda; per B un vault finto dello script",
    )
    parser.add_argument("--out", type=Path, default=None)
    arguments = parser.parse_args(argv)
    part, mode = arguments.parte, arguments.mode or "vera"
    asked_here = mode == "vera" and part == "B" and ask is input
    if asked_here and not (sys.stdin.isatty() and sys.stderr.isatty()):
        print(
            "La parte B vuole un terminale, con lo stderr sullo schermo: bw chiede lì la "
            "password principale.",
            file=sys.stderr,
        )
        return 2
    here = machine or Pc()
    users, machines = here.who()
    report = Report(
        arguments.out or default_out(part, mode),
        echo,
        Filter(home=here.home(), users=users, machines=machines),
    )
    report.say(f"# La misura di M13.11, parte {part} ({mode})\n\nIl file: {report.path}\n")
    try:
        return measure(report, part, mode, machine=here, ask=ask, temporary=temporary)
    finally:
        report.say(f"\nIl file: {report.path}")
        report.close()


if __name__ == "__main__":
    raise SystemExit(main())
