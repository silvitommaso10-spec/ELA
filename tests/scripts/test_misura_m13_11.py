"""``scripts/misura_m13_11.py`` before Tommaso runs it on the PC: what it writes, what it launches,
and the word it gives each row (SPEC of M13.11, «Test previsti — dello script»).

The measure runs on Tommaso's PC, with the Smart App Control on, and its file travels by email. So
what it decides on the way is tested here first, each with its negative: **the filter** — a key, a
name of the user, an address, the home, the name of the machine and a SID never reach the file, and
the reading back says so —; **the rule** — the outcome a fake builds gives the word of the table,
and whether it stops the stratum; and the table of the strata —; **the launches of ``bw``** — a
closed list, never a password or a key in ``argv``, the key only as ``BW_SESSION`` —; **the
installed Chrome** — only its exact paths, and nothing under its folder —; **part B without
Bitwarden's signature launches no ``bw``**; and **the dry run of both parts** writes a clean file.

**Everything here is a fake** (M13.17b): the PC is :class:`FakePc`, which launches nothing — the
vault of the dry run is the script's own program, run in this process —; what only Windows answers
is in ``tests/scripts/test_misura_m13_11_windows.py``, on the line of the job ``node-windows``.
"""

from __future__ import annotations

import base64
import importlib.util
import io
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "misura_m13_11.py"
USER = "Utente-Finto"
MACHINE = "PC-FINTO-07"
USER_SID = "S-1-5-21-1111111111-2222222222-3333333333-1001"
ADDRESS = "finto@example.invalid"
"""The address the script's fake vault prints in its status: never in the file."""
OPENJS = "CN=OpenJS Foundation, O=OpenJS Foundation, L=San Francisco, S=California, C=US"
GOOGLE = "CN=Google LLC, O=Google LLC, L=Mountain View, S=California, C=US"
BITWARDEN = "CN=Bitwarden Inc., O=Bitwarden Inc., L=Santa Barbara, S=California, C=US"
PROTECTED_SDDL = f"O:{USER_SID}G:{USER_SID}D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FA;;;OW)"
SECRET_OF_THE_PC = "valore-della-macchina-che-non-passa"  # pragma: allowlist secret — invented
SHELL_FILES = (
    "chrome-headless-shell.exe",
    "libEGL.dll",
    "libGLESv2.dll",
    "vk_swiftshader.dll",
    "vulkan-1.dll",
)
CFT_FILES = ("chrome.exe", "chrome.dll", "chrome_elf.dll", "libEGL.dll")


