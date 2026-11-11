"""``scripts/prova_m13_13.py`` against section 30 of the guide (M13.13; decision 10 of its SPEC).
The guide is the source of truth and the script reads it; this file keeps the two aligned, in the
form of ``test_prova_m13_10.py`` for section 29.

**The section and the script are one vocabulary**: every marker is a kind the script knows, every
kind it knows is used, every placeholder is one it fills, every plan it sends exists — and the
plans, the sentence of step 2 and the lines of the blocks name the same files and the same sites.

**Every judgement of its own has its negative case**: the plan of the model, the question, the
file on the disk, the file the script writes, the folder it empties.

**Steps 2 to 7 are walked by the script against a real ELA** — its routes, its command line, its
Guardian, its Planner over the real adapter of the model with the client double, its database —
with the two browsers of ``ela.testing``: what the guide says a command prints is what the command
printed here, and the files are on a real disk, under a declared root. **The whole path of a file
is on the screen and never in the file of the proof.**
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import importlib.util
import io
import json
import re
import shlex
import subprocess
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import cache
from pathlib import Path
from typing import Any, cast

import pytest
from anthropic import AsyncAnthropic
from typer.testing import CliRunner

from ela.api import create_app
from ela.cli import client as cli_client
from ela.cli.app import app as ela_app
from ela.composition import Settings, build, root
from ela.ports import Clock, Field, GivenFile, IdGenerator
from ela.providers.anthropic import AnthropicProvider, AnthropicSettings
from ela.testing.fakes import FakeAccountBrowser, FakeBrowser, FakePage, FakePower
from tests.api.planning import said
from tests.cli.support import LoopTransport, plain
from tests.composition.support import (  # noqa: F401 — re-exported as a fixture
    _only_the_declared_environment,
    create_schema,
    declare,
)
from tests.executive.planning import plan_of
from tests.providers.support import SECRET, FakeAnthropic

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prova_m13_13.py"
SIBLINGS = (
    "prova_m6_3c",
    "prova_m13_9",
    "prova_m13_10",
    "prova_m14_1",
    "prova_m14_2",
    "prova_m14_3",
)
PLACEHOLDER = re.compile(r"<[^>\s][^>]*>")
SENTENCE_FILE = "ELA/prova-m13.13/da-una-frase.bin"
GIVEN_FILE = "ELA/prova-m13.13/da-caricare.txt"


@cache
def script() -> Any:
    """The script, loaded as a module with its siblings — and what was in ``sys.modules`` put
    back, so that no other test finds them there."""
    before = {name: sys.modules.pop(name, None) for name in SIBLINGS}
    spec = importlib.util.spec_from_file_location("prova_m13_13", SCRIPT)
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


def lines_of(kind: str) -> list[tuple[int, str]]:
    return [
        (number, line)
        for number, blocks in marked().items()
        for one in blocks
        if one.kind == kind
        for line in one.lines
    ]


def example(name: str) -> dict[str, Any]:
    plan: dict[str, Any] = json.loads(
        (ROOT / "docs" / "examples" / name).read_text(encoding="utf-8")
    )
    (step,) = plan["steps"]
    return {"capability": step["required_capabilities"][0], **step["arguments"]}


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
    """The kinds the section uses, and not one more (decision 10 of the SPEC)."""
    used = {one.kind for blocks in marked().values() for one in blocks}

    assert used == set(script().KINDS)


def test_it_comes_after_section_29_and_before_where_to_look() -> None:
    text = guide()

    assert text.index("## 29. ") < text.index("## 30. ") < text.index("## Dove guardare dopo")


def test_every_placeholder_is_one_the_script_fills() -> None:
    module = script()
    found = {
        placeholder
        for blocks in marked().values()
        for one in blocks
        if one.kind in ("comando", "sì", "schermo")
        for placeholder in PLACEHOLDER.findall(one.body)
    }

    assert found == set(module.PLACEHOLDERS)


def test_every_plan_the_section_sends_is_an_example_of_the_repository() -> None:
    sent = {
        line.split("--file", 1)[1].split()[0]
        for blocks in marked().values()
        for one in blocks
        for line in one.lines
        if "--file" in line
    }

    assert sent, "the section sends plans"
    for name in sent:
        assert (ROOT / name).is_file(), name


def test_the_sites_of_the_proof_are_the_ones_the_section_tells_the_user_to_declare() -> None:
    """By name, and in the line it gives to write whole — which keeps every site the line of
    section 28 had: a line that dropped one would break the proofs before this one."""
    for site in script().SITES:
        assert f"`{site}`" in section(), site
    line = re.search(r"^ELA_BROWSER_SITES=(\[.*\])$", section(), flags=re.MULTILINE)
    assert line is not None, "the section gives the line to write"
    declared = json.loads(line.group(1))
    before = script().base.section(guide(), "## 28. ")
    had = json.loads(re.findall(r"^ELA_BROWSER_SITES=(\[.*\])$", before, flags=re.MULTILINE)[-1])
    assert set(script().SITES) <= set(declared)
    assert declared[: len(had)] == had and len(declared) == len(had) + 1


def test_every_line_of_every_block_of_the_section_is_in_the_vocabulary_of_its_kind() -> None:
    """Every line, read from the section, with the reader the script itself reads it with: a
    sentence of a tool the source has changed makes its ``fa`` line unreadable, here."""
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
    module = script()
    todo = {
        2: [block(2, "atteso", "outcome finished")],
        5: [block(5, "domanda", "fa downloads whatever it likes")],
        7: [block(7, "ferma", "5")],
    }

    wrong = module.outside_vocabulary(todo)

    assert len(wrong) == 3, wrong
    assert "outcome finished" in wrong[0] and "passo 2" in wrong[0]
    assert "is not a sentence a tool of the files says" in wrong[1]
    assert "'ferma' is not a kind of the section" in wrong[2], "a kind with no reader is wrong"


def test_main_reads_every_line_before_step_1_and_touches_nothing_when_one_is_wrong(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = script()
    guide_file = tmp_path / "GETTING_STARTED.md"
    guide_file.write_text(
        "## 30. La prova\n\n### 2. Uno\n\n<!-- prova: 2.scrive -->\n```\naltrove/file.txt testo\n"
        "```\n\n## Dove guardare dopo\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "GUIDE", guide_file)
    monkeypatch.setattr(
        module, "preconditions", lambda report: pytest.fail("the world was asked for")
    )
    out = tmp_path / "out.txt"

    assert module.main(["--out", str(out)]) == 1
    assert "fuori dal vocabolario" in out.read_text(encoding="utf-8")
    assert not (tmp_path / "altrove").exists()


@pytest.mark.parametrize(
    ("kind", "line"),
    [
        ("comando", "rm -rf docs"),
        ("comando", "uv run ela task run <un id che lo script non riempie>"),
        ("sì", "uv run ela task cancel <id>"),
        ("atteso", "outcome finished"),
        ("occhio", "Una frase che non chiede niente."),
        ("piano", "browser.download httpbin.org /bytes/1024"),
        ("piano", "browser.read httpbin.org /bytes/1024 ELA/file.bin"),
        ("piano", "browser.download https://httpbin.org /bytes/1024 ELA/file.bin"),
        ("piano", "browser.download httpbin.org bytes/1024 ELA/file.bin"),
        ("piano", "browser.download httpbin.org /bytes/1024 ../file.bin"),
        ("domanda", "nessuna domanda"),
        ("domanda", "capability"),
        ("domanda", "capability browser.act"),
        ("domanda", "file /etc/passwd"),
        ("domanda", "fa reads a file that is there"),
        ("domanda", "sito https://httpbin.org"),
        ("domanda", "impronta ELA/../fuori.txt"),
        ("domanda", "dimensione 12"),
        ("file", "ELA/file.bin"),
        ("file", "ELA/file.bin 1024 644"),
        ("file", "ELA/file.bin molti 600"),
        ("file", "/ELA/file.bin assente"),
        ("file", "ELA/prova-m13.13/ solo"),
        ("scrive", "ELA/prova-m13.13/da-caricare.txt"),
        ("scrive", "ELA/altrove/da-caricare.txt un testo"),
        ("scrive", "ELA/prova-m13.13/../../fuori.txt un testo"),
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
    assert out.name.startswith("prova-m13.13-") and out.suffix == ".txt"


def test_the_capabilities_of_the_script_are_the_ones_of_the_catalogue_whose_scope_is_a_file() -> (
    None
):
    """From what the source declares, not from a list of this test: the capabilities of the
    browser whose scoped argument is ``file``."""
    from ela.permissions.capabilities import production_catalogue

    of_a_file = {
        spec.id
        for spec in production_catalogue().specs()
        if spec.id.startswith("browser.") and spec.scoped_arguments == ("file",)
    }

    assert set(script().FILE_CAPABILITIES) == of_a_file and len(of_a_file) == 4


def test_each_of_the_four_capabilities_is_asked_by_a_step_that_ends_completed() -> None:
    """Answer 23 of the review of the SPEC: each of the four runs to a success at least once — a
    step that ends with a code does not prove that its capability works."""
    module = script()
    succeeded: set[str] = set()
    for blocks in marked().values():
        asked = {
            line.split()[1]
            for one in blocks
            if one.kind == "domanda"
            for line in one.lines
            if line.startswith("capability ")
        }
        ends = [line for one in blocks if one.kind == "atteso" for line in one.lines]
        if "outcome completed" in ends:
            succeeded |= asked

    assert succeeded == set(module.FILE_CAPABILITIES)


def test_the_sentence_the_plans_and_the_blocks_name_the_same_files_and_sites() -> None:
    """The file step 3 replaces is the one step 2 downloads; the file step 4 is denied is the one
    the script says is outside; the uploads give the file the script writes, to the site of the
    proof; and the sentence of step 2 names what its ``piano`` line wants."""
    module = script()
    (wanted,) = [module.a_planned(line) for _, line in lines_of("piano")]
    sentence = next(line for _, line in lines_of("comando") if " task create " in line)
    replaces = example("download-as-you-replaces.json")
    outside = example("download-outside-the-scope.json")
    written = {module.a_writing(line)[0] for _, line in lines_of("scrive")}

    assert (wanted.site, wanted.file) == ("httpbin.org", SENTENCE_FILE)
    assert wanted.file in sentence and f"https://{wanted.site}{wanted.path}" in sentence
    assert (replaces["file"], replaces["overwrite"]) == (SENTENCE_FILE, True)
    assert replaces["path"] != wanted.path, "another file of the site: the bytes on the disk change"
    assert outside["file"] == module.OUTSIDE and outside["overwrite"] is False
    assert written == {GIVEN_FILE}
    for name in ("upload-a-file.json", "upload-as-you.json"):
        given = example(name)
        assert (given["site"], given["file"]) == (module.SITES[1], GIVEN_FILE), name
        assert "click" not in given, "the page of the proof sends the file by itself"
    assert example("upload-a-file.json")["capability"] == "browser.upload"
    assert example("upload-as-you.json")["capability"] == "browser.upload_as_you"


def test_the_file_step_7_changes_is_changed_between_its_question_and_its_yes() -> None:
    """The order is the step: the question is read against the disk, **then** the script changes
    the file, **then** the yes."""
    kinds = [one.kind for one in marked()[7]]

    assert kinds.index("domanda") < kinds.index("scrive") < kinds.index("sì")
    (line,) = [line for number, line in lines_of("scrive") if number == 7]
    (first,) = [line for number, line in lines_of("scrive") if number == 5]
    assert script().a_writing(line)[1] != script().a_writing(first)[1]


# ----------------------------------------------------------------------------------------
# The judgements of its own, each with its negative case
# ----------------------------------------------------------------------------------------


def planned(**changed: Any) -> dict[str, Any]:
    """A task the Planner planned as the sentence of step 2 asks."""
    module = script()
    step = {
        "required_capabilities": ["browser.download"],
        "arguments": {
            "site": "httpbin.org",
            "path": "/bytes/1024",
            "file": SENTENCE_FILE,
            "overwrite": False,
        },
    }
    task = {
        "state": "QUEUED",
        "plan_author": {"by": "MODEL", "model": module.MODEL, "result_id": "r-1"},
        "steps": [step],
    }
    return {**task, **changed}


def wanted() -> list[Any]:
    return [script().a_planned(f"browser.download httpbin.org /bytes/1024 {SENTENCE_FILE}")]


def test_the_plan_of_the_sentence_passes() -> None:
    assert script().plan_failures(planned(), wanted()) == []


@pytest.mark.parametrize(
    ("changed", "said_"),
    [
        ({"state": "FAILED"}, "non QUEUED"),
        ({"plan_author": {"by": "USER"}}, "non MODEL"),
        ({"plan_author": {"by": "MODEL", "model": "un-altro", "result_id": "r"}}, "un-altro"),
        ({"steps": []}, "0 step, non 1"),
    ],
)
def test_a_plan_that_is_not_the_models_or_not_one_step_fails(
    changed: dict[str, Any], said_: str
) -> None:
    (failure,) = script().plan_failures(planned(**changed), wanted())

    assert said_ in failure


@pytest.mark.parametrize(
    ("argument", "value"),
    [
        ("file", "ELA/prova-m13.13/un-altro.bin"),
        ("site", "example.com"),
        ("path", "/bytes/16"),
    ],
)
def test_a_step_with_another_file_site_or_page_fails(argument: str, value: str) -> None:
    task = planned()
    task["steps"][0]["arguments"][argument] = value

    (failure,) = script().plan_failures(task, wanted())

    assert value in failure and "lo step 1" in failure


def test_a_step_of_another_capability_fails() -> None:
    task = planned()
    task["steps"][0]["required_capabilities"] = ["browser.read"]

    (failure,) = script().plan_failures(task, wanted())

    assert "browser.read" in failure


def a_question(root_: Path, **changed: Any) -> dict[str, Any]:
    module = script()
    size, digest = module.measured(root_ / GIVEN_FILE)
    asked = {
        "capability_id": "browser.upload",
        "target": str(root_.resolve() / GIVEN_FILE),
        "does": module.DOES[2],
        "site": module.SITES[1],
        "size": size,
        "digest": digest,
    }
    return {**asked, **changed}


@pytest.fixture
def declared(tmp_path: Path) -> Path:
    """A declared root with the file of the proof in it, as ``scrive`` leaves it."""
    under = tmp_path / "radice"
    (under / "ELA" / "prova-m13.13").mkdir(parents=True)
    (under / GIVEN_FILE).write_text("un testo neutro\n", encoding="utf-8")
    return under


def question_lines() -> list[str]:
    module = script()
    return [
        "capability browser.upload",
        f"file {GIVEN_FILE}",
        f"fa {module.DOES[2]}",
        f"sito {module.SITES[1]}",
        f"impronta {GIVEN_FILE}",
    ]


def test_the_question_of_the_file_on_the_disk_passes(declared: Path) -> None:
    assert script().asked_failures(question_lines(), a_question(declared), declared) == []


@pytest.mark.parametrize(
    ("field", "value", "said_"),
    [
        ("capability_id", "browser.upload_as_you", "browser.upload_as_you, non di browser.upload"),
        ("target", "/altrove/da-caricare.txt", "un percorso fuori dalla radice dichiarata"),
        ("does", "creates a new file", "«creates a new file»"),
        ("site", "example.com", "il sito example.com"),
        ("size", 3, "3 byte"),
        ("digest", "0" * 64, "0" * 64),
    ],
)
def test_each_line_of_domanda_fails_when_the_question_says_another_thing(
    declared: Path, field: str, value: Any, said_: str
) -> None:
    asked = a_question(declared, **{field: value})

    (failure,) = script().asked_failures(question_lines(), asked, declared)

    assert said_ in failure


def test_a_file_changed_after_the_question_is_not_the_one_it_named(declared: Path) -> None:
    """``impronta`` is the disk **now**: the comparison step 7 makes before it changes the file
    would fail after."""
    asked = a_question(declared)
    (declared / GIVEN_FILE).write_text("cambiato\n", encoding="utf-8")

    (failure,) = script().asked_failures([f"impronta {GIVEN_FILE}"], asked, declared)

    assert "il file sul disco" in failure


def test_no_question_where_one_is_wanted_fails(declared: Path) -> None:
    assert script().asked_failures(question_lines(), None, declared) == [
        "il task non ha una domanda in attesa"
    ]


def test_the_whole_path_of_a_question_is_never_what_the_script_writes(declared: Path) -> None:
    """What ``sì`` writes of a question: the file as the plan has it, under the root; the size
    and the fingerprint; and nothing of the path above the root."""
    lines = script().shown(a_question(declared, prompt=f"leggere {declared}/x"), declared)
    written = "\n".join(lines)

    assert f"file, sotto la radice: {GIVEN_FILE}" in written
    assert "impronta sha256" in written and "dimensione in byte" in written
    assert str(declared) not in written and str(declared.resolve()) not in written


def test_a_file_that_is_there_with_its_bytes_and_600_passes(declared: Path) -> None:
    module = script()
    (declared / GIVEN_FILE).chmod(0o600)
    size = (declared / GIVEN_FILE).stat().st_size

    assert module.file_failures(module.a_file_line(f"{GIVEN_FILE} {size} 600"), declared) == []
    assert (
        module.file_failures(module.a_file_line("ELA/prova-m13.13/ solo da-caricare.txt"), declared)
        == []
    )
    assert module.file_failures(module.a_file_line("ELA/non-c-e.bin assente"), declared) == []


def test_what_the_disk_does_not_have_as_the_line_says_fails(declared: Path) -> None:
    module = script()
    target = declared / GIVEN_FILE
    target.chmod(0o644)
    size = target.stat().st_size

    def failures(line: str) -> list[str]:
        found: list[str] = module.file_failures(module.a_file_line(line), declared)
        return found

    assert failures(f"{GIVEN_FILE} {size} 600") == [f"{GIVEN_FILE} ha i permessi 644, non 600"]
    target.chmod(0o600)
    assert failures(f"{GIVEN_FILE} {size + 1} 600") == [
        f"{GIVEN_FILE} ha {size} byte, non {size + 1}"
    ]
    assert failures("ELA/non-c-e.bin 4 600") == ["ELA/non-c-e.bin non c'è"]
    assert failures(f"{GIVEN_FILE} assente") == [f"{GIVEN_FILE} c'è, e non doveva"]
    assert failures("ELA/prova-m13.13 4 600")[0] == "ELA/prova-m13.13 non è un file regolare"
    (target.parent / "a1b2.crdownload").write_bytes(b"x")
    (only,) = failures("ELA/prova-m13.13/ solo da-caricare.txt")
    assert "a1b2.crdownload" in only
    assert "None" in failures("ELA/nessuna-cartella/ solo x")[0]


def a_proof(root_: Path, answers: dict[str, Any] | None = None) -> Any:
    module = script()

    class Answers:
        def get(self, path: str) -> Any:
            return (answers or {})[path]

    return module.Proof(
        api=Answers(),
        report=module.Report(io.StringIO()),
        ask=lambda question: "s",
        start=module.spending.Ledger.of({"cap": "30", "spent": "0", "reserved": "0", "open": 0}),
        root=root_,
    )


def test_scrive_writes_inside_the_folder_of_the_proof_with_600_in_a_folder_700(
    tmp_path: Path,
) -> None:
    module = script()
    proof = a_proof(tmp_path)
    one = block(5, "scrive", f"{GIVEN_FILE} Un testo neutro.")

    module.a_write(5, one, proof)
    module.a_write(5, block(5, "scrive", f"{GIVEN_FILE} Un altro testo."), proof)

    target = tmp_path / GIVEN_FILE
    assert target.read_text(encoding="utf-8") == "Un altro testo.\n"
    assert target.stat().st_mode & 0o777 == 0o600
    assert target.parent.stat().st_mode & 0o777 == 0o700
    digest = hashlib.sha256(b"Un altro testo.\n").hexdigest()
    assert f"    scritto {GIVEN_FILE}: 16 byte, sha256 {digest}" in proof.report.lines


def test_a_plan_that_is_not_the_sentences_closes_its_step_with_a_failure(tmp_path: Path) -> None:
    module = script()
    other = planned()
    other["steps"][0]["arguments"]["file"] = "ELA/prova-m13.13/un-altro.bin"
    proof = a_proof(tmp_path, {"/tasks/t-1": other})
    turn = module.guided.Turn()
    turn.task_id = "t-1"
    line = f"browser.download httpbin.org /bytes/1024 {SENTENCE_FILE}"
    todo = [block(2, "piano", line), block(2, "comando", "uv run ela task run <id>")]

    module.a_step(2, todo, proof, turn)

    assert proof.report.failures == 1 and proof.report.stopped is None
    assert f"    {module.NOT_PLANNED}" in proof.report.lines
    assert not any("task run" in one for one in proof.report.lines), "the rest is not done"
    assert proof.ids == {2: "t-1"}


def test_a_yes_to_the_planner_with_no_planning_task_stops_the_proof(tmp_path: Path) -> None:
    module = script()
    proof = a_proof(tmp_path, {"/tasks/t-1": {"planning_task_id": None}})
    turn = module.guided.Turn()
    turn.task_id = "t-1"
    yes = block(2, "sì", "uv run ela task approve <id del figlio> --approval <approval-id>")

    with pytest.raises(module.base.Stop, match="pianificazione"):
        module.a_block(2, yes, turn, proof)

    assert proof.report.failures == 1


def test_a_kind_that_is_not_of_the_section_is_refused(tmp_path: Path) -> None:
    module = script()

    with pytest.raises(ValueError, match="not a kind of the section"):
        module.a_block(2, block(2, "ferma", "5"), module.guided.Turn(), a_proof(tmp_path))


PLANNED = frozenset({"da-una-frase.bin", "da-caricare.txt"})


def test_the_names_step_1_may_remove_are_read_from_the_plans_of_the_section() -> None:
    """Decision 46: the files the plans name inside the folder of the proof — the plans the section
    sends, and the one the Planner is asked for —, never a list of the script's."""
    assert script().planned_names(marked()) == PLANNED


