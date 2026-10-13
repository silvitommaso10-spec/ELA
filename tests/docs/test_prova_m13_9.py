"""``scripts/prova_m13_9.py`` against section 28 of the guide (M13.9; the SPEC, «La prova a mano»).

The guide is the source of truth and the script reads it; this file keeps the two aligned, in
three ways.

**The section and the script are one vocabulary**: every marker is a kind the script knows, every
kind the script knows is used, every placeholder is one it fills, every plan it sends exists.

**Every comparison has its negative case**: the script's judgements are pure functions, and each
is called on an answer that passes and on that answer changed.

**The section is walked whole, by the script, against a real ELA** — its routes, its command
line, its Guardian, its database —, with fakes only at the edge of the machine: the browser with
the profile, the vault's program, the session's model, ``hdiutil``. What the guide says a command
prints is what the command printed here; a line of the guide that the CLI stopped printing turns
this file red. The last step, which stops ELA, is walked on its own with the machine injected.
"""

from __future__ import annotations

import asyncio
import dataclasses
import importlib.util
import io
import json
import os
import re
import shlex
import stat
import subprocess
import sys
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from ela.cli import client as cli_client
from ela.cli.app import app as ela_app
from ela.ports import Field, Opened, Secret, TaskStop
from ela.testing.fakes import FakeAccountBrowser, FakePage, FakeVault, FakeVaultEntry
from tests.api.guided import Script, call, gesture, guided
from tests.cli.support import LoopTransport, plain
from tests.composition.support import (  # noqa: F401 — re-exported as a fixture
    API_TOKEN,
    TOKEN,
    _only_the_declared_environment,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prova_m13_9.py"
SIBLINGS = ("prova_m6_3c", "prova_m14_1", "prova_m14_2", "prova_m14_3")
PLACEHOLDER = re.compile(r"<[^>\s][^>]*>")
LOGIN_PLAN = ROOT / "docs" / "examples" / "login-from-the-vault.json"
AS_YOU = frozenset(
    {"browser.read_as_you", "browser.act_as_you", "browser.login", "browser.guided_as_you"}
)
"""The capabilities that act on the profile with the user's sessions: what the proof asks."""
"""The shape of a login from the vault, for any site: what the tests of the script's own checks
hand it."""
PROOF_LOGIN = ROOT / "docs" / "examples" / "login-news-ycombinator.json"
"""The plan of the login **of the proof** (decision 95): the one the guide launches the script
with, and the one the walk below sends to a real ELA."""
PROOF_SITE = "news.ycombinator.com"
PROOF_ADDRESS = "https://news.ycombinator.com/login"
"""The address the guide tells the user to give the entry of their vault."""
SITES = ["www.youtube.com", "httpbin.org", "accounts.google.com", "example.com", PROOF_SITE]
WORD = "-".join(("SENTINEL", "the", "word", "of", "the", "proof"))
ENTRY = FakeVaultEntry(
    "11111111-2222-4333-8444-555555555555",
    "La voce della prova",
    ("https://example.com/login",),
    "mario.rossi@example.com",
    WORD,
    "m…@example.com",
)


@cache
def script() -> Any:
    """The script, loaded as a module with its siblings — and what was in ``sys.modules`` put
    back, so that no other test finds them there."""
    before = {name: sys.modules.pop(name, None) for name in SIBLINGS}
    spec = importlib.util.spec_from_file_location("prova_m13_9", SCRIPT)
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

    assert headings == set(range(1, 11))
    assert set(found) == set(range(2, 11)), "step 1 is the script's own preconditions"
    assert {one.kind for blocks in found.values() for one in blocks} <= set(module.KINDS)
    markers = re.findall(r"<!-- prova: (\d+)\.(\w+) -->", section())
    assert len(markers) == sum(len(blocks) for blocks in found.values()), "a marker with no block"


def test_every_kind_of_the_script_is_used_by_the_section() -> None:
    used = {one.kind for blocks in marked().values() for one in blocks}

    assert used == set(script().KINDS)


def test_it_comes_after_section_27_and_before_where_to_look() -> None:
    text = guide()

    assert text.index("## 27. ") < text.index("## 28. ") < text.index("## Dove guardare dopo")


def test_every_placeholder_is_one_the_script_fills() -> None:
    module = script()
    written = {
        found
        for blocks in marked().values()
        for one in blocks
        for found in PLACEHOLDER.findall(one.body)
    }

    assert written == set(module.PLACEHOLDERS)
    assert f"| `{module.LOGIN_PLAN}` |" in guide(), "the legend explains the placeholder"


def test_every_plan_the_section_sends_is_an_example_of_the_repository() -> None:
    module = script()
    plans = {
        plan
        for blocks in marked().values()
        for one in blocks
        for line in one.lines
        for plan in module.guided.PLAN_FILE.findall(line)
    }

    assert plans and all((ROOT / plan).is_file() for plan in plans)
    assert module.SESSION_PLAN.relative_to(ROOT).as_posix() in plans
    assert module.arguments_of(module.SESSION_PLAN)["sites"] == ["www.youtube.com"]
    with pytest.raises(ValueError, match="not a session of"):
        module.arguments_of(ROOT / "docs" / "examples" / "guided-youtube.json")


def test_every_line_of_the_scripts_kinds_is_in_its_vocabulary() -> None:
    module = script()
    by_kind: dict[str, list[Any]] = {}
    for blocks in marked().values():
        for one in blocks:
            by_kind.setdefault(one.kind, []).append(one)

    assert all(float(one.lines[0]) > 0 for one in by_kind["misura"])
    assert all(int(one.lines[0]) > 0 and len(one.lines) == 2 for one in by_kind["disco"])
    assert {one.lines[0] for one in by_kind["chiude"]} <= set(module.SIGNALS)
    assert {one.body for one in by_kind["coperte"]} == {"browser.read_as_you"}
    assert {one.body for one in by_kind["domanda"]} == {module.NOBODY, module.LOGIN}
    assert max(marked()) == 10 and marked()[10][-1].kind == "chiude", "the stop of ELA is last"


def test_the_sites_of_the_proof_are_the_ones_the_section_tells_the_user_to_declare() -> None:
    declared = re.search(r"^ELA_BROWSER_SITES=(\[.*\])$", section(), flags=re.MULTILINE)

    assert declared is not None
    assert json.loads(declared.group(1))[:-1] == list(script().SITES)


def test_the_file_is_in_downloads_with_the_name_of_the_milestone() -> None:
    out = script().default_out()

    assert out.parent == Path.home() / "Downloads" and out.name.startswith("prova-m13.9-")
    assert "`prova-m13.9-`" in section()


# ----------------------------------------------------------------------------------------
# Every comparison, with its negative case
# ----------------------------------------------------------------------------------------


def test_a_question_is_waiting_or_not_and_of_the_capability_the_block_names() -> None:
    module = script()
    mine = {"task_id": "t-1", "capability_id": "browser.login"}
    other = {"task_id": "t-2", "capability_id": "browser.login"}

    assert module.question_failures(module.NOBODY, [other], "t-1") == []
    assert module.question_failures(module.NOBODY, [mine, other], "t-1")
    assert module.question_failures("browser.login", [mine, other], "t-1") == []
    assert module.question_failures("browser.login", [other], "t-1")
    assert module.question_failures("browser.act_as_you", [mine], "t-1")
    assert module.question_failures("browser.login", [mine, mine], "t-1")


def a_child(identity: str, capability: str, state: str = "COMPLETED") -> dict[str, Any]:
    return {"id": identity, "state": state, "steps": [{"required_capabilities": [capability]}]}


def test_a_reading_is_covered_only_by_one_decision_of_the_session() -> None:
    module = script()
    read, act = a_child("c-1", "browser.read_as_you"), a_child("c-2", "browser.act_as_you")
    covered = {"c-1": [("ALLOWED", "SESSION")], "c-2": [("REQUIRES_APPROVAL", "RISK")]}

    assert module.covered_failures("browser.read_as_you", [read, act], covered) == []
    assert module.covered_failures("browser.read_as_you", [act], covered), "nothing was read"
    asked = {"c-1": [("REQUIRES_APPROVAL", "RISK"), ("ALLOWED", "AUTHORIZATION")]}
    assert module.covered_failures("browser.read_as_you", [read], asked), "a yes is not a cover"
    after = {"c-1": [("REQUIRES_APPROVAL", "RISK"), ("ALLOWED", "SESSION")]}
    assert module.covered_failures("browser.read_as_you", [read], after), (
        "a read that asked first is not one the session covered, whatever came after"
    )
    assert module.covered_failures("browser.read_as_you", [read], {}), "no decision at all"
    denied = a_child("c-1", "browser.read_as_you", "DENIED")
    assert module.covered_failures("browser.read_as_you", [denied], covered)


def test_the_decisions_of_a_child_are_read_from_its_audit_in_order() -> None:
    audit = [
        {"event_type": "TASK_CREATED", "payload": {}},
        {"event_type": "PERMISSION_DECIDED", "payload": {"outcome": "ALLOWED", "rule": "SESSION"}},
    ]

    assert script().decided(audit) == [("ALLOWED", "SESSION")]
    assert script().decided(audit[:1]) == []


def test_the_listing_is_a_difference_and_it_reopens_above_the_threshold_only() -> None:
    module = script()

    assert module.listing(2.5, 6.0) == 3.5
    assert module.listing(4.0, 3.0) == 0.0, "a difference is never below nothing"
    assert not module.reopens(10.0, 10.0), "at the threshold the line passes"
    assert module.reopens(10.1, 10.0)


def test_the_ram_disk_is_sized_named_and_looked_for_after_it_is_detached() -> None:
    module = script()

    assert module.blocks_of(64) == 131072
    assert module.device_of("/dev/disk9          \n") == "/dev/disk9"
    assert module.device_of("hdiutil: attach failed") is None
    assert module.still_there(False, "/dev/disk1 /dev/disk2", "/dev/disk9") == []
    assert module.still_there(True, "", "/dev/disk9")
    assert module.still_there(False, "image-path : ram://131072\n/dev/disk9", "/dev/disk9")


MOUNTED = "/dev/disk9 on /Volumes/ELA-prova (hfs, local, nodev, nosuid, noowners, mounted by tu)"
"""What ``mount`` says of a RAM disk ``diskutil erasevolume`` made, measured on 2026-10-11 on a
disk of the measure's own: with ``noowners``, which is how such a volume is mounted."""


def test_the_volume_of_the_proof_is_the_device_just_made_and_says_whether_it_knows_owners() -> None:
    """Whose volume ``/Volumes/ELA-prova`` is, is asked of ``mount``: a volume of that name that
    was already there — a run that was killed, or the user's — is another device's, and the new
    one is mounted beside it under another name."""
    module = script()
    other = MOUNTED.replace("/dev/disk9", "/dev/disk4")
    beside = "/dev/disk9 on /Volumes/ELA-prova 1 (hfs, local, nodev, nosuid, noowners)"

    assert module.mounted_on(MOUNTED, "/dev/disk9") is True
    assert module.mounted_on(other, "/dev/disk9") is False, "that volume is another device's"
    assert module.mounted_on(f"{other}\n{beside}", "/dev/disk9") is False
    assert module.mounted_on("/dev/disk91 on /Volumes/ELA-prova (hfs)", "/dev/disk9") is False
    assert module.mounted_on("", "/dev/disk9") is False
    assert module.ignores_owners(MOUNTED, "/dev/disk9") is True
    assert module.ignores_owners(MOUNTED.replace("noowners, ", ""), "/dev/disk9") is False
    assert module.ignores_owners(other, "/dev/disk9") is False


def test_ela_is_the_listener_whose_command_line_is_ela_serve_and_no_other() -> None:
    """The signal of step 10 goes to a process: which one is judged by what it runs, and not by
    its being the first that listens on that number."""
    module = script()
    commands = {
        310: "/usr/local/bin/another-server --port 8351",
        4321: "/Users/tu/ELA/.venv/bin/python3 /Users/tu/ELA/.venv/bin/ela serve",
        4400: "/Users/tu/ELA/.venv/bin/python -m ela.cli serve",
        5000: "uv run ela task run 7",
        5001: "/opt/tools/bin/cinderela serve",
        5002: "/Users/tu/ELA/.venv/bin/ela server-of-something",
    }

    assert module.serving(commands[4321]) and module.serving(commands[4400])
    assert not any(module.serving(commands[pid]) for pid in (310, 5000, 5001, 5002))
    assert module.the_ela_among([310, 4321], commands) == 4321, "not the first that listens"
    assert module.the_ela_among([4321, 310], commands) == 4321
    assert module.the_ela_among([310], commands) is None, "a listener that is not ELA"
    assert module.the_ela_among([], commands) is None
    assert module.the_ela_among([4321, 4400], commands) is None, "two: nobody is signalled"
    assert module.the_ela_among([9999], commands) is None, "a process that is gone"


def test_the_tests_of_the_proof_run_in_a_folder_of_their_own_with_no_env_file(
    tmp_path: Path,
) -> None:
    """The script of the proof reads ELA's settings, as it must when the user runs it: the
    variables, **and the** ``.env`` **of the folder it is run in**. A test of it that stood in
    the folder the suite is launched from read the ``.env`` of whoever uses ELA on that machine
    — and, the day that file declared the folder of the profile, two of these tests looked at
    that folder: its mode, and the lock inside it (found on 2026-10-12, the day after the
    profile first held real sessions). An empty variable does not hide the line of a file: it
    is a line nobody wrote. Every test of this module stands where no ``.env`` is."""
    here = Path.cwd().resolve()

    assert here == tmp_path.resolve(), "a folder of the test's, not the one the suite runs in"
    assert not (here / ".env").exists()
    assert not [name for name in os.environ if name.startswith("ELA_")], (
        "and nothing of ELA's inherited from whoever launched the suite"
    )


def test_the_listeners_are_asked_of_lsof_on_ela_s_port_and_judged_by_their_command_lines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The port is read from ELA's own settings, which want a token: **the test hands them
    both, and stands in a folder with no ``.env``** — on the desk of whoever wrote it the
    repository has one, and a test that read it passed there and nowhere else (the CI of
    2026-10-11, red on both runners)."""
    module = script()
    asked: list[str] = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(API_TOKEN, TOKEN)

    def run(line: str) -> subprocess.CompletedProcess[str]:
        asked.append(line)
        return subprocess.CompletedProcess(line, 0, "310\n4321\n", "")

    monkeypatch.setenv("ELA_API_PORT", "8399")
    monkeypatch.setattr(module.base, "run", run)
    monkeypatch.setattr(
        module.base,
        "processes",
        lambda: {310: "/usr/local/bin/another-server", 4321: "/x/.venv/bin/ela serve"},
    )

    assert module.ela_pid() == 4321
    assert asked == ["lsof -ti tcp:8399 -sTCP:LISTEN"], "who listens, and on ELA's port"


def test_whether_a_process_is_there_and_what_the_lock_names_are_asked_of_the_machine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The two looks of step 10 the other tests replace: asked here of a real process and of a
    real link."""
    module = script()
    ended = subprocess.Popen([sys.executable, "-c", "pass"])  # noqa: S603 — the suite's own
    ended.wait()
    profile = tmp_path / "profile"
    profile.mkdir()
    monkeypatch.setenv("ELA_BROWSER_PROFILE_DIR", str(profile))

    assert module.alive(os.getpid()) is True
    assert module.alive(ended.pid) is False
    assert module.profile_lock() is None, "no lock in the folder"
    (profile / "SingletonLock").symlink_to("the-mac.local-4321")
    assert module.profile_lock() == "the-mac.local-4321"
    (profile / "Another").symlink_to("the-mac.local-9")
    assert module.profile_lock() == "the-mac.local-4321", "the lock, and no other link"
    monkeypatch.setenv("ELA_BROWSER_PROFILE_DIR", "")
    assert module.profile_lock() is None, "no folder declared"


def test_after_the_stop_ela_is_gone_and_no_live_process_holds_the_profile() -> None:
    module = script()

    assert module.lock_pid("the-mac.local-4321") == 4321
    assert module.lock_pid(None) is None and module.lock_pid("no-pid-here-x") is None
    assert module.left_running(True, None, lambda pid: True) == []
    assert module.left_running(True, "mac-4321", lambda pid: False) == [], "a dead holder is none"
    assert module.left_running(False, None, lambda pid: False), "ELA did not end"
    assert module.left_running(True, "mac-4321", lambda pid: pid == 4321), "the folder is held"


def declared_in_the_guide() -> list[str]:
    """The sites the section tells the user to declare, read from its ``.env`` line."""
    (line,) = re.findall(r"^ELA_BROWSER_SITES=(\[.*\])$", section(), re.MULTILINE)
    found: list[str] = json.loads(line)
    return found


def test_the_login_plan_of_the_proof_is_the_one_the_guide_launches_on_a_site_it_declares() -> None:
    """Decision 95: the site is ``news.ycombinator.com``, written with its whole host in the
    ``.env`` line of the section; the plan is the file the launch command names; and the entry
    of the vault the guide asks for carries an address of that host — the one ELA binds an entry
    to a site by."""
    from ela.tools.vault import host_of

    module = script()
    plan = json.loads(PROOF_LOGIN.read_text(encoding="utf-8"))
    relative = PROOF_LOGIN.relative_to(ROOT).as_posix()

    assert module.login_plan_failures(plan, declared_in_the_guide()) == []
    assert proof_login()["site"] == PROOF_SITE and PROOF_SITE in declared_in_the_guide()
    assert f"scripts/prova_m13_9.py --login {relative}" in section()
    assert PROOF_ADDRESS in section() and host_of(PROOF_ADDRESS) == PROOF_SITE
    assert proof_login()["path"] == PROOF_ADDRESS.removeprefix(f"https://{PROOF_SITE}")


def test_the_login_plan_of_the_proof_carries_no_value_and_chooses_the_one_form_of_the_sign_in() -> (
    None
):
    """Nothing of the user is in the plan — no username, no password, no entry of their vault:
    they come from the vault, after the yes. And on a page with two forms — to sign in, and to
    make an account — each selector says which: the two fields of the form that does not
    create, and the button that says «login». The text awaited is what only a page from inside
    shows, and is not a word of the sign-in page."""
    asked = proof_login()

    assert set(asked) == {
        "site",
        "path",
        "username_field",
        "password_field",
        "click",
        "expect_text",
        "purpose",
    }, "the closed set of what a login names: no value, and no entry"
    the_one_form = "form:not(:has(input[name=creating])) "
    assert asked["username_field"] == f"{the_one_form}input[name=acct]"
    assert asked["password_field"] == f"{the_one_form}input[name=pw]"
    assert asked["click"].endswith("[value=login]")
    assert len({asked["username_field"], asked["password_field"], asked["click"]}) == 3
    assert asked["expect_text"] == "logout", (
        "not «login», which the page of whoever is outside shows"
    )
    after = json.loads(
        (ROOT / "docs/examples/read-as-you-news-ycombinator.json").read_text(encoding="utf-8")
    )
    (reading,) = after["steps"]
    assert reading["arguments"]["site"] == PROOF_SITE, "the reading after it is on the same site"
    assert reading["required_capabilities"] == ["browser.read_as_you"]


def test_the_plan_of_the_login_is_one_step_of_login_on_a_declared_site() -> None:
    module = script()
    plan = json.loads(LOGIN_PLAN.read_text(encoding="utf-8"))

    assert module.login_plan_failures(plan, ["example.com"]) == []
    assert module.login_plan_failures(plan, ["www.youtube.com"]), "its site is not declared"
    other = json.loads((ROOT / "docs/examples/act-as-you.json").read_text(encoding="utf-8"))
    assert module.login_plan_failures(other, ["httpbin.org"]), "not a login"
    assert module.login_plan_failures({"steps": []}, ["example.com"])


def test_a_proof_with_a_reopened_measure_has_not_passed_and_says_so() -> None:
    module = script()
    clean, reopened = module.Report(io.StringIO()), module.Report(io.StringIO())
    for report in (clean, reopened):
        report.passed(2, "una cosa")
    reopened.reopens(6, "l'elenco 12.0 s")
    clean.verdict()
    reopened.verdict()

    assert clean.ok and clean.lines[-1] == "La prova è passata."
    assert not reopened.ok
    assert "[6] RIAPRE: l'elenco 12.0 s" in reopened.lines
    assert reopened.lines[-1] == "La prova non è passata: un RIAPRE al passo 6."
    assert "RIAPRE: 1" in reopened.lines[-2]


# ----------------------------------------------------------------------------------------
# The section walked whole, by the script, against a real ELA
# ----------------------------------------------------------------------------------------


class World:
    """The edge of the machine of one walk: what ``base.run`` is asked — the command line of ELA
    answered in process, ``hdiutil`` and its friends by a fake —, and Tommaso's hands."""

    def __init__(self, ela: Any, accounts: FakeAccountBrowser, vault: FakeVault, loop: Any) -> None:
        self.ela, self.accounts, self.vault, self.loop = ela, accounts, vault, loop
        self.ran: list[str] = []
        self.asked: list[str] = []
        self.last_hand = ""

    def run(self, line: str) -> subprocess.CompletedProcess[str]:
        self.ran.append(line)
        prefix = "uv run ela "
        if line.startswith(prefix):
            done = CliRunner().invoke(ela_app, shlex.split(line.removeprefix(prefix)))
            return subprocess.CompletedProcess(line, done.exit_code, plain(done.output), "")
        printed = "/dev/disk9\n" if line.startswith("hdiutil attach") else ""
        if line == "mount":
            printed = MOUNTED
        return subprocess.CompletedProcess(line, 0, printed, "")

    def ask(self, question: str) -> str:
        """Tommaso: a yes to every question, and at «Premi Invio» the thing his hands were asked
        for — said by the ``A TE`` line the script wrote just before."""
        self.asked.append(question)
        if "Premi Invio" in question:
            self.hands()
        return "s"

    def hands(self) -> None:
        said = self.last_hand
        if "password principale" in said:
            opened = asyncio.run_coroutine_threadsafe(
                self.ela.vault.open(Secret(self.vault.key)), self.loop
            )
            assert opened.result(10) is None
        if "chiudi la finestra" in said.lower() and "pulsante rosso" not in said.lower():
            # Cmd-Q: the browser quits. With the red button it does not — the window is gone and
            # the process stays, which is what the step after it is there to show.
            self.accounts.holder = None


def proof_login() -> dict[str, str]:
    """The arguments of the one step of the proof's login plan."""
    (step,) = json.loads(PROOF_LOGIN.read_text(encoding="utf-8"))["steps"]
    return dict(step["arguments"])


THE_PAGE_SAYS = "Le tue iscrizioni: un canale. Esci. ELA prova 9139"
"""The text of the one page of the walk: what a reading as the user brings back. Not the text the
proof's login awaits — «logout» —: before the login nobody is inside."""


def a_page() -> FakePage:
    """A page that has what the proof's login plan names — its selectors, as it writes them."""
    asked = proof_login()
    return FakePage(
        fields={
            asked["username_field"]: Field("text", "username", "post"),
            asked["password_field"]: Field("password", "current-password", "post"),
            asked["click"]: Field("submit", "", "post"),
        },
        texts={None: THE_PAGE_SAYS},
        counts_after_click={asked["password_field"]: 0},
    )


LANDS = "https://news.ycombinator.com/news"
"""Where the page of the proof's login is once the login was sent."""


class OneBrowserOfTheProof(FakeAccountBrowser):
    """The browser of the whole proof, with one page for all its steps: **the page of the login
    lands where a login lands, and the pages of the other steps stay where they were opened** —
    each step has the boundary of its own site, and the fake asks it where the page is, as the
    real one does (M13.4f)."""

    async def open(self, address: str, allowed: Callable[[str], bool], stop: TaskStop) -> Opened:
        self.page.landed = LANDS if address.startswith(LANDS.rsplit("/", 1)[0] + "/") else None
        return await super().open(address, allowed, stop)


@dataclasses.dataclass
class Walked:
    """One walk of the section: what the script wrote in its file, what the world was asked,
    and what the browser and the vault of the walk saw."""

    report: Any
    world: World
    accounts: FakeAccountBrowser
    vault: FakeVault
    events: list[str]

    @property
    def written(self) -> str:
        return "\n".join(self.report.lines)


async def walked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, page: FakePage, before: int = 10
) -> Walked:
    """The steps of the section before ``before``, as written in the guide, run by the script
    itself against a real ELA whose browser shows ``page``.

    **In a folder of the test's, like every test here**: the guide names its plans from the root
    of the repository, so the test's folder is given a ``docs`` that leads there — and a ``.env``
    of the test's own, with nothing in it: the root of whoever uses ELA has one, and since
    decision 145 the line that opens the vault enters the folder of the one ELA read, which is
    what step 3 of the guide looks for."""
    module = script()
    (tmp_path / "docs").symlink_to(ROOT / "docs", target_is_directory=True)
    (tmp_path / ".env").write_text("", encoding="utf-8")
    program = tmp_path / "bw"
    program.write_bytes(b"\xcf\xfa\xed\xfe a native program")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    entry = dataclasses.replace(ENTRY, addresses=(PROOF_ADDRESS,))
    accounts, vault = OneBrowserOfTheProof(page), FakeVault([entry], state="locked")
    turns = Script([call(), gesture("read", site="www.youtube.com", path="/feed/channels"), call()])
    async with guided(
        monkeypatch,
        tmp_path,
        turns,
        accounts=accounts,
        vault=vault,
        ELA_BROWSER_SITES=json.dumps(SITES),
        ELA_VAULT_PROGRAM=str(program),
    ) as g:
        loop = asyncio.get_running_loop()
        transport = LoopTransport(g.app, loop)
        monkeypatch.setattr(
            cli_client,
            "connect",
            lambda: cli_client.open_client(g.ela.settings.api, transport=transport),
        )
        world = World(g.ela, accounts, vault, loop)
        monkeypatch.setattr(module.base, "run", world.run)
        monkeypatch.setattr(
            module, "mounted", lambda: False
        )  # the desk's own /Volumes is not asked
        report = module.Report(io.StringIO())
        say = report.say

        def said(text: str = "") -> None:
            if "A TE:" in text:
                world.last_hand = text
            say(text)

        report.say = said  # type: ignore[method-assign]

        def walk() -> None:
            api = module.base.Api()
            proof = module.Proof(
                api,
                report,
                world.ask,
                module.spending.Ledger.of(api.get("/spend")),
                login=PROOF_LOGIN,
            )
            todo = {number: blocks for number, blocks in marked().items() if number < before}
            try:
                module.base.walk(
                    report, todo, lambda number, its: module.a_step(number, its, proof)
                )
            finally:
                api.close()

        await asyncio.wait_for(asyncio.to_thread(walk), 120)
        events = [event.event_type.value for event in await g.ela.audit.read()]

    return Walked(report, world, accounts, vault, events)