@cache
def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("misura_m13_11_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Blocked(OSError):
    """What ``CreateProcess`` raises for a file the policy blocked: os error 4551, with the
    sentence of an Italian Windows — built here on a machine whose ``OSError`` has no
    ``winerror``."""

    winerror = 4551

    def __init__(self) -> None:
        super().__init__(22, "Un criterio di controllo dell'applicazione ha bloccato il file")


@dataclass(frozen=True)
class Call:
    argv: tuple[str, ...]
    env: Mapping[str, str] | None
    stdin: bytes | None
    interactive: bool


class Tommaso:
    """Tommaso, for a test: his server, Enter, and «no» to every yes-or-no. Every question kept."""

    def __init__(self, region: str = "eu") -> None:
        self.region = region
        self.asked: list[str] = []

    def __call__(self, question: str) -> str:
        self.asked.append(question)
        if "(com/eu)" in question:
            return self.region
        if "Invio" in question:
            return ""
        return "n"


@dataclass
class FakePc:
    """A PC that launches nothing and remembers what it was asked. Every answer is the one a PC
    with everything in order would give, unless the test says otherwise."""

    registry_value: Any = 1
    defender_value: Any = "On"
    version: tuple[int, int, int] = (3, 12, 13)
    pwsh: bool = True
    missing: set[str] = field(default_factory=set)
    installed_chrome: bool = False
    signatures: dict[str, tuple[str, str]] = field(default_factory=dict)
    launches: dict[str, str] = field(default_factory=dict)
    adapters: tuple[str, str, str] = ("BrowserUnsupported", "BrowserUnsupported", "False")
    reads: dict[str, str] = field(default_factory=dict)
    cookie_found: bool = True
    running: tuple[str, ...] = ("Default", "SingletonLock", "lockfile")
    folder_said: tuple[str, str] = ("0777", "AttributeError: module 'os' has no attribute 'getuid'")
    descriptor: str = PROTECTED_SDDL
    seconds: tuple[float, ...] = (0.4,) * 10
    left: tuple[tuple[int, str], ...] = ()
    remaining: tuple[tuple[int, str], ...] = ()
    pipe: dict[str, bytes] = field(default_factory=dict)
    shell_versions: dict[str, str] = field(
        default_factory=lambda: {"powershell.exe": "5.1.26100.1", "pwsh.exe": "7.4.6"}
    )
    alive_at_the_end: list[tuple[int, int, str]] = field(default_factory=list)
    bw_there: bool = True
    bw_signature: tuple[str, str] = ("Valid", BITWARDEN)
    asked: list[Path] = field(default_factory=list)
    listed: list[Path] = field(default_factory=list)
    read: list[Path] = field(default_factory=list)
    ran: list[Call] = field(default_factory=list)
    browsers: list[tuple[Any, ...]] = field(default_factory=list)
    killed: list[int] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)
    vault: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        home = Path.home()
        self.environ: dict[str, str] = {
            "LOCALAPPDATA": str(home / "AppData" / "Local"),
            "ProgramFiles": str(home / "Program Files"),
            "ProgramFiles(x86)": str(home / "Program Files (x86)"),
            "SystemRoot": "C:\\Windows",
            "TEMP": str(home / "AppData" / "Local" / "Temp"),
            "PSModulePath": "C:\\una\\cartella\\di\\moduli",
            "ELA_SEGRETO_FINTO": SECRET_OF_THE_PC,
        }
        if not self.pipe:
            key = script().KEY_LINE.encode("ascii")
            self.pipe = {"powershell.exe": key + b"\r\n??????? ?\r\n", "pwsh.exe": key + b"\n"}

    # Who and where

    def system(self) -> str:
        return "Windows"

    def pid(self) -> int:
        return 4242

    def home(self) -> str:
        return str(Path.home())

    def who(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        return (USER,), (MACHINE,)

    def commit(self) -> str:
        return "abc1234"

    def python(self) -> tuple[int, int, int]:
        return self.version

    def windows(self) -> list[str]:
        return [
            "sistema: Windows 11, versione 10.0.26100, AMD64",
            f"il nome della macchina: {MACHINE}",
            f"l'utente: {USER}",
        ]

    def registry_sac(self) -> Any:
        return self.registry_value

    def defender_sac(self) -> Any:
        return self.defender_value

    def shells(self) -> dict[str, Path | None]:
        windows = Path("C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
        seven = Path(self.environ["ProgramFiles"]) / "PowerShell" / "7" / "pwsh.exe"
        return {"powershell.exe": windows, "pwsh.exe": seven if self.pwsh else None}

    def processes(self) -> dict[int, tuple[int, str]]:
        table = {
            4242: (4241, "python.exe"),
            4241: (4000, "python.exe"),
            4000: (3000, "uv.exe"),
            3000: (100, "powershell.exe"),
            100: (1, "WindowsTerminal.exe"),
        }
        table.update({pid: (parent, name) for pid, parent, name in self.alive_at_the_end})
        return table

    # Files

    def chrome(self) -> Path:
        return Path(self.environ["LOCALAPPDATA"], "Google", "Chrome", "Application", "chrome.exe")

    def bw(self) -> Path:
        return Path.home() / ".ela" / "bin" / "bw.exe"

    def is_file(self, path: Path) -> bool:
        self.asked.append(path)
        if path == self.node():
            return True
        if path == self.bw():
            return self.bw_there
        return self.installed_chrome and path == self.chrome()

    def registry(self) -> tuple[Path, str]:
        return Path(self.environ["LOCALAPPDATA"]) / "ms-playwright", "la cartella di Windows"

    def lock(self) -> list[tuple[str, str]]:
        return [
            ("chromium", "1243"),
            ("chromium-headless-shell", "1243"),
            ("ffmpeg", "1011"),
            ("winldd", "1007"),
        ]

    def node(self) -> Path:
        return Path.home() / "ELA" / ".venv" / "playwright" / "driver" / "node.exe"

    def pe_files(self, folder: Path) -> list[Path]:
        self.listed.append(folder)
        if folder.name in self.missing:
            return []
        if folder.name == "chromium_headless_shell-1243":
            return [folder / "chrome-headless-shell-win64" / name for name in SHELL_FILES]
        if folder.name == "chromium-1243":
            return [folder / "chrome-win64" / name for name in CFT_FILES]
        if folder.name == "ffmpeg-1011":
            return [folder / "ffmpeg-win64.exe"]
        return []

    def file_facts(self, paths: Sequence[Path]) -> dict[Path, Any]:
        self.read.extend(paths)
        found = {}
        for path in paths:
            if path == self.bw():
                status, subject = self.bw_signature
            elif path.name in self.signatures:
                status, subject = self.signatures[path.name]
            elif path.name == "node.exe":
                status, subject = "Valid", OPENJS
            elif "chromium-1243" in path.parts or path == self.chrome():
                status, subject = "Valid", GOOGLE
            else:
                status, subject = "NotSigned", ""
            found[path] = script().FileFacts(1000, "ab" * 32, status, subject, "131.0.0.0")
        return found

    # Launches

    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        stdin: bytes | None = None,
        interactive: bool = False,
        timeout: float | None = 60.0,
    ) -> Any:
        self.ran.append(Call(tuple(argv), env, stdin, interactive))
        if len(argv) > 1 and argv[1].endswith("bw-finto.py"):
            return self._vault(argv[2:], env or {}, stdin)
        name = Path(argv[0]).name
        if name == "bw.exe":
            return self._vault(argv[1:], env or {}, stdin)
        if name in ("powershell.exe", "pwsh.exe"):
            return self._pipe(name, argv)
        label = name
        if "chromium-1243" in Path(argv[0]).parts:
            label = "cft"
        elif Path(argv[0]) == self.chrome():
            label = "installed"
        if self.launches.get(label) == "blocked":
            raise Blocked()
        first = {"node.exe": "v22.12.0", "ffmpeg-win64.exe": "ffmpeg version n7.1"}.get(
            name, f"<html><head><title>{script().TITLE}</title></head></html>"
        )
        return script().Ran(0, first, "", 5)

    def _vault(self, arguments: Sequence[str], env: Mapping[str, str], stdin: bytes | None) -> Any:
        if not self.vault:
            # the script's code under the script's name: the fences see it (M13.17b, decision 3)
            exec(compile(script().FAKE_VAULT, str(SCRIPT), "exec"), self.vault)  # noqa: S102
        code, out, err = self.vault["answer"](list(arguments), dict(env), stdin or b"")
        if arguments[:1] in (["login"], ["unlock"]) and code == 0:
            self.keys.append(out)
        return script().Ran(code, script().what_it_printed(out.encode("utf-8")), err.strip(), 3)

    def _pipe(self, name: str, argv: Sequence[str]) -> Any:
        line = base64.b64decode(argv[-1]).decode("utf-16-le")
        out = re.findall(r"'((?:[^']|'')*)'", line)[-1].replace("''", "'")
        if name in self.pipe:
            Path(out).write_bytes(self.pipe[name])
        return script().Ran(0, self.shell_versions.get(name, ""), "", 9)

    def kill_tree(self, pid: int) -> Any:
        self.killed.append(pid)
        return script().Ran(0, "", "", 1)

    # Browsers

    def _attempt(self, key: str) -> Any:
        outcome = self.reads.get(key, "reads")
        if outcome == "reads":
            return script().Attempt(script().TITLE)
        if outcome == "blocked":
            return script().Attempt(None, "Error", "spawn UNKNOWN, os error 4551")
        return script().Attempt(None, "BrowserFailed", "Target page, context or browser closed")

    def adapters_installed(self, registry: Path) -> tuple[str, str, str]:
        self.browsers.append(("installed", registry))
        return self.adapters

    def adapter_title(self, url: str) -> Any:
        self.browsers.append(("adapter", url))
        return self._attempt("adapter")

    def shell_title(self, url: str, *, whole: bool) -> Any:
        self.browsers.append(("shell", url, whole))
        return self._attempt("intero" if whole else "chiuso")

    def cft_title(self, url: str, folder: Path, *, window: bool, whole: bool) -> Any:
        self.browsers.append(("cft", url, folder, window, whole))
        mode = "finestra" if window else "senza"
        return self._attempt(f"cft-{mode}-{'intero' if whole else 'chiuso'}")

    def cookie_twice(self, origin: str, folder: Path, *, whole: bool) -> Any:
        self.browsers.append(("cookie", origin, folder, whole))
        return script().Cookie(self.cookie_found, self.running, ("Default",))

    def folder_check(self, folder: Path) -> tuple[str, str]:
        self.browsers.append(("folder", folder))
        return self.folder_said

    def sddl(self, folder: Path) -> Any:
        return self.descriptor

    def closings(self, kind: str, url: str, folder: Path, *, how: str) -> Any:
        self.browsers.append(("closings", kind, folder, how))
        return script().Closings(self.seconds)

    def orphans(self, kind: str, url: str, folder: Path, *, how: str) -> Any:
        self.browsers.append(("orphans", kind, folder, how))
        tree = (
            (10, "node.exe"),
            (11, "chrome-headless-shell.exe"),
            (12, "chrome-headless-shell.exe"),
        )
        return script().Orphans(tree, self.left, self.remaining)


MODES = ("senza", "finestra")
HOWS = ("chiuso", "intero")
"""The labels of the modes of A3.2 (c) and of their environments, as the fake reads them."""
THE_HOME = "<la casa del test>"
"""Where an id of a ``parametrize`` would say the home: it is read in the test, not at the
collection — a home is one for each process of pytest, and the workers of xdist must collect the
same tests."""


def a_filter() -> Any:
    return script().Filter(home=str(Path.home()), users=(USER,), machines=(MACHINE,))


def measured(tmp_path: Path, fake: FakePc, part: str, mode: str = "vera", **asked: Any) -> Any:
    """``measure`` on ``fake``, as ``main`` calls it: the report, closed, with its rows."""
    temporary = tmp_path / "temporanea"
    temporary.mkdir(exist_ok=True)
    report = script().Report(tmp_path / f"misura-{part}.txt", lambda line: None, a_filter())
    try:
        report.code = script().measure(
            report, part, mode, machine=fake, ask=asked.get("ask") or Tommaso(), temporary=temporary
        )
    finally:
        report.close()
    report.text = report.path.read_text(encoding="utf-8")
    return report


def verdict(word: str, stops: bool = False) -> Any:
    return script().Verdict(word, stops)


def never_in(text: str, fake: FakePc) -> None:
    """What no file of the measure may hold, whatever it measured."""
    for forbidden in (USER, MACHINE, USER_SID, ADDRESS, str(Path.home()), SECRET_OF_THE_PC):
        assert forbidden.lower() not in text.lower(), forbidden
    for key in fake.keys:
        assert key not in text


# --- the filter ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "shown"),
    [
        (
            "C:\\Users\\Utente-Finto\\AppData\\Local\\ms-playwright",
            "~\\AppData\\Local\\ms-playwright",
        ),
        ("C:\\Users\\UTENTE~1\\AppData\\Local\\Temp\\x", "~\\AppData\\Local\\Temp\\x"),
        ("C:/Users/Utente-Finto/ELA", "~/ELA"),
        ('{"path": "C:\\\\Users\\\\Utente-Finto\\\\x"}', '{"path": "~\\\\x"}'),
        ("c:\\users\\utente-finto, e poi", "~, e poi"),
    ],
)
def test_the_home_of_the_pc_is_written_as_a_tilde_in_every_spelling(line: str, shown: str) -> None:
    found = script().Filter(home="C:\\Users\\Utente-Finto", users=(), machines=())
    assert found.shown(line) == shown
    assert found.found(found.shown(line)) == []


