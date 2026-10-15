"""``scripts/prova_m13_10.py`` against section 29 of the guide (M13.10; decision 46 of the review of
its SPEC). The guide is the source of truth and the script reads it; this file keeps the two
aligned, as ``test_prova_m13_9.py`` does for section 28.

**The section and the script are one vocabulary**: every marker is a kind the script knows, every
kind it knows is used, every placeholder is one it fills, every plan it sends exists.

**Every judgement of its own has its negative case**: the stop given in time, the page that waits
and the processes left.

**WhatsApp is not in it** (decision 61 of the review of M13.10's implementation): with ELA's profile
the page did not get past its loading bar in the first measure, and the plan is out of the
repository, in ``.git/m13.10-reference/examples/``.

**Steps 2 and 3 are walked by the script against a real ELA** — its routes, its command line, its
Guardian, its database, its room of the pages —, with the browser of ``ela.testing``: what the
guide says a command prints is what the command printed here. Steps 4 and 5 want a vault, a model
and a real ELA to stop, and are walked block by block above, with the machine injected.
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
from ela.ports import Secret
from ela.testing.fakes import FakeAccountBrowser, FakeVault, FakeVaultEntry
from tests.api.guided import SITES, Script, gesture, guided
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


def test_every_plan_the_section_sends_is_an_example_of_the_repository() -> None:
    module = script()
    sent = {
        _named_after_file(line)
        for blocks in marked().values()
        for one in blocks
        for line in one.lines
        if "--file" in line
    }

    for name in sent:
        assert (ROOT / name).is_file(), name
    assert module.SESSION_PLAN.is_file()


def _named_after_file(line: str) -> str:
    """What follows ``--file``: a path, or a placeholder whole — its words and its brackets."""
    rest = line.split("--file", 1)[1].strip()
    return rest[: rest.index(">") + 1] if rest.startswith("<") else rest.split()[0]


def test_the_sites_of_the_proof_are_the_ones_the_section_tells_the_user_to_declare() -> None:
    for site in script().SITES:
        assert f"`{site}`" in section(), site


def test_every_line_of_every_block_of_the_section_is_in_the_vocabulary_of_its_kind() -> None:
    """Decision 69 of the review of M13.10's implementation: the proof fell at step 4 on a line of
    ``aspetta`` its script could not read — ``browser.login WAITING_APPROVAL``, outside the
    vocabulary of M14.3 —, and no check had read that line against it. Every line, read from the
    section, with the reader the script itself reads it with."""
    module = script()
    for number, blocks in marked().items():
        for one in blocks:
            for line in one.lines:
                try:
                    module.READERS[one.kind](line)
                except ValueError as error:
                    pytest.fail(f"step {number}, {one.kind}: {error}")


def test_no_kind_the_section_uses_is_left_out_of_the_vocabularies() -> None:
    used = {one.kind for blocks in marked().values() for one in blocks}

    assert used <= set(script().READERS)
    assert set(script().READERS) == set(script().KINDS)


def test_the_script_stops_before_step_1_on_a_line_outside_the_vocabulary_of_its_kind() -> None:
    """The proof that fell checked the line in the middle of step 4, after three steps and a yes:
    now it reads every line before it begins."""
    module = script()
    todo = {
        2: [block(2, "atteso", "outcome finished")],
        4: [block(4, "aspetta", "browser.login WAITING_APPROVAL")],
        7: [block(7, "numero", "NUMERO")],
    }

    wrong = module.outside_vocabulary(todo)

    assert len(wrong) == 2, wrong
    assert "outcome finished" in wrong[0] and "passo 2" in wrong[0]
    assert "'numero' is not a kind of the section" in wrong[1], "a kind with no reader is wrong"


def test_main_reads_every_line_before_step_1_and_touches_nothing_when_one_is_wrong(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = script()
    guide_file = tmp_path / "GETTING_STARTED.md"
    guide_file.write_text(
        "## 29. La prova\n\n### 2. Uno\n\n<!-- prova: 2.atteso -->\n```\noutcome finished\n```\n"
        "\n## Dove guardare dopo\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "GUIDE", guide_file)
    monkeypatch.setattr(
        module, "preconditions", lambda report: pytest.fail("the world was asked for")
    )
    out = tmp_path / "out.txt"

    assert module.main(["--out", str(out)]) == 1
    assert "fuori dal vocabolario" in out.read_text(encoding="utf-8")


def test_the_gestures_are_those_the_source_gives_the_session_of_step_4_in_the_catalogue() -> None:
    """The vocabulary takes the capabilities from what the source declares — the gestures of the
    kind of session the plan of step 4 asks for —, not from a list written by hand: the next
    gesture of that session does not make it false."""
    from ela.permissions.capabilities import production_catalogue
    from ela.tools.guided import SESSION_AS_YOU

    module = script()
    asked = json.loads(module.SESSION_PLAN.read_text(encoding="utf-8"))
    ((capability,),) = [step["required_capabilities"] for step in asked["steps"]]
    catalogue = {spec.id for spec in production_catalogue().specs()}

    assert capability == SESSION_AS_YOU.capability
    assert module.SESSION_GESTURES is SESSION_AS_YOU.gestures
    assert SESSION_AS_YOU.gestures.capabilities() <= catalogue


@pytest.mark.parametrize(
    ("rule", "failures"), [("SESSION", 0), ("APPROVAL_EVERY_USE", 1), (None, 1)]
)
def test_a_read_with_the_profile_asks_only_as_the_session_covers_it(
    rule: str | None, failures: int
) -> None:
    """Found walking step 4: the read of a session with the profile asks — ``browser.read_as_you``
    is ``MEDIUM`` — and the session covers it; a read the user was asked for is still a failure."""
    module = script()
    child = {
        "id": "c-1",
        "plan_author": {"by": "SESSION", "session": "s-1", "model": module.MODEL},
        "steps": [
            {
                "required_capabilities": ["browser.read_as_you"],
                "within": [HN],
                "requires_authorization": True,
            }
        ],
    }

    found = module.guided.child_failures(child, "s-1", [HN], module.SESSION_GESTURES, rule)

    assert len(found) == failures, found


@pytest.mark.parametrize(
    ("kind", "line"),
    [
        ("comando", "rm -rf docs"),
        ("comando", "uv run ela task run <un id che lo script non riempie>"),
        ("sì", "uv run ela task cancel <id>"),
        ("atteso", "outcome finished"),
        ("atteso", "outcome"),
        ("fine", "outcome done"),
        ("aspetta", "browser.read WAITING_APPROVAL"),
        ("aspetta", "browser.guided_as_you WAITING_APPROVAL"),
        ("aspetta", "browser.login COMPLETED"),
        ("figli", "browser.act COMPLETED"),
        ("figli", "browser.login DONE"),
        ("occhio", "Una frase che non chiede niente."),
        ("mano", ""),
        ("ferma", "trenta"),
        ("ferma", "45"),
        ("pagina", "SIGKILL"),
    ],
)
def test_a_line_outside_the_vocabulary_of_its_kind_is_the_guides_error(
    kind: str, line: str
) -> None:
    with pytest.raises(ValueError):
        script().READERS[kind](line)


def test_the_file_is_in_downloads_with_the_name_of_the_milestone() -> None:
    out = script().default_out()

    assert out.parent == Path.home() / "Downloads"
    assert out.name.startswith("prova-m13.10-") and out.suffix == ".txt"


def test_whatsapp_is_not_in_the_proof_nor_its_plan_in_the_repository() -> None:
    """Decision 61: no step of the section, no block, no kind and no site of the script is
    WhatsApp's — and the plan with its placeholders is no example of the repository."""
    module = script()
    headings = re.findall(r"^### \d+\. (.+)$", section(), flags=re.MULTILINE)

    assert not any("whatsapp" in heading.lower() for heading in headings)
    assert not any("whatsapp" in one.body.lower() for blocks in marked().values() for one in blocks)
    assert "numero" not in module.KINDS
    assert not any("whatsapp" in site for site in module.SITES)
    assert not (ROOT / "docs" / "examples" / "whatsapp-to-yourself.json").exists()


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


