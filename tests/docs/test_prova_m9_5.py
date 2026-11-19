"""``scripts/prova_m9_5.py`` and section 33 of the guide say the same thing (M13.13b and M9.5).

The guide is the source of truth: the script reads its blocks with the reader of ``prova_m6_3c``,
and this test reads them with the same reader — every kind is one the script knows, every line is
in the vocabulary of its kind, every plan the section sends is an example of the repository, and
the files the plans name are where the ``file`` blocks look. Then **steps 2 and 3 are walked by
the script itself against a real ELA** — the API, the CLI and the tools of ``build``, with the two
browsers of ``ela.testing`` —: the two downloads, their questions, and a folder that holds the
files asked for and nothing else. Step 4 waits the thirty seconds of the tool against a real site:
the walk leaves it to the hand, and what it promises — nothing of an interrupted download stays —
is the test of the door,
``test_what_is_announced_while_the_door_closes_is_cancelled_and_taken_away``.
"""

from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import sys
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from ela.permissions.capabilities import BROWSER_DOWNLOAD, BROWSER_DOWNLOAD_AS_YOU
from tests.composition.support import _only_the_declared_environment  # noqa: F401 — the fixture
from tests.docs import test_prova_m13_13 as of_m13_13

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prova_m9_5.py"
SIBLINGS = (*of_m13_13.SIBLINGS, "prova_m13_13")


@cache
def script() -> Any:
    """The script, loaded as a module with its siblings — and what was in ``sys.modules`` put
    back, so that no other test finds them there."""
    before = {name: sys.modules.pop(name, None) for name in SIBLINGS}
    spec = importlib.util.spec_from_file_location("prova_m9_5", SCRIPT)
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


def marked() -> dict[int, list[Any]]:
    module = script()
    found: dict[int, list[Any]] = module.base.steps(module.base.blocks(guide(), module.HEADING))
    return found


def plans() -> dict[int, dict[str, Any]]:
    """The plan each step sends, by step: the one step of it, with its capability."""
    sent: dict[int, dict[str, Any]] = {}
    for number, blocks in marked().items():
        for one in blocks:
            for line in one.lines:
                if one.kind == "comando" and "--file" in line:
                    path = ROOT / line.split("--file", 1)[1].split()[0]
                    (step,) = json.loads(path.read_text(encoding="utf-8"))["steps"]
                    sent[number] = {"capability": step["required_capabilities"][0], **step}
    return sent


def test_every_kind_of_the_section_is_one_the_script_knows_and_every_one_is_used() -> None:
    module = script()
    used = {one.kind for blocks in marked().values() for one in blocks}

    assert used == set(module.KINDS)
    assert sorted(marked()) == [2, 3, 4]


def test_it_comes_after_section_32_and_before_where_to_look() -> None:
    text = guide()

    assert text.index("## 32. ") < text.index("## 33. ") < text.index("## Dove guardare dopo")


def test_every_line_of_the_section_is_in_the_vocabulary_of_its_kind() -> None:
    assert script().outside_vocabulary(marked()) == []


def test_a_kind_of_another_section_is_refused_before_step_1() -> None:
    module = script()
    wrong = module.outside_vocabulary({2: [module.base.Block(2, "scrive", "x y\n")]})

    assert any("'scrive' is not a kind of the section" in one for one in wrong)


def test_the_plans_are_the_two_downloads_and_the_one_the_tool_cuts_short() -> None:
    sent = plans()

    assert [sent[number]["capability"] for number in (2, 3, 4)] == [
        BROWSER_DOWNLOAD,
        BROWSER_DOWNLOAD_AS_YOU,
        BROWSER_DOWNLOAD,
    ]
    assert {one["arguments"]["site"] for one in sent.values()} == set(script().SITES)
    assert all(not one["arguments"]["overwrite"] for one in sent.values())
    assert sent[4]["arguments"]["path"].startswith("/drip?duration=60")


