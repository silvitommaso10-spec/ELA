"""``scripts/prova_m13_10.py`` against section 29 of the guide (M13.10; decision 46 of the review of
its SPEC). The guide is the source of truth and the script reads it; this file keeps the two
aligned, as ``test_prova_m13_9.py`` does for section 28.

**The section and the script are one vocabulary**: every marker is a kind the script knows, every
kind it knows is used, every placeholder is one it fills, every plan it sends exists.

**Every judgement of its own has its negative case**: the stop given in time, the page that waits
and the processes left, the number that enters the copy of the plan and no line of the file.

**Steps 2 and 3 are walked by the script against a real ELA** — its routes, its command line, its
Guardian, its database, its room of the pages —, with the browser of ``ela.testing``: what the
guide says a command prints is what the command printed here. Steps 4 to 7 want a vault, a model,
a real ELA to stop and a phone, and are walked block by block above, with the machine injected.
"""

from __future__ import annotations

import asyncio
import dataclasses
import importlib.util
import io
import json
import re
import shlex
import signal
import stat
import subprocess
import sys
import threading
import time
from functools import cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from ela.cli import client as cli_client
from ela.cli.app import app as ela_app
from tests.api.guided import Script, guided
from tests.cli.support import LoopTransport, plain
from tests.composition.support import (  # noqa: F401 — re-exported as a fixture
    API_TOKEN,
    TOKEN,
    _only_the_declared_environment,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prova_m13_10.py"
SIBLINGS = (
    "prova_m6_3c",
    "prova_m13_9",
    "prova_m14_1",
    "prova_m14_2",
    "prova_m14_3",
    "misura_m13_10",
)
PLACEHOLDER = re.compile(r"<[^>\s][^>]*>")


@cache
def script() -> Any:
    """The script, loaded as a module with its siblings — and what was in ``sys.modules`` put
    back, so that no other test finds them there."""
    before = {name: sys.modules.pop(name, None) for name in SIBLINGS}
    spec = importlib.util.spec_from_file_location("prova_m13_10", SCRIPT)
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
    return script().GUIDE.read_text(encoding="utf-8")


def section() -> str:
    return str(script().base.section(guide(), script().HEADING))


def marked() -> dict[int, list[Any]]:
    module = script()
    found: dict[int, list[Any]] = module.base.steps(module.base.blocks(guide(), module.HEADING))
    return found


def block(number: int, kind: str, body: str) -> Any:
    return script().base.Block(number, kind, body)


# ----------------------------------------------------------------------------------------
# The section and the script are one vocabulary
# ----------------------------------------------------------------------------------------


def test_every_marker_is_a_kind_the_script_knows_and_belongs_to_a_step_of_the_section() -> None:
    module = script()
    headings = {int(n) for n in re.findall(r"^### (\d+)\. ", section(), flags=re.MULTILINE)}
    found = marked()

    assert set(found) <= headings and 1 not in found, "step 1 is the script's own checks"
    assert {kind for blocks in found.values() for kind in (one.kind for one in blocks)} <= set(
        module.KINDS
    )


def test_every_kind_of_the_script_is_used_by_the_section() -> None:
    used = {one.kind for blocks in marked().values() for one in blocks}

    assert used == set(script().KINDS)


def test_it_comes_after_section_28_and_before_where_to_look() -> None:
    text = guide()

    assert text.index("## 28. ") < text.index("## 29. ") < text.index("## Dove guardare dopo")


def test_every_placeholder_is_one_the_script_fills() -> None:
    module = script()
    found = {
        placeholder
        for blocks in marked().values()
        for one in blocks
        if one.kind in ("comando", "sì", "schermo", "assente", "sfondo")
        for placeholder in PLACEHOLDER.findall(one.body)
    }

    assert found == set(module.PLACEHOLDERS)


def test_every_plan_the_section_sends_is_an_example_of_the_repository_or_its_copy() -> None:
    module = script()
    sent = {
        _named_after_file(line)
        for blocks in marked().values()
        for one in blocks
        for line in one.lines
        if "--file" in line
    }

    assert module.WHATSAPP_PLAN in sent, "the copy the script makes, with the number in it"
    for name in sent - {module.WHATSAPP_PLAN}:
        assert (ROOT / name).is_file(), name
    assert module.WHATSAPP.is_file() and module.SESSION_PLAN.is_file()


def _named_after_file(line: str) -> str:
    """What follows ``--file``: a path, or a placeholder whole — its words and its brackets."""
    rest = line.split("--file", 1)[1].strip()
    return rest[: rest.index(">") + 1] if rest.startswith("<") else rest.split()[0]


def test_the_sites_of_the_proof_are_the_ones_the_section_tells_the_user_to_declare() -> None:
    for site in script().SITES:
        assert f"`{site}`" in section(), site


def test_the_lines_of_the_kinds_of_this_section_are_in_their_vocabularies() -> None:
    module = script()
    for blocks in marked().values():
        for one in blocks:
            if one.kind == "ferma":
                (seconds,) = one.lines
                assert 0 < float(seconds) < 30, "inside the thirty seconds of the step"
            if one.kind == "pagina":
                assert one.lines and all(line in module.SIGNALS for line in one.lines)
            if one.kind == "numero":
                assert one.lines == [module.NUMBER]
                assert module.NUMBER in module.WHATSAPP.read_text(encoding="utf-8")


def test_the_file_is_in_downloads_with_the_name_of_the_milestone() -> None:
    out = script().default_out()

    assert out.parent == Path.home() / "Downloads"
    assert out.name.startswith("prova-m13.10-") and out.suffix == ".txt"


def test_the_plan_of_whatsapp_carries_no_number() -> None:
    """Decision 46: the number is asked by the script, never written in a file of the repository."""
    text = script().WHATSAPP.read_text(encoding="utf-8")

    assert not re.search(r"[0-9]{6,}", text.replace("c0de1a28-0000-4b00-8a00-00000000100", ""))


# ----------------------------------------------------------------------------------------
# The kinds of its own, each with its negative case
# ----------------------------------------------------------------------------------------


class Answers:
    """An API that answers what the test wrote, by path."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers

    def get(self, path: str) -> Any:
        return self.answers[path]

    def close(self) -> None:
        return None


def a_proof(answers: dict[str, Any] | None = None, *, number: str = "+393331234567") -> Any:
    module = script()
    return module.Proof(
        api=Answers(answers or {}),
        report=module.Report(io.StringIO()),
        ask=lambda question: "s",
        start=module.spending.Ledger.of({"cap": "30", "spent": "0", "reserved": "0", "open": 0}),
        secret_ask=lambda question: number,
    )


def test_a_page_of_the_task_is_one_the_state_of_the_browser_says_waits() -> None:
    module = script()
    said = {"waiting": [{"task": "t-1", "profile": False, "until": None, "stop": "x"}]}

    assert module.waiting_page("t-1", said) is True
    assert module.waiting_page("t-2", said) is False
    assert module.waiting_page("t-1", {"waiting": []}) is False


def test_the_processes_left_are_the_two_browsers_and_no_other() -> None:
    module = script()
    listing = {
        1: "/opt/x/chrome-headless-shell --headless",
        2: "/Applications/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
        3: "/bin/zsh",
    }

    assert len(module.browsers_left(listing)) == 2
    assert module.browsers_left({3: "/bin/zsh"}) == []


@pytest.fixture
def ela_that_stops(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """ELA as a process the test owns: pid 777, alive until it is signalled."""
    module = script()
    signalled: list[Any] = []
    monkeypatch.setattr(module.accounts, "ela_pid", lambda: 777)
    monkeypatch.setattr(module.accounts, "alive", lambda pid: not signalled)
    monkeypatch.setattr(module.os, "kill", lambda pid, sent: signalled.append((pid, sent)))
    monkeypatch.setattr(module.base, "processes", lambda: {3: "/bin/zsh"})
    monkeypatch.setattr(module, "WAIT", 0.0)
    return signalled


def test_ela_is_stopped_while_the_page_of_the_task_waits_and_nothing_is_left(
    ela_that_stops: list[Any],
) -> None:
    module = script()
    proof = a_proof({"/browser": {"waiting": [{"task": "t-1"}]}})
    turn = module.guided.Turn()
    turn.task_id = "t-1"

    module.a_page_that_waits(5, block(5, "pagina", "SIGTERM"), turn, proof)

    assert ela_that_stops == [(777, signal.SIGTERM)]
    assert proof.report.failures == 0 and "del browser non resta niente" in "\n".join(
        proof.report.lines
    )


def test_a_page_that_does_not_wait_is_not_the_moment_to_stop_ela(
    ela_that_stops: list[Any],
) -> None:
    module = script()
    proof = a_proof({"/browser": {"waiting": []}})
    turn = module.guided.Turn()
    turn.task_id = "t-1"

    module.a_page_that_waits(5, block(5, "pagina", "SIGTERM"), turn, proof)

    assert ela_that_stops == [] and proof.report.failures == 1


def test_a_browser_left_after_ela_is_a_failure(
    ela_that_stops: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    module = script()
    monkeypatch.setattr(module.base, "processes", lambda: {9: "/x/chrome-headless-shell"})
    proof = a_proof({"/browser": {"waiting": [{"task": "t-1"}]}})
    turn = module.guided.Turn()
    turn.task_id = "t-1"

    module.a_page_that_waits(5, block(5, "pagina", "SIGTERM"), turn, proof)

    assert proof.report.failures == 1 and "restano processi del browser" in "\n".join(
        proof.report.lines
    )


def test_without_an_ela_that_listens_nobody_is_signalled(monkeypatch: pytest.MonkeyPatch) -> None:
    module = script()
    monkeypatch.setattr(module.accounts, "ela_pid", lambda: None)
    sent: list[Any] = []
    monkeypatch.setattr(module.os, "kill", lambda *args: sent.append(args))
    proof = a_proof({"/browser": {"waiting": [{"task": "t-1"}]}})

    module.a_page_that_waits(5, block(5, "pagina", "SIGTERM"), module.guided.Turn(), proof)

    assert sent == [] and proof.report.failures == 1


class Background:
    """A run of a step in the background, which ends when it is told."""

    def __init__(self, printed: str, *, ends: bool = True) -> None:
        self.printed, self.ends, self.killed = printed, ends, False

    def communicate(self, timeout: float) -> tuple[str, str]:
        if not self.ends:
            raise subprocess.TimeoutExpired("run", timeout)
        return self.printed, ""

    def kill(self) -> None:
        self.killed = True


@pytest.mark.parametrize(("code", "failures"), [(0, 0), (1, 1)], ids=["taken", "refused"])
def test_the_stop_is_given_after_its_seconds_while_the_step_waits(
    monkeypatch: pytest.MonkeyPatch, code: int, failures: int
) -> None:
    module = script()
    asked: list[str] = []
    slept: list[float] = []
    monkeypatch.setattr(module.base, "started", lambda line: Background("outcome cancelled\n"))
    monkeypatch.setattr(
        module.base,
        "run",
        lambda line: asked.append(line) or subprocess.CompletedProcess(line, code, "said\n", ""),
    )
    monkeypatch.setattr(
        module, "time", SimpleNamespace(sleep=slept.append, monotonic=time.monotonic)
    )
    proof = a_proof()
    turn = module.guided.Turn()
    turn.task_id = "t-1"

    module.a_stop(3, block(3, "ferma", "5"), turn, proof)

    assert slept == [5.0] and asked[0].startswith("uv run ela task cancel t-1")
    assert proof.report.failures == failures
    assert "outcome cancelled" in turn.last


def test_a_step_that_does_not_end_after_the_stop_is_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = script()
    running = Background("", ends=False)
    monkeypatch.setattr(module.base, "started", lambda line: running)
    monkeypatch.setattr(
        module.base, "run", lambda line: subprocess.CompletedProcess(line, 0, "", "")
    )
    monkeypatch.setattr(
        module, "time", SimpleNamespace(sleep=lambda seconds: None, monotonic=time.monotonic)
    )
    proof = a_proof()

    module.a_stop(3, block(3, "ferma", "5"), module.guided.Turn(), proof)

    assert running.killed and proof.report.failures == 1


def test_a_plan_of_whatsapp_with_the_placeholders_of_the_measure_is_skipped_unasked() -> None:
    """Decision 35: until the measure gives the selectors, the step is SALTATO — and the number is
    not asked for nothing."""
    module = script()
    asked: list[str] = []
    proof = a_proof()
    proof.secret_ask = asked.append

    assert module.still_to_measure(json.loads(module.WHATSAPP.read_text(encoding="utf-8")))
    with pytest.raises(module.Skipped, match="segnaposto della misura"):
        module.a_number(7, block(7, "numero", "NUMERO"), module.guided.Turn(), proof)
    assert asked == []


@pytest.fixture
def measured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """The plan of WhatsApp as the measure will leave it: selectors of a page seen from inside."""
    module = script()
    text = module.WHATSAPP.read_text(encoding="utf-8")
    for one in module.STILL_TO_MEASURE.findall(text):
        text = text.replace(one, "footer div[contenteditable]")
    measured = tmp_path / "whatsapp.json"
    measured.write_text(text, encoding="utf-8")
    monkeypatch.setattr(module, "WHATSAPP", measured)
    return measured


def test_the_number_enters_the_copy_of_the_plan_and_no_line_of_the_file(measured: Path) -> None:
    module = script()
    proof = a_proof(number="+393331234567")

    module.a_number(7, block(7, "numero", "NUMERO"), module.guided.Turn(), proof)
    proof.report.say("    | address  https://web.whatsapp.com/send?phone=393331234567")

    copy = proof.whatsapp
    assert copy is not None and "/send?phone=393331234567" in copy.read_text(encoding="utf-8")
    assert stat.S_IMODE(copy.stat().st_mode) == 0o600
    written = "\n".join(proof.report.lines)
    assert "393331234567" not in written and module.WITHHELD in written
    assert copy.parent != ROOT and ROOT not in copy.parents


def test_a_number_that_is_not_one_is_skipped(measured: Path) -> None:
    module = script()

    with pytest.raises(module.Skipped, match="non è un numero"):
        module.a_number(
            7, block(7, "numero", "NUMERO"), module.guided.Turn(), a_proof(number="339 abc")
        )


def test_in_the_one_try_of_step_7_a_failure_is_skipped_with_what_was_said() -> None:
    """Decision 16 of M13.10: the last step may be SALTATO with what the page said."""
    module = script()
    report = module.Report(io.StringIO())

    report.lenient = True
    report.failure(7, "mancano ['outcome completed']")
    report.lenient = False
    report.failure(2, "mancano ['outcome completed']")

    assert report.failures == 1
    assert any("un tentativo solo" in line for line in report.lines)


def test_main_stops_at_step_1_when_the_world_lacks_something(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = script()
    monkeypatch.setattr(
        module, "preconditions", lambda report: report.stop(1, "manca qualcosa") or False
    )
    out = tmp_path / "out.txt"

    assert module.main(["--out", str(out)]) == 1
    assert "La prova a mano di M13.10" in out.read_text(encoding="utf-8")


# ----------------------------------------------------------------------------------------
# Steps 2 and 3, walked against a real ELA
# ----------------------------------------------------------------------------------------


class World:
    """The edge of the machine of one walk: the command line of ELA answered in process — in the
    foreground and in the background —, and Tommaso's yes."""

    def __init__(self) -> None:
        self.ran: list[str] = []

    def run(self, line: str) -> subprocess.CompletedProcess[str]:
        self.ran.append(line)
        prefix = "uv run ela "
        assert line.startswith(prefix), line
        done = CliRunner().invoke(ela_app, shlex.split(line.removeprefix(prefix)))
        return subprocess.CompletedProcess(line, done.exit_code, plain(done.output), "")

    def started(self, line: str) -> Any:
        world = self

        class InTheBackground:
            def __init__(self) -> None:
                self.done: subprocess.CompletedProcess[str] | None = None
                self.thread = threading.Thread(target=self.go)
                self.thread.start()

            def go(self) -> None:
                self.done = world.run(line)

            def communicate(self, timeout: float) -> tuple[str, str]:
                self.thread.join(timeout)
                assert self.done is not None, "the run did not end"
                return self.done.stdout, ""

            def kill(self) -> None:
                return None

        return InTheBackground()


@dataclasses.dataclass
class Walked:
    report: Any
    world: World
    browser: Any

    @property
    def written(self) -> str:
        return "\n".join(self.report.lines)


async def walked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, steps: set[int]) -> Walked:
    """The steps of the section in ``steps``, as written in the guide, run by the script itself
    against a real ELA with the browser of ``ela.testing``."""
    module = script()
    (tmp_path / "docs").symlink_to(ROOT / "docs", target_is_directory=True)
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        loop = asyncio.get_running_loop()
        transport = LoopTransport(g.app, loop)
        monkeypatch.setattr(
            cli_client,
            "connect",
            lambda: cli_client.open_client(g.ela.settings.api, transport=transport),
        )
        # The button of step 3 never comes: its gesture waits until the task is stopped.
        g.browser.appear_later("button#non-esiste")
        g.browser.page.texts['pre:has-text("ELA prova 7431")'] = (
            '{"form": {"custname": "ELA prova 7431"}}'
        )
        world = World()
        monkeypatch.setattr(module.base, "run", world.run)
        monkeypatch.setattr(module.base, "started", world.started)
        monkeypatch.setattr(
            module,
            "time",
            SimpleNamespace(sleep=lambda seconds: time.sleep(0.5), monotonic=time.monotonic),
        )
        report = module.Report(io.StringIO())

        def walk() -> None:
            api = module.base.Api()
            proof = module.Proof(
                api,
                report,
                lambda question: "s",
                module.spending.Ledger.of(api.get("/spend")),
                login=module.LOGIN_PLAN,
            )
            todo = {number: blocks for number, blocks in marked().items() if number in steps}
            try:
                module.base.walk(
                    report, todo, lambda number, its: module.a_step(number, its, proof)
                )
            finally:
                api.close()

        await asyncio.wait_for(asyncio.to_thread(walk), 120)
        browser = g.browser
    return Walked(report, world, browser)


async def test_steps_2_and_3_walk_against_a_real_ela_and_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Every ``atteso`` of steps 2 and 3 judged on what ELA's own command line printed: two steps on
    one page, and the stop given while a gesture waits for its element."""
    walk = await walked(monkeypatch, tmp_path, {2, 3})

    assert walk.report.ok, walk.written
    assert walk.report.failures == 0 and walk.report.stopped is None, walk.written
    assert walk.browser.resumed == ["page-1"], "step 2's read took step 1's page back"
    assert walk.browser.fills[-1] == ("input[name=custname]", "ELA prova 7431")
    assert "button#non-esiste" in walk.browser.waited, "step 3's click waited for its element"
    assert any(line.startswith("uv run ela task cancel") for line in walk.world.ran)