async def test_the_script_walks_the_section_against_a_real_ela_and_the_proof_passes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Steps 2 to 9, as written in the guide, run by the script itself. Every ``atteso`` of the
    section is judged on what ELA's own command line printed."""
    walk = await walked(monkeypatch, tmp_path, a_page())
    report, world, accounts = walk.report, walk.world, walk.accounts
    events = walk.events
    on_the_screen = capsys.readouterr().out

    written = "\n".join(report.lines)
    assert report.ok, written
    assert report.failures == 0 and report.stopped is None and report.lost_at is None
    # Decision 155: what the eye has to look at, the script puts in front of it — the result
    # of the task it names, **on the screen and never in the file** —, for the questions of the
    # steps that used to send the user to another Terminal with an id to copy.
    assert THE_PAGE_SAYS in on_the_screen, "the result is put in front of whoever answers"
    assert THE_PAGE_SAYS not in written and "Le tue iscrizioni" not in written, (
        "and nothing of the text of a page enters the file"
    )
    for step in (5, 6, 8):
        its = written.split(f"—— passo {step} ——", 1)[1].split("—— passo", 1)[0]
        assert "sullo schermo, e non in questo file" in its, f"step {step} says what it showed"
    eyes = [
        block.body
        for blocks in marked().values()
        for block in blocks
        if block.kind in ("occhio", "prosegui")
    ]
    assert not any("task results" in asked_ for asked_ in eyes), (
        "no question of the eye sends the user to launch the results by hand any more"
    )
    # Decision 151: step 6 begins by looking that the user is not inside the site yet — a read
    # as them of the page it will read after the login —, and nothing of that read is written.
    step_6 = written.split("—— passo 6 ——", 1)[1].split("—— passo 7 ——", 1)[0]
    before_the_login = step_6.split("login-news-ycombinator.json", 1)[0]
    assert "read-as-you-news-ycombinator.json" in before_the_login
    assert "[6] PASSATO: nel sito del login non sei ancora dentro" in before_the_login
    asked = proof_login()
    assert accounts.secrets == [
        (asked["username_field"], ENTRY.username),
        (asked["password_field"], WORD),
    ], "the login: what the vault holds for the site of the plan, typed where the plan says"
    step_6 = written.split("—— passo 6 ——", 1)[1].split("—— passo 7 ——", 1)[0]
    assert "read-as-you-news-ycombinator.json" in step_6.split("browser.login", 1)[1], (
        "after the login, the reading that finds the user inside, on the same site"
    )
    assert accounts.windows == ["https://accounts.google.com/", None], "the two windows"
    assert "BROWSER_WINDOW_OPENED" in events and "VAULT_CLOSED" in events
    assert len(accounts.shuts) == 1 and "BROWSER_CLOSE_ASKED" in events, (
        "the window closed with the red button stayed open for ELA, and the command ended it"
    )
    step_7 = written.split("—— passo 7 ——", 1)[1].split("—— passo 8 ——", 1)[0]
    after_the_red_button = step_7.split("pulsante rosso", 1)[1].split("$ uv run ela browser close")[
        0
    ]
    assert ["state", "window"] in [
        line.split()[1:3] for line in after_the_red_button.splitlines()
    ], "with the window closed by the red button the state still says it is open"
    assert WORD not in written and ENTRY.username not in written
    assert ENTRY.name not in written, "nothing of the vault enters the file"
    questions = {
        block.split("| capability: ", 1)[1].split("\n", 1)[0]: block.split("    $ ", 1)[0]
        for block in written.split("    la domanda ")[1:]
    }
    assert set(questions) >= AS_YOU, "each capability with the profile was asked"
    for capability in sorted(AS_YOU):
        shown = questions[capability]
        assert "    | che cosa: " in shown, shown
        assert "signed in" in shown.split("    | che cosa: ", 1)[1].split("\n", 1)[0], (
            f"decision 107: what the user reads of a question of {capability} before the yes "
            "says that ELA acts signed in as them — in a sentence, not only in the capability's "
            f"name:\n{shown}"
        )
    for capability in sorted(AS_YOU - {"browser.guided_as_you"}):
        assert "    | che cosa fa: " in questions[capability], "the tool's own sentence"
        assert "as you" in questions[capability].split("| che cosa fa: ", 1)[1].split("\n")[0]
    disk = [line for line in world.ran if not line.startswith("uv run ela ")]
    assert disk == [
        "hdiutil attach -nomount ram://131072",
        'diskutil erasevolume HFS+ "ELA-prova" /dev/disk9',
        "mount",
        'chmod 700 "/Volumes/ELA-prova"',
        'find "/Volumes/ELA-prova" -mindepth 1 -delete',
        "hdiutil detach /dev/disk9 -force",
        "hdiutil info",
    ], "the machine is asked these lines, in this order, and no other"
    assert any("ignora i proprietari" in line for line in report.lines), (
        "what 0700 is worth on a volume that knows no owners is said"
    )