def test_a_plan_that_names_another_file_gives_its_name_and_one_elsewhere_gives_none(
    tmp_path: Path,
) -> None:
    module = script()
    line = "browser.download httpbin.org /bytes/1024"
    todo = {
        2: [block(2, "piano", f"{line} ELA/prova-m13.13/un-altro.bin")],
        3: [block(3, "piano", f"{line} ELA/altrove/fuori.bin")],
    }

    assert module.planned_names(todo) == frozenset({"un-altro.bin"})


def test_the_folder_of_the_proof_loses_the_files_of_its_plans_and_each_is_said(
    tmp_path: Path,
) -> None:
    module = script()
    folder = tmp_path / module.FOLDER
    folder.mkdir(parents=True)
    (folder / "da-una-frase.bin").write_bytes(b"di prima")
    (folder / "da-caricare.txt").write_bytes(b"di prima")
    (tmp_path / "ELA" / "non-della-prova.txt").write_text("resta", encoding="utf-8")
    report = module.Report(io.StringIO())

    assert module.emptied(tmp_path, report, PLANNED) is None

    assert list(folder.iterdir()) == []
    assert (tmp_path / "ELA" / "non-della-prova.txt").exists(), "only the folder of the proof"
    assert report.lines == [
        f"    tolto {module.FOLDER}/da-caricare.txt, di una prova di prima",
        f"    tolto {module.FOLDER}/da-una-frase.bin, di una prova di prima",
    ]


