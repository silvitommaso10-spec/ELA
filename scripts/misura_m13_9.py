"""La misura di M13.9 che vuole Tommaso: l'account Bitwarden, e un login Google nel Chrome di ELA.

    uv run python scripts/misura_m13_9.py              # la misura
    uv run python scripts/misura_m13_9.py --a-secco    # nessun account, nessuna domanda

**La lancia Tommaso, dal repository, con un comando solo** (SPEC di M13.9, decisione 4). Scrive
tutto in un file, ``~/Downloads/misura-m13.9-<data e ora>.txt``, e lo stampa anche qui. Le misure
che non vogliono Tommaso sono già in ``docs/milestones/M13.9.md``, «Le misure della notte»; questa
prende le altre, e risponde alle righe di «La regola scritta prima dei numeri» (G1–G5, K1–K3,
V1–V3).

**Lo script non riceve mai una password.** Quella principale di Bitwarden la chiede ``bw``, sul
terminale, a Tommaso: lo script lancia ``bw`` con il terminale in mano e legge solo ciò che ``bw``
scrive sul suo stdout con ``--raw``, cioè la chiave di sessione. Quella di Google la scrive Tommaso
nella finestra di Chrome. Lo script non le chiede, non le legge, non le passa.

**Il file va in chat**, e non contiene password, chiavi di sessione, cookie, nomi di voci, nomi
utente né indirizzi email: numeri, sì e no, versioni, codici. Ogni riga passa da un filtro prima di
essere scritta (:func:`withheld`), e alla fine lo script rilegge il file e lo dice.

Che cosa fa, nell'ordine:

* **Bitwarden**, con una cartella dei dati sua, che alla fine cancella: dove sta ``bw``, **e che
  sia di Bitwarden prima di lanciarlo** — ``codesign --verify --strict`` deve passare e il team
  della firma deve essere il suo: la password principale non si scrive in un programma che non è
  il suo, e fra i posti in cui lo script cerca vale il primo che passa —; l'unica domanda —
  bitwarden.com o bitwarden.eu —; ``bw login`` e ``bw unlock``, con la chiave **solo in memoria**
  e, per i figli, **solo nell'ambiente**, mai in ``argv``; una **voce di prova** con un valore
  inventato qui e l'indirizzo di una pagina locale, creata, riletta e cancellata; che cosa fa un
  nuovo ``bw unlock`` alla chiave di prima, **chiesto mentre quella è ancora viva**, e quanto dura
  una chiave; e alla fine ``bw lock``, letto su ogni chiave che la misura ha avuto, l'uscita
  dall'account, e la verifica di tutti e due. **Nessuna password vera entra nel vault.**
* **Google**, in una cartella di profilo di prova, che alla fine cancella. **Prima** la finestra
  del binario lanciata senza automazione, su una cartella pulita (G1): è la riga che decide il
  binario, e un login fatto prima da un'altra finestra la falserebbe. Poi se quel login si ritrova
  in un lancio di Playwright (G3), se il browser risulta collegato all'account, letto da
  ``Default/Preferences`` (G4), e l'uscita dall'account, verificata. **Dopo**, sulla stessa cartella
  ormai fuori dall'account, la finestra lanciata da Playwright (G2), e di nuovo l'uscita.

Le parole dell'esito, una per significato: **PASSATO** — misurato, e la risposta lascia la decisione
com'è —; **RIAPRE** — misurato, e la risposta riapre la riga che nomina —; **SALTATO** — non
misurato, perché il mondo non l'ha dato: un login rifiutato da ``bw``, un binario che manca, un
browser che ha sollevato, un ``bw`` che Bitwarden non ha firmato —; **FALLITO** — un dovere dello
script non verificato: la chiusura, il file, la cancellazione, **una recinzione che non ha
tenuto**. Ogni passo che vuole la mano di Tommaso ha una precondizione che lo script verifica.

**Le recinzioni restano**: mai la cartella di profilo del Chrome di Tommaso, mai il portachiavi —
ogni lancio porta ``--use-mock-keychain``, riletto dal processo prima che lo script vada avanti —,
e ogni cartella di prova nasce sotto una cartella temporanea di questo script. Una recinzione che
non tiene è FALLITO con la sua frase, e ferma la parte di Google lì. **Una cosa sola è
diversa dalla notte del 2026-10-10**: se Google rifiuta Chrome for Testing, la riga G1 vuole lo
stesso login nel Chrome installato «nelle stesse condizioni», cioè in una finestra del suo binario
lanciata da qui e non da Playwright — su una cartella di prova nuova, con ``--use-mock-keychain``.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Final, Protocol, TextIO
from urllib.parse import urlsplit

ROOT: Final = Path(__file__).resolve().parents[1]
EMAIL: Final = re.compile(r"[A-Za-z0-9._%+-]+(?:@|%40)[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
YES: Final = frozenset({"s", "si", "sì"})
NO: Final = frozenset({"n", "no"})
FORBIDDEN_PROFILE: Final = "Application Support/Google/Chrome"
"""The folder of the profile of the installed Chrome: never opened, read, copied or listed."""

MOCK_KEYCHAIN: Final = "--use-mock-keychain"
BARE_WINDOW: Final = (MOCK_KEYCHAIN, "--no-first-run", "--no-default-browser-check")
WINDOW_ARGUMENTS: Final = (*BARE_WINDOW, "--disable-sync", "--allow-browser-signin=false")
"""What a window of the binary launched **without automation** receives, beside its folder and an
address: no debugging pipe, no port, no driver (SPEC, proposta 8). ``BARE_WINDOW`` is the same
without what switches the browser's own sign-in off: only G5 uses it, to see what the binary does
when nothing stops it."""

PREFERENCES: Final[Mapping[str, Any]] = {
    "credentials_enable_service": False,
    "credentials_enable_autosignin": False,
    "profile": {"password_manager_leak_detection": False},
    "autofill": {"profile_enabled": False, "credit_card_enabled": False},
    "signin": {"allowed": False, "allowed_on_next_startup": False},
}
"""The preferences the SPEC proposes for ELA's profile (proposta 3): here written once, when a test
folder is made, before its first launch."""

LINKED_KEYS: Final = (
    "account_info",
    "google.services.account_id",
    "google.services.last_username",
    "google.services.consented_to_sync",
    "sync.has_setup_completed",
    "signin.allowed",
)
"""What says whether the browser is linked to a Google account (G4): read as presence and booleans,
never as values — an account id and a username are Tommaso's."""


@dataclass(frozen=True)
class Words:
    """The words of one command of ``bw`` this script uses: the objects it names, its options, and
    how many free values — an id, an address — may follow the object."""

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
"""Every command of ``bw`` this script composes, with the words it uses of each: a closed list.
:func:`refused` holds every launch to it, word by word, and a test holds it against the help of the
real CLI, recorded without an account. ``login`` and ``unlock`` take **no** value: the master
password is never an argument."""

VALUED: Final = frozenset({"--url", "--search"})
"""The options of the list above that take a value: the word after them is that value."""

BW_TIMEOUT_SECONDS: Final = 60
"""How long a launch of ``bw`` that asks nothing of Tommaso may take: measured at 1,2 s without an
account; a network that does not answer must not hold the measure, and its vault, open."""

SAVED_TABLES: Final = (
    ("logins", "Login Data", "logins"),
    ("stats", "Login Data", "stats"),
    ("autofill", "Web Data", "autofill"),
)
"""Where Chrome would keep a saved password, the record of an offer to save, and a remembered
value of a form (measure 7 of the night): each read as a count of rows."""

SESSION_COOKIES: Final = frozenset({"SID", "__Secure-1PSID", "__Secure-3PSID"})
"""The names of the cookies that say «signed in» at Google (the local pages of the dry run use the
first): looked for by name, their values never kept."""

CLOSED_PATH: Final = "/usr/bin:/bin:/usr/sbin:/sbin"
CODESIGN: Final = Path("/usr/bin/codesign")
BITWARDEN_TEAM: Final = "LTZ2PFU5D6"
BITWARDEN_S: Final = f'anchor apple generic and certificate leaf[subject.OU] = "{BITWARDEN_TEAM}"'
"""What a ``bw`` must satisfy before this script launches it at all (decision 43): signed with a
certificate Apple gave Bitwarden's team. The team is read from the certificate, by ``codesign``,
and not from what the binary says of itself."""
INVENTED_NAME: Final = "ELA-misura-M13.9-voce-di-prova"
INVENTED_USER: Final = "utente-inventato-m139"
SERVERS: Final = {
    "com": (None, "bitwarden.com"),
    "eu": ("https://vault.bitwarden.eu", "vault.bitwarden.eu"),
}
"""For each answer to the one question: what ``bw config server`` is given — nothing for the
default —, and the host ``bw config server`` must then read."""

