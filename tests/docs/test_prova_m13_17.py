"""``scripts/prova_m13_17.py`` against section 35 of the guide (M13.17; decisions 20–23 of its
starting block, answers 44, 45 and 54 of the review of its SPEC). The guide is the source of truth
and the script reads it; this file keeps the two aligned, in the form of ``test_prova_m13_15.py``.

**The section and the script are one vocabulary**: every marker is a kind the script knows, every
kind it knows is used, every plan it sends exists and names a file only in the two folders of the
proof — or the one in Library that step 7 wants refused.

**Every judgement of its own has its negative case**: the field of the branch, the root that is the
home, the list that admits the two folders and never Library, the bell, the live policies, the
silence of a refusal, a refusal at the start-up, the folders prepared and taken away.

**Steps 2 to 12 are walked by the script against a real ELA** — its routes, its command line, its
Guardian, its executor and its tools, its database — on a real disk, **with the root at a home of
the walk**: ``HOME`` is a folder under ``tmp_path/Users``, and the root is that home, as on the Mac
of the proof. The two lines of ``rifiuto`` load the settings in process, with their variable
changed for that line alone; ``/Users`` is the folder that holds the home of the walk.
"""

from __future__ import annotations

import asyncio
import dataclasses
import importlib.util
import io
import json
import os
import shlex
import subprocess
import sys
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from ela.api import create_app
from ela.cli import client as cli_client
from ela.composition import ConfigurationError, Settings, build
from ela.testing.fakes import FakePower
from tests.cli.support import LoopTransport
from tests.composition.support import (  # noqa: F401 — re-exported as a fixture
    _only_the_declared_environment,
    create_schema,
    declare,
)
from tests.docs.test_prova_m13_15 import World as WithTheGuard

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prova_m13_17.py"
SIBLINGS = (
    "prova_m6_3c",
    "prova_m13_9",
    "prova_m13_10",
    "prova_m13_13",
    "prova_m13_14",
    "prova_m13_15",
    "prova_m14_1",
    "prova_m14_2",
    "prova_m14_3",
)