def test_a_folder_of_the_proof_that_is_not_there_is_empty(tmp_path: Path) -> None:
    assert script().emptied(tmp_path, script().Report(io.StringIO()), PLANNED) is None


@pytest.mark.parametrize("other", ["a name no plan has", "a folder", "a link"])
def test_anything_else_in_the_folder_stops_the_proof_and_nothing_is_touched(
    tmp_path: Path, other: str
) -> None:
    """Decision 46: a leftover of the browser's own (``<guid>.crdownload``), a folder or a link
    with a name of the plans: the proof stops at step 1, and **the files of the plans stay too**."""
    module = script()
    folder = tmp_path / module.FOLDER
    folder.mkdir(parents=True)
    (folder / "da-una-frase.bin").write_bytes(b"di prima")
    if other == "a name no plan has":
        (folder / "a1b2.crdownload").write_bytes(b"di prima")
    elif other == "a folder":
        (folder / "da-caricare.txt").mkdir()
    else:
        (folder / "da-caricare.txt").symlink_to(tmp_path / "ELA" / "altrove.txt")
    before = sorted(one.name for one in folder.iterdir())
    report = module.Report(io.StringIO())

    why = module.emptied(tmp_path, report, PLANNED)

    assert why is not None and "non tocca niente" in why
    assert sorted(one.name for one in folder.iterdir()) == before, "nothing was removed"
    assert report.lines == []