def test_the_home_of_this_machine_is_written_as_a_tilde_and_a_longer_name_is_not_cut() -> None:
    found = script().Filter(home="/case/tom", users=(), machines=())
    assert found.shown("/case/tom/ELA") == "~/ELA"
    assert found.shown("/case/tomaso/ELA") == "/case/tomaso/ELA"


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        ("la chiave: chiave-di-prova-abcdef", "un valore che la misura tiene per sé"),
        ("scrivi a finto@example.invalid", "un indirizzo"),
        ("scrivi a finto%40example.invalid", "un indirizzo"),
        ("ciao Utente-Finto", "un nome utente"),
        ("ciao utente-finto, come va", "un nome utente"),
        (f"la macchina {MACHINE}", "il nome della macchina"),
        (f"D:(A;;FA;;;{USER_SID})", "un SID"),
        ("node.exe: 1000 byte, firma Valid", None),
        ("Utente-Fintone non è il nome", None),
    ],
)
def test_the_filter_withholds_a_key_an_address_a_user_the_machine_and_a_sid(
    line: str, reason: str | None
) -> None:
    found = a_filter()
    found.secret("chiave-di-prova-abcdef")
    assert found.withheld(found.shown(line)) == reason


def test_a_line_is_written_through_the_filter_and_the_reading_back_finds_nothing(
    tmp_path: Path,
) -> None:
    report = script().Report(tmp_path / "f.txt", lambda line: None, a_filter())
    report.secret("chiave-di-prova-abcdef")
    report.fact(f"il registro: {Path.home() / 'AppData'}")
    report.fact(f"una chiave: chiave-di-prova-abcdef, di {USER} su {MACHINE}")
    report.close()
    text = (tmp_path / "f.txt").read_text(encoding="utf-8")

    assert "~" in text and "[una riga trattenuta: portava" in text
    assert report.withheld_lines == 1
    assert report.filter.found(text) == []


@pytest.mark.parametrize(
    ("raw", "found"),
    [
        (f"proprietario {USER_SID}", "un SID"),
        (f"la macchina {MACHINE}", "il nome della macchina"),
        (f"la casa {THE_HOME}", "la casa del PC"),
        ("C:\\Users\\Qualcuno\\x", "la casa del PC"),
        ("chiave-di-prova-abcdef", "un valore che la misura tiene per sé"),
        (f"{USER}", "un nome utente"),
        (f"{ADDRESS}", "un indirizzo"),
    ],
)
def test_what_reached_the_file_by_another_door_is_found_and_the_file_does_not_leave_the_pc(
    tmp_path: Path, raw: str, found: str
) -> None:
    report = script().Report(tmp_path / "f.txt", lambda line: None, a_filter())
    report.secret("chiave-di-prova-abcdef")
    report._file.write(raw.replace(THE_HOME, str(Path.home())) + "\n")

    script().the_file(report)
    report.close()

    assert found in report.filter.found(report.path.read_text(encoding="utf-8"))
    assert report.counts["FALLITO"] == 1
    assert "non lascia il PC" in report.path.read_text(encoding="utf-8")


def test_a_clean_file_is_said_clean(tmp_path: Path) -> None:
    report = script().Report(tmp_path / "f.txt", lambda line: None, a_filter())
    report.fact("niente di suo")

    script().the_file(report)
    report.close()

    assert report.counts == {"PASSATO": 1, "RIAPRE": 0, "SALTATO": 0, "FALLITO": 0}
    assert "niente di ciò che non deve" in report.path.read_text(encoding="utf-8")


def test_the_dacl_is_written_only_from_d_and_without_a_user_s_sid() -> None:
    shown = script().dacl_shown(f"{PROTECTED_SDDL}(A;OICI;FA;;;{USER_SID})")
    assert shown.startswith("D:P(A;OICI;FA;;;SY)")
    assert USER_SID not in shown and "S-1-5-21-…" in shown and "O:" not in shown


# --- what the PC says, read ----------------------------------------------------------------------


def test_the_list_of_processes_leaves_out_the_powershell_that_listed_it() -> None:
    said = (
        "4100\n4 0 System\n4100 4000 powershell.exe\n4242 4241 python.exe\n"
        "0 0 System%20Idle%20Process\nrotto\n"
    )
    table = script().processes_from(said)
    assert table == {4: (0, "System"), 4242: (4241, "python.exe"), 0: (0, "System Idle Process")}
    assert script().processes_from("") == {}


def test_the_facts_of_a_file_are_read_with_their_spaces_given_back() -> None:
    said = (
        "C%3A%5Cx%20y%5Cnode.exe Valid CN%3DOpenJS%20Foundation%2C%20O%3DOpenJS%20Foundation 22.1\n"
    )
    assert script().facts_from(said) == {
        "C:\\x y\\node.exe": ("Valid", "CN=OpenJS Foundation, O=OpenJS Foundation", "22.1")
    }


# What PowerShell prints, read field by field (answer 61 (a)): the fake was more regular than the
# world. On the runner of 2026-11-20 a file with no signer and no version was the last line printed,
# its last two fields empty — and two strips took them away, the line's and the whole output's.


def test_what_a_program_printed_loses_only_the_ends_of_its_lines() -> None:
    assert script().what_it_printed(b"\r\nC%3A%5Cx NotSigned  \r\n") == "C%3A%5Cx NotSigned  "
    assert script().what_it_printed(b"\xff\n") == "\ufffd"
    assert script().what_it_printed(None) == ""


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        (
            b"C%3A%5Cx%5Cpython.exe NotSigned  \r\n",
            {"C:\\x\\python.exe": ("NotSigned", "", "")},
        ),
        (
            b"C%3A%5Ca.dll Valid CN%3DX \r\nC%3A%5Cb.exe Valid CN%3DY 1.0\r\n",
            {"C:\\a.dll": ("Valid", "CN=X", ""), "C:\\b.exe": ("Valid", "CN=Y", "1.0")},
        ),
        (b"C%3A%5Cc.exe NotSigned  2.0\r\n", {"C:\\c.exe": ("NotSigned", "", "2.0")}),
        (b" Valid CN%3DZ 3.0\r\n", {}),
    ],
    ids=["at-the-end-the-runner-s", "at-the-end-not-last", "in-the-middle", "at-the-head"],
)
def test_the_facts_of_a_file_keep_an_empty_field_wherever_it_is(
    printed: bytes, expected: dict[str, tuple[str, str, str]]
) -> None:
    """At the head, the path: a line that names no file is no file's."""
    assert script().facts_from(script().what_it_printed(printed)) == expected


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        (b"4100\r\n77 4 \r\n", {77: (4, "")}),
        (b"4100\r\n77 4 \r\n78 77 a.exe\r\n", {77: (4, ""), 78: (77, "a.exe")}),
        (b"4100\r\n77  a.exe\r\n78 77 b.exe\r\n", {78: (77, "b.exe")}),
        (b"4100\r\n 4 a.exe\r\n78 77 b.exe\r\n", {78: (77, "b.exe")}),
        (b"\r\n77 4 a.exe\r\n", {}),
    ],
    ids=["at-the-end-last", "at-the-end-not-last", "in-the-middle", "at-the-head", "no-own-number"],
)
def test_the_list_of_processes_keeps_an_empty_name_and_no_row_without_its_numbers(
    printed: bytes, expected: dict[int, tuple[int, str]]
) -> None:
    """A process with no name is still a process of the tree; a row without its own number or its
    parent's has no place in it; and without PowerShell's own number there is no table."""
    assert script().processes_from(script().what_it_printed(printed)) == expected


@pytest.mark.parametrize(
    ("printed", "expected", "on"),
    [(b"On\r\n", "On", True), (b"\r\n", "", None), (b"", "", None)],
)
def test_an_empty_state_of_defender_is_read_as_not_said(
    printed: bytes, expected: str, on: bool | None
) -> None:
    read = script().defender_from(script().what_it_printed(printed))
    assert read == expected
    assert script().sac_on(read) is on


def test_an_empty_descriptor_is_not_read_as_a_descriptor() -> None:
    """Read as one, an empty answer is a DACL that is not protected, and A4 (iv) reopens on nothing:
    not read, it is SALTATO with its reason."""
    assert (
        script().sddl_from(script().what_it_printed(PROTECTED_SDDL.encode() + b"\r\n"))
        == PROTECTED_SDDL
    )
    empty = script().sddl_from(script().what_it_printed(b"\r\n"))
    assert isinstance(empty, script().Failure)
    assert "vuot" in empty.said