async def test_a_user_already_inside_the_site_of_the_login_stops_the_proof_before_the_login(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Decision 151 of the review of 2026-10-13. Step 6 is written for a site nobody has entered
    yet: its last question — «is logout at the top?» — would have a yes whatever the login of
    the day did. So before the login the script reads the page as the user and looks that **the
    text the login's plan awaits is not there** — read from the plan, written by hand nowhere.
    If it is, the proof stops — FERMATO, not FALLITO —, says how to leave the site by hand, and
    spends no yes of a login and no password. Nothing of that read is in the file."""
    awaited = proof_login()["expect_text"]
    inside = dataclasses.replace(
        a_page(), texts={None: f"mario | {awaited} — SENTINELLA di chi è già dentro"}
    )

    walk = await walked(monkeypatch, tmp_path, inside, before=8)

    written = walk.written
    assert not walk.report.ok and walk.report.failures == 0, written
    assert walk.report.stopped is not None and walk.report.stopped[0] == 6, written
    why = walk.report.stopped[1]
    assert "uv run ela browser open news.ycombinator.com" in why and "Cmd-Q" in why
    assert "—— passo 7 ——" not in written, "no step after it is walked"
    assert walk.accounts.secrets == [] and walk.accounts.clicks == [], "no login was sent"
    assert not any(call.startswith("take:") for call in walk.vault.calls), "no password was taken"
    assert "login-news-ycombinator.json" not in written.split("—— passo 6 ——", 1)[1], (
        "the login was not even planned"
    )
    assert "SENTINELLA" not in written and "mario |" not in written, (
        "nothing of what the read brought back is in the file"
    )


def test_the_text_the_login_awaits_is_read_from_its_plan_and_looked_for_whole(
    tmp_path: Path,
) -> None:
    """The pure halves of ``assente``: the text is the plan's own ``expect_text`` — of whichever
    plan the proof was given, written by hand nowhere —, and it is «there» when the read printed
    it, as it is written, wherever it is."""
    module = script()
    another = json.loads(PROOF_LOGIN.read_text(encoding="utf-8"))
    another["steps"][0]["arguments"].update(expect_text="Esci", site="posta.example")
    plan = tmp_path / "another-login.json"
    plan.write_text(json.dumps(another), encoding="utf-8")

    assert module.awaited_by(PROOF_LOGIN) == proof_login()["expect_text"] == "logout"
    assert module.awaited_by(plan) == "Esci" and module.site_of(plan) == "posta.example"
    assert module.site_of(PROOF_LOGIN) == PROOF_SITE
    assert "uv run ela browser open posta.example" in module.inside_already("posta.example", "Esci")
    assert module.already_there("logout", "mario | logout\nla prima pagina")
    assert module.already_there("logout", "x logout")
    assert not module.already_there("logout", "login | la prima pagina")
    assert not module.already_there("logout", "")


def test_what_is_shown_on_the_screen_is_not_written_in_the_file(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Decision 155, on the function alone: the commands of a ``schermo`` are run by the script,
    what they print goes to the screen, and the file gets one line that says a result was shown
    — with the command, and nothing of what it printed."""
    module = script()
    ran: list[str] = []

    def run(line: str) -> subprocess.CompletedProcess[str]:
        ran.append(line)
        return subprocess.CompletedProcess(line, 0, "il testo di una pagina tua\n", "")

    monkeypatch.setattr(module.base, "run", run)
    report = module.Report(io.StringIO())
    proof = module.Proof(None, report, lambda question: "s", None, login=PROOF_LOGIN)
    turn = module.guided.Turn()
    turn.task_id = "the-task"
    block = module.base.Block(5, "schermo", "uv run ela task results <id>")

    module.a_block(5, block, turn, proof)

    assert ran == ["uv run ela task results the-task"]
    assert "il testo di una pagina tua" in capsys.readouterr().out
    assert not any("il testo di una pagina tua" in line for line in report.lines)
    assert any(
        "uv run ela task results the-task" in line and "sullo schermo, e non in questo file" in line
        for line in report.lines
    )


async def test_a_line_of_the_guide_the_command_line_does_not_print_is_a_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The negative case of the walk: one ``atteso`` changed, and the same script on the same ELA
    reports it — FALLITO, with what was printed."""
    module = script()
    async with guided(
        monkeypatch, tmp_path, Script([]), accounts=FakeAccountBrowser(), vault=None
    ) as g:
        loop = asyncio.get_running_loop()
        transport = LoopTransport(g.app, loop)
        monkeypatch.setattr(
            cli_client,
            "connect",
            lambda: cli_client.open_client(g.ela.settings.api, transport=transport),
        )
        world = World(g.ela, FakeAccountBrowser(), FakeVault(), loop)
        monkeypatch.setattr(module.base, "run", world.run)
        report = module.Report(io.StringIO())

        def walk() -> None:
            api = module.base.Api()
            proof = module.Proof(
                api, report, world.ask, module.spending.Ledger.of(api.get("/spend"))
            )
            todo = {
                7: [
                    block(7, "comando", "uv run ela browser status"),
                    block(7, "atteso", "state window"),
                ]
            }
            try:
                module.base.walk(
                    report, todo, lambda number, its: module.a_step(number, its, proof)
                )
            finally:
                api.close()

        await asyncio.wait_for(asyncio.to_thread(walk), 60)

    assert report.failures == 1 and not report.ok
    assert any("FALLITO: mancano ['state window']" in line for line in report.lines)


# ----------------------------------------------------------------------------------------
# The kinds whose machine is injected
# ----------------------------------------------------------------------------------------


class Answers:
    """An API that answers what the test wrote, by path: each answer once and the last for ever."""

    def __init__(self, answers: dict[str, list[Any]]) -> None:
        self.answers = {path: list(found) for path, found in answers.items()}

    def get(self, path: str) -> Any:
        found = self.answers[path]
        return found.pop(0) if len(found) > 1 else found[0]

    def close(self) -> None:
        return None


class Running:
    """The run of a step in the background: over, or not."""

    def __init__(self, code: int | None) -> None:
        self.code = code

    def poll(self) -> int | None:
        return self.code

    def terminate(self) -> None:
        self.code = -15


def a_proof(answers: dict[str, list[Any]], said: list[str] | None = None) -> Any:
    module = script()
    answered = list(said or [])
    return module.Proof(
        api=Answers(answers),
        report=module.Report(io.StringIO()),
        ask=lambda question: answered.pop(0) if answered else "s",
        start=module.spending.Ledger.of({"cap": "30", "spent": "0", "reserved": "0", "open": 0}),
    )


def stopping(monkeypatch: pytest.MonkeyPatch, *, lock: str | None, dies: bool) -> list[Any]:
    """ELA as a process the test owns: pid 777, alive until it is signalled — or for ever."""
    module = script()
    signalled: list[Any] = []
    monkeypatch.setattr(module, "ela_pid", lambda: 777)
    monkeypatch.setattr(module, "alive", lambda pid: pid != 777 or not (signalled and dies))
    monkeypatch.setattr(module, "profile_lock", lambda: lock)
    monkeypatch.setattr(module, "EXIT_SECONDS", 0.2)
    monkeypatch.setattr(module.base, "started", lambda line: Running(None))
    monkeypatch.setattr(module.os, "kill", lambda pid, number: signalled.append((pid, number)))
    return signalled


def test_ela_is_stopped_once_a_step_holds_the_profile_and_nothing_is_left(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = script()
    signalled = stopping(monkeypatch, lock=None, dies=True)
    proof = a_proof({"/browser": [{"state": "free"}, {"state": "free"}, {"state": "step"}]})
    turn = module.guided.Turn(task_id="t-1")

    module.a_step(10, [block(10, "chiude", "SIGINT")], proof, turn)

    assert signalled == [(777, module.signal.SIGINT)], "one signal, once the profile was held"
    assert proof.report.ok, proof.report.lines
    assert any("PASSATO: ELA è uscita" in line for line in proof.report.lines)


@pytest.mark.parametrize(
    ("lock", "dies", "says"),
    [
        (None, False, "ELA non è uscita"),
        ("mac-888", True, "ancora tenuta dal processo 888"),
    ],
)
def test_an_ela_that_stays_or_a_folder_still_held_is_a_failure(
    monkeypatch: pytest.MonkeyPatch, lock: str | None, dies: bool, says: str
) -> None:
    module = script()
    stopping(monkeypatch, lock=lock, dies=dies)
    proof = a_proof({"/browser": [{"state": "step"}]})

    module.a_step(10, [block(10, "chiude", "SIGINT")], proof, module.guided.Turn(task_id="t-1"))

    assert proof.report.failures == 1
    assert any(says in line for line in proof.report.lines)


def test_without_an_ela_that_listens_step_10_fails_and_signals_nobody(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = script()
    signalled = stopping(monkeypatch, lock=None, dies=True)
    monkeypatch.setattr(module, "ela_pid", lambda: None)
    proof = a_proof({"/browser": [{"state": "step"}]})

    module.a_step(10, [block(10, "chiude", "SIGINT")], proof, module.guided.Turn(task_id="t-1"))

    assert signalled == [] and proof.report.failures == 1
    assert any("ela serve" in line for line in proof.report.lines)


@pytest.mark.parametrize("held_by", ["window", "process"])
def test_a_profile_held_by_anything_but_a_step_is_not_the_moment_to_stop_ela(
    monkeypatch: pytest.MonkeyPatch, held_by: str
) -> None:
    """The step never holds the profile — a window does —, and the wait for it has an end: ELA
    is not signalled, the run in the background is ended, and the step fails saying so."""
    module = script()
    signalled = stopping(monkeypatch, lock=None, dies=True)
    monkeypatch.setattr(module, "HOLD_SECONDS", 0.2)
    running = Running(None)
    monkeypatch.setattr(module.base, "started", lambda line: running)
    proof = a_proof({"/browser": [{"state": held_by}]})

    module.a_step(10, [block(10, "chiude", "SIGINT")], proof, module.guided.Turn(task_id="t-1"))

    assert signalled == [] and proof.report.failures == 1
    assert running.code == -15, "the run in the background is not left waiting"
    assert any("non ha tenuto il profilo" in line for line in proof.report.lines)


def test_a_step_that_ended_before_it_held_the_profile_is_skipped_and_ela_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = script()
    signalled = stopping(monkeypatch, lock=None, dies=True)
    monkeypatch.setattr(module.base, "started", lambda line: Running(0))
    proof = a_proof({"/browser": [{"state": "free"}]})

    module.a_step(10, [block(10, "chiude", "SIGINT")], proof, module.guided.Turn(task_id="t-1"))

    assert signalled == [] and proof.report.skipped_steps == [10]


def test_a_signal_the_section_does_not_know_and_a_kind_it_does_not_have_are_the_guides_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = script()
    stopping(monkeypatch, lock=None, dies=True)
    proof = a_proof({"/browser": [{"state": "step"}]})

    with pytest.raises(ValueError, match="vocabulary of chiude"):
        module.a_step(10, [block(10, "chiude", "SIGKILL")], proof, module.guided.Turn())
    with pytest.raises(ValueError, match="not a kind of the section"):
        module.a_step(2, [block(2, "fascia", "<id>")], proof)


def test_a_no_to_what_the_world_gave_stops_the_proof_and_is_not_a_failure() -> None:
    """Decision 50: FERMATO, before the session and its spending."""
    module = script()
    proof = a_proof({}, said=["n"])

    module.base.walk(
        proof.report,
        {5: [block(5, "prosegui", "Il testo porta i tuoi canali?")], 8: [block(8, "mano", "x")]},
        lambda number, its: module.a_step(number, its, proof),
    )

    assert proof.report.stopped == (5, module.SAID_NO)
    assert proof.report.failures == 0 and not proof.report.ok
    assert not any("passo 8" in line for line in proof.report.lines), "nothing after it was done"


def measured(monkeypatch: pytest.MonkeyPatch, seconds: list[float], printed: str) -> Any:
    module = script()
    clock = iter(seconds)
    monkeypatch.setattr(module.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(
        module.base, "run", lambda line: subprocess.CompletedProcess(line, 0, printed, "")
    )
    proof = a_proof({})
    module.base.walk(
        proof.report,
        {6: [block(6, "misura", "10")]},
        lambda number, its: module.a_step(number, its, proof, module.guided.Turn(task_id="t-1")),
    )
    return proof.report


def test_the_measure_writes_three_numbers_and_passes_under_the_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = measured(monkeypatch, [0.0, 2.5, 10.0, 16.0], "outcome  waiting_approval")

    assert report.ok, report.lines
    assert any(
        "status 2.5 s, fino alla domanda 6.0 s, l'elenco per differenza 3.5 s" in line
        for line in report.lines
    )


def test_a_listing_above_the_threshold_reopens_and_the_proof_has_not_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = measured(monkeypatch, [0.0, 2.0, 10.0, 23.0], "outcome  waiting_approval")

    assert report.reopened == [6] and not report.ok and report.failures == 0


def test_a_login_that_did_not_reach_its_question_has_nothing_to_measure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = measured(monkeypatch, [0.0, 2.0, 10.0, 12.0], "outcome  failed")

    assert report.failures == 1 and report.stopped is not None and report.reopened == []


def test_a_ram_disk_that_is_not_born_or_is_still_there_is_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = script()
    body = "64\nEsporta e importa."

    def with_run(run: Any) -> Any:
        monkeypatch.setattr(module.base, "run", run)
        proof = a_proof({})
        module.base.walk(
            proof.report,
            {2: [block(2, "disco", body)]},
            lambda number, its: module.a_step(number, its, proof),
        )
        return proof.report

    def answer(line: str, printed: str = "", code: int = 0) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(line, code, printed, "")

    ran: list[str] = []

    def a_machine(**changed: Any) -> Any:
        """The machine of a disk that is born and goes away — or that, at one word, changed."""

        def run(line: str) -> subprocess.CompletedProcess[str]:
            ran.append(line)
            word = line.split()[0]
            if word in changed:
                return changed[word](line)  # type: ignore[no-any-return]
            if line.startswith("hdiutil attach"):
                return answer(line, "/dev/disk9\n")
            return answer(line, MOUNTED if line == "mount" else "")

        return run

    def still(line: str) -> subprocess.CompletedProcess[str]:
        return answer(line, "/dev/disk9\n" if not line.startswith("hdiutil detach") else "")

    monkeypatch.setattr(module, "mounted", lambda: False)
    unborn = with_run(lambda line: answer(line, "hdiutil: attach failed", 1))
    born = with_run(a_machine())
    left = with_run(a_machine(hdiutil=still))
    another = with_run(
        a_machine(mount=lambda line: answer(line, MOUNTED.replace("disk9", "disk4")))
    )
    unformatted = with_run(a_machine(diskutil=lambda line: answer(line, "", 1)))
    wide = with_run(a_machine(chmod=lambda line: answer(line, "", 1)))
    full = with_run(a_machine(find=lambda line: answer(line, "", 1)))

    assert unborn.failures == 1 and unborn.stopped is not None
    assert born.failures == 0 and born.stopped is None, born.lines
    assert left.failures == 1, "hdiutil info still names the device"
    assert any("il dispositivo /dev/disk9 c'è ancora" in line for line in left.lines)
    for refused in (another, unformatted, wide):
        assert refused.failures == 1 and refused.stopped is not None, refused.lines
    assert any("non è il disco appena fatto" in line for line in another.lines)
    assert full.failures == 1 and any("non è stato svuotato" in line for line in full.lines)
    assert ran.count("hdiutil detach /dev/disk9 -force") == 6, (
        "a disk that was born is detached whatever came after, with the force a busy one needs"
    )


def test_a_volume_of_the_proof_s_name_that_is_already_there_is_not_touched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What a run that was killed left, or the user's own: the new disk would be mounted beside
    it under another name, and everything after would be done to the other one — narrowed,
    filled with the exports, emptied. Nothing is made, and nothing is run."""
    module = script()
    ran: list[str] = []
    monkeypatch.setattr(module, "mounted", lambda: True)
    monkeypatch.setattr(module.base, "run", lambda line: ran.append(line))
    proof = a_proof({})

    module.base.walk(
        proof.report,
        {2: [block(2, "disco", "64\nEsporta e importa.")]},
        lambda number, its: module.a_step(number, its, proof),
    )

    assert ran == [] and proof.report.failures == 1 and proof.report.stopped is not None
    assert "già montato" in "\n".join(proof.report.lines)


def test_the_volume_is_looked_for_where_macos_mounts_it() -> None:
    module = script()

    assert str(module.MOUNT) == "/Volumes/ELA-prova"
    assert module.mounted() is module.MOUNT.exists()


# ----------------------------------------------------------------------------------------
# Step 1, and the whole
# ----------------------------------------------------------------------------------------


def test_the_margin_and_the_plan_of_the_login_say_what_is_missing(tmp_path: Path) -> None:
    module = script()
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")

    assert module.margin_short("5.00", module.Decimal("0.60")) is None
    assert "ne chiede 0.60" in str(module.margin_short("0.10", module.Decimal("0.60")))
    assert module.margin_short(None, module.Decimal("0.60")) is not None
    assert "--login" in str(module.login_plan_ready(None))
    assert "non si legge" in str(module.login_plan_ready(broken))


def step_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **changed: Any
) -> tuple[Any, list[str]]:
    """Step 1 on a world of the test's: the routes answer what a ready ELA answers — or that
    changed —, ``codesign`` and ``tmutil`` are the fake's, and the folder of the profile is a
    real folder of the test."""
    module = script()
    profile = tmp_path / "profile"
    profile.mkdir()
    profile.chmod(changed.pop("mode", 0o700))  # set, and not left to the umask of the suite
    declared = "" if changed.pop("undeclared", False) else str(profile)
    program = tmp_path / "bw"
    program.write_bytes(b"a native program")
    signed, excluded = changed.pop("signed", True), changed.pop("excluded", True)
    answers = {
        "/health": [{"status": "ok"}],
        "/openapi.json": [{"paths": {"/browser": {}, "/vault": {}}}],
        "/spend": [{"cap": "30", "left": "30", "spent": "0", "reserved": "0", "open": 0}],
        "/browser": [{"state": "free", "message": ""}],
        "/vault": [{"state": "locked", "program": str(program), "message": "the vault is locked"}],
        **{path: [answer] for path, answer in changed.items()},
    }
    ran: list[str] = []

    def run(line: str) -> subprocess.CompletedProcess[str]:
        ran.append(line)
        if line.startswith("codesign"):
            return subprocess.CompletedProcess(line, 0 if signed else 1, "", "")
        printed = "[Excluded]" if excluded and "isexcluded" in line else "[Included]"
        return subprocess.CompletedProcess(line, 0, printed, "")

    monkeypatch.setattr(module.base, "Api", lambda: Answers(answers))
    monkeypatch.setattr(module.base, "run", run)
    monkeypatch.setattr(module.planning, "on_origin", lambda: None)
    monkeypatch.setattr(module.guided, "route_model", lambda: module.MODEL)
    monkeypatch.setattr(module.spending, "keyed", lambda: True)
    monkeypatch.setenv("ELA_BROWSER_SITES", json.dumps(SITES))
    monkeypatch.setenv("ELA_BROWSER_PROFILE_DIR", declared)
    report = module.Report(io.StringIO())
    module.preconditions(report, LOGIN_PLAN)
    return report, ran


