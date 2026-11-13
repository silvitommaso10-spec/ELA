"""``scripts/prova_m13_14.py`` against section 32 of the guide (M13.14; decision 15 of its prompt,
and answers 30 and 34 of the review of its SPEC). The guide is the source of truth and the script
reads it; this file keeps the two aligned, in the form of ``test_prova_m13_13.py`` for section 30.

**The section and the script are one vocabulary**: every marker is a kind the script knows, every
kind it knows is used, every placeholder is one it fills, every plan it sends exists and writes
only inside the folder of the proof.

**Every judgement of its own has its negative case**: the policy and its uses, the line «why I
ask», the live policy that stops the proof, the folder it prepares, the home kept out of the file,
the policies a proof stopped midway leaves alive.

**Steps 2 to 10 are walked by the script against a real ELA** — its routes, its command line, its
Guardian, its executor and its tools, its database — with the two browsers of ``ela.testing``, on
a real disk under a declared root: what the guide says a command prints is what the command
printed here. No model is called: the plans are the section's own.
"""

from __future__ import annotations

import asyncio
import dataclasses
import importlib.util
import io
import json
import re
import shlex
import subprocess
import sys
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from functools import cache
from pathlib import Path
from typing import Any, Final

import pytest
from typer.testing import CliRunner

from ela.api import create_app
from ela.cli import client as cli_client
from ela.cli.app import app as ela_app
from ela.composition import Settings, build
from ela.permissions import no_policy_for, production_catalogue
from ela.permissions.capabilities import terminal_run
from ela.testing.fakes import FakeAccountBrowser, FakeBrowser, FakePower
from tests.cli.support import LoopTransport, plain
from tests.composition.support import (  # noqa: F401 — re-exported as a fixture
    _only_the_declared_environment,
    create_schema,
    declare,
)

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prova_m13_14.py"
SIBLINGS = (
    "prova_m6_3c",
    "prova_m13_9",
    "prova_m13_10",
    "prova_m13_13",
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
    spec = importlib.util.spec_from_file_location("prova_m13_14", SCRIPT)
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


def sent_plans() -> list[str]:
    return [
        line.split("--file", 1)[1].split()[0] for _, line in lines_of("comando") if "--file" in line
    ]


def step_of(plan: str) -> dict[str, Any]:
    (step,) = json.loads((ROOT / plan).read_text(encoding="utf-8"))["steps"]
    return dict(step)


# ----------------------------------------------------------------------------------------
# The section and the script are one vocabulary
# ----------------------------------------------------------------------------------------


def test_every_marker_is_a_kind_the_script_knows_and_belongs_to_a_step_of_the_section() -> None:
    module = script()
    headings = {int(number) for number in re.findall(r"^### (\d+)\. ", section(), re.MULTILINE)}

    assert headings == set(range(1, 11))
    assert set(marked()) == set(range(2, 11)), "step 1 is the script's own"
    for blocks in marked().values():
        for one in blocks:
            assert one.kind in module.KINDS, one


def test_every_kind_of_the_script_is_used_by_the_section() -> None:
    used = {one.kind for blocks in marked().values() for one in blocks}

    assert used == set(script().KINDS)
    assert set(script().READERS) == set(script().KINDS)


def test_it_comes_after_section_31_and_before_where_to_look() -> None:
    text = guide()

    assert text.index("## 31. ") < text.index("## 32. ") < text.index("## Dove guardare dopo")


def test_every_placeholder_is_one_the_script_fills_and_a_policy_is_named_after_its_birth() -> None:
    """``<id della policy N>`` is the policy the ``crea`` of step N created: used in step N after
    the ``crea``, or in a step after it — never before it was born."""
    module = script()
    born = {number for number, _ in lines_of("crea")}
    for number, blocks in marked().items():
        seen_creation = False
        for one in blocks:
            seen_creation = seen_creation or one.kind == "crea"
            for found in PLACEHOLDER.findall(one.body):
                policy = module.POLICY.fullmatch(found)
                if policy is None:
                    assert found in module.PLACEHOLDERS, found
                    continue
                step = int(policy.group(1))
                assert step in born, found
                assert step < number or (step == number and seen_creation), (number, found)


def test_every_line_is_in_the_vocabulary_of_its_kind() -> None:
    assert script().outside_vocabulary(marked()) == []


@pytest.mark.parametrize(
    ("kind", "line"),
    [
        ("comando", "ela task list"),
        ("schermo", "rm -rf ELA"),
        ("crea", "uv run ela policy create fs.write --scope ELA --days 1 --confirm"),
        ("crea", "uv run ela policy list"),
        ("no", "uv run ela task approve <id> --approval <approval-id>"),
        ("policy", "<id della policy 2> LIVE usi 2 azioni 2"),
        ("policy", "<id della policy 2> ALIVE usi 2 senza limite azioni 2"),
        ("nessuna", "nessuna policy"),
        ("console", "/console"),
        ("file", "ELA/prova-m13.14/uno/prova.md 30 644"),
        ("tetto", "1"),
    ],
    ids=[
        "comando-not-ela",
        "schermo-not-ela",
        "crea-with-confirm",
        "crea-not-a-creation",
        "no-that-says-yes",
        "policy-without-the-cap",
        "policy-unknown-state",
        "nessuna-other-words",
        "console-another-page",
        "file-another-mode",
        "a-kind-the-section-has-not",
    ],
)
def test_a_line_outside_the_vocabulary_of_its_kind_is_the_guides_error(
    kind: str, line: str
) -> None:
    module = script()

    (wrong,) = module.outside_vocabulary({9: [module.base.Block(9, kind, f"{line}\n")]})
    assert wrong.startswith(f"passo 9, {kind}: ")


def test_every_plan_the_section_sends_is_an_example_that_writes_only_in_the_folder() -> None:
    """The fs.write plans write inside the folder of the proof, one file each, never twice the
    same — the gestures go to the two sites of the proof."""
    module = script()
    paths: list[str] = []
    for plan in sent_plans():
        assert (ROOT / plan).is_file(), plan
        step = step_of(plan)
        (capability,) = step["required_capabilities"]
        assert capability in module.CAPABILITIES, plan
        if capability == "fs.write":
            path = step["arguments"]["path"]
            assert path.startswith(f"{module.FOLDER}/"), plan
            assert step["arguments"]["overwrite"] is False, plan
            paths.append(path)
        else:
            assert step["arguments"]["site"] in module.SITES, plan
    assert len(paths) == len(set(paths))


def test_the_three_capabilities_are_the_high_ones_that_declare_terms() -> None:
    """From the catalogue, not from a list of this test: the ``HIGH`` M13.14 opens to policies."""
    opened = {
        spec.id
        for spec in production_catalogue().specs()
        if spec.risk.value == "HIGH" and spec.policy_terms is not None
    }

    assert set(script().CAPABILITIES) == opened


def test_the_refusal_step_6_expects_is_the_one_no_policy_for_gives() -> None:
    (expected, _) = [line for number, line in lines_of("atteso") if number == 6]
    reason = no_policy_for(terminal_run())

    assert reason is not None and expected == f"policy.refused: ADMITS: {reason}"
    assert "only you create one" in expected


def test_step_5_ends_exhausted_and_is_not_revoked() -> None:
    """Answer 30 of the review: the policy whose use is spent is ``EXHAUSTED``, among the ended
    ones, and the proof does not revoke it — there is nothing to take away."""
    step = [one for one in marked()[5]]

    assert not any("policy revoke" in line for one in step for line in one.lines)
    assert step[-1].kind == "policy" and " EXHAUSTED " in step[-1].lines[0]


def test_the_eye_of_step_2_sees_the_whole_folder_before_the_yes() -> None:
    """Answer 34: the eye of step 2 looks at the preview — the folder as the disk names it beside
    each entry — on the screen, before the creation asks its yes."""
    kinds = [one.kind for one in marked()[2]]
    eye = next(one for one in marked()[2] if one.kind == "occhio").body

    assert kinds.index("schermo") < kinds.index("occhio") < kinds.index("crea")
    assert "cartella intera" in eye and "HIGH" in eye


def test_the_script_touches_neither_the_env_nor_the_database_nor_ela_serve() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    run = [line for _, line in lines_of("comando") + lines_of("schermo") + lines_of("crea")]

    assert "persistence" not in source and "sqlite" not in source
    assert all("serve" not in line.split() for line in run)
    assert all(line.startswith("uv run ela ") for line in run)


def test_the_file_is_in_downloads_with_the_name_of_the_milestone() -> None:
    out = script().default_out()

    assert out.parent == Path.home() / "Downloads"
    assert out.name.startswith("prova-m13.14-") and out.suffix == ".txt"


# ----------------------------------------------------------------------------------------
# The judgements of the script, and their negative cases
# ----------------------------------------------------------------------------------------


def a_policy(**changed: Any) -> dict[str, Any]:
    return {
        "id": "p-1",
        "short": "3f2a1b2c",
        "capability": "fs.write",
        "state": "LIVE",
        "uses": 2,
        "max_uses": None,
        "recent": [{}, {}],
        **changed,
    }


def test_a_policy_line_is_read_whole() -> None:
    module = script()

    wanted = module.a_policy_line("<id della policy 5> EXHAUSTED usi 1 di 1 azioni 1")
    free = module.a_policy_line("<id della policy 2> LIVE usi 2 senza limite azioni 2")

    assert (wanted.step, wanted.state, wanted.uses, wanted.most, wanted.actions) == (
        5,
        "EXHAUSTED",
        1,
        1,
        1,
    )
    assert free.most is None


def test_a_policy_as_the_line_wants_it_passes() -> None:
    module = script()
    wanted = module.a_policy_line("<id della policy 2> LIVE usi 2 senza limite azioni 2")

    assert module.policy_failures(wanted, a_policy()) == []


@pytest.mark.parametrize(
    ("found", "said"),
    [
        (None, "non è fra quelle"),
        (a_policy(state="REVOKED"), "è REVOKED, non LIVE"),
        (a_policy(uses=3), "ha 3 usi, non 2"),
        (a_policy(max_uses=2), "il tetto agli usi è 2, non nessuno"),
        (a_policy(recent=[{}]), "dice 1 azioni, non 2"),
    ],
    ids=["absent", "state", "uses", "cap", "actions"],
)
def test_a_policy_that_is_not_as_the_line_wants_it_is_found(
    found: dict[str, Any] | None, said: str
) -> None:
    module = script()
    wanted = module.a_policy_line("<id della policy 2> LIVE usi 2 senza limite azioni 2")

    failures = module.policy_failures(wanted, found)
    assert failures and said in "; ".join(failures)


def test_the_why_that_says_the_block_passes_and_another_fails() -> None:
    module = script()
    why = ["policy 3f2a1b2c was used 1 of its 1 times", "policy 9e8d7c6b was revoked on 2026-11-12"]

    assert module.why_failures("policy 9e8d7c6b was revoked on", why) == []
    assert module.why_failures("policy 3f2a1b2c was revoked on", why)
    assert module.why_failures("was used 1 of its 1", ["policy a was used 1 of its 10 times"])
    assert module.why_failures("anything", []) == ["la domanda non ha la riga why I ask"]


def test_a_live_policy_of_the_three_stops_the_proof_and_is_named() -> None:
    module = script()
    others = [
        a_policy(capability="browser.guided"),
        a_policy(state="REVOKED"),
        a_policy(state="EXHAUSTED"),
    ]

    assert module.live_of_the_three(others) is None
    why = module.live_of_the_three([*others, a_policy(capability="browser.act_as_you")])
    assert why is not None and "3f2a1b2c di browser.act_as_you" in why


def test_the_home_never_enters_what_the_script_writes(tmp_path: Path) -> None:
    module = script()
    home = tmp_path / "casa"
    home.mkdir()

    said = module.private(f"ELA/prova-m13.14/uno = {home}/ELA/prova-m13.14/uno", home)

    assert said == "ELA/prova-m13.14/uno = ~/ELA/prova-m13.14/uno"
    assert str(home) not in module.private(f"{home.resolve()}/x", home)


@pytest.mark.parametrize("scope", ["ELA", "ELA/prova-m13.14"])
def test_a_scope_that_admits_the_folder_of_the_proof_passes(scope: str) -> None:
    assert script().scope_admits(scope) is None


@pytest.mark.parametrize("scope", ["ELA/altro", "altrove"])
def test_a_scope_that_does_not_admit_the_folder_stops_the_proof(scope: str) -> None:
    why = script().scope_admits(scope)

    assert why is not None and scope in why


def planned() -> Mapping[str, frozenset[str]]:
    module = script()
    found: Mapping[str, frozenset[str]] = module.planned_files(marked())
    return found


def test_the_folder_is_prepared_with_its_three_folders_and_two_links(tmp_path: Path) -> None:
    module = script()
    report = module.Report(io.StringIO())

    assert module.prepared(tmp_path, report, planned()) is None

    folder = tmp_path / module.FOLDER
    assert sorted(one.name for one in folder.iterdir()) == ["due", "sorgente", "tre", "uno"]
    assert (folder / "uno" / "fuori").resolve() == (folder / "tre").resolve()
    assert (folder / "sorgente").resolve() == ROOT.resolve()
    assert (folder / "uno").stat().st_mode & 0o777 == 0o700


def test_what_a_proof_before_left_is_removed_one_by_one(tmp_path: Path) -> None:
    module = script()
    module.prepared(tmp_path, module.Report(io.StringIO()), planned())
    folder = tmp_path / module.FOLDER
    (folder / "uno" / "prova.md").write_text("di prima", encoding="utf-8")
    (folder / "due" / "prova.md").write_text("di prima", encoding="utf-8")
    report = module.Report(io.StringIO())

    assert module.prepared(tmp_path, report, planned()) is None

    assert not (folder / "uno" / "prova.md").exists()
    assert not (folder / "due" / "prova.md").exists()
    assert any("tolto ELA/prova-m13.14/uno/prova.md" in line for line in report.lines)
    assert (folder / "uno" / "fuori").is_symlink() and (folder / "sorgente").is_symlink()


@pytest.mark.parametrize(
    "other", ["a name no plan has", "a plan's file in another folder", "a link for a folder"]
)
def test_anything_else_in_the_folder_stops_the_proof_and_touches_nothing(
    tmp_path: Path, other: str
) -> None:
    module = script()
    module.prepared(tmp_path, module.Report(io.StringIO()), planned())
    folder = tmp_path / module.FOLDER
    (folder / "uno" / "prova.md").write_text("di prima", encoding="utf-8")
    if other == "a name no plan has":
        (folder / "uno" / "mio.txt").write_text("tuo", encoding="utf-8")
    elif other == "a plan's file in another folder":
        (folder / "tre" / "con-un-uso.md").write_text("tuo", encoding="utf-8")
    else:
        (tmp_path / "altrove").mkdir()
        (folder / "due").rename(tmp_path / "altrove" / "due")
        (folder / "due").symlink_to(tmp_path / "altrove" / "due")
    report = module.Report(io.StringIO())

    why = module.prepared(tmp_path, report, planned())

    assert why is not None and "non tocca niente" in why
    assert (folder / "uno" / "prova.md").exists(), "nothing was removed"
    assert report.lines == []


def test_a_folder_of_the_proof_that_is_a_link_stops_it(tmp_path: Path) -> None:
    module = script()
    (tmp_path / "ELA").mkdir()
    (tmp_path / "altrove").mkdir()
    (tmp_path / module.FOLDER).symlink_to(tmp_path / "altrove")

    why = module.prepared(tmp_path, module.Report(io.StringIO()), planned())

    assert why is not None and "non è una cartella" in why
    assert list((tmp_path / "altrove").iterdir()) == []


class Policies:
    """The API of the policies, as the leftovers of a proof read it: answers written by the test,
    and every revocation remembered."""

    def __init__(self, policies: list[dict[str, Any]], *, failing: bool = False) -> None:
        self.policies = policies
        self.failing = failing
        self.revoked: list[str] = []

    def get(self, path: str) -> Any:
        if self.failing:
            raise ConnectionError("ELA does not answer")
        assert path.startswith("/policies"), path
        return {"policies": self.policies}

    def post(self, path: str, body: Any = None) -> Any:
        self.revoked.append(path)
        return {}


def test_a_proof_stopped_midway_revokes_the_live_policies_it_created_and_says_so() -> None:
    module = script()
    api = Policies(
        [
            a_policy(id="p-2", short="aaaaaaaa"),
            a_policy(id="p-5", short="bbbbbbbb", state="EXHAUSTED"),
            a_policy(id="p-x", short="cccccccc"),
        ]
    )
    report = module.Report(io.StringIO())
    proof = module.Proof(api, report, lambda _: "s")
    proof.policies = {2: ("p-2", "aaaaaaaa"), 5: ("p-5", "bbbbbbbb")}

    module.leftovers(proof)

    assert api.revoked == ["/policies/p-2/revoke"], "only the proof's own, and only the live one"
    assert any("revocata la policy aaaaaaaa del passo 2" in line for line in report.lines)


def test_when_ela_does_not_answer_the_leftovers_say_how_to_revoke() -> None:
    module = script()
    report = module.Report(io.StringIO())
    proof = module.Proof(Policies([], failing=True), report, lambda _: "s")
    proof.policies = {7: ("p-7", "dddddddd")}

    module.leftovers(proof)

    assert any("uv run ela policy revoke dddddddd" in line for line in report.lines)


def test_an_interruption_is_a_stop_of_its_step_and_the_leftovers_are_revoked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = script()
    api = Policies([a_policy(id="p-2", short="aaaaaaaa")])
    report = module.Report(io.StringIO())
    proof = module.Proof(api, report, lambda _: "s", root=tmp_path)

    def interrupted(number: int, todo: Any, proof_: Any) -> None:
        proof_.current = number
        proof_.policies[2] = ("p-2", "aaaaaaaa")
        raise KeyboardInterrupt

    monkeypatch.setattr(module, "a_step", interrupted)

    module.walked(report, {2: []}, proof)

    assert report.stopped is not None and report.stopped[0] == 2
    assert api.revoked == ["/policies/p-2/revoke"]
    assert not report.ok


CREATION: Final = "uv run ela policy create fs.write --scope ELA/prova-m13.14/uno --days 1"


def test_a_preview_that_created_a_policy_fails_and_stops_the_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The preview, out of a terminal, prints and creates nothing: one that created — the live
    policies changed — is FAILED, and the proof stops before asking a yes."""
    module = script()
    api = Policies([])
    asked: list[str] = []

    def printed(line: str) -> subprocess.CompletedProcess[str]:
        api.policies.append(a_policy(id="p-new", short="eeeeeeee"))
        return subprocess.CompletedProcess(line, 0, "level HIGH\nnot created\n", "")

    monkeypatch.setattr(module.base, "run", printed)
    report = module.Report(io.StringIO())
    proof = module.Proof(api, report, lambda question: asked.append(question) or "s")
    crea = module.base.Block(2, "crea", f"{CREATION}\n")

    with pytest.raises(module.base.Stop):
        module.a_creation(2, crea, module.guided.Turn(), proof)

    assert report.failures == 1 and asked == [] and proof.policies == {}


def test_a_preview_that_does_not_say_it_created_nothing_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = script()
    monkeypatch.setattr(
        module.base,
        "run",
        lambda line: subprocess.CompletedProcess(line, 0, "created policy eeeeeeee\n", ""),
    )
    report = module.Report(io.StringIO())
    proof = module.Proof(Policies([]), report, lambda question: "s")
    crea = module.base.Block(2, "crea", f"{CREATION}\n")

    with pytest.raises(module.base.Stop):
        module.a_creation(2, crea, module.guided.Turn(), proof)

    assert report.failures == 1


def test_a_no_to_the_creation_stops_the_proof_and_creates_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = script()
    ran: list[str] = []

    def printed(line: str) -> subprocess.CompletedProcess[str]:
        ran.append(line)
        return subprocess.CompletedProcess(line, 0, "level HIGH\nnot created\n", "")

    monkeypatch.setattr(module.base, "run", printed)
    proof = module.Proof(Policies([]), module.Report(io.StringIO()), lambda question: "n")
    crea = module.base.Block(2, "crea", f"{CREATION}\n")

    with pytest.raises(module.base.Stop):
        module.a_creation(2, crea, module.guided.Turn(), proof)

    assert ran == [CREATION], "no --confirm after a no"
    assert proof.policies == {}


def test_main_stops_at_step_1_when_the_world_lacks_something(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = script()
    monkeypatch.setattr(
        module, "preconditions", lambda report: report.stop(1, "manca qualcosa") or False
    )
    out = tmp_path / "out.txt"

    assert module.main(["--out", str(out)]) == 1
    assert "La prova a mano di M13.14" in out.read_text(encoding="utf-8")


# ----------------------------------------------------------------------------------------
# Steps 2 to 10, walked against a real ELA
# ----------------------------------------------------------------------------------------


class World:
    """The edge of the machine of one walk: the command line of ELA answered in process."""

    def __init__(self) -> None:
        self.ran: list[str] = []

    def run(self, line: str) -> subprocess.CompletedProcess[str]:
        self.ran.append(line)
        prefix = "uv run ela "
        assert line.startswith(prefix), line
        done = CliRunner().invoke(ela_app, shlex.split(line.removeprefix(prefix)))
        return subprocess.CompletedProcess(line, done.exit_code, plain(done.output), "")


@dataclasses.dataclass
class Walked:
    report: Any
    world: World
    empty: FakeBrowser
    yours: FakeAccountBrowser
    files: Path
    policies: list[dict[str, Any]]
    """``GET /policies?all=true`` after the walk."""

    @property
    def written(self) -> str:
        return "\n".join(self.report.lines)


@asynccontextmanager
async def an_ela(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> AsyncIterator[tuple[Any, FakeBrowser, FakeAccountBrowser]]:
    """ELA as ``build`` makes it, with the two sites of the proof, a declared root and the two
    browsers of ``ela.testing``. No key and no cap: the proof calls no model."""
    module = script()
    declare(monkeypatch, tmp_path, ELA_BROWSER_SITES=json.dumps(list(module.SITES)))
    settings = Settings.load()
    await create_schema(settings.persistence.db_url)
    empty, yours = FakeBrowser(), FakeAccountBrowser()
    ela = await build(settings, power=FakePower(), browser=empty, accounts=yours)
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
    answers: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Walked:
    """Steps 2 to 10 of the section as written, run by the script itself against a real ELA,
    after the folder of step 1 is prepared; the walk ends with what the script does after, and
    the verdict, as ``main`` does. ``answers`` say «n» to the questions that start with a key."""
    module = script()
    (tmp_path / "docs").symlink_to(ROOT / "docs", target_is_directory=True)
    said = dict(answers or {})

    def ask(question: str) -> str:
        return next((no for start, no in said.items() if question.startswith(start)), "s")

    async with an_ela(monkeypatch, tmp_path) as (_, empty, yours):
        world = World()
        monkeypatch.setattr(module.base, "run", world.run)
        report = module.Report(io.StringIO())
        files = module.declared_root()[0]
        after: list[dict[str, Any]] = []

        def walk() -> None:
            assert module.prepared(files, report, module.planned_files(marked())) is None
            api = module.base.Api()
            proof = module.Proof(api, report, ask, root=files)
            if home is not None:
                proof.home = home
            try:
                module.walked(report, marked(), proof)
                after.extend(api.get("/policies?all=true")["policies"])
            finally:
                api.close()
            report.verdict()

        await asyncio.wait_for(asyncio.to_thread(walk), 120)
    return Walked(report, world, empty, yours, files, after)


async def test_steps_2_to_10_walk_against_a_real_ela_and_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Every block of the section judged on what a real ELA did: the writes under the policy with
    no question, the one outside that asks and the one through the link that fails without a use,
    the revocation, the use spent and the policy ``EXHAUSTED``, the two that are not born, the two
    gestures covered and the two outside, and the revocations after."""
    module = script()

    walk = await walked(monkeypatch, tmp_path)

    assert walk.report.ok, walk.written
    folder = walk.files / module.FOLDER
    assert (folder / "uno" / "prova.md").read_text(encoding="utf-8").startswith("ELA prova 32")
    assert sorted(one.name for one in (folder / "tre").iterdir()) == []
    assert not (folder / "uno" / "fuori").is_symlink(), "the script takes its links away"
    assert not (folder / "sorgente").is_symlink()
    states = sorted((one["capability"], one["state"], one["uses"]) for one in walk.policies)
    assert states == [
        ("browser.act", "REVOKED", 1),
        ("browser.act_as_you", "REVOKED", 1),
        ("fs.write", "EXHAUSTED", 1),
        ("fs.write", "REVOKED", 2),
    ]
    assert walk.empty.fills and walk.yours.fills, "each covered gesture filled its form"
    confirmed = [
        line for line in walk.world.ran if " policy create " in line and "--confirm" in line
    ]
    assert len(confirmed) == len(lines_of("crea")) + 2, "each policy was born from a crea's yes"
    assert all(line.endswith(" --confirm") for line in confirmed)


async def test_a_proof_stopped_midway_leaves_no_policy_alive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A no to the «no» of step 3 stops the proof — FERMATO —; the policy of step 2 is alive, and
    the script revokes it before it ends, and says so."""
    walk = await walked(monkeypatch, tmp_path, answers={"[3] Rispondi no?": "n"})

    assert walk.report.stopped is not None and walk.report.stopped[0] == 3, walk.written
    assert [one["state"] for one in walk.policies] == ["REVOKED"]
    assert "revocata la policy" in walk.written and "del passo 2" in walk.written


async def test_the_whole_folder_is_on_the_screen_and_the_home_never_in_the_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Answer 34: the preview the eye of step 2 reads names, beside each entry, the folder whole
    — on the screen. What the script writes carries ``~`` where the home is: here the home is the
    folder of the test, which holds the declared root."""
    walk = await walked(monkeypatch, tmp_path, home=tmp_path)
    screen = capsys.readouterr().out
    folder = walk.files.resolve() / "ELA" / "prova-m13.14" / "uno"

    assert f"ELA/prova-m13.14/uno = {folder}" in " ".join(screen.split())
    assert str(tmp_path) not in walk.written and str(tmp_path.resolve()) not in walk.written
    assert "~/" in walk.written
