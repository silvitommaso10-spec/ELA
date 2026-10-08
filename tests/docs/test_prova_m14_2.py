"""Section 24 of the guide and ``scripts/prova_m14_2.py`` say the same thing (M14.2, «La prova a
mano»).

The guide is the source of truth, and the script reads it with the reader of M6.3c: this file reads
the section with the script's own functions and asserts that every marker is a kind the script knows
and a step of the section, that every placeholder is one it fills, and that every line of its kinds
is in their vocabulary. **Each comparison of the script has its negative case**: a check that only
ever passes proves nothing.

**Every kind that reads the API is fed the answers of the real routes** — step 1, ``sì``, ``piano``,
``chiamata``, ``rifiuto``, ``spesa`` —, recorded once by ``tests/docs/real_planning.py`` on an ELA
whose model answers through the real adapter and no socket, with the output of the command line
next to them (decision 25 of the review of the proof, 2026-10-08). The first round by hand had two
FAILED, both the script's, and both passed here: the answers were dictionaries written by hand, one
with a key the route does not have, and no test ran two commands in one block. **A negative case
starts from a real answer and changes it**; nothing the API says is written here. That the question
the section expects is the one ELA asks — the worst case of a planning, as ``ela task plan`` prints
it — is proved in ``tests/api/test_planning.py`` and ``tests/cli/test_planning.py``.
"""

from __future__ import annotations

import copy
import importlib.util
import io
import json
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from ela.executive.planner import PLANNER_NO_PLAN
from ela.permissions.capabilities import DEFAULT_NOTES_SCOPE, production_catalogue
from tests.api.test_planning import WORST
from tests.docs.real_planning import Real, Recorded, changed, record
from tests.executive.planning import NOTE_BODY, NOTE_PATH

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prova_m14_2.py"
PLACEHOLDER = re.compile(r"<[^>\s][^>]*>")


SIBLINGS = ("prova_m6_3c", "prova_m14_1")
"""The scripts ``prova_m14_2`` imports. Other test files load them by path and register their own
copies under these names (``test_prova_m6_3c.py``, ``test_prova_m14_1.py``): a ``prova_m14_1``
loaded before a new ``prova_m6_3c`` keeps the old one, and the script would hold two — a test that
patched one left the other to the real client (decision 31 of the review of the proof)."""


