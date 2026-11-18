"""``scripts/prova_m13_15.py`` against section 34 of the guide (M13.15; decisions 26, 27 and 52,
answers 48–52 of the review of its SPEC). The guide is the source of truth and the script reads it;
this file keeps the two aligned, in the form of ``test_prova_m13_14.py``.

**The section and the script are one vocabulary**: every marker is a kind the script knows, every
kind it knows is used, every plan it sends exists and names a file only inside the folder of the
proof.

**Every judgement of its own has its negative case**: the size and the sha256 of an upload, the
words that must be absent, the step skipped for an ambiguous vault, the id of the entry kept out of
the file and its temporary plan taken away.

**Steps 2 to 14 are walked by the script against a real ELA** — its routes, its command line, its
Guardian, its executor and its tools, its database — with the two browsers and the vault of
``ela.testing``, on a real disk under a declared root. No model is called and no site is reached.
"""

from __future__ import annotations

import asyncio
import dataclasses
import importlib.util
import io
import json
import re
import stat
import sys
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from functools import cache
from pathlib import Path
from typing import Any, Final

import pytest

from ela.api import create_app
from ela.cli import client as cli_client
from ela.composition import Settings, build
from ela.ports import DOWNLOAD_GESTURE, Field, Secret
from ela.testing.fakes import (
    FakeAccountBrowser,
    FakeBrowser,
    FakePage,
    FakePower,
    FakeVault,
    FakeVaultEntry,
)
from tests.cli.support import LoopTransport
from tests.composition.support import (  # noqa: F401 — re-exported as a fixture
    _only_the_declared_environment,
    create_schema,
    declare,
)
from tests.docs.test_prova_m13_10 import World as WithABackground

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prova_m13_15.py"
SIBLINGS = (
    "prova_m6_3c",
    "prova_m13_9",
    "prova_m13_10",
    "prova_m13_13",
    "prova_m13_14",
    "prova_m14_1",
    "prova_m14_2",
    "prova_m14_3",
)
ENTRY_ID: Final = "5e1f0c2a-7b3d-4e8f-9a01-23456789abcd"
"""An id of an entry of the fake vault — searched for in the file of the proof, and never found."""
USERNAME: Final = "tester@example.com"
MASKED_USERNAME: Final = "t…@example.com"
"""The username as a surface shows it: on the screen at the birth of the policy, never in the file
(finding 5 of the consistency reading: the guide promises the file without the username)."""
HN: Final = FakeVaultEntry(
    ENTRY_ID,
    "Hacker News",
    ("https://news.ycombinator.com/login",),
    USERNAME,
    "-".join(("SENTINEL", "of", "the", "word")),
    MASKED_USERNAME,
)
ACCT = "form:not(:has(input[name=creating])) input[name=acct]"
PW = "form:not(:has(input[name=creating])) input[name=pw]"
SUBMIT = "input[type=submit][value=login]"


@cache
def script() -> Any:
    before = {name: sys.modules.pop(name, None) for name in SIBLINGS}
    spec = importlib.util.spec_from_file_location("prova_m13_15", SCRIPT)
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
    assert sorted(marked()) == list(range(2, 16))


def test_every_line_is_in_the_vocabulary_of_its_kind() -> None:
    assert script().outside_vocabulary(marked()) == []


def test_it_comes_after_section_33_and_before_where_to_look() -> None:
    text = guide()

    assert text.index("## 33. ") < text.index("## 34. ") < text.index("## Dove guardare dopo")


def test_every_plan_the_section_sends_exists_and_names_files_only_in_the_folder() -> None:
    module = script()
    sent = [
        line.split("--file", 1)[1].split()[0] for _, line in lines_of("comando") if "--file" in line
    ]

    assert sent
    for plan in sent:
        (step,) = json.loads((ROOT / plan).read_text(encoding="utf-8"))["steps"]
        file = step["arguments"].get("file")
        assert file is None or file.startswith(f"{module.FOLDER}/"), plan
        assert step["arguments"]["site"] in module.SITES, plan


def test_the_section_says_the_interruption_is_proven_by_tests_that_exist() -> None:
    """Decision 22 and answer 49: no step of the hand interrupts a download **at the tool's time**
    — the section says the tests prove it, and names three that the suite holds. The stop of the
    task while the file arrives has a step, since M13.9d (decision 94)."""
    names = re.findall(r"`(test_[a-z_]+)`", section().split("### 1. Prima", 1)[0])
    machine = ROOT / "tests" / "infrastructure" / "machine" / "test_the_files_of_a_page.py"
    held = machine.read_text(encoding="utf-8")
    said = " ".join(section().split())

    assert "**L'interruzione di uno scaricamento per il tempo del tool non ha un passo**" in said
    assert "**Il «ferma» mentre il file arriva ha un passo, il 14**" in said
    assert len(names) == 3
    for name in names:
        assert f"def {name}(" in held, name