@pytest.mark.parametrize(
    ("subject", "organization"),
    [
        (BITWARDEN, "Bitwarden Inc."),
        ('CN=Bitwarden, O="Bitwarden, Inc.", C=US', "Bitwarden, Inc."),
        ("CN=Solo un nome", None),
        ("", None),
    ],
)
def test_the_organization_of_a_signer_is_read_from_o(
    subject: str, organization: str | None
) -> None:
    assert script().organization(subject) == organization


def test_the_descendants_of_a_process_are_found_by_parentage_and_only_they() -> None:
    table = {10: (1, "node.exe"), 11: (10, "chrome.exe"), 12: (11, "chrome.exe"), 13: (1, "altro")}
    assert script().descendants(10, table) == [(11, "chrome.exe"), (12, "chrome.exe")]
    assert script().still([(11, "chrome.exe"), (12, "altro.exe")], table) == ((11, "chrome.exe"),)
    assert script().counted([(11, "chrome.exe"), (12, "chrome.exe")]) == "chrome.exe ×2"


QUESTION_MARKS = "arriva diversa — i suoi byte: 3f 3f 3f 3f 3f 20 3f 3f 3f"
"""The line that is not ASCII as Windows PowerShell 5.1 of the runner gave it on 2026-11-20."""
IN_UTF_8 = "arriva in UTF-8, intatta"


@pytest.mark.parametrize(
    ("received", "shape", "before", "ending", "other"),
    [
        (b"\xef\xbb\xbfKEY\nNONASCII\n", "WITH_BOM", "ef bb bf (un BOM)", "LF", IN_UTF_8),
        (b"KEY\r\nNONASCII\r\n", "CLEAN", "nessuno", "CRLF", IN_UTF_8),
        (b"KEY\n????? ???\n", "CLEAN", "nessuno", "LF", QUESTION_MARKS),
        (
            b"\xef\xbb\xbfKEY\r\n????? ???\r\n",
            "WITH_BOM",
            "ef bb bf (un BOM)",
            "CRLF",
            QUESTION_MARKS,
        ),
        (b"KEY\nNONASCII\n", "CLEAN", "nessuno", "LF", IN_UTF_8),
        (b"KEY", "BROKEN", "nessuno", "nessuna", "arriva diversa — i suoi byte: nessuno"),
        (
            b"\xef\xbb\xbfKEY \n",
            "BROKEN",
            "ef bb bf (un BOM)",
            "LF",
            "arriva diversa — i suoi byte: nessuno",
        ),
        (
            b"\xef\xbb\xbf\xef\xbb\xbfKEY\n",
            "BROKEN",
            "ef bb bf ef bb bf",
            "LF",
            "arriva diversa — i suoi byte: nessuno",
        ),
        (b" KEY\n", "BROKEN", "20", "LF", "arriva diversa — i suoi byte: nessuno"),
        (b"KE\n", "BROKEN", "la riga non c'è", "LF", "arriva diversa — i suoi byte: nessuno"),
        (None, "BROKEN", "niente", "nessuna", "niente è arrivato"),
    ],
    ids=[
        "a-bom-in-front",
        "the-end-crlf",
        "not-ascii-as-question-marks",
        "the-runner-s-windows-powershell-5-1",
        "clean",
        "no-end-of-line",
        "a-bom-and-something-after",
        "two-boms",
        "a-space-in-front",
        "the-line-cut",
        "nothing",
    ],
)
def test_what_arrives_through_the_pipe_is_judged_by_its_bytes(
    received: bytes | None, shape: str, before: str, ending: str, other: str
) -> None:
    """The three of the runner (answer 61 (b)), on every system: a BOM in front, the end CRLF,
    the line that is not ASCII as question marks; and the three outcomes of answer 62 — the line
    alone and whole, whole with a BOM in front and nothing else, neither."""
    key = script().KEY_LINE.encode("ascii")
    other_line = script().NON_ASCII.encode("utf-8")
    given = (
        None if received is None else received.replace(b"KEY", key).replace(b"NONASCII", other_line)
    )
    piped = script().read_pipe(given)
    assert piped == script().Piped(
        len(given or b""), getattr(script(), shape), before, ending, other
    )


def test_the_line_of_the_shape_of_a_key_is_the_shape_of_k1() -> None:
    assert len(script().KEY_LINE) == 88 and script().KEY_LINE.isascii()


# --- the rule: part A ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("registry", "defender", "version", "expected"),
    [
        (1, "On", (3, 12, 4), ("PASSATO", False)),
        (0, "On", (3, 12, 13), ("RIAPRE", True)),
        (2, "Eval", (3, 12, 13), ("RIAPRE", True)),
        (1, "Off", (3, 12, 13), ("RIAPRE", True)),
        ("niente", "On", (3, 12, 13), ("PASSATO", False)),
        ("niente", "niente", (3, 12, 13), ("SALTATO", False)),
        (1, "On", (3, 12, 3), ("RIAPRE", True)),
    ],
)
def test_a1_is_on_only_if_every_source_read_says_on_and_python_is_new_enough(
    tmp_path: Path, registry: Any, defender: Any, version: tuple[int, int, int], expected: Any
) -> None:
    unread = script().Failure("FileNotFoundError: non trovato")
    fake = FakePc(
        registry_value=unread if registry == "niente" else registry,
        defender_value=unread if defender == "niente" else defender,
        version=version,
    )
    report = measured(tmp_path, fake, "A", "a-secco")
    assert report.rows["A1"] == verdict(*expected)
    assert "la shell che ha lanciato lo script: powershell.exe" in report.text


@pytest.mark.parametrize(
    ("change", "row", "expected"),
    [
        ({}, "A2 node.exe", ("PASSATO", False)),
        ({}, "A2 lo shell", ("PASSATO", False)),
        ({}, "A2 Chrome for Testing", ("PASSATO", False)),
        ({}, "A2 ffmpeg", ("PASSATO", False)),
        ({"signatures": {"node.exe": ("NotSigned", "")}}, "A2 node.exe", ("RIAPRE", False)),
        (
            {"signatures": {"node.exe": ("Valid", "CN=Altri, O=Altri Srl")}},
            "A2 node.exe",
            ("RIAPRE", False),
        ),
        ({"signatures": {"libEGL.dll": ("Valid", GOOGLE)}}, "A2 lo shell", ("RIAPRE", False)),
        ({"missing": {"chromium_headless_shell-1243"}}, "A2 lo shell", ("SALTATO", False)),
        ({"missing": {"chromium-1243"}}, "A2 Chrome for Testing", ("SALTATO", False)),
    ],
)
def test_a2_compares_the_files_of_m8_and_says_a_browser_that_is_not_there(
    tmp_path: Path, change: dict[str, Any], row: str, expected: Any
) -> None:
    report = measured(tmp_path, FakePc(**change), "A", "a-secco")
    assert report.rows[row] == verdict(*expected)


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        (("BrowserUnsupported", "BrowserUnsupported", "False"), ("PASSATO", False)),
        (("BrowserUnsupported", "BrowserUnsupported", "True"), ("RIAPRE", False)),
        (("False", "BrowserUnsupported", "False"), ("RIAPRE", False)),
    ],
)
def test_a3_0_reads_the_adapters_of_today_against_difference_7(
    tmp_path: Path, answers: tuple[str, str, str], expected: Any
) -> None:
    report = measured(tmp_path, FakePc(adapters=answers), "A", "a-secco")
    assert report.rows["A3.0"] == verdict(*expected)


def test_a_pc_where_everything_starts_lets_s1_and_s2_start(tmp_path: Path) -> None:
    fake = FakePc()
    report = measured(tmp_path, fake, "A")

    assert report.code == 0, report.text
    for row in ("A3.1 node.exe", "A3.1 lo shell", "A3.1 Chrome for Testing", "A3.2 lo shell"):
        assert report.rows[row] == verdict("PASSATO"), row
    assert report.rows["A3.2 (c) con la finestra"] == verdict("PASSATO")
    assert "- S1: comincia" in report.text and "- S2: comincia" in report.text
    assert "- S3: si legge con il file dell'altra parte — B1; B2; B3" in report.text
    assert "- S4: comincia" in report.text
    never_in(report.text, fake)