def a_proof(answers: dict[str, Any] | None = None) -> Any:
    module = script()
    return module.Proof(
        api=Answers(answers or {}),
        report=module.Report(io.StringIO()),
        ask=lambda question: "s",
        start=module.spending.Ledger.of({"cap": "30", "spent": "0", "reserved": "0", "open": 0}),
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

            def poll(self) -> int | None:
                return None if self.thread.is_alive() or self.done is None else self.returncode

            @property
            def returncode(self) -> int:
                return 0 if self.done is None else self.done.returncode

            def communicate(self, timeout: float | None = None) -> tuple[str, str]:
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


async def walked(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    steps: set[int],
    *,
    session: Script | None = None,
    accounts: FakeAccountBrowser | None = None,
    vault: FakeVault | None = None,
    **declared: str,
) -> Walked:
    """The steps of the section in ``steps``, as written in the guide, run by the script itself
    against a real ELA with the browsers of ``ela.testing`` — and, for a step with the profile, the
    model of ``session``, the browser of the profile and an open vault."""
    module = script()
    (tmp_path / "docs").symlink_to(ROOT / "docs", target_is_directory=True)
    async with guided(
        monkeypatch,
        tmp_path,
        Script([]) if session is None else session,
        accounts=accounts,
        vault=vault,
        **declared,
    ) as g:
        if vault is not None:
            assert await g.ela.vault.open(Secret(vault.key)) is None
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


HN = "news.ycombinator.com"
HN_ENTRY = FakeVaultEntry(
    "33333333-4444-4555-8666-777777777777",
    "SENTINEL-entry-of-the-proof",
    (f"https://{HN}/",),
    "-".join(("SENTINEL", "user")) + "@example.com",
    "-".join(("SENTINEL", "word", "of", "the", "proof")),
    "S…@example.com",
)


async def test_step_4_walks_against_a_real_ela_through_its_wait_its_yes_and_its_children(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Decision 69: the step the proof fell at, walked by the script itself as the guide writes it
    — the reading that finds Tommaso still outside, the session, its yes, the run in the
    background, the login it asks for (``aspetta``), the yes to that child, the end, the children
    — against a real ELA with the browser of the profile, an open vault and a model that asks
    for the login by the site alone."""
    from ela.ports import Field
    from ela.testing.fakes import FakePage
    from tests.api.test_login_from_the_model import WRITTEN, program
    from tests.tools.test_login_form import LOGIN, SIGN_UP

    page = FakePage(
        texts={None: "login | Hacker News"},
        forms=(LOGIN, SIGN_UP),
        fields={
            WRITTEN["username_field"]: Field("text", "username", "post"),
            WRITTEN["password_field"]: Field("password", "current-password", "post"),
            WRITTEN["click"]: Field("submit", "", "post"),
        },
        counts_after_click={WRITTEN["password_field"]: 0},
        landed=f"https://{HN}/news",
        landed_status=200,
    )
    walk = await walked(
        monkeypatch,
        tmp_path,
        {4},
        session=Script([gesture("login", site=HN)]),
        accounts=FakeAccountBrowser(page),
        vault=FakeVault([HN_ENTRY]),
        ELA_VAULT_PROGRAM=program(tmp_path),
        ELA_BROWSER_SITES=json.dumps([*SITES, HN]),
    )

    assert walk.report.ok, walk.written
    assert walk.report.failures == 0 and walk.report.stopped is None, walk.written
    assert "il gesto browser.login chiede" in walk.written, walk.written
    for secret in (HN_ENTRY.password, HN_ENTRY.username, HN_ENTRY.name):
        assert secret not in walk.written