def test_the_script_never_launches_the_vault_s_program() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "subprocess" not in source and '"bw"' not in source and "'bw'" not in source
    with pytest.raises(ValueError):
        script().a_hand_line("bw unlock --raw")


def test_the_policies_of_the_proof_have_the_uses_they_plan_and_one_more() -> None:
    """Decision 50: no policy is spent before the last step that leans on it — the login 2 —, and
    decision 94 of M13.9d: the stop of step 14 is one use more of the policy of step 3. The cap of
    each is the most uses a ``policy`` block of the section says of it, and one."""
    module = script()
    for number, line in lines_of("crea"):
        cap = int(line.split(" --uses ", 1)[1].split()[0])
        said = [
            int(found.group(1))
            for _, one in lines_of("policy")
            if one.startswith(f"<id della policy {number}> ")
            and (found := re.search(r" usi (\d+) di (\d+) ", one))
            and int(found.group(2)) == cap
        ]
        assert said and max(said) + 1 == cap, (number, line, said)
    assert module.RUN_LIMIT == 120


def test_the_file_is_in_downloads_with_the_name_of_the_milestone() -> None:
    out = script().default_out()

    assert out.parent == Path.home() / "Downloads"
    assert out.name.startswith("prova-m13.15-") and out.suffix == ".txt"


# ----------------------------------------------------------------------------------------
# The judgements of the script, each with its negative case
# ----------------------------------------------------------------------------------------


def test_the_size_and_the_sha256_of_an_upload_pass_and_another_fails() -> None:
    module = script()
    good = {"size": 3, "digest": "abc"}

    assert module.result_failures(good, 3, "abc") == []
    assert module.result_failures({**good, "size": 4}, 3, "abc")
    assert module.result_failures({**good, "digest": "abd"}, 3, "abc")
    assert module.result_failures(None, 3, "abc")


def test_words_that_must_be_absent_pass_when_absent_and_fail_when_said() -> None:
    module = script()

    assert module.absent_failures(["goes on until it ends"], "revoked policy 3f2a1b2c") == []
    assert module.absent_failures(["goes on"], "a session goes on until it ends")


def test_the_id_of_the_entry_never_enters_the_file_and_its_plan_is_taken_away(
    tmp_path: Path,
) -> None:
    """Decision 52: the command with the id is written with the placeholder; the plan that holds it
    is a temporary file, ``600``, outside the repository, taken away at the end of the step."""
    module = script()
    report = module.Report(io.StringIO())
    proof = module.Proof(None, report, lambda _: "s", root=tmp_path)
    proof.entry = ENTRY_ID
    line = "uv run ela task plan 1 --file docs/examples/policy-login-ycombinator.json"

    sent = module.with_the_entry(line, proof)
    (temporary,) = proof.temporary
    held = temporary.read_text(encoding="utf-8")
    mode = stat.S_IMODE(temporary.stat().st_mode)
    module.removed(proof)

    assert ENTRY_ID in held and str(temporary) in sent
    assert mode == 0o600 and not str(temporary).startswith(str(ROOT))
    assert not temporary.exists()
    assert module.masked(f"--entry {ENTRY_ID}", proof) == f"--entry {module.ENTRY}"


def test_a_command_past_its_limit_is_closed_and_said() -> None:
    """Decision 84, the negative case: a command that does not return within its limit is closed
    — its group, which is the command and what it started — and ``Overdue`` says it."""
    module = script()
    marker = "31.0817"
    began = time.monotonic()

    with pytest.raises(module.base.Overdue) as late:
        # Two commands, so that the shell stays the parent of what it started: closing the shell
        # alone would leave the sleep, and its pipe, for half a minute.
        module.base.run(f"sleep {marker}; true", 0.5)

    assert time.monotonic() - began < 10, "the command was waited for past its limit"
    assert late.value.limit == 0.5 and "non è tornato in 0.5 s" in str(late.value)
    listed = module.base.processes()
    assert not any(f"sleep {marker}" in command for command in listed.values())


def test_a_command_without_a_limit_is_run_as_before() -> None:
    module = script()

    done = module.base.run("echo come prima")

    assert done.returncode == 0 and done.stdout == "come prima\n"