def test_step_1_passes_on_a_ready_world_and_writes_the_digest_of_the_vaults_program(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = script()

    report, ran = step_1(monkeypatch, tmp_path)

    assert report.stopped is None, report.lines
    assert report.passes == {1: 12}
    digest = module.hashlib.sha256(b"a native program").hexdigest()
    assert f"    lo sha256 del programma del vault: {digest}" in report.lines
    assert any(line.startswith("tmutil addexclusion") for line in ran), (
        "the script asks, then looks"
    )
    assert any(f"-R='{module.BITWARDEN}'" in line for line in ran), "the maker's team, by codesign"
    assert 'certificate leaf[subject.OU] = "LTZ2PFU5D6"' in module.BITWARDEN, (
        "Bitwarden's team, written here too: measured by scripts/misura_m13_9.py"
    )


def test_a_vault_nobody_signed_in_to_yet_is_a_closed_vault_for_step_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The first ``bw login`` of the proof is in step 2: on a data folder that is new the vault
    is ``unauthenticated`` at step 1, and that is not what stops the proof."""
    answer = {"state": "unauthenticated", "program": str(tmp_path / "bw"), "message": "sign in"}

    report, _ = step_1(monkeypatch, tmp_path, **{"/vault": answer})

    assert report.stopped is None, report.lines


def test_the_paths_step_1_hands_to_a_shell_are_quoted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The folder and the program are the user's, and are written into lines a shell reads: a
    space, a quote or a dollar in either is a part of a name, and not of the line."""
    odd = tmp_path / "a folder's $HOME `id`"
    odd.mkdir()

    report, ran = step_1(monkeypatch, odd)

    assert report.stopped is None, report.lines
    profile, program = odd / "profile", odd / "bw"
    assert f"tmutil addexclusion {shlex.quote(str(profile))}" in ran
    assert f"tmutil isexcluded {shlex.quote(str(profile))}" in ran
    assert any(line.endswith(f" {shlex.quote(str(program))}") for line in ran)


NOT_READY = [
    pytest.param(
        {"/vault": {"state": "unlocked", "program": "/x", "message": ""}},
        "il vault è chiuso",
        id="a-vault-already-open",
    ),
    pytest.param({"signed": False}, "firmato da Bitwarden", id="a-program-nobody-signed"),
    pytest.param(
        {"/browser": {"state": "window", "message": "its window is open"}},
        "nessuno lo tiene",
        id="a-profile-held",
    ),
    pytest.param({"mode": 0o755}, "la cartella del profilo è 0700", id="a-folder-open-to-others"),
    pytest.param({"undeclared": True}, "la cartella del profilo è 0700", id="no-folder-declared"),
    pytest.param({"excluded": False}, "Time Machine la esclude", id="a-folder-time-machine-copies"),
    pytest.param(
        {"/openapi.json": {"paths": {"/vault": {}}}},
        "il Core gira dal codice del branch",
        id="an-older-core",
    ),
    pytest.param(
        {"/spend": {"cap": "30", "left": "0.10", "spent": "0", "reserved": "0", "open": 0}},
        "restano almeno",
        id="a-month-with-no-room",
    ),
]


@pytest.mark.parametrize(("changed", "what"), NOT_READY)
def test_step_1_stops_at_the_first_thing_the_world_lacks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, changed: dict[str, Any], what: str
) -> None:
    """Each negative starts from the ready world and changes one thing: FERMATO, with what."""
    report, _ = step_1(monkeypatch, tmp_path, **changed)

    assert report.stopped is not None and report.stopped[0] == 1
    assert what in report.stopped[1], report.stopped
    assert not any("sha256" in line for line in report.lines), "nothing is vouched for after a stop"