def test_the_files_the_plans_name_are_the_ones_the_folder_is_looked_for() -> None:
    module = script()

    assert module.planned_names(marked()) == {"vuoto.bin", "come-te.bin", "interrotto.bin"}
    assert "outcome failed" in "\n".join(
        line for one in marked()[4] if one.kind == "atteso" for line in one.lines
    )
    assert "failed" in module.files.OUTCOME_WORDS


def test_the_sites_are_the_ones_section_30_declared() -> None:
    """Decision 63: no new line in the ``.env``."""
    assert set(script().SITES) <= set(of_m13_13.script().SITES)


def test_a_scope_that_does_not_admit_the_folder_stops_the_proof() -> None:
    module = script()

    assert module.scope_admits(("ELA",)) is None
    assert module.scope_admits(("Documenti", "ELA")) is None, "a list: one folder is enough"
    assert module.scope_admits(("Documenti",)) is not None


def test_a_crdownload_left_in_the_folder_stops_the_proof_and_nothing_is_touched(
    tmp_path: Path,
) -> None:
    """What the proof is about, before it begins: a ``.crdownload`` in its folder is not a file of
    its plans, and the proof stops there without removing it — it is Tommaso's to look at."""
    module = script()
    folder = tmp_path / module.FOLDER
    folder.mkdir(parents=True)
    (folder / "vuoto.bin").write_bytes(b"x")
    (folder / "1234.crdownload").write_bytes(b"x")
    report = module.Report(io.StringIO())

    said = module.emptied(tmp_path, report, module.planned_names(marked()))

    assert said is not None and "1234.crdownload" in said
    assert sorted(one.name for one in folder.iterdir()) == ["1234.crdownload", "vuoto.bin"]


def test_the_files_of_a_proof_before_are_removed_and_each_is_said(tmp_path: Path) -> None:
    module = script()
    folder = tmp_path / module.FOLDER
    folder.mkdir(parents=True)
    (folder / "vuoto.bin").write_bytes(b"x")
    report = module.Report(io.StringIO())

    assert module.emptied(tmp_path, report, module.planned_names(marked())) is None
    assert list(folder.iterdir()) == []
    assert "tolto ELA/prova-m9.5/vuoto.bin" in "\n".join(report.lines)


def test_the_file_is_in_downloads_with_the_name_of_the_branch() -> None:
    assert script().default_out().name.startswith("prova-m9.5-")


async def test_steps_2_and_3_walk_against_a_real_ela_and_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Every block of steps 2 and 3 judged on what a real ELA did: the two questions read from the
    API, the files where the plans name them, and a folder that holds them and nothing else."""
    module = script()
    (tmp_path / "docs").symlink_to(ROOT / "docs", target_is_directory=True)
    async with of_m13_13.an_ela(monkeypatch, tmp_path) as (_, empty, yours):
        world = of_m13_13.World()
        monkeypatch.setattr(module.base, "run", world.run)
        report = module.Report(io.StringIO())
        files = module.files.declared_root()[0]

        def walk() -> None:
            api = module.base.Api()
            proof = module.Proof(
                api,
                report,
                lambda question: "s",
                module.spending.Ledger.of(api.get("/spend")),
                root=files,
            )
            todo = {number: blocks for number, blocks in marked().items() if number in {2, 3}}
            try:
                module.base.walk(
                    report, todo, lambda number, its: module.files.a_step(number, its, proof)
                )
            finally:
                api.close()
            report.verdict()

        await asyncio.wait_for(asyncio.to_thread(walk), 120)

    written = "\n".join(report.lines)
    assert report.ok and report.failures == 0 and report.stopped is None, written
    assert sorted(one.name for one in (files / module.FOLDER).iterdir()) == [
        "come-te.bin",
        "vuoto.bin",
    ]
    assert len(empty.downloads) == 1 and len(yours.downloads) == 1