@cache
def script() -> ModuleType:
    """The script, loaded by path: ``scripts/`` is not a package. Its siblings are imported anew
    for it, once each, as ``python scripts/prova_m14_2.py`` imports them — whatever another test
    file registered under their names —, and ``sys.modules`` is given back as it was found."""
    found = {name: sys.modules.pop(name, None) for name in SIBLINGS}
    try:
        spec = importlib.util.spec_from_file_location("prova_m14_2", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    finally:
        for name, before in found.items():
            if before is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = before
    return module


def test_the_script_and_its_siblings_are_one_world() -> None:
    """Decision 31: a test patches the module the script uses, never a second copy of it. The
    script reads ELA's API through ``prova_m6_3c`` both itself and through ``prova_m14_1``: they
    are one module, as when ``python scripts/prova_m14_2.py`` imports them, whatever another test
    file registered under their names before."""
    module = script()

    assert module.spending.base is module.base


def guide() -> str:
    return str(script().GUIDE.read_text(encoding="utf-8"))


def section() -> str:
    return str(script().base.section(guide(), script().HEADING))


def marked() -> dict[int, list[Any]]:
    module = script()
    by_step: dict[int, list[Any]] = module.base.steps(module.base.blocks(guide(), module.HEADING))
    return by_step


def lines_of(kind: str) -> list[tuple[int, str]]:
    return [
        (number, line)
        for number, blocks in marked().items()
        for block in blocks
        if block.kind == kind
        for line in block.lines
    ]


# ----------------------------------------------------------------------------------------
# The section and the script
# ----------------------------------------------------------------------------------------


def test_every_marker_is_a_kind_the_script_knows_and_belongs_to_a_step_of_the_section() -> None:
    headings = {int(number) for number in re.findall(r"^### (\d+)\. ", section(), re.MULTILINE)}
    found = marked()

    assert found, "section 24 has no marked block: the script would do nothing"
    assert set(found) <= headings
    assert set(found) == set(range(2, 7)), "steps 2 to 6; step 1 is the script's own"
    assert all(block.kind in script().KINDS for blocks in found.values() for block in blocks)
    every_marker = re.findall(r"<!-- prova: (\d+)\.(\w+) -->", section())
    assert len(every_marker) == sum(len(blocks) for blocks in found.values()), (
        "a marker the reader did not take: it is not right above a fenced block"
    )


def test_it_comes_after_section_23_which_two_readers_find_by_its_heading() -> None:
    """The script of M14.1 and ``test_adr_spending.py`` look for ``## 23. `` by name."""
    text = guide()

    assert text.index("## 23. ") < text.index(script().HEADING) < text.index("## Dove guardare")


def test_every_kind_of_the_script_is_used_by_the_section() -> None:
    """A kind nobody writes is code nobody runs: the vocabulary and the guide move together."""
    used = {block.kind for blocks in marked().values() for block in blocks}

    assert used == set(script().KINDS)


def test_every_placeholder_is_one_the_script_fills() -> None:
    used = {
        found
        for blocks in marked().values()
        for block in blocks
        for found in PLACEHOLDER.findall(block.body)
    }

    assert used == set(script().PLACEHOLDERS)


def test_four_tasks_are_created_with_the_json_and_four_calls_are_asked_a_yes() -> None:
    module = script()
    created = [line for _, line in lines_of("comando") if module.CREATE in f" {line} "]

    assert len(created) == 4
    assert all(line.endswith(" --json") for line in created), created
    assert module.calls_of(marked()) == 4
    assert [line for _, line in lines_of("sì")] == [
        f"uv run ela task approve {module.CHILD} --approval {module.APPROVAL_ID}"
    ] * 4


def test_no_plan_of_the_section_is_written_by_hand() -> None:
    """The plans of this proof are the model's: a ``--file`` would test the other door."""
    assert not [line for _, line in lines_of("comando") if "--file" in line]


def test_the_worst_case_it_expects_is_the_one_ela_asks_with() -> None:
    """The line of every question is the one ``tests/api/test_planning.py`` reads off the API."""
    worst = [line for _, line in lines_of("atteso") if line.startswith("worst case ")]

    assert worst == [f"worst case {WORST}"] * 4


def test_the_margin_is_four_worst_cases_computed_and_the_section_writes_it() -> None:
    module = script()

    assert module.margin(4) == Decimal("17.048576")
    assert "4 × 4,262144 = 17,048576 $" in section()
    assert "**il suo caso peggiore è 4,262144 $**" in " ".join(section().split())


def test_every_line_of_the_scripts_kinds_is_in_its_vocabulary() -> None:
    module = script()
    ids = {str(spec.id) for spec in production_catalogue().specs()}

    assert {line for _, line in lines_of("piano")} <= ids
    assert {line for _, line in lines_of("chiamata")} == {module.MODEL}
    assert [line for _, line in lines_of("rifiuto")] == [PLANNER_NO_PLAN]
    assert {line for _, line in lines_of("spesa")} == set(module.LEDGER_WORDS)


def test_the_note_is_named_by_the_script_inside_the_scope_of_the_notes() -> None:
    module = script()
    (create,) = [line for number, line in lines_of("comando") if number == 2 and "create" in line]

    assert f"{DEFAULT_NOTES_SCOPE}/{module.NOTE}" in create
    assert module.NOTE in " ".join(line for number, line in lines_of("comando") if number == 2)
    first = module.note_name(datetime(2026, 10, 8, 10, 15, 0))
    second = module.note_name(datetime(2026, 10, 8, 10, 15, 1))
    assert first != second, "a second round never finds the note of the first"
    assert first == "prova-m14.2-20261008-101500.md"


def test_the_note_step_runs_its_plan_and_the_others_do_not() -> None:
    runs = {number for number, line in lines_of("comando") if " task run " in f" {line} "}

    assert runs == {2}


def test_the_file_is_in_downloads_with_the_name_of_the_milestone() -> None:
    out = script().default_out()

    assert out.parent == Path.home() / "Downloads"
    assert out.name.startswith("prova-m14.2-")


def test_every_refusal_reads_what_the_ela_task_plan_before_it_printed() -> None:
    """Decision 24: ``rifiuto`` reads the reason in what the commands of the block before it
    printed, and that block is ``ela task plan <id>``: the surface Tommaso reads."""
    for blocks in marked().values():
        for index, block in enumerate(blocks):
            if block.kind != "rifiuto":
                continue
            run = [one for one in blocks[:index] if one.kind in ("comando", "sì")]
            assert run, "a refusal with no command before it reads nothing"
            assert run[-1].lines == [f"uv run ela task plan {script().ID}"]


def test_the_commit_of_origin_with_a_clean_tree_passes() -> None:
    assert script().same_as_origin("ab87d9d\n", "ab87d9d\n", "") is None


@pytest.mark.parametrize(
    ("head", "upstream", "dirty"),
    [("ab87d9d", "e482170", ""), ("ab87d9d", "ab87d9d", " M docs/GETTING_STARTED.md\n")],
    ids=["behind", "dirty"],
)
def test_another_commit_or_a_dirty_tree_stops(head: str, upstream: str, dirty: str) -> None:
    assert script().same_as_origin(head, upstream, dirty) is not None


def test_the_migration_of_m14_2_is_read_from_alembic() -> None:
    module = script()

    assert module.at_the_migration("0014 (head)\n")
    assert not module.at_the_migration("0013 (head)\n")
    assert not module.at_the_migration("")


def test_a_precondition_missing_stops_the_proof_with_what_is_missing() -> None:
    module = script()
    report = module.base.Report(io.StringIO())

    went_on = module.stopping(report, [("ELA risponde", lambda: True), ("un tetto", lambda: False)])

    assert went_on is False
    assert report.stopped == (1, "la prova richiede «un tetto», e non è così")
    assert report.skipped_steps == [], "FERMATO, not SALTATO (rule 5 of the session)"


def test_a_precondition_that_raises_stops_it_too() -> None:
    module = script()
    report = module.base.Report(io.StringIO())

    def away() -> bool:
        raise ConnectionError("refused")

    assert module.stopping(report, [("ELA risponde", away)]) is False
    assert report.stopped is not None and "ConnectionError: refused" in report.stopped[1]


# ----------------------------------------------------------------------------------------
# The catalogue of the code: what «piano» reads a plan against
# ----------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def code() -> dict[str, Any]:
    """The catalogue of the code, as the script reads it: never from the Planner's functions."""
    read: dict[str, Any] = script().read_code_catalogue()
    return read


def test_the_code_s_catalogue_is_every_capability_a_verifier_checks(code: dict[str, Any]) -> None:
    assert set(code) == {str(spec.id) for spec in production_catalogue().specs()}
    assert code["workspace.write_note"] == {
        "risk": "LOW",
        "asks_the_user": False,
        "success_conditions": ["note.content_matches", "note.exists"],
    }
    assert code["model.complete"]["risk"] == "MEDIUM"
    assert code["model.complete"]["asks_the_user"] is True
    assert "reasoning" in code["model.complete"]["task_types"]
    assert code["fs.write"]["risk"] == "HIGH"


def test_a_capability_no_verifier_checks_is_not_in_the_code_s_catalogue() -> None:
    specs = list(production_catalogue().specs())

    found = script().code_catalogue(specs, [], ["reasoning"])

    assert found == {}


def test_instructions_without_a_catalogue_are_refused() -> None:
    with pytest.raises(ValueError, match="no catalogue"):
        script().catalogue_of("You are the Planner.")


# ----------------------------------------------------------------------------------------
# The answers of the real routes (decision 25 of the review of the proof): every kind that
# reads the API is fed them, and a negative case starts from one of them, changed
# ----------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real(tmp_path_factory: pytest.TempPathFactory) -> Real:
    return record(tmp_path_factory)


def proof_on(real: Real, answers: dict[str, Any], said: list[str] | None = None) -> Any:
    """A proof whose API answers what the real one answered."""
    module = script()
    asked: list[str] = []

    def ask(question: str) -> str:
        asked.append(question)
        return said.pop(0) if said else "s"

    proof = module.Proof(
        api=Recorded(answers),
        report=module.base.Report(io.StringIO()),
        ask=ask,
        note="prova-m14.2-20261008-101500.md",
        start=module.spending.Ledger.of(real.spend_start),
    )
    proof.asked = asked
    return proof


def walked_on(proof: Any, todo: dict[int, list[Any]], turn: Any) -> list[int]:
    module = script()
    done: list[int] = []

    def one(number: int, its: list[Any]) -> None:
        done.append(number)
        module.a_step(number, its, proof, turn)

    module.base.walk(proof.report, todo, one)
    proof.report.verdict()
    return done


def block(number: int, kind: str, body: str) -> Any:
    return script().base.Block(number, kind, body)


def stepped(task: Any, index: int, **fields: Any) -> Any:
    """A real task whose step ``index`` has ``fields`` changed."""
    copied = copy.deepcopy(task)
    copied["steps"][index].update(fields)
    return copied


def answered_of(results: Any) -> Any:
    """The result that answered, of a planning task's real results."""
    (found,) = [one for one in results if one["status"] == "SUCCEEDED"]
    return found


def costs_of(real: Real) -> list[Decimal]:
    """The cost of each of the three calls, as their results say it."""
    every = (real.results, real.asking_results, real.refused_results)
    return [Decimal(answered_of(results)["usage"]["cost"]) for results in every]


# «comando» and «atteso» -------------------------------------------------------------------


def outputs(real: Real, monkeypatch: pytest.MonkeyPatch) -> None:
    """``ela task run`` prints what it printed in the recorded world; ``cat`` the note."""
    module = script()
    printed = {"uv run ela task run": real.run_output, "cat": f"{NOTE_BODY}\n"}

    def run(line: str) -> subprocess.CompletedProcess[str]:
        (said,) = [out for start, out in printed.items() if line.startswith(start)]
        return subprocess.CompletedProcess(line, 0, said, "")

    monkeypatch.setattr(module.base, "run", run)


def test_the_expected_lines_are_read_in_the_output_of_every_command_of_the_block(
    real: Real, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decision 23: step 2 runs ``ela task run`` and ``cat`` in one block, and its expected block
    has a line of each. The script kept the output of the last command only, and failed a run
    that had completed (the file of 2026-10-08, lines 88 and 94)."""
    module = script()
    outputs(real, monkeypatch)
    proof = proof_on(real, {})
    todo = {
        2: [
            block(2, "comando", f"uv run ela task run <id>\ncat {NOTE_PATH}"),
            block(2, "atteso", f"outcome completed\n{NOTE_BODY}"),
        ]
    }

    walked_on(proof, todo, module.Turn(task_id=real.task))

    assert proof.report.failures == 0, proof.report.lines
    assert proof.report.ok


def test_the_expected_lines_are_not_read_in_the_output_of_an_earlier_block(
    real: Real, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative case of decision 23: what the block before the last printed is not there."""
    module = script()
    outputs(real, monkeypatch)
    proof = proof_on(real, {})
    todo = {
        2: [
            block(2, "comando", "uv run ela task run <id>"),
            block(2, "comando", f"cat {NOTE_PATH}"),
            block(2, "atteso", "outcome completed"),
        ]
    }

    walked_on(proof, todo, module.Turn(task_id=real.task))

    assert proof.report.failures == 1


# Step 1 -----------------------------------------------------------------------------------


def step_1(real: Real, **changed_answers: Any) -> dict[str, Any]:
    """What step 1 reads of ELA, as the real routes answered at the start of the proof."""
    answers = {
        "/health": real.health,
        "/openapi.json": real.openapi,
        "/diagnostics": real.diagnostics,
        "/spend": real.spend_start,
    }
    return {**answers, **changed_answers}


def preconditions_on(answers: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> Any:
    """Step 1 with its API the recorded one; the commit, the migration and the sites as the Mac
    of the proof has them — they are not the API's, and have their own cases above."""
    module = script()
    monkeypatch.setattr(module.base, "Api", lambda: Recorded(answers))
    monkeypatch.setattr(module, "on_origin", lambda: None)
    monkeypatch.setattr(module, "migrated", lambda: True)
    monkeypatch.setenv("ELA_BROWSER_SITES", json.dumps([module.SITE]))
    report = module.base.Report(io.StringIO())
    module.preconditions(report, 4)
    return report


def test_step_1_goes_on_with_what_the_real_routes_answer(
    real: Real, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = preconditions_on(step_1(real), monkeypatch)

    assert report.stopped is None, report.lines
    assert report.passes == {1: 8}


def test_exactly_four_worst_cases_left_is_enough(
    real: Real, monkeypatch: pytest.MonkeyPatch
) -> None:
    left = str(script().margin(4))

    report = preconditions_on(
        step_1(real, **{"/spend": changed(real.spend_start, left=left)}), monkeypatch
    )

    assert report.stopped is None, report.lines


NOT_AS_THE_PROOF_WANTS: dict[str, tuple[str, Callable[[Real], Any], str]] = {
    "no-planning-route": (
        "/openapi.json",
        lambda real: changed(
            real.openapi,
            paths={
                path: one
                for path, one in real.openapi["paths"].items()
                if path != script().PLANNING_ROUTE
            },
        ),
        "il Core gira dal codice del branch: lo schema ha /tasks/{task_id}/planning",
    ),
    "no-key": (
        "/diagnostics",
        lambda real: changed(real.diagnostics, providers={"anthropic": "UNAVAILABLE"}),
        "il provider del modello ha una chiave",
    ),
    "no-cap": (
        "/spend",
        lambda real: changed(real.spend_start, cap=None, left=None),
        "il tetto è dichiarato",
    ),
    "too-little-left": (
        "/spend",
        lambda real: changed(real.spend_start, left="17.04"),
        "restano almeno 17.04857600 USD, 4 pianificazioni al caso peggiore",
    ),
}
"""Each answer that stops step 1, and the check that says no to it: the whole sentence of the
check, so that a case stops for its own reason — a check that raised says what it raised instead,
and the case without a key once passed on a stop that was a ``ConfigurationError`` (decision 31)."""


@pytest.mark.parametrize(
    ("path", "answer", "what"),
    list(NOT_AS_THE_PROOF_WANTS.values()),
    ids=list(NOT_AS_THE_PROOF_WANTS),
)
def test_step_1_stops_on_an_answer_that_is_not_what_the_proof_wants(
    real: Real,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    answer: Callable[[Real], Any],
    what: str,
) -> None:
    report = preconditions_on(step_1(real, **{path: answer(real)}), monkeypatch)

    assert report.stopped == (1, f"la prova richiede «{what}», e non è così"), report.lines


# «sì» -------------------------------------------------------------------------------------


def asking(real: Real, **changed_answers: Any) -> dict[str, Any]:
    """What ``sì`` reads: the task while its planning task asks, the questions, the child after."""
    answers = {
        f"/tasks/{real.task}": real.waiting,
        "/approvals": real.approvals,
        f"/tasks/{real.child}": real.child_after_yes,
    }
    return {**answers, **changed_answers}


YES = "uv run ela task approve <id del figlio> --approval <approval-id>"
"""The line of every ``sì`` of the section (asserted above)."""


def test_a_yes_runs_the_line_of_the_guide_with_the_planning_task_and_its_question(
    real: Real, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = script()
    ran: list[str] = []

    def run(line: str) -> subprocess.CompletedProcess[str]:
        ran.append(line)
        return subprocess.CompletedProcess(line, 0, "", "")

    monkeypatch.setattr(module.base, "run", run)
    proof = proof_on(real, asking(real), ["s"])
    (question,) = real.approvals

    walked_on(proof, {2: [block(2, "sì", YES)]}, module.Turn(task_id=real.task))

    assert ran == [f"uv run ela task approve {real.child} --approval {question['id']}"]
    assert proof.report.ok, proof.report.lines
    assert f"    | caso peggiore: {question['worst_case']}" in proof.report.lines


def test_a_no_to_the_question_stops_the_proof_and_says_why(real: Real) -> None:
    module = script()
    proof = proof_on(real, asking(real), ["n"])
    todo = {2: [block(2, "sì", YES)], 3: [block(3, "occhio", "Mai chiesto?")]}

    done = walked_on(proof, todo, module.Turn(task_id=real.task))

    assert done == [2], "no step after the no"
    assert not proof.report.ok
    assert any(
        line.startswith("[2] FERMATO: ") and module.SAID_NO in line for line in proof.report.lines
    )


def test_a_planning_task_without_its_question_stops_the_proof(real: Real) -> None:
    module = script()
    others = [one for one in real.approvals if one["task_id"] != real.child]
    proof = proof_on(real, asking(real, **{"/approvals": others}))

    walked_on(proof, {2: [block(2, "sì", YES)]}, module.Turn(task_id=real.task))

    assert proof.report.failures == 1 and proof.report.stopped is not None
    assert proof.asked == [], "no question to say yes to"


def test_a_planning_task_that_is_not_queued_after_the_yes_fails(
    real: Real, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = script()
    monkeypatch.setattr(
        module.base, "run", lambda line: subprocess.CompletedProcess(line, 0, "", "")
    )
    still = changed(real.child_after_yes, state="WAITING_APPROVAL")
    proof = proof_on(real, asking(real, **{f"/tasks/{real.child}": still}), ["s"])

    walked_on(proof, {2: [block(2, "sì", YES)]}, module.Turn(task_id=real.task))

    assert proof.report.failures == 1


# «piano» ----------------------------------------------------------------------------------


def sent_of(child: Any) -> dict[str, Any]:
    """The catalogue a planning task sent, as the script reads it from its own step."""
    (call,) = child["steps"]
    read: dict[str, Any] = script().catalogue_of(call["arguments"]["instructions"])
    return read


def resent(real: Real, **fields: Any) -> Any:
    """The real planning task, the entry of ``workspace.write_note`` in the catalogue it sent
    changed — renamed, with ``capability``."""
    module = script()
    child = copy.deepcopy(real.planning_child)
    arguments = child["steps"][0]["arguments"]
    before, rest = arguments["instructions"].split(module.CATALOGUE_OPENS, 1)
    listed, after = rest.split(module.CATALOGUE_CLOSES, 1)
    entries = [
        {**entry, **fields} if entry["capability"] == "workspace.write_note" else entry
        for entry in json.loads(listed)
    ]
    arguments["instructions"] = (
        f"{before}{module.CATALOGUE_OPENS}{json.dumps(entries)}{module.CATALOGUE_CLOSES}{after}"
    )
    return child


def planned_on(real: Real, planned: Any = None, child: Any = None) -> Any:
    """``piano`` on step 2, its answers the real ones unless a case changes one."""
    module = script()
    answers = {
        f"/tasks/{real.task}": real.planned if planned is None else planned,
        f"/tasks/{real.child}": real.planning_child if child is None else child,
    }
    proof = proof_on(real, answers)
    walked_on(
        proof, {2: [block(2, "piano", "workspace.write_note")]}, module.Turn(task_id=real.task)
    )
    return proof.report


def test_the_plan_of_the_model_passes_against_the_catalogue_of_the_code(real: Real) -> None:
    report = planned_on(real)

    assert report.failures == 0 and report.ok, report.lines
    assert any(
        "workspace.write_note" in line and line.lstrip().startswith("step 2:")
        for line in report.lines
    ), "the plan is written in the file, step by step"


def test_a_plan_with_a_question_to_the_model_passes(real: Real, code: dict[str, Any]) -> None:
    assert script().plan_failures(real.asking, code, ["model.complete"]) == []


def test_the_catalogue_the_planner_sent_is_the_code_s(real: Real, code: dict[str, Any]) -> None:
    """The positive case of :func:`sent_failures`, on what the real Planner sent."""
    sent = sent_of(real.planning_child)

    assert set(sent) == set(code)
    assert sent["model.complete"]["asks_the_user"] is True
    assert "reasoning" in sent["model.complete"]["task_types"]
    assert script().sent_failures(sent, code) == []


NOT_THE_CATALOGUE_S: dict[str, tuple[Callable[[Real], Any], list[str]]] = {
    "not-queued": (lambda real: changed(real.planned, state="FAILED"), []),
    "written-by-hand": (
        lambda real: changed(real.planned, plan_author={"by": "HAND", "result_id": None}),
        [],
    ),
    "another-model": (
        lambda real: changed(
            real.planned, plan_author={**real.planned["plan_author"], "model": "claude-x"}
        ),
        [],
    ),
    "no-step": (lambda real: changed(real.planned, steps=[]), []),
    "two-capabilities": (
        lambda real: stepped(
            real.planned, 1, required_capabilities=["core.echo", "workspace.write_note"]
        ),
        [],
    ),
    "outside-the-catalogue": (
        lambda real: stepped(real.planned, 1, required_capabilities=["home.lights"]),
        [],
    ),
    "a-condition-of-another-verifier": (
        lambda real: stepped(real.planned, 1, success_conditions=["echo.message_matches"]),
        [],
    ),
    "no-condition": (lambda real: stepped(real.planned, 1, success_conditions=[]), []),
    "another-risk": (lambda real: stepped(real.planned, 1, risk="MEDIUM"), []),
    "asks-when-the-catalogue-does-not": (
        lambda real: stepped(real.planned, 1, requires_authorization=True),
        [],
    ),
    "prefers-a-machine": (
        lambda real: stepped(real.planned, 1, preferred_device_traits=["gpu"]),
        [],
    ),
    "a-task-type-outside-the-table": (
        lambda real: stepped(
            real.asking,
            0,
            arguments={**real.asking["steps"][0]["arguments"], "task_type": "astrology"},
        ),
        [],
    ),
    "without-the-capability-the-step-wants": (lambda real: real.planned, ["browser.read"]),
}


@pytest.mark.parametrize(
    ("task", "wanted"), list(NOT_THE_CATALOGUE_S.values()), ids=list(NOT_THE_CATALOGUE_S)
)
def test_a_plan_that_is_not_the_catalogue_s_fails(
    real: Real, code: dict[str, Any], task: Callable[[Real], Any], wanted: list[str]
) -> None:
    assert script().plan_failures(task(real), code, wanted) != []


def test_a_high_step_fails_even_where_the_catalogue_says_high(
    real: Real, code: dict[str, Any]
) -> None:
    """No HIGH step in the proof's plans (decision L), whatever the catalogue holds."""
    high = code["fs.write"]
    task = stepped(
        real.planned,
        1,
        required_capabilities=["fs.write"],
        success_conditions=high["success_conditions"],
        risk="HIGH",
        requires_authorization=high["asks_the_user"],
    )

    assert script().plan_failures(task, code, []) == ["lo step 2 è HIGH"]


def test_a_catalogue_sent_with_a_wrong_risk_fails_the_plan_that_agrees_with_it(
    real: Real,
) -> None:
    """Question 3 of the review of the summary: the check was circular. A Planner that derived a
    wrong risk would send it and write it in the plan, and a plan read against what was sent
    would pass. Read against the code, both fail."""
    report = planned_on(real, stepped(real.planned, 1, risk="SAFE"), resent(real, risk="SAFE"))

    assert report.failures == 1
    (failed,) = [line for line in report.lines if "FALLITO" in line]
    assert "SAFE" in failed and "LOW" in failed


def test_a_catalogue_sent_that_asks_when_the_code_does_not_fails(real: Real) -> None:
    report = planned_on(
        real,
        stepped(real.planned, 1, requires_authorization=True),
        resent(real, asks_the_user=True),
    )

    assert report.failures == 1


def test_a_catalogue_sent_with_a_capability_the_code_does_not_have_fails(real: Real) -> None:
    report = planned_on(real, child=resent(real, capability="home.lights"))

    assert report.failures == 1


# «chiamata» -------------------------------------------------------------------------------


def called_on(real: Real, results: Any) -> Any:
    module = script()
    proof = proof_on(real, {f"/tasks/{real.child}/results": results})
    turn = module.Turn(task_id=real.task, child_id=real.child)
    walked_on(proof, {2: [block(2, "chiamata", module.MODEL)]}, turn)
    return proof


def test_the_call_of_the_planning_task_passes_and_is_measured(real: Real) -> None:
    proof = called_on(real, real.results)

    assert proof.report.failures == 0 and proof.report.ok, proof.report.lines
    answer = answered_of(real.results)
    assert proof.costs == [Decimal(answer["usage"]["cost"])]
    tokens = answer["usage"]["output_tokens"]
    assert (
        f"    la risposta era un oggetto JSON: sì; token d'uscita: {tokens}" in proof.report.lines
    )


def test_a_call_answered_by_another_model_fails(real: Real) -> None:
    results = copy.deepcopy(real.results)
    answered_of(results)["output"]["model"] = "claude-x"

    proof = called_on(real, results)

    assert proof.report.failures == 1 and proof.costs == []


def reanswered(real: Real, text: str | None = None, status: str | None = None) -> Any:
    """The real results of the planning task, the answer's text or status changed."""
    results = copy.deepcopy(real.results)
    answer = answered_of(results)
    if text is not None:
        answer["output"]["output"] = text
    if status is not None:
        answer["status"] = status
    return results


NOT_ONE_JSON_OBJECT: dict[str, Callable[[Real], Any]] = {
    "text-around-it": lambda real: reanswered(
        real, text=f"Here is the plan: {answered_of(real.results)['output']['output']}"
    ),
    "an-array": lambda real: reanswered(real, text="[1, 2]"),
    "nothing-succeeded": lambda real: reanswered(real, status="FAILED"),
    "no-result": lambda real: [],
}


@pytest.mark.parametrize(
    "results", list(NOT_ONE_JSON_OBJECT.values()), ids=list(NOT_ONE_JSON_OBJECT)
)
def test_anything_else_is_measured_as_not_a_json_object(
    real: Real, results: Callable[[Real], Any]
) -> None:
    assert script().measured(results(real)).json_object is False


# «rifiuto» --------------------------------------------------------------------------------


def refused_on(real: Real, task: Any = None, printed: str | None = None) -> Any:
    """``rifiuto`` on step 5: the task as ``GET /tasks`` answers it, and what the
    ``ela task plan <id>`` before it printed — the real ones, unless a case changes one."""
    module = script()
    proof = proof_on(real, {f"/tasks/{real.refused_task}": real.refused if task is None else task})
    turn = module.Turn(
        task_id=real.refused_task, last=real.refused_output if printed is None else printed
    )
    walked_on(proof, {5: [block(5, "rifiuto", PLANNER_NO_PLAN)]}, turn)
    return proof


def test_no_plan_is_read_with_the_reason_ela_task_plan_printed(real: Real) -> None:
    """Decision 24: ``rifiuto`` looked for ``reason`` in ``GET /tasks/<id>``, which has no such
    field, and could never pass; its test passed on a dictionary written by hand that had it. The
    reason is the one ``ela task plan <id>`` printed, the surface Tommaso reads."""
    assert "reason" not in real.refused, "the premise of the fix: the task has no reason"

    proof = refused_on(real)

    assert proof.report.failures == 0, proof.report.lines
    assert proof.report.ok
    assert f"    le parole del modello: {real.refused['no_plan']}" in proof.report.lines


def test_the_reason_is_the_row_of_ela_task_plan_and_a_dash_is_none(real: Real) -> None:
    module = script()
    reason = module.reason_of(real.refused_output)

    assert reason is not None and PLANNER_NO_PLAN in reason
    assert module.reason_of(real.planned_output) is None, "«reason —» is no reason"
    assert module.reason_of("") is None


NOT_A_NO_PLAN: dict[str, tuple[Callable[[Real], Any], Callable[[Real], str]]] = {
    "not-failed": (
        lambda real: changed(real.refused, state="DENIED"),
        lambda real: real.refused_output,
    ),
    "another-code": (
        lambda real: real.refused,
        lambda real: real.refused_output.replace(PLANNER_NO_PLAN, "planner.malformed"),
    ),
    "no-reason": (lambda real: real.refused, lambda real: real.run_output),
    "a-plan": (
        lambda real: changed(real.refused, plan_id=real.planned["plan_id"]),
        lambda real: real.refused_output,
    ),
    "no-words": (
        lambda real: changed(real.refused, no_plan=None),
        lambda real: real.refused_output,
    ),
}


@pytest.mark.parametrize(("task", "printed"), list(NOT_A_NO_PLAN.values()), ids=list(NOT_A_NO_PLAN))
def test_anything_but_a_no_plan_with_its_reason_and_its_words_fails(
    real: Real, task: Callable[[Real], Any], printed: Callable[[Real], str]
) -> None:
    proof = refused_on(real, task(real), printed(real))

    assert proof.report.failures == 1, proof.report.lines


def test_a_valid_plan_where_none_was_asked_is_skipped_and_shown_to_the_eye(real: Real) -> None:
    """Decision 16: what the model did not give is not ELA's error; the plan goes in the file."""
    module = script()
    proof = proof_on(real, {f"/tasks/{real.task}": real.planned}, ["s"])
    todo = {
        5: [block(5, "rifiuto", PLANNER_NO_PLAN), block(5, "occhio", "La ragione dice perché?")]
    }

    walked_on(proof, todo, module.Turn(task_id=real.task, last=real.planned_output))

    assert proof.report.skipped_steps == [5]
    assert proof.report.failures == 0, "skipped, never failed"
    assert any("workspace.write_note" in line for line in proof.report.lines), "the plan is written"
    assert [question for question in proof.asked if "ragione" in question] == [], (
        "the eye on the reason is not asked of a plan"
    )


# «spesa» ----------------------------------------------------------------------------------


def spent_on(real: Real, spend: Any, lines: list[str]) -> Any:
    module = script()
    proof = proof_on(real, {"/spend": spend})
    proof.costs.extend(costs_of(real))
    walked_on(proof, {6: [block(6, "spesa", "\n".join(lines))]}, module.Turn())
    return proof.report


def test_the_spend_grown_by_the_costs_of_the_calls_with_nothing_reserved_passes(
    real: Real,
) -> None:
    report = spent_on(real, real.spend_end, list(script().LEDGER_WORDS))

    assert report.failures == 0 and report.ok, report.lines


SPEND_NOT_AS_SAID: dict[str, Callable[[Real], Any]] = {
    "speso cresciuto dei costi delle chiamate": lambda real: changed(
        real.spend_end, spent=str(Decimal(real.spend_end["spent"]) + Decimal("0.5"))
    ),
    "prenotato com'era al passo 1": lambda real: changed(
        real.spend_end, reserved="4.262144", open=1
    ),
}


@pytest.mark.parametrize(
    ("line", "spend"), list(SPEND_NOT_AS_SAID.items()), ids=["spent", "reserved"]
)
def test_each_word_of_spesa_fails_when_it_is_not(
    real: Real, line: str, spend: Callable[[Real], Any]
) -> None:
    assert spent_on(real, spend(real), [line]).failures == 1


def test_a_word_outside_the_vocabulary_of_spesa_is_the_guides_error(real: Real) -> None:
    module = script()
    ledger = module.spending.Ledger.of(real.spend_end)

    with pytest.raises(ValueError, match="vocabulary of spesa"):
        module.ledger_failures(["speso dimezzato"], ledger, ledger, [])