def test_a_folder_of_the_proof_that_is_a_link_stops_it(tmp_path: Path) -> None:
    module = script()
    (tmp_path / "ELA").mkdir()
    (tmp_path / "altrove").mkdir()
    (tmp_path / "altrove" / "da-una-frase.bin").write_text("resta", encoding="utf-8")
    (tmp_path / module.FOLDER).symlink_to(tmp_path / "altrove")

    why = module.emptied(tmp_path, module.Report(io.StringIO()), PLANNED)

    assert why is not None and "non è una cartella" in why
    assert (tmp_path / "altrove" / "da-una-frase.bin").exists()


@pytest.mark.parametrize("scope", ["ELA", "ELA/prova-m13.13"])
def test_a_scope_that_admits_the_folder_of_the_proof_passes(scope: str) -> None:
    assert script().scope_admits(scope) is None


@pytest.mark.parametrize("scope", ["ELA/altro", "altrove", "fuori-dallo-scope"])
def test_a_scope_that_does_not_admit_the_folder_of_the_proof_stops_it(scope: str) -> None:
    why = script().scope_admits(scope)

    assert why is not None and scope in why


def test_main_stops_at_step_1_when_the_world_lacks_something(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = script()
    monkeypatch.setattr(
        module, "preconditions", lambda report: report.stop(1, "manca qualcosa") or False
    )
    out = tmp_path / "out.txt"

    assert module.main(["--out", str(out)]) == 1
    assert "La prova a mano di M13.13" in out.read_text(encoding="utf-8")


# ----------------------------------------------------------------------------------------
# Steps 1 to 7, walked against a real ELA
# ----------------------------------------------------------------------------------------

DOWNLOAD_STEP: dict[str, Any] = {
    "name": "download",
    "goal": "scaricare il file della frase",
    "capability": "browser.download",
    "arguments": {
        "site": "httpbin.org",
        "path": "/bytes/1024",
        "file": SENTENCE_FILE,
        "overwrite": False,
        "purpose": "la prova a mano dei file dal browser",
    },
    "expected_result": "il file al nome della frase",
    "success_conditions": ["browser.file_downloaded"],
}
"""What a model writes from the sentence of step 2, in the Planner's own format."""
FIELD = "#fileinput"


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
    """The declared root of the walk."""

    @property
    def written(self) -> str:
        return "\n".join(self.report.lines)


@asynccontextmanager
async def an_ela(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *answers: Any, **declared_: str
) -> AsyncIterator[tuple[Any, FakeBrowser, FakeAccountBrowser]]:
    """ELA as ``build`` makes it, with a cap, a key, the two sites of the proof, the real adapter
    of the model over the client double — which answers what the test writes —, and the two
    browsers of ``ela.testing``: the empty one brings 1024 bytes, the one of the profile 2048."""
    module = script()
    client = FakeAnthropic(*answers)

    def provider(
        clock: Clock, ids: IdGenerator, *, settings: AnthropicSettings | None = None
    ) -> AnthropicProvider:
        assert settings is not None
        return AnthropicProvider(
            cast(AsyncAnthropic, client), clock=clock, ids=ids, settings=settings
        )

    monkeypatch.setattr(root, "anthropic_provider", provider)
    values = {
        "ELA_SPENDING_CAP_USD": "30",
        "ELA_ANTHROPIC_API_KEY": SECRET,
        "ELA_BROWSER_SITES": json.dumps(list(module.SITES)),
        **declared_,
    }
    declare(monkeypatch, tmp_path, **values)
    settings = Settings.load()
    await create_schema(settings.persistence.db_url)
    empty = FakeBrowser(FakePage(download=bytes(1024), fields={FIELD: Field("file", "")}))
    yours = FakeAccountBrowser(FakePage(download=bytes(2048), fields={FIELD: Field("file", "")}))
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
    steps: set[int],
    *,
    model: dict[str, Any] | None = None,
) -> Walked:
    """The steps of the section in ``steps``, as written in the guide, run by the script itself
    against a real ELA; the walk ends with the verdict, as ``main`` does."""
    module = script()
    (tmp_path / "docs").symlink_to(ROOT / "docs", target_is_directory=True)
    answer = said(plan_of(DOWNLOAD_STEP if model is None else model))
    async with an_ela(monkeypatch, tmp_path, answer) as (_, empty, yours):
        world = World()
        monkeypatch.setattr(module.base, "run", world.run)
        report = module.Report(io.StringIO())
        files = module.declared_root()[0]

        def walk() -> None:
            api = module.base.Api()
            proof = module.Proof(
                api,
                report,
                lambda question: "s",
                module.spending.Ledger.of(api.get("/spend")),
                root=files,
            )
            todo = {number: blocks for number, blocks in marked().items() if number in steps}
            try:
                module.base.walk(
                    report, todo, lambda number, its: module.a_step(number, its, proof)
                )
            finally:
                api.close()
            report.verdict()

        await asyncio.wait_for(asyncio.to_thread(walk), 120)
    return Walked(report, world, empty, yours, files)