KNOWN: Final = {
    "You are not logged in.": "non autenticato",
    "Vault is locked.": "vault chiuso",
    "Not found.": "non trovato",
}
"""What ``bw`` says on its stderr that this script knows, and the code the file carries for it."""


class Interrupted(BaseException):
    """The terminal was closed or the process told to end: cleaned up after, like a Ctrl-C."""


class FenceBroken(RuntimeError):
    """A fence of the measure did not hold: a browser launched without ``--use-mock-keychain``, a
    folder that is not a test folder of the measure. Its text is a sentence of this script's, for
    the file. **It is not a browser that broke**: the step is FALLITO and not SALTATO, and the
    Google part stops there (decision 45)."""


def on_signal(number: int, handler: Any) -> Any:
    """Set ``handler`` for a signal and return what was there — or ``None`` where signals cannot
    be set at all: a thread that is not the main one, as some test runners use."""
    try:
        return signal.signal(number, handler)
    except ValueError:
        return None


# ---------------------------------------------------------------------------------------------
# Il rapporto: ogni riga passa da un filtro
# ---------------------------------------------------------------------------------------------


def withheld(line: str, secrets: frozenset[str]) -> str | None:
    """Why ``line`` may not be written, or ``None``: it carries a value the measure keeps to
    itself — a session key, the invented password, a name of the test entry —, or an address."""
    if any(secret in line for secret in secrets):
        return "un valore che la misura tiene per sé"
    if EMAIL.search(line) is not None:
        return "un indirizzo"
    return None


class Report:
    """What goes on the screen and in the file: the same lines, each through :func:`withheld`."""

    def __init__(self, path: Path, echo: Callable[[str], None] = print) -> None:
        self.path = path
        self._file: TextIO = path.open("w", encoding="utf-8")
        self._echo = echo
        self._secrets: set[str] = set()
        self.number = 0
        self.counts = {"PASSATO": 0, "RIAPRE": 0, "SALTATO": 0, "FALLITO": 0}
        self.withheld_lines = 0
        self.interrupted = False

    def secret(self, value: str) -> None:
        """A value no line may carry from now on — whole, and each of its long words: an output
        of several lines must not get through one line at a time. Short values are not registered:
        a filter that withheld every line with an ``s`` in it would say nothing."""
        if len(value) >= 6:
            self._secrets.add(value)
        self._secrets.update(word for word in value.split() if len(word) >= 16)

    def say(self, line: str = "") -> None:
        reason = withheld(line, frozenset(self._secrets))
        if reason is not None:
            self.withheld_lines += 1
            line = f"[una riga trattenuta: portava {reason}]"
        self._echo(line)
        self._file.write(line + "\n")
        self._file.flush()

    def step(self, title: str) -> None:
        self.number += 1
        self.say(f"\n—— passo {self.number}: {title} ——")

    def _mark(self, word: str, text: str) -> None:
        self.counts[word] += 1
        self.say(f"[{self.number}] {word}: {text}")

    def passed(self, text: str) -> None:
        self._mark("PASSATO", text)

    def reopens(self, row: str, text: str) -> None:
        self._mark("RIAPRE", f"{row} — {text}")

    def skipped(self, text: str) -> None:
        self._mark("SALTATO", text)

    def failed(self, text: str) -> None:
        self._mark("FALLITO", text)

    def fact(self, text: str) -> None:
        self.say(f"    {text}")

    def looked(self, question: str, answer: bool) -> None:
        self.say(f"[{self.number}] GUARDATO: {question} — {'sì' if answer else 'no'}")

    def found_in_the_file(self) -> list[str]:
        """What the file holds that it must not, read back from the disk: nothing, or why."""
        self._file.flush()
        found = []
        text = self.path.read_text(encoding="utf-8")
        if any(secret in text for secret in self._secrets):
            found.append("un valore che la misura tiene per sé")
        if EMAIL.search(text) is not None:
            found.append("un indirizzo")
        return found

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
    """Tommaso's eye or hand: asked until the answer is a yes or a no, and written as GUARDATO."""
    while True:
        answer = ask(f"{question} (s/n) ").strip().lower()
        if answer in YES or answer in NO:
            report.looked(question, answer in YES)
            return answer in YES


def tried[T](report: Report, what: str, call: Callable[[], T]) -> T | None:
    """What ``call`` returns, or ``None`` after a SALTATO that says which step a browser broke —
    with the type of the error and never its message, which may carry an address or a value."""
    try:
        return call()
    except FenceBroken:
        raise
    except Exception as error:  # noqa: BLE001 — whatever a browser raises, the measure goes on
        report.skipped(f"{what}: non misurato, il browser ha sollevato {type(error).__name__}")
        return None


# ---------------------------------------------------------------------------------------------
# Bitwarden
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Ran:
    code: int
    out: str
    err: str
    ms: int

    @property
    def said(self) -> str:
        """What ``bw`` said on its stderr, as a code of this script's — never its text."""
        if self.code == 0:
            return "uscita 0"
        return f"uscita {self.code}, {KNOWN.get(self.err, f'altro, {len(self.err)} caratteri')}"


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


@contextlib.contextmanager
def quiet_terminal() -> Iterator[None]:
    """The terminal without its own echo while ``bw`` starts: what Tommaso types before ``bw``
    has shown its prompt — its start takes a second — is not written on the screen in clear.
    ``bw`` draws its own prompts; the terminal is given back as it was."""
    try:
        import termios
    except ImportError:
        yield
        return
    try:
        descriptor = sys.stdin.fileno()
        before = termios.tcgetattr(descriptor)
    except (termios.error, OSError, ValueError):
        # No terminal there — a pipe, the null device, a test: nothing to quieten.
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
    """The CLI of Bitwarden, launched by its path with a data folder of the measure's own.

    The session key reaches the child **in its environment and never in argv**; the master password
    never reaches this process at all: an interactive launch leaves the terminal to ``bw`` and reads
    only its stdout."""

    def __init__(self, path: Path, data: Path) -> None:
        self.path = path
        self.data = data

    def environment(self, session: str | None, *, interactive: bool) -> dict[str, str]:
        made = {
            "PATH": CLOSED_PATH,
            "HOME": str(Path.home()),
            "TMPDIR": tempfile.gettempdir(),
            "LANG": "C.UTF-8",
            "BITWARDENCLI_APPDATA_DIR": str(self.data),
        }
        if interactive:
            made["TERM"] = os.environ.get("TERM", "dumb")
        else:
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
        started = time.monotonic()
        with quiet_terminal() if interactive else contextlib.nullcontext():
            try:
                done = subprocess.run(
                    [str(self.path), *arguments],
                    env=self.environment(session, interactive=interactive),
                    input=stdin,
                    stdin=None if interactive or stdin is not None else subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=None if interactive else subprocess.PIPE,
                    timeout=None if interactive else BW_TIMEOUT_SECONDS,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return Ran(code=-1, out="", err="", ms=BW_TIMEOUT_SECONDS * 1000)
        return Ran(
            code=done.returncode,
            out=done.stdout.decode("utf-8", "replace").strip(),
            err=(done.stderr or b"").decode("utf-8", "replace").strip(),
            ms=round((time.monotonic() - started) * 1000),
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
        """The host of the server ``bw`` is configured for: a host, never a path."""
        ran = self.run("config", "server")
        return urlsplit(ran.out).hostname or "illeggibile"


def places_of_bw(named: Path | None, *, search: bool) -> list[Path]:
    """Where a ``bw`` is, in the order they are tried, without asking Tommaso. A path given is that
    path or nothing — a dry run that named a fake must never fall back to the real one —;
    otherwise, when ``search`` is on, the usual places, the PATH, and the copy the night of
    2026-10-10 downloaded. **Being here is not being launched**: :func:`not_of_bitwarden` first."""
    if named is not None:
        return [named] if named.is_file() and os.access(named, os.X_OK) else []
    if not search:
        return []
    places = [
        Path.home() / ".ela/bin/bw",
        Path.home() / ".local/bin/bw",
        Path("/opt/homebrew/bin/bw"),
        Path("/usr/local/bin/bw"),
        Path(shutil.which("bw") or "/nonexistent"),
        ROOT / ".git" / "m13.9-reference" / "bw" / "bin" / "bw",
    ]
    there = [place for place in places if place.is_file() and os.access(place, os.X_OK)]
    return list(dict.fromkeys(there))


def codesign(path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CODESIGN), *arguments, str(path)], capture_output=True, text=True, check=False
    )