@cache
def script() -> Any:
    before = {name: sys.modules.pop(name, None) for name in SIBLINGS}
    spec = importlib.util.spec_from_file_location("prova_m13_17", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        for name, found in before.items():
            sys.modules.pop(name, None)
            if found is not None:
                sys.modules[name] = found
    return module


def guide() -> str:
    return str(script().GUIDE.read_text(encoding="utf-8"))


def section() -> str:
    return str(script().base.section(guide(), script().HEADING))


def marked() -> dict[int, list[Any]]:
    module = script()
    found: dict[int, list[Any]] = module.base.steps(module.base.blocks(guide(), module.HEADING))
    return found


def lines_of(kind: str) -> list[tuple[int, str]]:
    return [
        (number, line)
        for number, blocks in marked().items()
        for one in blocks
        if one.kind == kind
        for line in one.lines
    ]


# ----------------------------------------------------------------------------------------
# The section and the script are one vocabulary
# ----------------------------------------------------------------------------------------


def test_every_marker_is_a_kind_the_script_knows_and_every_kind_is_used() -> None:
    used = {one.kind for blocks in marked().values() for one in blocks}

    assert used == set(script().KINDS)
    assert sorted(marked()) == list(range(2, 13))


def test_every_line_is_in_the_vocabulary_of_its_kind() -> None:
    assert script().outside_vocabulary(marked()) == []


def test_a_line_outside_the_vocabulary_is_named() -> None:
    module = script()
    wrong = {
        2: [
            module.base.Block(2, "rifiuto", "ELA_FS_ROOT=/x uv run ela serve\nholds your home"),
            module.base.Block(2, "sì", "uv run ela task approve <id>"),
            module.base.Block(2, "muto", "QUIET"),
            module.base.Block(2, "pulizia", "Documents/ELA/prova-m13.17"),
            module.base.Block(2, "fatto", "Che cosa è successo."),
        ]
    }

    assert len(module.outside_vocabulary(wrong)) == 5


def test_it_comes_after_section_34_and_before_where_to_look() -> None:
    text = guide()

    assert text.index("## 34. ") < text.index("## 35. ") < text.index("## Dove guardare dopo")


def test_every_plan_the_section_sends_exists_and_names_files_only_in_the_folders() -> None:
    module = script()
    sent = [
        line.split("--file", 1)[1].split()[0] for _, line in lines_of("comando") if "--file" in line
    ]

    assert sent
    for plan in sent:
        (step,) = json.loads((ROOT / plan).read_text(encoding="utf-8"))["steps"]
        path = step["arguments"]["path"]
        inside = any(path.startswith(f"{one}/") for one in module.FOLDERS)
        assert inside or path == module.OUTSIDE, plan


def test_the_section_writes_the_real_lines_and_says_the_old_line_does_not_start_ela() -> None:
    """Decision 54 and answer 35: the lines of the Mac of the proof, the order of the list, no
    live policy of the files before the root changes, the windows of macOS at the restart — and
    yesterday's line refused."""
    said = " ".join(section().split())

    assert "ELA_FS_ROOT=/Users/tommasosilvi ELA_FS_SCOPE=[" in said
    assert "**La riga di ieri non fa più partire ELA**" in said
    assert "**Nessuna policy viva dei file prima di cambiare la radice.**" in said
    assert "**L'ordine conta**" in said
    assert "**Se macOS apre una finestra**" in said


def test_the_policy_of_the_proof_has_the_uses_it_plans_and_one_more() -> None:
    for number, line in lines_of("crea"):
        cap = int(line.split(" --uses ", 1)[1].split()[0])
        said = [
            int(one.split(" usi ", 1)[1].split()[0])
            for _, one in lines_of("policy")
            if one.startswith(f"<id della policy {number}> ")
        ]
        assert said and max(said) + 1 == cap, (number, line, said)


def test_the_file_is_in_downloads_with_the_name_of_the_milestone() -> None:
    out = script().default_out()

    assert out.parent == Path.home() / "Downloads"
    assert out.name.startswith("prova-m13.17-") and out.suffix == ".txt"


def test_the_script_reads_the_root_from_ela_and_never_joins_library_to_it() -> None:
    """Answer 45, and the rule of the section: the root and the list are read from ELA, never from
    the settings in the script's own process, and the folder in Library is only compared with the
    list. What this source check cannot say: step 8 makes ``Settings.load()`` read the ``.env`` in a
    child process, by design — the configuration refused with one variable changed (answer 44)."""
    source = SCRIPT.read_text(encoding="utf-8")

    assert "FilesystemSettings" not in source and "declared_root" not in source
    assert "/ OUTSIDE" not in source and "OUTSIDE)" not in source.replace(
        "within_scope(entries, OUTSIDE)", ""
    ), "the folder in Library is only compared with the list, never joined to the root"
    assert script().OUTSIDE.startswith("Library/")


# ----------------------------------------------------------------------------------------
# The judgements of the script, each with its negative case
# ----------------------------------------------------------------------------------------


def test_the_branch_is_the_field_files_of_the_diagnostics() -> None:
    module = script()

    assert module.the_branch({"files": {}}) is None
    assert "non ha «files»" in module.the_branch({"bell": {}})


def test_the_root_must_be_the_home(tmp_path: Path) -> None:
    module = script()
    home = tmp_path / "you"
    home.mkdir()

    assert module.the_root_is_the_home({"root": str(home)}, home) is None
    why = module.the_root_is_the_home({"root": str(tmp_path)}, home)
    assert why is not None and str(tmp_path) not in why, "the sentence names no path"


@pytest.mark.parametrize(
    ("entries", "passes"),
    [
        (["Documents", "Desktop", "Downloads"], True),
        (["Desktop", "Documents/ELA"], True),
        (["Documents"], False),
        (["Documents", "Desktop", "Library"], False),
        (["Documents", "Desktop", "Library/prova-m13.17"], False),
    ],
    ids=str,
)
def test_the_list_admits_both_folders_and_never_library(entries: list[str], passes: bool) -> None:
    open_files = {"folders": [{"entry": one, "folder": f"/x/{one}"} for one in entries]}

    assert (script().the_list_admits(open_files) is None) is passes


def test_the_bell_must_be_ready() -> None:
    module = script()

    assert module.the_bell_rings({"bell": {"configured": True, "ready": True}}) is None
    assert module.the_bell_rings({"bell": {"configured": True, "ready": False}}) is not None
    assert module.the_bell_rings({}) is not None


def test_a_live_policy_of_the_five_stops_the_proof() -> None:
    module = script()
    written = {"short": "ab12cd34", "capability": "fs.write", "state": "LIVE"}

    assert module.live_of_the_five([{**written, "state": "REVOKED"}]) is None
    assert module.live_of_the_five([{**written, "capability": "browser.login"}]) is None
    assert "ab12cd34 di fs.write" in module.live_of_the_five([written])


def decided(rule: str) -> dict[str, Any]:
    return {"event_type": "PERMISSION_DECIDED", "payload": {"rule": rule}}


def test_silence_is_the_rule_and_no_question_and_no_bell() -> None:
    module = script()

    assert module.silent_failures([decided("SCOPE")], "SCOPE") == []
    assert module.silent_failures([decided("APPROVAL")], "SCOPE") != []
    asked = [decided("SCOPE"), {"event_type": "APPROVAL_REQUESTED"}]
    assert module.silent_failures(asked, "SCOPE") == [
        "il task ha una domanda: APPROVAL_REQUESTED è nell'audit"
    ]
    rang = [decided("SCOPE"), {"event_type": "BELL_RUNG"}]
    assert module.silent_failures(rang, "SCOPE") == [
        "il task ha un campanello: BELL_RUNG è nell'audit"
    ]


TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "<string>", line 1, in <module>\n'
    "ela.composition.errors.ConfigurationError: ELA is not configured:\n"
    "  ELA_FS_ROOT (/Users) holds your home (/Users/you): the folders ELA may touch reach at most\n"
)