async def test_steps_2_to_7_walk_against_a_real_ela_and_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Every block of the section judged on what a real ELA did: the plan the Planner wrote from
    the sentence, the four questions read from the API and compared with the disk, the files where
    the plans name them — the second download in the place of the first —, the denial with no
    question, the two uploads, and the file changed after its question, which does not leave."""
    module = script()

    walk = await walked(monkeypatch, tmp_path, {2, 3, 4, 5, 6, 7})

    assert walk.report.ok, walk.written
    assert walk.report.failures == 0 and walk.report.stopped is None, walk.written
    downloaded = walk.files / SENTENCE_FILE
    assert downloaded.read_bytes() == bytes(2048), "the download of step 3 replaced step 2's"
    assert downloaded.stat().st_mode & 0o777 == 0o600
    assert len(walk.empty.downloads) == 1 and len(walk.yours.downloads) == 1
    first = GivenFile(
        "da-caricare.txt",
        "text/plain",
        (module.a_writing(lines_of("scrive")[0][1])[1] + "\n").encode(),
    )
    assert walk.empty.given == [(FIELD, first)], "step 5 gave the file; step 7 gave nothing"
    assert walk.yours.given == [(FIELD, first)]
    assert not (walk.files / module.OUTSIDE).exists()
    assert "error browser.file_changed" in " ".join(walk.written.split())


async def test_the_whole_path_of_a_file_is_on_the_screen_and_never_in_the_file_of_the_proof(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Before each eye a ``schermo`` shows the question as the command line prints it — with the
    whole path, the size and the sha256 —, on the screen alone; what the script writes carries the
    path as the plan has it, under the root, and nothing above it."""
    walk = await walked(monkeypatch, tmp_path, {2, 3, 4, 5, 6, 7})
    screen = capsys.readouterr().out
    above = str(walk.files.resolve())
    only_on_the_screen = [line for line in screen.splitlines() if line.startswith("    | ")]

    assert f"{above}/{GIVEN_FILE}" in " ".join(only_on_the_screen)
    assert "sha256" in " ".join(only_on_the_screen)
    assert above not in walk.written and str(tmp_path) not in walk.written, walk.written
    assert f"file, sotto la radice: {GIVEN_FILE}" in walk.written
    for number in (2, 5):
        step = walk.written.split(f"—— passo {number} ——", 1)[1].split("—— passo", 1)[0]
        assert step.index("$ uv run ela approvals") < step.index(f"[{number}] GUARDATO"), step