def team_of(path: Path) -> str:
    """The team ``codesign`` reads in the signature of ``path``, or that there is none."""
    shown = codesign(path, "-dv", "--verbose=2")
    lines = (shown.stdout + shown.stderr).splitlines()
    team = next((line for line in lines if line.startswith("TeamIdentifier=")), None)
    return team.partition("=")[2] if team else "nessun team"


def not_of_bitwarden(path: Path) -> str | None:
    """Why ``path`` is not launched as the CLI of Bitwarden, or ``None`` (decision 43):
    ``codesign --verify --strict`` must pass, and the signature must be of a certificate Apple gave
    the team of Bitwarden. Asked **before** the first launch: what is launched as ``bw login`` is
    what Tommaso types his master password into, and printing who signed it and going on would be
    a defence that looks armed and never fires."""
    if not CODESIGN.is_file():
        return "la firma non si può verificare: su questa macchina non c'è codesign"
    verified = codesign(path, "--verify", "--strict")
    if verified.returncode != 0:
        return f"codesign --verify --strict non passa (uscita {verified.returncode})"
    if codesign(path, "--verify", "--strict", f"-R={BITWARDEN_S}").returncode != 0:
        return (
            "non è firmato da Bitwarden: la firma è buona, ma non è di un certificato che Apple "
            f"ha dato al team {BITWARDEN_TEAM} (il suo team: {team_of(path)})"
        )
    return None