def test_a_program_blocked_with_4551_stops_its_stratum_and_says_the_error_as_it_is(
    tmp_path: Path,
) -> None:
    fake = FakePc(launches={"chrome-headless-shell.exe": "blocked"}, reads={"adapter": "blocked"})
    fake.reads.update({"chiuso": "blocked", "intero": "blocked"})
    report = measured(tmp_path, fake, "A")

    assert report.rows["A3.1 lo shell"] == verdict("RIAPRE", True)
    assert report.rows["A3.2 lo shell"] == verdict("RIAPRE", True)
    assert "errore 4551: Un criterio di controllo dell'applicazione ha bloccato il file" in (
        report.text
    )
    assert "- S1: non comincia — A3.1 lo shell (RIAPRE, ferma)" in report.text
    assert "Nessuno strato comincia: la milestone non comincia (decisione 14)." in report.text


@pytest.mark.parametrize(
    ("reads", "expected", "how"),
    [
        ({}, ("PASSATO", False), "adapter"),
        ({"adapter": "fails"}, ("RIAPRE", False), "chiuso"),
        ({"adapter": "fails", "chiuso": "fails"}, ("RIAPRE", False), "intero"),
        ({"adapter": "fails", "chiuso": "blocked", "intero": "blocked"}, ("RIAPRE", True), None),
        ({"adapter": "fails", "chiuso": "fails", "intero": "fails"}, ("SALTATO", False), None),
    ],
)
def test_a3_2_separates_the_adapter_the_environment_and_the_smart_app_control(
    tmp_path: Path, reads: dict[str, str], expected: Any, how: str | None
) -> None:
    fake = FakePc(reads=reads)
    report = measured(tmp_path, fake, "A")

    assert report.rows["A3.2 lo shell"] == verdict(*expected)
    closings = [one for one in fake.browsers if one[:2] == ("closings", "shell")]
    if how is None:
        assert closings == []
        assert report.rows["A5 (i) lo shell"] == verdict("SALTATO")
    else:
        assert [one[3] for one in closings] == [how]


@pytest.mark.parametrize(
    ("reads", "expected"),
    [
        ({}, ("PASSATO", False)),
        ({"cft-finestra-chiuso": "fails"}, ("RIAPRE", False)),
        ({"cft-finestra-chiuso": "blocked", "cft-finestra-intero": "blocked"}, ("RIAPRE", True)),
        ({"cft-finestra-chiuso": "fails", "cft-finestra-intero": "fails"}, ("SALTATO", False)),
    ],
)
def test_a3_2_c_reads_chrome_for_testing_with_the_window_too(
    tmp_path: Path, reads: dict[str, str], expected: Any
) -> None:
    report = measured(tmp_path, FakePc(reads=reads), "A")
    assert report.rows["A3.2 (c) con la finestra"] == verdict(*expected)
    assert report.rows["A3.2 (c) senza finestra"] == verdict("PASSATO")


def test_the_installed_chrome_is_not_launched_when_chrome_for_testing_starts(
    tmp_path: Path,
) -> None:
    fake = FakePc(installed_chrome=True)
    report = measured(tmp_path, fake, "A")

    assert all(Path(call.argv[0]) != fake.chrome() for call in fake.ran)
    assert "A3.3" not in report.rows
    assert "131.0.0.0" in report.text


@pytest.mark.parametrize(("installed", "expected"), [("started", "RIAPRE"), ("blocked", "PASSATO")])
def test_the_installed_chrome_is_launched_on_a_folder_of_the_script_only_when_cft_does_not_start(
    tmp_path: Path, installed: str, expected: str
) -> None:
    fake = FakePc(installed_chrome=True, launches={"cft": "blocked", "installed": installed})
    fake.reads.update({f"cft-{mode}-{how}": "blocked" for mode in MODES for how in HOWS})
    report = measured(tmp_path, fake, "A")

    launched = [call for call in fake.ran if Path(call.argv[0]) == fake.chrome()]
    assert len(launched) == 1
    folders = [one for one in launched[0].argv if one.startswith("--user-data-dir=")]
    (folder,) = folders
    assert Path(folder.partition("=")[2]).is_relative_to(tmp_path / "temporanea")
    assert report.rows["A3.3"] == verdict(expected, expected == "RIAPRE")
    assert "- S2: non comincia" in report.text


@pytest.mark.parametrize(
    ("launches", "reads"),
    [
        ({"cft": "started"}, {f"cft-{mode}-{how}": "fails" for mode in MODES for how in HOWS}),
        ({"cft": "blocked"}, {"cft-senza-chiuso": "blocked", "cft-senza-intero": "blocked"}),
    ],
    ids=["partito in A3.1, non legge in (c)", "bloccato in A3.1, legge in (c) con la finestra"],
)
def test_the_installed_chrome_is_not_launched_when_chrome_for_testing_started_anywhere(
    tmp_path: Path, launches: dict[str, str], reads: dict[str, str]
) -> None:
    """Decision 45: the installed Chrome is launched only if Chrome for Testing started neither in
    A3.1 nor in A3.2 (c) — a page it did not read is not a launch that did not happen."""
    fake = FakePc(installed_chrome=True, launches={**launches, "installed": "started"})
    fake.reads.update(reads)
    report = measured(tmp_path, fake, "A")

    assert all(Path(call.argv[0]) != fake.chrome() for call in fake.ran)
    assert "A3.3" not in report.rows


def test_the_installed_chrome_is_not_launched_when_chrome_for_testing_is_not_there(
    tmp_path: Path,
) -> None:
    fake = FakePc(installed_chrome=True, missing={"chromium-1243"})
    report = measured(tmp_path, fake, "A")

    assert all(Path(call.argv[0]) != fake.chrome() for call in fake.ran)
    assert report.rows["A3.3"] == verdict("SALTATO", False)


def test_the_installed_chrome_is_looked_for_at_its_exact_paths_and_nothing_under_it(
    tmp_path: Path,
) -> None:
    """Three questions «is it a file?», and of its own folder only the program at its path."""
    fake = FakePc(installed_chrome=True, launches={"cft": "blocked"})
    measured(tmp_path, fake, "A")
    places = [place for _, place in script().chrome_places(fake.environ)]
    forbidden = Path(fake.environ["LOCALAPPDATA"], "Google", "Chrome")

    assert [path for path in fake.asked if path.name == "chrome.exe"] == places
    touched = [
        *fake.asked,
        *fake.listed,
        *fake.read,
        *(Path(word.partition("=")[2] or word) for call in fake.ran for word in call.argv),
        *(one for entry in fake.browsers for one in entry if isinstance(one, Path)),
    ]
    under = {path for path in touched if path.is_relative_to(forbidden)}
    assert under == {fake.chrome()}


def test_a_folder_of_a_profile_under_the_installed_chrome_s_folder_is_a_broken_fence(
    tmp_path: Path,
) -> None:
    local = tmp_path / "local"
    root = local / "Google" / "Chrome" / "User Data"
    root.mkdir(parents=True)
    work = script().Work(root, {"LOCALAPPDATA": str(local)})
    with pytest.raises(script().FenceBroken):
        work.profile("cft")
    (tmp_path / "altrove").mkdir()
    elsewhere = script().Work(tmp_path / "altrove", {"LOCALAPPDATA": str(local)})
    assert elsewhere.profile("cft").is_dir()
    exact = local / "Google" / "Chrome" / "Application" / "chrome.exe"
    assert not script().fenced(exact, {"LOCALAPPDATA": str(local)})
    assert script().fenced(root / "Default", {"LOCALAPPDATA": str(local)})