async def test_a_plan_of_the_model_that_names_another_file_closes_step_2_and_downloads_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    other = {
        **DOWNLOAD_STEP,
        "arguments": {**DOWNLOAD_STEP["arguments"], "file": "ELA/prova-m13.13/un-altro.bin"},
    }

    walk = await walked(monkeypatch, tmp_path, {2}, model=other)

    assert walk.report.failures == 1 and not walk.report.ok, walk.written
    assert "un-altro.bin" in walk.written and script().NOT_PLANNED in walk.written
    assert not any(" task run " in line for line in walk.world.ran), "the plan was never run"
    assert walk.empty.downloads == []


async def test_step_1_passes_on_what_the_real_routes_answer_and_empties_the_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The checks of step 1 against the routes themselves: the field of the question that says
    the Core runs this code, the key, the cap, the sites, the scope, the profile — and the folder
    of the proof, emptied of what a proof before left."""
    module = script()
    monkeypatch.setattr(module.planning, "on_origin", lambda: None)
    async with an_ela(monkeypatch, tmp_path):
        left = module.declared_root()[0] / module.FOLDER / "da-una-frase.bin"
        left.parent.mkdir(parents=True)
        left.write_bytes(b"di prima")
        report = module.Report(io.StringIO())

        ok = await asyncio.to_thread(module.preconditions, report)

    assert ok and report.stopped is None, report.lines
    assert not left.exists()
    assert f"    tolto {module.FOLDER}/da-una-frase.bin, di una prova di prima" in report.lines


def test_the_field_step_1_asks_the_schema_for_is_one_m13_13_gave_the_question() -> None:
    """A field the question had before M13.13 would say «the branch's code» of a Core started from
    ``main``: the one the script asks for is among those ADR 0066 §5 names as the question's new
    ones, and the schema of today has it."""
    from ela.api.schemas import ApprovalOut

    adr = (ROOT / "docs" / "adr" / "0066-browser-files.md").read_text(encoding="utf-8")
    fifth = adr.split("### 5. ", 1)[1].split("\n### ", 1)[0]
    named = re.findall(r"^- `(\w+)`(?: e `(\w+)`)?", fifth, flags=re.MULTILINE)
    new = {name for found in named for name in found if name}

    assert new == {"site", "visits", "size", "digest"}
    assert script().QUESTION_FIELD in new
    assert script().QUESTION_FIELD in ApprovalOut.model_fields


async def test_a_core_whose_question_lacks_the_field_is_not_the_branch_s_and_stops_the_proof(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The check itself, against the real schema: asked for a field it does not have, step 1
    stops — as it would on a Core started from the code of before."""
    module = script()
    monkeypatch.setattr(module.planning, "on_origin", lambda: None)
    monkeypatch.setattr(module, "QUESTION_FIELD", "un-campo-di-domani")
    async with an_ela(monkeypatch, tmp_path):
        report = module.Report(io.StringIO())

        ok = await asyncio.to_thread(module.preconditions, report)

    assert not ok and report.stopped is not None
    assert "il Core gira dal codice del branch" in report.stopped[1], report.lines