def test_a_refusal_is_judged_by_its_exit_and_by_its_last_line() -> None:
    """Answer 44: the exit decides — a line that succeeded loaded what had to be refused —, and
    the words are looked for in the last line only."""
    module = script()

    assert module.refusal_failures(1, TRACEBACK, "holds your home") == []
    assert module.refusal_failures(0, TRACEBACK, "holds your home") != []
    assert module.refusal_failures(1, TRACEBACK + "\nsomething else\n", "holds your home") != []
    assert module.refusal_failures(1, "", "holds your home") != []
    assert module.last_line("a\n\n  b  \n\n") == "b"


def test_a_refusal_puts_its_last_line_on_the_screen_and_only_its_exit_in_the_file(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    module = script()
    (line, words) = (
        'ELA_FS_ROOT=/Users uv run python -c "from ela.composition import Settings; '
        'Settings.load()"',
        "holds your home",
    )
    monkeypatch.setattr(
        module.base,
        "run",
        lambda sent, limit=None: subprocess.CompletedProcess(sent, 1, "", TRACEBACK),
    )
    report = module.Report(io.StringIO())
    proof = module.Proof(None, report, lambda _: "s", root=tmp_path)

    module.a_refusal(8, module.base.Block(8, "rifiuto", f"{line}\n{words}"), proof)

    written = "\n".join(report.lines)
    shown = capsys.readouterr().out
    assert report.failures == 0
    assert "/Users/you" not in written and "uscita 1" in written
    assert "holds your home (/Users/you)" in shown
    assert module.PYTHON_REMOVED in shown and "Traceback" not in shown


def test_the_folders_are_prepared_and_what_is_not_the_proof_s_stops_it(tmp_path: Path) -> None:
    module = script()
    planned = module.planned_files(marked())
    report = module.Report(io.StringIO())
    left = tmp_path / "Desktop/prova-m13.17/due.md"
    left.parent.mkdir(parents=True)
    left.write_text("di prima", encoding="utf-8")

    assert module.prepared(tmp_path, report, planned) is None
    assert not left.exists(), "a file of the plans, from a proof before, is removed"
    assert (tmp_path / "Desktop/prova-m13.17/policy").is_dir()
    assert (tmp_path / "Documents/ELA/prova-m13.17").is_dir()

    stranger = tmp_path / "Desktop/prova-m13.17/mio.txt"
    stranger.write_text("di Tommaso", encoding="utf-8")
    why = module.prepared(tmp_path, report, planned)
    assert why is not None and "mio.txt" in why
    assert stranger.exists()


def test_the_cleaning_takes_the_folder_away_only_with_the_proof_s_files(tmp_path: Path) -> None:
    module = script()
    planned = module.planned_files(marked())
    folder = tmp_path / "Desktop/prova-m13.17"
    (folder / "policy").mkdir(parents=True)
    (folder / "policy/tre.md").write_text("x", encoding="utf-8")

    stranger = folder / "policy/tuo.md"
    stranger.write_text("di Tommaso", encoding="utf-8")
    assert module.cleaned(tmp_path, "Desktop/prova-m13.17", planned) != []
    assert stranger.exists()

    stranger.unlink()
    assert module.cleaned(tmp_path, "Desktop/prova-m13.17", planned) == []
    assert not folder.exists()


# ----------------------------------------------------------------------------------------
# The walk: steps 2 to 12 against a real ELA, with the root at the home of the walk
# ----------------------------------------------------------------------------------------


class World(WithTheGuard):
    """M13.15's edge of the machine, and the two lines of ``rifiuto``: the settings loaded in
    process with the line's variable changed for that line alone — ``/Users`` is the folder that
    holds the home of the walk —, and what ``python -c`` prints when it raises."""

    def __init__(self, users: Path) -> None:
        super().__init__()
        self.users = users
        self.lock = threading.Lock()

    def run(self, line: str, limit: float | None = None) -> Any:
        if not line.startswith("ELA_"):
            return super().run(line, limit)
        self.ran.append(line)
        name, value = shlex.split(line)[0].split("=", 1)
        value = str(self.users) if value == "/Users" else value
        with self.lock:
            before = os.environ.get(name)
            os.environ[name] = value
            try:
                Settings.load()
            except ConfigurationError as refused:
                printed = (
                    "Traceback (most recent call last):\n"
                    '  File "<string>", line 1, in <module>\n'
                    f"ela.composition.errors.ConfigurationError: {refused}\n"
                )
                return subprocess.CompletedProcess(line, 1, "", printed)
            finally:
                if before is None:
                    del os.environ[name]
                else:
                    os.environ[name] = before
        return subprocess.CompletedProcess(line, 0, "", "")


@dataclasses.dataclass
class Walked:
    report: Any
    world: World
    home: Path
    policies: list[dict[str, Any]]

    @property
    def written(self) -> str:
        return "\n".join(self.report.lines)


@asynccontextmanager
async def an_ela(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, home: Path) -> AsyncIterator[Any]:
    """ELA as ``build`` makes it, with the root at ``home`` and the list of the proof. No key, no
    cap, no browser."""
    for folder in ("Documents/ELA", "Desktop", "Library", ".ela"):
        (home / folder).mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    declare(
        monkeypatch,
        tmp_path,
        ELA_FS_ROOT=str(home),
        ELA_FS_SCOPE='["Documents", "Desktop"]',
    )
    settings = Settings.load()
    await create_schema(settings.persistence.db_url)
    ela = await build(settings, power=FakePower())
    app = create_app(ela)
    transport = LoopTransport(app, asyncio.get_running_loop())
    monkeypatch.setattr(
        cli_client, "connect", lambda: cli_client.open_client(ela.settings.api, transport=transport)
    )
    try:
        async with app.router.lifespan_context(app):
            yield ela
    finally:
        await ela.aclose()


async def walked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Walked:
    """Steps 2 to 12 as written, run by the script against a real ELA after the folders of step 1
    are prepared. Tommaso says yes to every question, and «s» to every fact."""
    module = script()
    (tmp_path / "docs").symlink_to(ROOT / "docs", target_is_directory=True)
    home = tmp_path / "Users" / "you"

    async with an_ela(monkeypatch, tmp_path, home):
        world = World(tmp_path / "Users")
        monkeypatch.setattr(module.base, "run", world.run)
        monkeypatch.setattr(module.base, "started", world.started)
        report = module.Report(io.StringIO())
        after: list[dict[str, Any]] = []

        def walk() -> None:
            assert module.prepared(home, report, module.planned_files(marked())) is None
            api = module.base.Api()
            proof = module.Proof(api, report, lambda _: "s", root=home, home=home)
            try:
                module.walked(report, marked(), proof)
                after.extend(api.get("/policies?all=true")["policies"])
            finally:
                api.close()
            report.verdict()

        await asyncio.wait_for(asyncio.to_thread(walk), 180)
    return Walked(report, world, home, after)


async def test_steps_2_to_12_walk_against_a_real_ela_and_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Every block of the section judged on what a real ELA did: the two writes that ask in the two
    folders, the read whose question says the size, the write in Library refused before any
    question, the two refusals at the start-up, the policy on a folder of the second entry, the
    lines «why I ask» both ways, and the folder of the Desktop taken away — **and no whole path
    of a file in the file of the proof**."""
    walk = await walked(monkeypatch, tmp_path)

    assert walk.report.ok, walk.written
    assert walk.report.skipped_steps == [], walk.written
    assert [(one["capability"], one["state"], one["uses"]) for one in walk.policies] == [
        ("fs.write", "REVOKED", 1)
    ]
    assert (walk.home / "Documents/ELA/prova-m13.17/uno.md").is_file()
    assert not (walk.home / "Desktop/prova-m13.17").exists()
    assert not (walk.home / "Library/prova-m13.17").exists()
    assert str(walk.home) not in walk.written and str(walk.home.resolve()) not in walk.written
    assert [line for line in walk.world.ran if line.startswith("ELA_")] == [
        line for _, line in lines_of("rifiuto") if line.startswith("ELA_")
    ]