def test_a_run_past_its_guard_fails_the_step_writes_the_task_and_stops(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Decision 84: every ``ela task run`` has the guard; past it the step is FALLITO with its
    reason, ``ela task show`` of the task goes in the file, and the walk stops."""
    module = script()
    asked: list[tuple[str, float | None]] = []

    def run(line: str, limit: float | None = None) -> Any:
        asked.append((line, limit))
        if line.startswith(module.RUN):
            raise module.base.Overdue(line, limit or 0)
        return module.base.subprocess.CompletedProcess(line, 0, "state EXECUTING\n", "")

    monkeypatch.setattr(module.base, "run", run)
    report = module.Report(io.StringIO())
    proof = module.Proof(None, report, lambda _: "s", root=tmp_path)
    proof.current = 3
    turn = module.guided.Turn()
    turn.task_id = "t-1"

    with pytest.raises(module.base.Stop) as stopped:
        module.a_command("uv run ela task run t-1", turn, proof)

    assert asked == [("uv run ela task run t-1", 120), ("uv run ela task show t-1", None)]
    written = "\n".join(report.lines)
    assert report.failures == 1 and "non è tornato in 120 s" in written
    assert "state EXECUTING" in written and "non è tornato in 120 s" in str(stopped.value)


def test_a_stop_is_judged_by_its_code_and_by_the_time_from_the_stop() -> None:
    """Decision 94: ``browser.stopped`` within 35 s of the stop passes; another code, or later,
    fails; a step that ended before the stop is SALTATO when it finished or the site did not
    answer, and is a failure otherwise."""
    module = script()
    stopped = {"status": "FAILED", "error": {"code": "browser.stopped"}}

    assert module.stop_failures(stopped, 3.0) == []
    assert module.stop_failures(stopped, 35.5)
    assert module.stop_failures({"status": "FAILED", "error": {"code": "browser.timeout"}}, 3.0)
    assert module.stop_failures(None, 3.0)
    assert module.skipped_because({"status": "SUCCEEDED"}) == module.SKIPPED_FINISHED
    assert (
        module.skipped_because({"status": "FAILED", "error": {"code": "browser.unreachable"}})
        == module.SKIPPED_UNREACHABLE
    )
    assert module.skipped_because(stopped) is None
    assert module.skipped_because(None) is None


# ----------------------------------------------------------------------------------------
# Steps 2 to 15, walked against a real ELA
# ----------------------------------------------------------------------------------------


class World(WithABackground):
    """M13.10's edge of the machine — the command line in process, in the foreground and in the
    background —, with the guard of ``ela task run``, which in process has nothing to close."""

    def run(self, line: str, limit: float | None = None) -> Any:
        return super().run(line)


class Arriving(FakeAccountBrowser):
    """The browser of the profile of these walks, whose download from ``/drip`` arrives and never
    ends: its file is in the folder, under a name of the browser's, until the task is stopped —
    and then taken away, as the door does."""

    async def downloaded_from(self, address: str, allowed: Any, stop: Any, into: str) -> Any:
        if "/drip" not in address:
            return await super().downloaded_from(address, allowed, stop, into)
        stop.listen(DOWNLOAD_GESTURE)
        arriving = Path(into) / "4f3a9c1e-0000-4000-8000-000000000014.crdownload"
        arriving.parent.mkdir(parents=True, exist_ok=True)
        arriving.write_bytes(b"y")
        try:
            await asyncio.Event().wait()
        finally:
            arriving.unlink(missing_ok=True)
        raise AssertionError("a download that never ends ended")


@dataclasses.dataclass
class Walked:
    report: Any
    world: World
    files: Path
    policies: list[dict[str, Any]]

    @property
    def written(self) -> str:
        return "\n".join(self.report.lines)


def _file() -> Field:
    return Field("file", "", "post")


@asynccontextmanager
async def an_ela(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, entries: tuple[FakeVaultEntry, ...]
) -> AsyncIterator[tuple[Any, FakeBrowser, FakeAccountBrowser]]:
    """ELA as ``build`` makes it, with the three sites of the proof, a declared root, the two
    browsers of ``ela.testing`` and a vault open on ``entries``. No key and no cap."""
    module = script()
    program = tmp_path / "bw"
    program.write_bytes(b"\xcf\xfa\xed\xfe a native program")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    declare(
        monkeypatch,
        tmp_path,
        ELA_BROWSER_SITES=json.dumps(list(module.SITES)),
        ELA_VAULT_PROGRAM=str(program),
    )
    settings = Settings.load()
    await create_schema(settings.persistence.db_url)
    shown = {None: "Upload successful! logout"}
    empty = FakeBrowser(
        FakePage(download=b"x" * 1024, fields={"#fileinput": _file()}, texts=dict(shown))
    )
    login = {
        ACCT: Field("text", "username", "post"),
        PW: Field("password", "current-password", "post"),
        SUBMIT: Field("submit", "", "post"),
    }
    yours = Arriving(
        FakePage(
            download=b"y" * 2048,
            fields={"#fileinput": _file(), **login},
            texts=dict(shown),
        )
    )
    vault = FakeVault(list(entries))
    ela = await build(settings, power=FakePower(), browser=empty, accounts=yours, vault=vault)
    assert await ela.vault.open(Secret(vault.key)) is None
    app = create_app(ela)
    transport = LoopTransport(app, asyncio.get_running_loop())
    monkeypatch.setattr(
        cli_client, "connect", lambda: cli_client.open_client(ela.settings.api, transport=transport)
    )
    try:
        async with app.router.lifespan_context(app):
            yield ela, empty, yours
    finally:
        await ela.aclose()


async def walked(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    entries: tuple[FakeVaultEntry, ...] = (HN,),
    answers: Mapping[str, str] | None = None,
) -> Walked:
    """Steps 2 to 15 as written, run by the script against a real ELA after the folder of step 1
    is prepared. The hands: step 12 closes the vault, as Tommaso would."""
    module = script()
    (tmp_path / "docs").symlink_to(ROOT / "docs", target_is_directory=True)
    said = dict(answers or {})
    loop = asyncio.get_running_loop()

    async with an_ela(monkeypatch, tmp_path, entries) as (ela, _, _):

        def ask(question: str) -> str:
            if question.startswith("[12] Premi Invio"):
                asyncio.run_coroutine_threadsafe(ela.vault.close(), loop).result(30)
            return next((no for start, no in said.items() if question.startswith(start)), "s")

        world = World()
        monkeypatch.setattr(module.base, "run", world.run)
        monkeypatch.setattr(module.base, "started", world.started)
        report = module.Report(io.StringIO())
        files = module.m14.declared_root()[0]
        after: list[dict[str, Any]] = []

        def walk() -> None:
            assert module.prepared(files, report, module.planned_files(marked())) is None
            api = module.base.Api()
            proof = module.Proof(api, report, ask, root=files)
            try:
                module.walked(report, marked(), proof, lambda _: ENTRY_ID)
                after.extend(api.get("/policies?all=true")["policies"])
            finally:
                api.close()
            report.verdict()

        await asyncio.wait_for(asyncio.to_thread(walk), 180)
    return Walked(report, world, files, after)


async def test_steps_2_to_15_walk_against_a_real_ela_and_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Every block of the section judged on what a real ELA did: the two downloads and the two
    uploads under their policies with no question, the three that ask, the file with two names
    refused before the spend, the login covered and the one without its entry that asks, the
    vault closed, the stop of a download while its file arrives, and the revocations — **and the
    id of the entry never in the file**."""
    module = script()

    walk = await walked(monkeypatch, tmp_path)

    assert walk.report.ok, walk.written
    assert walk.report.skipped_steps == [], walk.written
    assert f"fermato mentre il file arrivava: {module.STOPPED}" in walk.written, walk.written
    states = sorted((one["capability"], one["state"], one["uses"]) for one in walk.policies)
    assert states == [
        ("browser.download", "REVOKED", 1),
        ("browser.download_as_you", "REVOKED", 2),
        ("browser.login", "REVOKED", 1),
        ("browser.upload", "REVOKED", 1),
        ("browser.upload_as_you", "REVOKED", 1),
    ]
    folder = walk.files / module.FOLDER
    assert sorted(one.name for one in (folder / "giu").iterdir()) == [
        "come-te.bin",
        "scaricato.bin",
    ]
    assert ENTRY_ID not in walk.written, "the id of the entry entered the file of the proof"
    assert USERNAME not in walk.written, "the whole username entered the file of the proof"
    assert MASKED_USERNAME not in walk.written, "the masked username entered the file of the proof"
    assert str(walk.files) not in walk.written and str(walk.files.resolve()) not in walk.written
    assert not list(Path(module.tempfile.gettempdir()).glob("prova-m13.15-*.json"))


async def test_an_ambiguous_vault_skips_the_login_that_asks_and_says_why(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Answer 48 (i): two entries for the site, and the login without ``entry`` stops before the
    question — the step is SALTATO with its reason, never FAILED, and the steps after go on."""
    module = script()
    twin = dataclasses.replace(HN, id="6e1f0c2a-7b3d-4e8f-9a01-23456789abce", name="Altra")

    walk = await walked(monkeypatch, tmp_path, entries=(HN, twin))

    assert walk.report.skipped_steps == [11], walk.written
    assert walk.report.failures == 0, walk.written
    assert module.SKIPPED_AMBIGUOUS in walk.written