@pytest.mark.parametrize(
    ("change", "row", "expected"),
    [
        ({}, "A4 (i)", ("PASSATO", False)),
        ({"cookie_found": False}, "A4 (i)", ("RIAPRE", True)),
        ({}, "A4 (ii)", ("PASSATO", False)),
        ({"running": ("Default", "lockfile")}, "A4 (ii)", ("RIAPRE", False)),
        ({}, "A4 (iii)", ("RIAPRE", False)),
        ({"folder_said": ("0700", "accetta")}, "A4 (iii)", ("PASSATO", False)),
        ({}, "A4 (iv)", ("PASSATO", False)),
        ({"descriptor": f"{PROTECTED_SDDL}(A;OICI;FA;;;{USER_SID})"}, "A4 (iv)", ("RIAPRE", False)),
        ({"descriptor": PROTECTED_SDDL.replace("D:P", "D:")}, "A4 (iv)", ("RIAPRE", False)),
    ],
)
def test_a4_reads_the_cookie_the_names_the_mode_and_the_dacl(
    tmp_path: Path, change: dict[str, Any], row: str, expected: Any
) -> None:
    fake = FakePc(**change)
    report = measured(tmp_path, fake, "A")
    assert report.rows[row] == verdict(*expected)
    never_in(report.text, fake)


@pytest.mark.parametrize(
    ("change", "row", "expected"),
    [
        ({}, "A5 (i) lo shell", ("PASSATO", False)),
        ({"seconds": (0.3,) * 9 + (2.6,)}, "A5 (i) lo shell", ("RIAPRE", False)),
        ({"seconds": (2.5,) * 10}, "A5 (i) Chrome for Testing", ("PASSATO", False)),
        ({}, "A5 (ii)", ("PASSATO", False)),
        ({"left": ((11, "chrome-headless-shell.exe"),)}, "A5 (ii)", ("RIAPRE", False)),
        (
            {
                "left": ((11, "chrome-headless-shell.exe"),),
                "remaining": ((11, "chrome-headless-shell.exe"),),
            },
            "A5 (ii)",
            ("FALLITO", False),
        ),
    ],
)
def test_a5_reads_the_longest_closing_against_half_the_limit_and_what_is_left(
    tmp_path: Path, change: dict[str, Any], row: str, expected: Any
) -> None:
    report = measured(tmp_path, FakePc(**change), "A")
    assert report.rows[row] == verdict(*expected)


def test_a5_ii_never_hands_the_adapter_s_own_kill_and_takes_the_shell_with_its_options(
    tmp_path: Path,
) -> None:
    fake = FakePc()
    measured(tmp_path, fake, "A")
    orphans = [one for one in fake.browsers if one[0] == "orphans"]
    assert [(one[1], one[3]) for one in orphans] == [("shell", "chiuso")]


def test_a_dry_run_of_part_a_launches_nothing_and_no_browser(tmp_path: Path) -> None:
    fake = FakePc()
    report = measured(tmp_path, fake, "A", "a-secco")

    assert report.code == 0, report.text
    assert fake.ran == []
    assert [one[0] for one in fake.browsers] == ["installed", "folder"]
    assert "- S1: non comincia" in report.text


# --- the strata ----------------------------------------------------------------------------------

A_ROWS = (
    "A1",
    "A2 node.exe",
    "A2 lo shell",
    "A3.1 node.exe",
    "A3.1 lo shell",
    "A3.2 lo shell",
    "A2 Chrome for Testing",
    "A3.1 Chrome for Testing",
    "A3.2 (c) senza finestra",
    "A3.2 (c) con la finestra",
    "A4 (i)",
)


def rows(**changed: Any) -> dict[str, Any]:
    made = {name: verdict("PASSATO") for name in A_ROWS}
    made.update({name.replace("_", " "): one for name, one in changed.items()})
    return made


def states(decided: Mapping[str, tuple[str, list[str]]]) -> dict[str, str]:
    return {name: state for name, (state, _) in decided.items()}


def test_every_row_passed_starts_s1_and_s2_and_leaves_s3_to_part_b() -> None:
    decided = script().strata(rows(), "A")
    assert states(decided) == {
        "S1": "comincia",
        "S2": "comincia",
        "S3": "si legge con il file dell'altra parte",
        "S4": "comincia",
    }
    assert decided["S3"][1] == ["B1", "B2", "B3"]


def test_a_row_that_reopens_without_stopping_lets_its_stratum_start() -> None:
    decided = script().strata({**rows(), "A3.2 lo shell": verdict("RIAPRE", False)}, "A")
    assert states(decided)["S1"] == "comincia"


@pytest.mark.parametrize(
    "row",
    ["A1", "A3.1 lo shell", "A2 node.exe"],
)
@pytest.mark.parametrize(
    "outcome", [verdict("RIAPRE", True), verdict("SALTATO"), verdict("FALLITO"), None]
)
def test_a_row_of_s1_that_stops_or_was_not_measured_stops_everything(
    row: str, outcome: Any
) -> None:
    given = rows()
    if outcome is None:
        del given[row]
    else:
        given[row] = outcome
    decided = script().strata(given, "A")
    assert states(decided) == dict.fromkeys(("S1", "S2", "S3", "S4"), "non comincia")


def test_chrome_for_testing_blocked_stops_s2_and_s3_and_lets_s1_and_s4_start() -> None:
    given = {**rows(), "A3.1 Chrome for Testing": verdict("RIAPRE", True)}
    decided = script().strata(given, "A")
    assert states(decided) == {
        "S1": "comincia",
        "S2": "non comincia",
        "S3": "non comincia",
        "S4": "comincia",
    }
    assert decided["S2"][1] == ["A3.1 Chrome for Testing (RIAPRE, ferma)"]


def test_part_b_reads_s3_with_its_own_rows_and_leaves_the_rest_to_part_a() -> None:
    passed = {name: verdict("PASSATO") for name in ("B1", "B2", "B3")}
    assert states(script().strata(passed, "B")) == dict.fromkeys(
        ("S1", "S2", "S3", "S4"), "si legge con il file dell'altra parte"
    )
    stopped = {**passed, "B3": verdict("RIAPRE", True)}
    assert states(script().strata(stopped, "B"))["S3"] == "non comincia"


# --- the launches of bw --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "arguments",
    [
        ["--version"],
        ["status"],
        ["config", "server"],
        ["config", "server", "https://vault.bitwarden.eu"],
        ["login", "--raw"],
        ["unlock", "--raw"],
        ["lock"],
        ["logout"],
        ["create", "item"],
        ["list", "items", "--url", "http://127.0.0.1:1/login"],
        ["list", "items", "--search", "nome"],
        ["get", "password", "id"],
        ["delete", "item", "id", "--permanent"],
    ],
)
def test_the_closed_list_lets_the_measure_s_own_commands_through(arguments: list[str]) -> None:
    assert script().refused(arguments) is None


@pytest.mark.parametrize(
    ("arguments", "session"),
    [
        (["login", "utente", "password"], None),
        (["login", "--passwordenv", "X"], None),
        (["unlock", "la-password"], None),
        (["unlock", "--passwordfile", "x"], None),
        (["status", "--session", "k"], None),
        (["get", "item", "CHIAVE-VIVA"], "CHIAVE-VIVA"),
        (["export"], None),
        (["config", "server", "a", "b"], None),
        (["list", "items", "--trash"], None),
        ([], None),
    ],
)
def test_the_closed_list_refuses_a_password_a_key_and_every_other_word(
    arguments: list[str], session: str | None
) -> None:
    assert script().refused(arguments, session) is not None


def test_a_refused_command_never_reaches_the_machine(tmp_path: Path) -> None:
    fake = FakePc()
    bw = script().Bw(fake, ("bw.exe",), tmp_path)
    with pytest.raises(ValueError, match="argv"):
        bw.run("status", "--session", "k")
    assert fake.ran == []