@pytest.mark.parametrize(
    ("declared_", "missing"),
    [
        ({"ELA_BROWSER_SITES": '["httpbin.org"]'}, "sono fra i siti dichiarati"),
        ({"ELA_FS_SCOPE": "altrove"}, "non ammette"),
        ({"ELA_SPENDING_CAP_USD": "1"}, "una pianificazione al caso peggiore"),
    ],
)
async def test_step_1_stops_on_a_world_that_is_not_the_one_the_proof_wants(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, declared_: dict[str, str], missing: str
) -> None:
    module = script()
    monkeypatch.setattr(module.planning, "on_origin", lambda: None)
    async with an_ela(monkeypatch, tmp_path, **declared_):
        report = module.Report(io.StringIO())

        ok = await asyncio.to_thread(module.preconditions, report)

    assert not ok and report.stopped is not None
    assert missing in report.stopped[1], report.lines


async def test_step_1_stops_on_what_no_plan_names_in_the_folder_and_touches_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Decision 46, through the real routes: a leftover of the browser's own beside a file of
    the plans stops the proof at step 1, and neither of the two is removed."""
    module = script()
    monkeypatch.setattr(module.planning, "on_origin", lambda: None)
    async with an_ela(monkeypatch, tmp_path):
        folder = module.declared_root()[0] / module.FOLDER
        folder.mkdir(parents=True)
        (folder / "da-una-frase.bin").write_bytes(b"di prima")
        (folder / "a1b2.crdownload").write_bytes(b"di prima")
        report = module.Report(io.StringIO())

        ok = await asyncio.to_thread(module.preconditions, report)

    assert not ok and report.stopped is not None
    assert "non tocca niente" in report.stopped[1], report.lines
    assert sorted(one.name for one in folder.iterdir()) == ["a1b2.crdownload", "da-una-frase.bin"]