def test_main_stops_at_step_1_and_the_file_says_what_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = script()

    def fallen(report: Any, login: Path | None) -> bool:
        report.stop(1, "la prova richiede «ELA risponde», e non è così")
        return False

    monkeypatch.setattr(module, "preconditions", fallen)
    out = tmp_path / "prova.txt"

    code = module.main(["--out", str(out), "--login", str(LOGIN_PLAN)])

    written = out.read_text(encoding="utf-8")
    assert code == 1
    assert written.startswith("La prova a mano di M13.9, ")
    assert "[1] FERMATO: la prova richiede «ELA risponde»" in written
    assert "La prova non è passata" in written


def test_main_walks_every_step_of_the_section_when_step_1_holds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = script()
    walked: list[list[int]] = []
    monkeypatch.setattr(module, "preconditions", lambda report, login: True)
    monkeypatch.setattr(
        module.base,
        "Api",
        lambda: Answers({"/spend": [{"cap": "30", "spent": "0", "reserved": "0", "open": 0}]}),
    )
    monkeypatch.setattr(module.base, "walk", lambda report, todo, one: walked.append(sorted(todo)))

    code = module.main(["--out", str(tmp_path / "prova.txt"), "--login", str(LOGIN_PLAN)])

    assert code == 0 and walked == [list(range(2, 11))]