def signed_by(path: Path) -> str:
    """Who signed ``path``, as ``codesign`` says it: a team's name, or why it could not be read."""
    if not CODESIGN.is_file():
        return "non letto: su questa macchina non c'è codesign"
    done = subprocess.run(
        [str(CODESIGN), "-dv", "--verbose=2", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    lines = (done.stdout + done.stderr).splitlines()
    authority = next((line for line in lines if line.startswith("Authority=")), None)
    team = next((line for line in lines if line.startswith("TeamIdentifier=")), None)
    if authority is None:
        signature = next((line for line in lines if line.startswith("Signature=")), "nessuna firma")
        return f"{signature}; {team or 'nessun team'}"
    return f"{authority}; {team or 'nessun team'}"


def invented_item(value: str, addresses: Sequence[str]) -> bytes:
    """The test entry, encoded as ``bw create item`` wants it on its stdin: a login of type 1 with
    an invented user, an invented value for its secret, and the addresses of local pages."""
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


def carries_a_password(listed: object) -> bool:
    """Whether what ``bw list items`` or ``bw get item`` printed carries a ``login.password``."""
    items = listed if isinstance(listed, list) else [listed]
    return any(
        isinstance(item, dict)
        and isinstance(item.get("login"), dict)
        and bool(item["login"].get("password"))
        for item in items
    )


def parsed(text: str) -> object:
    try:
        return json.loads(text)
    except ValueError:
        return None


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


def a_key(
    report: Report, ask: Callable[[str], str], bw: Bw, command: str, *, real: bool
) -> tuple[str | None, int]:
    """``bw login --raw`` or ``bw unlock --raw`` with the terminal left to ``bw``: the key it wrote
    on its stdout — registered before anything else is said —, or ``None``; and how many seconds
    it took, Tommaso's time included. A refusal — a mistyped password — is asked again."""
    for _ in range(3):
        report.say(
            f"    Parte bw {command}: aspetta che mostri la sua domanda, e scrivi lì. Lo script "
            "non legge ciò che scrivi, e ciò che scrivi può non comparire sullo schermo: è voluto."
        )
        report.say(
            "    Se bw non mostra nessuna domanda entro venti secondi, premi Ctrl-C una volta "
            "sola: lo script chiude da sé il vault e le cartelle, e lo scrive."
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
            return ran.out, seconds
        report.fact(f"bw {command} è uscito con {ran.code}, senza una chiave")
        if not real or not yes_or_no(ask, report, f"bw {command} non è riuscito: riprovare?"):
            break
    return None, 0


def swept(vault: Vault) -> int | None:
    """Every entry with the name of the test entry, deleted for good: how many were found, or
    ``None`` if the vault did not let them be listed. A measure interrupted halfway leaves one,
    and the next run — or the end of this one — takes it away."""
    bw, key = vault.bw, vault.key
    left = parsed(bw.run("list", "items", "--search", INVENTED_NAME, session=key).out)
    if not isinstance(left, list):
        return None
    ours = [item for item in left if isinstance(item, dict) and item.get("name") == INVENTED_NAME]
    for item in ours:
        bw.run("delete", "item", str(item.get("id")), "--permanent", session=key)
    return len(ours)


def none_left(vault: Vault) -> bool:
    """Whether no entry with the name of the test entry is in the vault — ``False`` when the vault
    did not answer: what was not read is not said to be clean."""
    bw, key = vault.bw, vault.key
    left = parsed(bw.run("list", "items", "--search", INVENTED_NAME, session=key).out)
    return isinstance(left, list) and not any(
        isinstance(item, dict) and item.get("name") == INVENTED_NAME for item in left
    )


def bitwarden(
    report: Report,
    ask: Callable[[str], str],
    bw_path: Path | None,
    work: Path,
    mode: str,
    made: list[Vault],
    signature: Callable[[Path], str | None],
) -> None:
    """The second half of measure 4. In the real measure a ``bw`` is launched only once
    ``signature`` has nothing against it — not even for its version —, and of each one set aside
    the file says where it is and why. The vault is appended to ``made`` **before** the login, so
    that whatever interrupts the rest finds it and closes it."""
    real = mode == "vera"
    report.step("dove sta bw, e che sia di Bitwarden prima di lanciarlo")
    places = places_of_bw(bw_path, search=real)
    found: Path | None = None
    if real:
        for place in places:
            why = signature(place)
            if why is None:
                found = place
                break
            report.fact(f"scartato: {at(place)} — {why}")
    elif places:
        found = places[0]
    if found is None and places:
        report.skipped(
            "nessun bw firmato da Bitwarden fra quelli trovati (codesign --verify --strict, e il "
            f"team {BITWARDEN_TEAM}): la password principale non si scrive in un programma che "
            "non è il suo, e i passi di Bitwarden non si fanno"
        )
        return
    if found is None:
        report.skipped(
            "il percorso dato con --bw non è un eseguibile: i passi di Bitwarden non si fanno"
            if bw_path is not None
            else "nessun bw: né nei posti soliti né in .git/m13.9-reference/bw/bin (a secco si "
            "nomina con --bw); i passi di Bitwarden non si fanno"
        )
        return
    report.fact(f"dove: {at(found)}")
    if real:
        report.fact(
            "firma: verificata prima di lanciarlo — codesign --verify --strict passa, e il "
            f"certificato è del team {BITWARDEN_TEAM}"
        )
        report.fact(f"firma, per esteso: {signed_by(found)}")
    else:
        report.fact("firma: non verificata, a secco")
    data = work / "bw-data"
    data.mkdir(mode=0o700)
    bw = Bw(found, data)
    version = bw.run("--version")
    digest = hashlib.sha256(found.read_bytes()).hexdigest()
    report.fact(f"versione: {version.out}; sha256 del binario: {digest}")
    state = bw.status()
    if not (data / "data.json").exists():
        report.failed(
            "bw non scrive nella cartella dei dati della misura (una cartella bw-data accanto al "
            "binario vince sulla variabile): i passi di Bitwarden non si fanno"
        )
        return
    report.fact("cartella dei dati: una della misura, sotto la cartella temporanea, e bw la usa")
    made.append(Vault(bw))
    vault = made[0]
    if state != "unauthenticated":
        report.failed(f"una cartella dei dati nuova dovrebbe dire unauthenticated, e dice {state}")
        return
    report.passed("bw parte, e senza account dice unauthenticated")

    report.step("bitwarden.com o bitwarden.eu — l'unica domanda")
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

    report.step("bw login — la password principale la chiede bw, sul terminale")
    key, _ = a_key(report, ask, bw, "login", real=real)
    if key is None:
        report.skipped(
            "bw login non ha dato una chiave: il vault non si è aperto, e i passi che lo vogliono "
            "non si fanno"
        )
        return
    vault.keys.append(key)
    vault.unlocked_at = time.monotonic()
    with_key, without = bw.status(key), bw.status()
    report.fact(f"bw status con la chiave nell'ambiente: {with_key}; senza: {without}")
    if with_key != "unlocked":
        vault.unlocked_at = None
        report.reopens("K1", "dopo il login la chiave scritta sullo stdout non apre il vault")
        return
    report.passed("login fatto, e la chiave apre il vault solo a chi la porta nell'ambiente")
    if real:
        yes_or_no(
            ask, report, "bw ti ha chiesto un codice arrivato per email, da dispositivo nuovo?"
        )

    entry(report, vault)
    keys(report, ask, vault, real=real)


def entry(report: Report, vault: Vault) -> None:
    """The round trip of one entry: invented here, created, read back, deleted (V1, V2, V3)."""
    report.step("una voce di prova: creata, riletta, cancellata")
    bw, key = vault.bw, vault.key
    invented = "parola-inventata-" + hashlib.sha256(os.urandom(16)).hexdigest()[:20]
    report.secret(invented)
    report.secret(INVENTED_NAME)
    report.secret(INVENTED_USER)
    before = swept(vault)
    if before:
        report.fact(f"voci di prova rimaste da una misura interrotta, cancellate prima: {before}")
    port, other = free_port(), free_port()
    first, second = f"http://127.0.0.1:{port}/login", f"http://127.0.0.1:{port}/secondo"
    vault.entries_made += 1
    created = bw.run("create", "item", session=key, stdin=invented_item(invented, (first, second)))
    made = parsed(created.out)
    if created.code != 0 or not isinstance(made, dict) or "id" not in made:
        report.skipped(f"bw create item non ha dato una voce ({created.said}): V3 non misurato")
        return
    identifier = str(made["id"])
    report.fact(f"V3: creata in {created.ms} ms, con il JSON sullo stdin e mai in argv")
    round_trip = False
    try:
        listed = bw.run("list", "items", "--url", first, session=key)
        items = parsed(listed.out)
        ours = (
            [i for i in items if isinstance(i, dict) and i.get("id") == identifier]
            if isinstance(items, list)
            else []
        )
        report.fact(
            f"V1: bw list items --url trova la voce: {'sì' if ours else 'no'}, in {listed.ms} ms; "
            f"la sua uscita porta login.password: {'sì' if carries_a_password(items) else 'no'}"
        )
        whole = bw.run("get", "item", identifier, session=key)
        report.fact(
            f"V1: bw get item porta login.password: "
            f"{'sì' if carries_a_password(parsed(whole.out)) else 'no'}, in {whole.ms} ms"
        )
        for label, address in (
            ("lo stesso host su un'altra porta", f"http://127.0.0.1:{other}/"),
            ("un altro host", f"http://localhost:{port}/"),
        ):
            also = parsed(bw.run("list", "items", "--url", address, session=key).out)
            hit = isinstance(also, list) and any(
                isinstance(i, dict) and i.get("id") == identifier for i in also
            )
            report.fact(f"V2: --url con {label} trova la voce: {'sì' if hit else 'no'}")
        uri = bw.run("get", "uri", identifier, session=key)
        report.fact(
            f"V2: bw get uri stampa {len(uri.out.splitlines())} riga, ed è il primo indirizzo: "
            f"{'sì' if uri.out == first else 'no'}"
        )
        user = bw.run("get", "username", identifier, session=key)
        word = bw.run("get", "password", identifier, session=key)
        report.fact(
            "bw get username rende il nome inventato: "
            f"{'sì' if user.out == INVENTED_USER else 'no'}, in {user.ms} ms; "
            "bw get password rende il valore inventato: "
            f"{'sì' if word.out == invented else 'no'}, in {word.ms} ms"
        )
        round_trip = bool(ours) and user.out == INVENTED_USER and word.out == invented
    finally:
        deleted = bw.run("delete", "item", identifier, "--permanent", session=key)
        after = bw.run("get", "item", identifier, session=key)
        # «Not there» only counts while the vault still answers: a locked vault finds nothing too.
        gone = after.code != 0 and bw.status(key) == "unlocked"
        clean = none_left(vault)
        report.fact(
            f"cancellata per sempre ({deleted.said}); bw get item dopo: {after.said}; una ricerca "
            f"del suo nome non ne trova più: {'sì' if clean else 'no'}"
        )
    if gone and clean:
        vault.entries_gone += 1
    in_the_file = report.found_in_the_file()
    if in_the_file:
        report.failed("il file porta " + " e ".join(in_the_file))
    elif not (gone and clean):
        report.failed(
            "la voce di prova non risulta cancellata: è da togliere a mano dal vault (il suo nome "
            "è INVENTED_NAME in scripts/misura_m13_9.py)"
        )
    elif round_trip:
        report.passed("la voce ha fatto il giro, è cancellata, e il suo valore non è nel file")
    else:
        report.reopens(
            "V3", "la voce è cancellata, ma il giro non ha reso ciò che era stato scritto"
        )


def keys(report: Report, ask: Callable[[str], str], vault: Vault, *, real: bool) -> None:
    """What a new ``bw unlock`` does to the key before it (K2), **asked while that key is alive**:
    a lock first would close it whatever an unlock does, and the file would read its own lock
    (decision 44). What ``bw lock`` does is read at the closing, of every key the measure had."""
    report.step("che cosa fa un nuovo bw unlock alla chiave di prima, ancora viva")
    bw, first = vault.bw, vault.key
    before = bw.status(first)
    if before != "unlocked":
        vault.unlocked_at = None
        report.skipped(f"la chiave di prima non apre più il vault ({before}): K2 non misurato")
        return
    key, _ = a_key(report, ask, bw, "unlock", real=real)
    if key is None:
        report.skipped("bw unlock non ha dato una chiave: K2 non misurato")
        return
    old, new = bw.status(first), bw.status(key)
    report.fact(
        f"K2: subito dopo il nuovo unlock la chiave di prima dice: {old}; quella nuova: {new}"
    )
    report.fact(
        f"K2: la chiave nuova è diversa da quella di prima: {'sì' if key != first else 'no'}"
    )
    if new != "unlocked":
        if old != "unlocked":
            vault.unlocked_at = None
        report.reopens("K1", "la chiave scritta da bw unlock --raw non apre il vault")
        return
    if key != first:
        vault.keys.append(key)
    vault.unlocked_at = time.monotonic()
    report.passed(
        "K2, un fatto: un nuovo unlock chiude la chiave di prima: "
        f"{'sì' if old != 'unlocked' else 'no'}"
    )


def still_open(report: Report, vault: Vault) -> None:
    """K3: whether the key still opens the vault after the time the rest of the measure took."""
    report.step("quanto dura la chiave senza essere usata, per il tempo di questa misura")
    if vault.key is None or vault.unlocked_at is None:
        report.skipped("il vault non è rimasto aperto con una chiave buona: K3 non misurato")
        return
    idle = round(time.monotonic() - vault.unlocked_at)
    state = vault.bw.status(vault.key)
    report.fact(f"K3: {idle} s dopo l'ultimo unlock, senza nessun uso, la chiave dice: {state}")
    if state == "unlocked":
        report.passed(f"la chiave vale ancora dopo {idle} s")
    else:
        report.reopens("K3", f"la chiave è caduta da sola entro {idle} s")


def close_the_vault(report: Report, vault: Vault) -> None:
    """The end, whatever happened before: the test entry swept, the vault locked — and what
    ``bw lock`` did read on every key the measure had (K2) —, the account left, the data folder
    gone. **What bw says is asked of bw**, not remembered: a login that half-succeeded, or an
    interrupt, leave an account this still leaves."""
    report.step(
        "la fine di Bitwarden: il vault chiuso, l'uscita dall'account, la cartella cancellata"
    )
    bw = vault.bw
    state = bw.status(vault.key)
    report.fact(f"prima di chiudere, bw dice: {state}")
    entries = "nessuna creata"
    if vault.entries_made:
        if state == "unlocked":
            swept(vault)
            entries = "nessuna rimasta" if none_left(vault) else "UNA È RIMASTA"
        elif vault.entries_gone == vault.entries_made:
            entries = (
                "nessuna rimasta (verificato quando è stata cancellata; ora il vault è chiuso)"
            )
        else:
            entries = "NON VERIFICABILE: il vault è chiuso"
    report.fact(f"voci di prova nel vault: {entries}")
    after: list[str] = []
    if state != "unauthenticated":
        lock = bw.run("lock", session=vault.key)
        # Every key the measure had, not the last alone: a new unlock may have left the first alive.
        after = [bw.status(key) for key in vault.keys] or [bw.status()]
        logout = bw.run("logout")
        report.fact(
            f"K2: dopo bw lock ({lock.said}) le chiavi che la misura ha avuto dicono: "
            + ", ".join(after)
        )
        report.fact(f"bw logout: {logout.said}")
    out = bw.status()
    report.fact(f"alla fine bw dice: {out}")
    vault.keys.clear()
    shutil.rmtree(bw.data, ignore_errors=True)
    gone = not bw.data.exists()
    report.fact(f"la cartella dei dati della misura non c'è più: {'sì' if gone else 'no'}")
    if any(said != "locked" for said in after) or out != "unauthenticated" or not gone:
        report.failed(
            "la chiusura non è verificata: vedi i fatti qui sopra. La cartella dei dati è "
            "cancellata, quindi questa macchina non tiene più la sessione; dal vault web, "
            "Impostazioni → Sicurezza, si chiudono le sessioni rimaste"
        )
    elif not entries.startswith(("nessuna creata", "nessuna rimasta")):
        report.failed(
            "una voce di prova può essere rimasta nel vault: è da togliere a mano (il suo nome è "
            "INVENTED_NAME in scripts/misura_m13_9.py)"
        )
    else:
        report.passed(
            "il vault è chiuso, l'account è lasciato, e la misura non tiene più niente di bw"
        )


# ---------------------------------------------------------------------------------------------
# Le pagine locali della prova a secco
# ---------------------------------------------------------------------------------------------


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class LocalAccount:
    """A site with an account, on 127.0.0.1, for the dry run: a login that sets a cookie, a page
    only the cookie opens, a logout. The cookie's value is invented here."""

    COOKIE: Final = "inventato-a-secco"
    LOGIN: Final = "<h1>Entra</h1><form method=post action=/session><button>Entra</button></form>"

    def __init__(self) -> None:
        self.requests: list[str] = []
        site = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self) -> None:
                site.requests.append(f"{self.command} {self.path}")
                inside = "SID=" in (self.headers.get("Cookie") or "")
                status, headers, html = 200, {}, site.LOGIN
                if self.path in ("/session", "/auto"):
                    headers = {"Set-Cookie": f"SID={site.COOKIE}; Max-Age=3600; Path=/"}
                    html = "<h1>Dentro</h1>"
                elif self.path == "/account":
                    if inside:
                        html = "<h1>Il tuo account</h1>"
                    else:
                        status, headers, html = 302, {"Location": "/"}, ""
                elif self.path == "/logout":
                    headers, html = {"Set-Cookie": "SID=; Max-Age=0; Path=/"}, "<h1>Fuori</h1>"
                data = html.encode()
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = _answer  # noqa: N815
            do_POST = _answer  # noqa: N815

            def log_message(self, *args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.origin = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@dataclass(frozen=True)
class Addresses:
    """Where the Google part goes: Google's own pages, or the local ones of the dry run."""

    login: str
    hands_free: str
    account: str
    logout: str
    inside_host: str
    inside_path: str | None

    @classmethod
    def google(cls) -> Addresses:
        return cls(
            login="https://accounts.google.com/",
            hands_free="https://accounts.google.com/",
            account="https://myaccount.google.com/",
            logout="https://accounts.google.com/Logout",
            inside_host="myaccount.google.com",
            inside_path=None,
        )

    @classmethod
    def local(cls, origin: str) -> Addresses:
        return cls(
            login=origin + "/",
            hands_free=origin + "/auto",
            account=origin + "/account",
            logout=origin + "/logout",
            inside_host=urlsplit(origin).netloc,
            inside_path="/account",
        )

    def inside(self, where: str) -> bool:
        """Whether the address a visit to the account page ended on is the account page."""
        parts = urlsplit(where)
        return parts.netloc == self.inside_host and (
            self.inside_path is None or parts.path == self.inside_path
        )


def shown(address: str) -> str:
    """An address as the file may carry it: the host, its port and the path — never the query,
    never what stands before an ``@``."""
    parts = urlsplit(address)
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.hostname or ''}{port}{parts.path}"


# ---------------------------------------------------------------------------------------------
# Chrome
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Seen:
    """What a visit left to read: where it ended, and whether a session cookie is there — its
    name looked for, its value never kept."""

    ended_on: str
    cookie: bool
    exit: int | None = None


class Browsers(Protocol):
    """What the Google part needs of a browser. The real one is :class:`Chrome`; a test names one
    that launches nothing."""

    def binary(self, kind: str) -> Path | None: ...
    def profile(self, name: str, *, preferences: bool) -> Path: ...
    def occupied(self, profile: Path) -> bool: ...
    def guided_window(
        self, kind: str, profile: Path, address: str, person: Callable[[], None]
    ) -> Seen: ...
    def plain_window(
        self, kind: str, profile: Path, address: str, person: Callable[[], None], *, bare: bool
    ) -> Seen: ...
    def visit(
        self, kind: str, profile: Path, address: str, *, window: bool, gated: bool = False
    ) -> Seen: ...
    def linked(self, profile: Path) -> dict[str, object] | None: ...
    def saved(self, profile: Path) -> dict[str, int | None]: ...
    def remove(self, profile: Path) -> bool: ...


def dig(data: object, dotted: str) -> object:
    for part in dotted.split("."):
        if not isinstance(data, dict) or part not in data:
            return None
        data = data[part]
    return data


def linked_from(preferences: object) -> dict[str, object]:
    """The keys of G4, as presence and booleans: a list becomes its length, a string becomes
    whether it is there, a boolean stays what it is."""
    read: dict[str, object] = {}
    for key in LINKED_KEYS:
        value = dig(preferences, key)
        if isinstance(value, bool) or value is None:
            read[key] = value
        elif isinstance(value, list):
            read[key] = len(value)
        else:
            read[key] = bool(value)
    return read


def is_linked(read: Mapping[str, object]) -> bool:
    """Whether the browser itself knows an account: one in ``account_info``, a primary account id,
    or a consent to sync."""
    return (
        bool(read.get("account_info"))
        or bool(read.get("google.services.account_id"))
        or bool(read.get("google.services.consented_to_sync"))
    )


def attaches_nothing(arguments: Sequence[str]) -> bool:
    """No argument of a window without automation attaches anything to it."""
    attached = ("--remote-debugging", "--headless", "--enable-automation", "--load-extension")
    return not any(argument.startswith(attached) for argument in arguments)


def keeps_the_fence(arguments_of_the_process: str, folder: Path) -> bool:
    """Whether a browser's own arguments, read back from the kernel, are the measure's: its folder
    and ``--use-mock-keychain`` — never the keychain, never another profile."""
    return f"--user-data-dir={folder}" in arguments_of_the_process and (
        MOCK_KEYCHAIN in arguments_of_the_process
    )


class Chrome:
    """Chrome for Testing of the lock, and the installed Chrome, on test folders of the measure.

    ``simulated`` is the dry run: no person is there, so the guided window clicks the local login
    itself, and the plain window is closed by the script once the local page has been reached."""

    KINDS: Final = {"cft": "chromium", "chrome": "chrome"}

    def __init__(
        self, work: Path, *, simulated: bool, reached: Callable[[], bool] | None = None
    ) -> None:
        self._profiles = (work / "profili").resolve()
        self._profiles.mkdir(mode=0o700)
        self._simulated = simulated
        self._reached = reached

    def binary(self, kind: str) -> Path | None:
        if kind == "chrome":
            found = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
            return found if found.is_file() else None
        from playwright.sync_api import sync_playwright

        # Where Playwright launches the Chrome for Testing of the lock from: asked, not guessed.
        with sync_playwright() as playwright:
            found = Path(playwright.chromium.executable_path)
        return found if found.is_file() else None

    def _guard(self, profile: Path) -> Path:
        if FORBIDDEN_PROFILE in str(profile):
            raise FenceBroken("la cartella è il profilo del Chrome installato")
        resolved = profile.resolve()
        if FORBIDDEN_PROFILE in str(resolved) or not resolved.is_relative_to(self._profiles):
            raise FenceBroken("la cartella non è una cartella di prova della misura")
        return resolved

    def profile(self, name: str, *, preferences: bool) -> Path:
        made = self._guard(self._profiles / name)
        made.mkdir(mode=0o700)
        if preferences:
            (made / "Default").mkdir(mode=0o700)
            (made / "Default" / "Preferences").write_text(json.dumps(PREFERENCES), encoding="utf-8")
        return made

    def occupied(self, profile: Path) -> bool:
        lock = self._guard(profile) / "SingletonLock"
        if not lock.is_symlink():
            return False
        try:
            os.kill(int(os.readlink(lock).rpartition("-")[2]), 0)
        except (ProcessLookupError, ValueError):
            return False
        except PermissionError:
            return True
        return True

    @staticmethod
    def _arguments_of(folder: Path) -> str:
        """The arguments of the browser's main process on ``folder``, as the kernel has them."""
        listing = subprocess.run(
            ["/bin/ps", "-ww", "-A", "-o", "args="], capture_output=True, text=True, check=False
        )
        ours = [
            line
            for line in listing.stdout.splitlines()
            if f"--user-data-dir={folder}" in line and "--type=" not in line
        ]
        return ours[0] if ours else ""

    def _launched(self, playwright: Any, kind: str, profile: Path, *, window: bool) -> Any:
        """A persistent context, with ``--use-mock-keychain`` read back from the browser's own
        process before any page is opened: without it the context is closed at once."""
        folder = self._guard(profile)
        context = playwright.chromium.launch_persistent_context(
            str(folder),
            channel=self.KINDS[kind],
            headless=not window,
            chromium_sandbox=True,
            handle_sigint=False,
        )
        if not keeps_the_fence(self._arguments_of(folder), folder):
            context.close()
            raise FenceBroken("il browser è partito senza --use-mock-keychain")
        return context

    @staticmethod
    def _seen(context: Any, page: Any) -> Seen:
        names = {cookie["name"] for cookie in context.cookies()}
        return Seen(ended_on=page.url, cookie=bool(names & SESSION_COOKIES))

    def guided_window(
        self, kind: str, profile: Path, address: str, person: Callable[[], None]
    ) -> Seen:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            context = self._launched(playwright, kind, profile, window=not self._simulated)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(address)
                if self._simulated:
                    page.click("button")
                    page.wait_for_load_state()
                person()
                return self._seen(context, page)
            finally:
                with contextlib.suppress(Exception):
                    context.close()

    def plain_window(
        self, kind: str, profile: Path, address: str, person: Callable[[], None], *, bare: bool
    ) -> Seen:
        """A window of the binary with nothing attached. It stays open while ``person`` — Tommaso —
        is at it, and it is this script that closes it after: he need not quit anything, and
        cannot quit the wrong Chrome."""
        binary = self.binary(kind)
        if binary is None:
            raise RuntimeError("no binary to launch")
        folder = self._guard(profile)
        arguments = BARE_WINDOW if bare else WINDOW_ARGUMENTS
        if not attaches_nothing(arguments):
            raise FenceBroken("la finestra senza automazione ha qualcosa attaccato")
        child = subprocess.Popen(
            [str(binary), f"--user-data-dir={folder}", *arguments, address],
            env={
                "PATH": CLOSED_PATH,
                "HOME": str(Path.home()),
                "TMPDIR": tempfile.gettempdir(),
                "LANG": "C.UTF-8",
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            if not keeps_the_fence(self._arguments_of(folder), folder):
                raise FenceBroken("la finestra è partita senza --use-mock-keychain")
            if self._simulated:
                deadline = time.monotonic() + 30
                while (
                    self._reached is not None
                    and not self._reached()
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.1)
                time.sleep(1.5)
            else:
                person()
        finally:
            # Whatever ends the wait — Tommaso's Enter, an error, a Ctrl-C —, the window does not
            # outlive it: SIGTERM is a clean exit for Chrome, which writes its cookies first.
            if child.poll() is None:
                child.send_signal(signal.SIGTERM)
            try:
                code = child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                child.kill()
                code = child.wait()
        return Seen(ended_on="", cookie=False, exit=code)

    @staticmethod
    def _gate(route: Any, request: Any) -> None:
        """The road ELA's adapter gives the document of the main frame (ADR 0052 §6): fetched by
        the driver without following redirects, and handed back to the page."""
        if not (request.is_navigation_request() and request.frame.parent_frame is None):
            route.continue_()
            return
        try:
            response = route.fetch(max_redirects=0)
        except Exception:  # noqa: BLE001 — a site that does not answer: the route is resolved
            route.abort("failed")
            return
        route.fulfill(response=response)

    def visit(
        self, kind: str, profile: Path, address: str, *, window: bool, gated: bool = False
    ) -> Seen:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            context = self._launched(playwright, kind, profile, window=window)
            try:
                if gated:
                    context.route("**/*", self._gate)
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(address)
                return self._seen(context, page)
            finally:
                with contextlib.suppress(Exception):
                    context.close()

    def linked(self, profile: Path) -> dict[str, object] | None:
        file = self._guard(profile) / "Default" / "Preferences"
        read = parsed(file.read_text(encoding="utf-8")) if file.exists() else None
        return linked_from(read) if isinstance(read, dict) else None

    def saved(self, profile: Path) -> dict[str, int | None]:
        """How many rows the browser's own password manager and autofill hold in a test folder:
        counts, never a row. ``None`` where a table could not be read."""
        import sqlite3

        default = self._guard(profile) / "Default"
        counts: dict[str, int | None] = {}
        for name, database, table in SAVED_TABLES:
            try:
                with sqlite3.connect(f"file:{default / database}?mode=ro", uri=True) as opened:
                    counts[name] = int(
                        opened.execute(f"select count(*) from {table}").fetchone()[0]
                    )
            except sqlite3.Error:
                counts[name] = None
        return counts

    def remove(self, profile: Path) -> bool:
        folder = self._guard(profile)
        deadline = time.monotonic() + 10
        while self.occupied(folder) and time.monotonic() < deadline:
            time.sleep(0.2)
        shutil.rmtree(folder, ignore_errors=True)
        return not folder.exists()


@dataclass
class Outcome:
    """What one binary answered: whether the window let Tommaso in, where a launch of Playwright
    found the login again, and whether the browser turned out linked to the account."""

    entered: bool | None = None
    found: dict[bool, bool] = field(default_factory=dict)
    linked: bool | None = None
    left: bool = False


NAMES: Final = {"cft": "Chrome for Testing", "chrome": "il Chrome installato"}


def google(
    report: Report, ask: Callable[[str], str], browsers: Browsers, where: Addresses, mode: str
) -> None:
    """Measure 3: a Google login in ELA's Chrome, in the two ways of decision 18."""
    real = mode == "vera"
    report.step(
        "Chrome for Testing del lock: c'è, e la finestra senza automazione non porta niente"
    )
    binary = tried(report, "il binario", lambda: browsers.binary("cft"))
    if binary is None:
        report.skipped(
            "Chrome for Testing non è installato (uv run playwright install chromium): i passi di "
            "Google non si fanno"
        )
        return
    if not attaches_nothing(WINDOW_ARGUMENTS) or not attaches_nothing(BARE_WINDOW):
        report.failed("gli argomenti della finestra senza automazione attaccano qualcosa")
        return
    report.fact("argomenti della finestra senza automazione: " + " ".join(WINDOW_ARGUMENTS))
    report.passed("il binario c'è, e la finestra senza automazione non ha pipe né porta di debug")

    profiles: list[Path] = []
    kind = "cft"
    try:
        outcome = one_binary(report, ask, browsers, where, kind, profiles, real)
        if real and (outcome.entered is False or outcome.linked is True):
            report.step("l'altra metà di G1 e G4: il Chrome installato, nelle stesse condizioni")
            if tried(report, "il Chrome installato", lambda: browsers.binary("chrome")) is None:
                report.skipped("il Chrome installato non c'è: il confronto non si fa")
            else:
                report.say(
                    "    Si apre una seconda finestra di «Google Chrome», su una cartella di prova "
                    "vuota e senza il portachiavi: non è la tua, e la chiude lo script. Se chiede "
                    "il motore di ricerca, scegline uno e vai avanti."
                )
                report.passed("c'è: stesso giro, cartella di prova nuova, stesse preferenze")
                kind = "chrome"
                outcome = one_binary(report, ask, browsers, where, kind, profiles, real)
        report.step("G5: lo stesso binario senza niente che spenga l'accesso del browser")
        if not real:
            report.skipped("a secco non c'è un account a cui il browser possa collegarsi")
        elif not outcome.entered:
            report.skipped("nessun login riuscito da cui partire")
        else:
            report.say(
                "    La decisione 20 chiede se questo binario offre l'accesso del browser "
                "all'account: è un altro login, in una finestra senza le preferenze di ELA. Chi "
                "non vuole farlo preme Invio senza entrare, e risponde «n»."
            )
            without_preferences(report, ask, browsers, where, kind, profiles)
    except FenceBroken as broken:
        report.failed(f"una recinzione non ha tenuto — {broken}: la parte di Google si ferma qui")
    finally:
        report.step("le cartelle di profilo di prova: cancellate, e verificato")
        gone = [removed(report, browsers, one) for one in profiles]
        if all(gone):
            report.passed(f"cancellate: {len(gone)}, e nessuna c'è più")
        else:
            report.failed("una cartella di profilo di prova è ancora lì")


def removed(report: Report, browsers: Browsers, profile: Path) -> bool:
    """Whether a test folder is gone. A folder the fence does not know is not touched, and said."""
    try:
        return bool(tried(report, "la cancellazione", lambda: browsers.remove(profile)))
    except FenceBroken as broken:
        report.failed(f"una recinzione non ha tenuto — {broken}: la cartella non si tocca")
        return False


def at_the_window(report: Report, ask: Callable[[str], str], real: bool) -> Callable[[], None]:
    """What Tommaso is told while a window without automation is open: he presses Enter here when
    he is done, and the script closes the window — he quits nothing."""

    def person() -> None:
        if real:
            report.say(
                "    Entra nel tuo account Google nella finestra che si è aperta. Quando hai "
                "finito — dentro, o rifiutato — torna qui: la finestra la chiude lo script."
            )
            ask("    Premi Invio quando hai finito. ")

    return person


def one_binary(
    report: Report,
    ask: Callable[[str], str],
    browsers: Browsers,
    where: Addresses,
    kind: str,
    profiles: list[Path],
    real: bool,
) -> Outcome:
    """G1, G3, G4 and the way out on one binary, on a clean folder; then G2 on the same folder,
    once out of the account. The same round for both binaries."""
    name, outcome = NAMES[kind], Outcome()
    profile = browsers.profile(f"google-{kind}", preferences=True)
    profiles.append(profile)

    report.step(f"G1: il login in una finestra di {name} lanciata senza automazione")
    window = tried(
        report,
        "G1",
        lambda: browsers.plain_window(
            kind, profile, where.hands_free, at_the_window(report, ask, real), bare=False
        ),
    )
    if window is None:
        return outcome
    report.fact(f"la finestra, chiusa dallo script, è uscita con {window.exit}")
    outcome.entered = yes_or_no(ask, report, "Google ti ha fatto entrare?") if real else True
    if outcome.entered:
        report.passed("G1: nella finestra senza automazione il login passa")
    else:
        report.reopens("G1", f"nella finestra senza automazione di {name} Google non fa entrare")
        return outcome

    report.step("G3: il login della finestra si ritrova in un lancio di Playwright dopo")
    for label, with_window in (("con la finestra", True), ("senza finestra", False)):
        seen = tried(
            report,
            f"G3 {label}",
            lambda with_window=with_window: browsers.visit(
                kind, profile, where.account, window=with_window
            ),
        )
        if seen is None:
            continue
        outcome.found[with_window] = where.inside(seen.ended_on)
        report.fact(
            f"{label}: la pagina dell'account è finita su {shown(seen.ended_on)}; un cookie di "
            f"sessione c'è: {'sì' if seen.cookie else 'no'}"
        )
    if len(outcome.found) < 2:
        pass
    elif all(outcome.found.values()):
        report.passed("G3: si ritrova, con la finestra e senza: la stessa chiave nei due lanci")
    elif any(outcome.found.values()):
        only = "con la finestra" if outcome.found[True] else "senza finestra"
        report.reopens("G3", f"si ritrova solo {only}")
    else:
        report.reopens("G3", "non si ritrova in nessuno dei due lanci")

    report.step("G6: la pagina dell'account aperta come la aprirebbe l'adapter di ELA")
    seeing = [with_window for with_window, inside in outcome.found.items() if inside]
    if not seeing:
        report.skipped("nessun lancio di Playwright ha visto il login: niente da confrontare")
    else:
        gated = tried(
            report,
            "G6",
            lambda: browsers.visit(
                kind, profile, where.account, window=False not in seeing, gated=True
            ),
        )
        if gated is not None:
            report.fact(
                "con il documento scaricato dal driver e riconsegnato alla pagina, è finita su "
                f"{shown(gated.ended_on)}; un cookie di sessione c'è: "
                f"{'sì' if gated.cookie else 'no'}"
            )
            if where.inside(gated.ended_on):
                report.passed("G6: per la strada dell'adapter il login si ritrova")
            else:
                report.reopens("G6", "per la strada dell'adapter il sito non riconosce il login")

    linked(report, browsers, profile, f"G4: {name}, con le preferenze di ELA", outcome)

    report.step("P1: dopo un login fatto a mano, che cosa il browser ha tenuto di suo")
    kept = tried(report, "P1", lambda: browsers.saved(profile))
    if kept is not None:
        for table, rows in kept.items():
            report.fact(f"righe di {table}: {'illeggibile' if rows is None else rows}")
        if any(rows is None for rows in kept.values()):
            report.skipped("una tabella non si legge: P1 non misurato per intero")
        elif any(kept.values()):
            report.reopens("P1", "il browser ha tenuto qualcosa del login nonostante le preferenze")
        else:
            report.passed("P1: niente salvato, niente offerto, niente ricordato")

    leave(report, browsers, where, kind, profile, outcome)

    report.step(f"G2: il login in una finestra di {name} lanciata da Playwright")
    if not outcome.left:
        report.skipped("la cartella non è fuori dall'account: un login qui non direbbe niente")
        return outcome
    if browsers.occupied(profile):
        report.skipped("la cartella di prova è occupata da un altro processo")
        return outcome
    answer: list[bool] = []

    def person() -> None:
        if real:
            report.say(
                "    Prova a entrare nel tuo account Google nella finestra che si è aperta, e "
                "NON chiuderla: rispondi qui, e la chiude lo script."
            )
            answer.append(yes_or_no(ask, report, "Google ti ha fatto entrare?"))

    guided = tried(report, "G2", lambda: browsers.guided_window(kind, profile, where.login, person))
    if guided is None:
        return outcome
    said = answer[0] if answer else guided.cookie
    report.fact(
        f"la finestra è finita su: {shown(guided.ended_on)}; un cookie di sessione c'è: "
        f"{'sì' if guided.cookie else 'no'}"
    )
    report.passed(
        f"G2, un fatto: in una finestra guidata Google fa entrare: {'sì' if said else 'no'}"
    )
    if said or guided.cookie:
        outcome.left = False
        outcome.found = {True: True}
        leave(report, browsers, where, kind, profile, outcome)
    return outcome


def linked(
    report: Report, browsers: Browsers, profile: Path, title: str, outcome: Outcome | None
) -> None:
    """G4, read from ``Default/Preferences`` after a login. With ``outcome`` the answer decides;
    with ``None`` it is G5's, a fact."""
    report.step(f"{title} — il browser risulta collegato a un account Google")
    read = tried(report, "G4", lambda: browsers.linked(profile))
    if read is None:
        report.skipped("Default/Preferences non si legge: collegato o no, non misurato")
        return
    for key, value in read.items():
        report.fact(f"{key}: {'assente' if value is None else value}")
    is_it = is_linked(read)
    if outcome is None:
        report.passed(
            f"G5, un fatto: senza niente che lo spenga, collegato: {'sì' if is_it else 'no'}"
        )
        return
    outcome.linked = is_it
    if is_it:
        report.reopens("G4", "il browser risulta collegato a un account nonostante le preferenze")
    else:
        report.passed(
            "G4: il browser non è collegato a nessun account, e la sincronizzazione è spenta"
        )


def leave(
    report: Report,
    browsers: Browsers,
    where: Addresses,
    kind: str,
    profile: Path,
    outcome: Outcome,
) -> None:
    """The way out of the account, in a launch that saw the login — and verified there: inside
    before, outside after, and no session cookie left."""
    report.step("l'uscita dall'account, e la verifica")
    seeing = [with_window for with_window, inside in outcome.found.items() if inside]
    if not seeing:
        report.skipped(
            "nessun lancio di Playwright ha visto il login: l'uscita non si può fare né verificare "
            "da qui. La cartella si cancella; la sessione, dal lato di Google, si chiude da "
            "myaccount.google.com → Sicurezza → I tuoi dispositivi"
        )
        return
    window = False not in seeing  # without a window, when a launch without one saw the login

    def out_and_back() -> tuple[Seen, Seen]:
        before = browsers.visit(kind, profile, where.account, window=window)
        browsers.visit(kind, profile, where.logout, window=window)
        return before, browsers.visit(kind, profile, where.account, window=window)

    visits = tried(report, "l'uscita", out_and_back)
    if visits is None:
        return
    before, after = visits
    report.fact(
        f"prima la pagina dell'account era su {shown(before.ended_on)}; dopo l'uscita è su "
        f"{shown(after.ended_on)}; un cookie di sessione resta: {'sì' if after.cookie else 'no'}"
    )
    if where.inside(before.ended_on) and not where.inside(after.ended_on) and not after.cookie:
        outcome.left = True
        report.passed("fuori dall'account: la pagina dell'account non si apre più")
    else:
        report.failed(
            "l'uscita non è verificata: chiudi la sessione da myaccount.google.com → Sicurezza → "
            "I tuoi dispositivi"
        )


def without_preferences(
    report: Report,
    ask: Callable[[str], str],
    browsers: Browsers,
    where: Addresses,
    kind: str,
    profiles: list[Path],
) -> None:
    """G5: a folder with no preference of ELA's, in a window with nothing that switches the
    browser's own sign-in off — what the binary does when nothing stops it (decision 20)."""
    profile = browsers.profile(f"google-{kind}-senza-preferenze", preferences=False)
    profiles.append(profile)
    window = tried(
        report,
        "G5",
        lambda: browsers.plain_window(
            kind, profile, where.hands_free, at_the_window(report, ask, True), bare=True
        ),
    )
    if window is None:
        return
    if not yes_or_no(ask, report, "Google ti ha fatto entrare?"):
        report.skipped("senza un login non c'è niente da leggere")
        return
    linked(report, browsers, profile, f"G5: {NAMES[kind]}, senza le preferenze di ELA", None)
    outcome = Outcome(entered=True)
    for with_window in (True, False):
        seen = tried(
            report,
            "G5, il lancio dopo",
            lambda with_window=with_window: browsers.visit(
                kind, profile, where.account, window=with_window
            ),
        )
        if seen is not None:
            outcome.found[with_window] = where.inside(seen.ended_on)
    leave(report, browsers, where, kind, profile, outcome)


# ---------------------------------------------------------------------------------------------
# La misura
# ---------------------------------------------------------------------------------------------


def line_of(error: BaseException) -> int:
    """The line of this file an error came through last: enough to find it, and no content."""
    here, found, trace = str(Path(__file__).resolve()), 0, error.__traceback__
    while trace is not None:
        if str(Path(trace.tb_frame.f_code.co_filename).resolve()) == here:
            found = trace.tb_lineno
        trace = trace.tb_next
    return found


def measure(
    report: Report,
    mode: str,
    *,
    ask: Callable[[str], str],
    bw_path: Path | None,
    browsers: Callable[[Path, Callable[[], bool]], Browsers] | None = None,
    signature: Callable[[Path], str | None] | None = None,
) -> int:
    head = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    report.say(
        f"Quando: {datetime.now():%Y-%m-%d %H:%M:%S}; "
        f"dove: {platform.system()} {platform.release()}, {platform.machine()}"
    )
    report.say(f"Il commit: {head.stdout.strip() or 'illeggibile'}; il modo: {mode}")
    work = Path(tempfile.mkdtemp(prefix="ela-misura-m139-")).resolve()
    work.chmod(0o700)
    vaults: list[Vault] = []
    local = LocalAccount() if mode != "vera" else None

    def ended(number: int, frame: object) -> None:
        raise Interrupted(signal.Signals(number).name)

    watched = [s for s in (getattr(signal, "SIGHUP", None), signal.SIGTERM) if s is not None]
    before = {one: on_signal(one, ended) for one in watched}
    try:
        report.say("\n# Bitwarden")
        bitwarden(report, ask, bw_path, work, mode, vaults, signature or not_of_bitwarden)
        report.say("\n# Google, nel Chrome di ELA")
        where = Addresses.google() if local is None else Addresses.local(local.origin)

        def reached() -> bool:
            return local is not None and "GET /auto" in local.requests

        make = browsers or (
            lambda folder, seen: Chrome(folder, simulated=mode != "vera", reached=seen)
        )
        google(report, ask, make(work, reached), where, mode)
        report.say("\n# La fine")
        if vaults:
            still_open(report, vaults[0])
    except (KeyboardInterrupt, Interrupted) as stop:
        report.interrupted = True
        report.say(
            f"\nINTERROTTA ({type(stop).__name__}) al passo {report.number}: ciò che segue è la "
            "chiusura, e dice da sé che cosa ha verificato."
        )
    except Exception as error:  # noqa: BLE001 — a defect of the measure is said, then cleaned up
        report.step("un errore della misura")
        report.failed(
            f"la misura si è rotta: {type(error).__name__} alla riga {line_of(error)} di "
            "scripts/misura_m13_9.py; ciò che segue è la chiusura"
        )
    finally:
        # The closing is not interrupted halfway: a second Ctrl-C would leave the vault open.
        quiet = on_signal(signal.SIGINT, signal.SIG_IGN)
        for one in watched:
            on_signal(one, signal.SIG_IGN)
        try:
            if vaults:
                close_the_vault(report, vaults[0])
            if local is not None:
                local.close()
            shutil.rmtree(work, ignore_errors=True)
            report.step("la cartella temporanea della misura, e il file")
            left = work.exists()
            found = report.found_in_the_file()
            report.fact(f"la cartella temporanea non c'è più: {'no' if left else 'sì'}")
            report.fact(
                "nel file: "
                + (" e ".join(found) if found else "nessun valore trattenuto, nessun indirizzo")
            )
            if left or found:
                report.failed("la misura lascia qualcosa che non doveva")
            else:
                report.passed("la misura non lascia niente sul disco, e il file si può mandare")
            report.verdict()
        finally:
            if quiet is not None:
                on_signal(signal.SIGINT, quiet)
            for one, handler in before.items():
                if handler is not None:
                    on_signal(one, handler)
    return 0 if report.ok else 1


def at(path: Path) -> str:
    """Where a file is, as the file may say it: the home is written ``~``."""
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def default_out(mode: str) -> Path:
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}"
    tag = "" if mode == "vera" else f"-{mode}"
    return Path.home() / "Downloads" / f"misura-m13.9{tag}-{stamp}.txt"


def main(
    argv: Sequence[str] | None = None,
    ask: Callable[[str], str] = input,
    browsers: Callable[[Path, Callable[[], bool]], Browsers] | None = None,
    signature: Callable[[Path], str | None] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--a-secco",
        action="store_const",
        const="a-secco",
        dest="mode",
        help="nessun account e nessuna domanda: pagine locali, e il bw che --bw nomina",
    )
    parser.add_argument(
        "--bw", type=Path, default=None, help="dove sta bw, se non è nei posti soliti"
    )
    parser.add_argument("--out", type=Path, default=None)
    arguments = parser.parse_args(argv)
    mode = arguments.mode or "vera"
    if mode == "vera" and ask is input and not (sys.stdin.isatty() and sys.stderr.isatty()):
        print(
            "La misura vuole un terminale, con lo stderr sullo schermo: bw chiede lì la password "
            "principale.",
            file=sys.stderr,
        )
        return 2
    report = Report(arguments.out or default_out(mode))
    report.say(f"# La misura di M13.9 ({mode})\n\nIl file: {at(report.path)}\n")
    try:
        return measure(
            report,
            mode,
            ask=ask,
            bw_path=arguments.bw,
            browsers=browsers,
            signature=signature,
        )
    finally:
        report.say(f"\nIl file: {at(report.path)}")
        report.close()


if __name__ == "__main__":
    raise SystemExit(main())