def test_part_b_hands_the_key_only_as_bw_session_and_never_in_argv(tmp_path: Path) -> None:
    fake = FakePc()
    tommaso = Tommaso("eu")
    report = measured(tmp_path, fake, "B", ask=tommaso)

    assert report.code == 0, report.text
    vault = [call for call in fake.ran if Path(call.argv[0]) == fake.bw()]
    allowed = script().WINDOWS_KEPT | {
        "PATH",
        "BITWARDENCLI_APPDATA_DIR",
        "BW_NOINTERACTION",
        "BW_SESSION",
    }
    assert len(fake.keys) == 2
    for call in vault:
        assert script().refused(call.argv[1:]) is None, call.argv
        assert not any(key in word for key in fake.keys for word in call.argv)
        assert call.env is not None, call.argv
        assert {name.upper() for name in call.env} <= allowed, sorted(call.env)
        assert SECRET_OF_THE_PC not in call.env.values()
        if call.argv[1:2] in (("login",), ("unlock",)):
            assert call.interactive and call.stdin is None and "BW_SESSION" not in call.env
    sessions = {call.env["BW_SESSION"] for call in vault if call.env and "BW_SESSION" in call.env}
    assert sessions == set(fake.keys)
    assert ("config", "server", "https://vault.bitwarden.eu") in [c.argv[1:] for c in vault]
    assert any("Invio" in question for question in tommaso.asked)
    for row in ("B1", "B2", "B2 voce", "B2 K2", "B2 K3", "B3"):
        assert report.rows[row] == verdict("PASSATO"), row
    assert "il vault è chiuso, l'account è lasciato" in report.text
    never_in(report.text, fake)


@pytest.mark.parametrize(
    ("there", "signature"),
    [
        (False, ("Valid", BITWARDEN)),
        (True, ("NotSigned", "")),
        (True, ("HashMismatch", BITWARDEN)),
        (True, ("Valid", "CN=Altri, O=Altri Srl, C=IT")),
        (True, ("Valid", 'CN=Bitwarden, O="Bitwarden, Inc.", C=US')),
    ],
)
def test_part_b_without_bitwarden_s_signature_launches_no_bw(
    tmp_path: Path, there: bool, signature: tuple[str, str]
) -> None:
    fake = FakePc(bw_there=there, bw_signature=signature)
    report = measured(tmp_path, fake, "B")

    assert all(Path(call.argv[0]) != fake.bw() for call in fake.ran)
    assert report.rows["B1"] == verdict("SALTATO")
    assert "bw non è lanciato" in report.text
    assert "- S3: non comincia" in report.text


def test_bw_is_looked_for_only_in_the_ela_folder_of_the_home(tmp_path: Path) -> None:
    fake = FakePc(bw_there=False)
    measured(tmp_path, fake, "B")
    assert [path for path in fake.asked if "bw" in path.name] == [fake.bw()]


def test_b3_says_a_shell_that_is_not_there_and_reopens_when_no_line_arrives_whole(
    tmp_path: Path,
) -> None:
    fake = FakePc(pwsh=False, pipe={"powershell.exe": b"AAAA\r\n"})
    report = measured(tmp_path, fake, "B", "a-secco")

    assert report.rows["B3 pwsh.exe"] == verdict("SALTATO")
    assert report.rows["B3 powershell.exe"] == verdict("RIAPRE")
    assert report.rows["B3"] == verdict("RIAPRE", True)


def with_a_bom() -> bytes:
    """What Windows PowerShell 5.1 of the runner gave on 2026-11-20: a BOM, the key, CRLF, and the
    line that is not ASCII as question marks."""
    return b"\xef\xbb\xbf" + script().KEY_LINE.encode("ascii") + b"\r\n????? ???\r\n"


def test_b3_passes_when_one_shell_gives_the_line_alone_and_whole(tmp_path: Path) -> None:
    key = script().KEY_LINE.encode("ascii")
    fake = FakePc(pipe={"powershell.exe": with_a_bom(), "pwsh.exe": key + b"\n"})
    report = measured(tmp_path, fake, "B", "a-secco")

    assert report.rows["B3 powershell.exe"] == verdict("RIAPRE")
    assert report.rows["B3 pwsh.exe"] == verdict("PASSATO")
    assert report.rows["B3"] == verdict("PASSATO")


def test_b3_reopens_without_stopping_when_the_line_is_whole_only_after_a_bom(
    tmp_path: Path,
) -> None:
    """Answer 62: the road is there if who receives takes the BOM away — part two decides."""
    fake = FakePc(pipe={"powershell.exe": with_a_bom(), "pwsh.exe": b"AAAA\n"})
    report = measured(tmp_path, fake, "B", "a-secco")

    assert report.rows["B3 powershell.exe"] == verdict("RIAPRE")
    assert report.rows["B3 pwsh.exe"] == verdict("RIAPRE")
    assert report.rows["B3"] == verdict("RIAPRE")
    assert "ADR 0063 §3" in report.text


def test_b3_says_for_each_shell_the_bytes_before_the_line_its_end_and_the_line_not_ascii(
    tmp_path: Path,
) -> None:
    key = script().KEY_LINE.encode("ascii")
    whole = key + b"\n" + script().NON_ASCII.encode("utf-8") + b"\n"
    fake = FakePc(
        pipe={"powershell.exe": with_a_bom(), "pwsh.exe": whole},
        shell_versions={"powershell.exe": "", "pwsh.exe": "7.4.6"},
    )
    report = measured(tmp_path, fake, "B", "a-secco")

    assert (
        "powershell.exe ? (uscita 0): 104 byte; prima della riga: ef bb bf (un BOM); la riga: "
        "intera, con un BOM davanti; fine riga CRLF; la riga non ASCII arriva diversa — i suoi "
        "byte: 3f 3f 3f 3f 3f 20 3f 3f 3f"
    ) in report.text
    assert (
        f"pwsh.exe 7.4.6 (uscita 0): {len(whole)} byte; prima della riga: nessuno; la riga: sola "
        "e intera; fine riga LF; la riga non ASCII arriva in UTF-8, intatta"
    ) in report.text


def test_b3_launches_each_shell_without_its_profile_and_without_psmodulepath(
    tmp_path: Path,
) -> None:
    fake = FakePc()
    measured(tmp_path, fake, "B", "a-secco")
    shells = [
        call for call in fake.ran if Path(call.argv[0]).name in ("powershell.exe", "pwsh.exe")
    ]

    assert len(shells) == 2
    for call in shells:
        assert call.argv[1:4] == ("-NoProfile", "-NonInteractive", "-EncodedCommand")
        assert call.env is not None and "PSModulePath" not in call.env
        line = base64.b64decode(call.argv[4]).decode("utf-16-le")
        assert "primo.py' | & '" in line


# --- the dry run, whole --------------------------------------------------------------------------


def dry(tmp_path: Path, fake: FakePc, part: str) -> tuple[int, str]:
    out = tmp_path / "Downloads" / f"misura-a-secco-{part}.txt"
    temporary = tmp_path / "temporanea"
    temporary.mkdir(exist_ok=True)
    shown: list[str] = []
    code = script().main(
        [part, "--a-secco", "--out", str(out)],
        ask=Tommaso(),
        machine=fake,
        temporary=temporary,
        echo=shown.append,
    )
    text = out.read_text(encoding="utf-8")
    assert "\n".join(shown) + "\n" == text
    assert list(temporary.iterdir()) == [], "the temporary folder of the measure was left"
    return code, text


def test_the_dry_run_of_part_a_writes_a_clean_file_and_says_so(tmp_path: Path) -> None:
    fake = FakePc()
    code, text = dry(tmp_path, fake, "A")

    assert code == 0, text
    assert "[una riga trattenuta: portava il nome della macchina]" in text
    assert "[una riga trattenuta: portava un nome utente]" in text
    assert "nel file: niente di ciò che non deve" in text
    assert text.rstrip().endswith(f"Il file: {tmp_path / 'Downloads' / 'misura-a-secco-A.txt'}")
    assert fake.ran == []
    never_in(text, fake)


def test_the_dry_run_of_part_b_goes_round_the_script_s_own_vault_and_writes_a_clean_file(
    tmp_path: Path,
) -> None:
    fake = FakePc()
    code, text = dry(tmp_path, fake, "B")

    assert code == 0, text
    vault = [call for call in fake.ran if call.argv[1:2] and call.argv[1].endswith("bw-finto.py")]
    assert vault and all(call.argv[0] == sys.executable for call in vault)
    assert all(script().refused(call.argv[2:]) is None for call in vault)
    assert len(fake.keys) == 2
    assert "il vault è chiuso, l'account è lasciato" in text
    assert "la cartella dei dati della misura non c'è più: sì" in text
    never_in(text, fake)


def test_a_child_of_the_script_alive_at_the_end_is_taken_away_and_failed(tmp_path: Path) -> None:
    fake = FakePc(alive_at_the_end=[(5000, 4242, "chrome.exe"), (5001, 5000, "chrome.exe")])
    report = measured(tmp_path, fake, "A", "a-secco")

    assert report.code == 1
    assert fake.killed == [5000, 5001]
    assert "processi dello script vivi alla fine: chrome.exe ×2" in report.text


def test_part_b_for_real_wants_a_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO())
    out = tmp_path / "misura.txt"
    assert script().main(["B", "--out", str(out)]) == 2
    assert not out.exists()


@pytest.mark.parametrize(
    ("mode", "name"), [("vera", "misura-m13.11-A-"), ("a-secco", "misura-m13.11-a-secco-A-")]
)
def test_the_file_of_a_dry_run_is_named_so_that_step_7_never_takes_it(mode: str, name: str) -> None:
    out = script().default_out("A", mode)
    assert out.parent == Path.home() / "Downloads" and out.name.startswith(name)
    assert re.fullmatch(rf"{re.escape(name)}\d{{8}}-\d{{6}}\.txt", out.name)


def test_a_broken_step_is_failed_and_the_closing_still_reads_the_file(tmp_path: Path) -> None:
    fake = FakePc()

    def broken() -> list[str]:
        raise RuntimeError(f"rotto a {Path.home()} da {USER}")

    fake.windows = broken  # type: ignore[method-assign]
    report = measured(tmp_path, fake, "A", "a-secco")

    assert report.code == 1
    assert "la misura si è rotta: RuntimeError alla riga" in report.text
    assert "nel file: niente di ciò che non deve" in report.text
    never_in(report.text, fake)


def test_an_interrupt_is_said_and_the_vault_is_closed_all_the_same(tmp_path: Path) -> None:
    fake = FakePc()

    def interrupted() -> dict[str, Path | None]:
        raise KeyboardInterrupt

    fake.shells = interrupted  # type: ignore[method-assign]
    report = measured(tmp_path, fake, "B", "a-secco")

    assert report.code == 1
    assert "INTERROTTA (KeyboardInterrupt)" in report.text
    assert "il vault è chiuso, l'account è lasciato" in report.text


@pytest.mark.parametrize("how", ["loose", "packed", "detached", "missing", "not a commit"])
def test_the_commit_is_read_from_the_clone_s_files_and_no_git_is_launched(
    tmp_path: Path, how: str
) -> None:
    """The re-read of 25afb1e (R15): the file says the commit the PC is at, as step 1 of the guide
    wants it, without launching a ``git`` the ``PATH`` chose."""
    commit = "0123456789abcdef0123456789abcdef01234567"  # pragma: allowlist secret — invented
    git = tmp_path / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    ref = "refs/heads/m13.11-il-browser-sul-pc"
    (git / "HEAD").write_text(
        commit + "\n" if how == "detached" else f"ref: {ref}\n", encoding="ascii"
    )
    if how == "loose":
        (git / ref).write_text(commit + "\n", encoding="ascii")
    elif how == "packed":
        (git / "packed-refs").write_text(
            f"# pack-refs with: peeled fully-peeled sorted\n{'f' * 40} refs/heads/main\n"
            f"{commit} {ref}\n^{'e' * 40}\n",
            encoding="ascii",
        )
    elif how == "not a commit":
        (git / ref).write_text("non un commit\n", encoding="ascii")

    expected = "illeggibile" if how in ("missing", "not a commit") else commit[:7]
    assert script().head_of(tmp_path) == expected


# ----------------------------------------------------------------------------------------
# Answer 58 (d): the script never loads the configuration — a test, not a re-read
# ----------------------------------------------------------------------------------------

SOURCE = Path(__file__).resolve().parents[2] / "src"
STARTS_ELA = frozenset({"Settings", "build", "serve", "main", "load"})
"""What would start ELA or read its configuration: the settings, ``Settings.load``, and the
``build``, ``serve`` and ``main`` of ``ela``."""


def settings_classes() -> frozenset[str]:
    """Every class of settings of ``src/ela``, derived from the source as the probe derived it — a
    class whose bases reach ``BaseSettings`` —, read and never imported."""
    import ast

    defined: dict[str, set[str]] = {}
    for path in sorted((SOURCE / "ela").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef):
                defined.setdefault(node.name, set()).update(
                    base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
                    for base in node.bases
                )
    found = {"BaseSettings"}
    grew = True
    while grew:
        new = {name for name, bases in defined.items() if bases & found} - found
        found |= new
        grew = bool(new)
    return frozenset(found - {"BaseSettings"})


def configuration_named(source: str, settings: frozenset[str]) -> list[str]:
    """What a source names of ELA's configuration and start: a class of settings, or ``Settings``,
    anywhere; a module of ``ela`` that is a ``__main__``; ``build``, ``serve``, ``main`` or ``load``
    imported from ``ela`` or reached through a name imported from it; and a module of ``ela``
    imported by a name built at run time. The script's own ``main`` is not ``ela``'s."""
    import ast

    tree = ast.parse(source)
    of_ela = {"ela"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "ela":
            of_ela |= {alias.asname or alias.name for alias in node.names}
        elif isinstance(node, ast.Import):
            of_ela |= {
                alias.asname or alias.name.split(".")[0]
                for alias in node.names
                if alias.name.split(".")[0] == "ela"
            }
    anywhere = settings | {"Settings"}
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "ela":
            names = {alias.name for alias in node.names}
            if (node.module or "").endswith("__main__") or names & (anywhere | STARTS_ELA):
                found.append(f"{node.lineno}: from {node.module} import {sorted(names)}")
            elif "__main__" in names:
                found.append(f"{node.lineno}: from {node.module} import __main__")
        elif isinstance(node, ast.Import):
            found += [
                f"{node.lineno}: import {alias.name}"
                for alias in node.names
                if alias.name.split(".")[0] == "ela" and alias.name.endswith("__main__")
            ]
        elif isinstance(node, ast.Attribute):
            root = node.value
            while isinstance(root, ast.Attribute):
                root = root.value
            reached = isinstance(root, ast.Name) and root.id in of_ela
            if node.attr in anywhere or (reached and node.attr in STARTS_ELA):
                found.append(f"{node.lineno}: {ast.unparse(node)}")
        elif isinstance(node, ast.Name) and node.id in anywhere:
            found.append(f"{node.lineno}: {node.id}")
        elif (
            isinstance(node, ast.Call)
            and getattr(node.func, "attr", getattr(node.func, "id", ""))
            in ("import_module", "__import__")
            and "ela" in ast.unparse(node)
        ):
            found.append(f"{node.lineno}: {ast.unparse(node)}")
    return found


def test_the_script_never_names_the_configuration_nor_what_starts_ela() -> None:
    """Answer 58 (d): on the PC the script runs from the repository, where there is a ``.env``
    with the PC's key (decision 17). It imports by name only what it measures."""
    settings = settings_classes()

    assert {"PersistenceSettings"} <= settings, "the classes of settings are derived"
    assert configuration_named(SCRIPT.read_text(encoding="utf-8"), settings) == []


@pytest.mark.parametrize(
    "source",
    [
        "from ela.config import Settings\n",
        "from ela.infrastructure.persistence.settings import PersistenceSettings\n",
        "from ela.composition.root import build\n",
        "from ela.api.server import serve\n",
        "from ela.cli.app import main\n",
        "import ela.api.__main__\n",
        "from ela.api import __main__\n",
        "import ela.composition.root\nela.composition.root.build()\n",
        "from ela import config\nconfig.Settings.load()\n",
        "import importlib\nimportlib.import_module('ela.api.__main__')\n",
    ],
)
def test_a_script_that_names_the_configuration_is_found(source: str) -> None:
    assert configuration_named(source, frozenset({"PersistenceSettings"})) != []


def test_what_the_script_imports_of_ela_today_is_not_found() -> None:
    allowed = (
        "from ela.composition.root import BROWSER_CLOSE_GRACE_SECONDS\n"
        "from ela.infrastructure.machine.account import LAUNCH_ARGUMENTS, AccountChrome\n"
        "def main() -> int:\n    return 0\n"
    )

    assert configuration_named(allowed, frozenset({"PersistenceSettings"})) == []
