"""Section 24 of the guide and ``scripts/prova_m14_2.py`` say the same thing (M14.2, «La prova a
mano»).

The guide is the source of truth, and the script reads it with the reader of M6.3c: this file reads
the section with the script's own functions and asserts that every marker is a kind the script knows
and a step of the section, that every placeholder is one it fills, and that every line of its kinds
is in their vocabulary. **Each comparison of the script has its negative case**, on constructed
answers: a check that only ever passes proves nothing. That the question the section expects is the
one ELA asks — the worst case of a planning, as ``ela task plan`` prints it — is proved in
``tests/api/test_planning.py`` and ``tests/cli/test_planning.py``, on an ELA whose model answers
through the real adapter and no socket.
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import subprocess
import sys
from datetime import datetime
from decimal import Decimal
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from ela.executive.planner import PLANNER_NO_PLAN, catalogue, instructions
from ela.permissions.capabilities import DEFAULT_NOTES_SCOPE, production_catalogue
from ela.routing import DEFAULT_ROUTES
from tests.api.test_planning import WORST
from tests.executive.planning import Planned

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prova_m14_2.py"
PLACEHOLDER = re.compile(r"<[^>\s][^>]*>")
TASK = "7c1e2d3f-0a4b-4c5d-8e6f-000000000142"
CHILD = "7c1e2d3f-0a4b-4c5d-8e6f-000000000143"
RESULT = "7c1e2d3f-0a4b-4c5d-8e6f-000000000144"


@cache
def script() -> ModuleType:
    """The script, loaded by path: ``scripts/`` is not a package."""
    spec = importlib.util.spec_from_file_location("prova_m14_2", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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


# ----------------------------------------------------------------------------------------
# The comparisons of its own, each with its negative case
# ----------------------------------------------------------------------------------------


def test_enough_left_for_the_calls_passes() -> None:
    assert script().enough_left("17.048576", Decimal("17.048576")) is None


@pytest.mark.parametrize("left", ["17.04", None], ids=["too-little", "no-cap"])
def test_too_little_left_or_no_cap_stops(left: str | None) -> None:
    assert script().enough_left(left, Decimal("17.048576")) is not None


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


@pytest.fixture(scope="module")
def offered(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """The catalogue as the Planner writes it in its instructions, read back by the script."""
    world = Planned(Path(tmp_path_factory.mktemp("prova")) / "workspace")
    entries = catalogue(capabilities=world.registry, tools=world.tools, verifiers=world.verifiers)
    written = instructions(entries, task_types=tuple(sorted(DEFAULT_ROUTES)))
    read: dict[str, Any] = script().catalogue_of(written)
    return read


def test_the_catalogue_is_read_from_the_instructions_the_planner_sent(
    offered: dict[str, Any],
) -> None:
    assert set(offered) == {"core.echo", "workspace.write_note", "model.complete"}
    assert offered["model.complete"]["asks_the_user"] is True
    assert "reasoning" in offered["model.complete"]["task_types"]


def test_instructions_without_a_catalogue_are_refused() -> None:
    with pytest.raises(ValueError, match="no catalogue"):
        script().catalogue_of("You are the Planner.")


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


def test_the_catalogue_the_planner_sends_in_the_suite_is_the_code_s(
    offered: dict[str, Any], code: dict[str, Any]
) -> None:
    """The positive case of :func:`sent_failures`, on what the real Planner writes."""
    assert script().sent_failures(offered, code) == []


def step(**changed: Any) -> dict[str, Any]:
    base = {
        "required_capabilities": ["workspace.write_note"],
        "success_conditions": ["note.exists"],
        "risk": "LOW",
        "requires_authorization": False,
        "preferred_device_traits": [],
        "arguments": {"path": "workspace/notes/a.md", "body": "b"},
        "goal": "write it",
    }
    return {**base, **changed}


def planned(*steps: dict[str, Any], **changed: Any) -> dict[str, Any]:
    task = {
        "state": "QUEUED",
        "plan_author": {"by": "MODEL", "result_id": RESULT, "model": "claude-opus-5-5"},
        "steps": list(steps) or [step()],
    }
    return {**task, **changed}


def test_a_plan_inside_the_catalogue_passes(code: dict[str, Any]) -> None:
    asked = step(
        required_capabilities=["model.complete"],
        success_conditions=["model.answered"],
        risk="MEDIUM",
        requires_authorization=True,
        arguments={"input": "?", "task_type": "reasoning"},
    )

    assert script().plan_failures(planned(step(), asked), code, ["model.complete"]) == []


@pytest.mark.parametrize(
    ("task", "wanted"),
    [
        (planned(state="FAILED"), []),
        (planned(plan_author={"by": "HAND", "result_id": None, "model": None}), []),
        (planned(plan_author={"by": "MODEL", "result_id": RESULT, "model": "claude-x"}), []),
        (planned(steps=[]), []),
        (planned(step(required_capabilities=["core.echo", "workspace.write_note"])), []),
        (planned(step(required_capabilities=["home.lights"])), []),
        (planned(step(success_conditions=["echo.message_matches"])), []),
        (planned(step(success_conditions=[])), []),
        (planned(step(risk="MEDIUM")), []),
        (planned(step(requires_authorization=True)), []),
        (planned(step(preferred_device_traits=["gpu"])), []),
        (
            planned(
                step(
                    required_capabilities=["model.complete"],
                    success_conditions=["model.answered"],
                    risk="MEDIUM",
                    requires_authorization=True,
                    arguments={"input": "?", "task_type": "astrology"},
                )
            ),
            [],
        ),
        (planned(), ["browser.read"]),
    ],
    ids=[
        "not-queued",
        "written-by-hand",
        "another-model",
        "no-step",
        "two-capabilities",
        "outside-the-catalogue",
        "a-condition-of-another-verifier",
        "no-condition",
        "another-risk",
        "asks-when-the-catalogue-does-not",
        "prefers-a-machine",
        "a-task-type-outside-the-table",
        "without-the-capability-the-step-wants",
    ],
)
def test_a_plan_that_is_not_the_catalogue_s_fails(
    code: dict[str, Any], task: dict[str, Any], wanted: list[str]
) -> None:
    assert script().plan_failures(task, code, wanted) != []


def test_a_high_step_fails_even_where_the_catalogue_says_high() -> None:
    """No HIGH step in the proof's plans (decision L), whatever the catalogue holds."""
    catalogue_with_a_high = {
        "fs.write": {"risk": "HIGH", "asks_the_user": True, "success_conditions": ["fs.exists"]}
    }
    task = planned(
        step(
            required_capabilities=["fs.write"],
            success_conditions=["fs.exists"],
            risk="HIGH",
            requires_authorization=True,
        )
    )

    assert script().plan_failures(task, catalogue_with_a_high, []) == ["lo step 1 è HIGH"]


def answered(text: str, tokens: int = 612, status: str = "SUCCEEDED") -> dict[str, Any]:
    return {"status": status, "output": {"output": text}, "usage": {"output_tokens": tokens}}


def test_an_answer_that_is_one_json_object_is_measured_with_its_tokens() -> None:
    measure = script().measured([{"status": "STARTED"}, answered('{"plan": {"steps": []}}')])

    assert measure == script().Measure(True, 612)


@pytest.mark.parametrize(
    "results",
    [
        [answered('Here is the plan: {"plan": {}}')],
        [answered("[1, 2]")],
        [answered('{"plan": {}}', status="FAILED")],
        [],
    ],
    ids=["text-around-it", "an-array", "nothing-succeeded", "no-result"],
)
def test_anything_else_is_measured_as_not_a_json_object(results: list[dict[str, Any]]) -> None:
    assert script().measured(results).json_object is False


def refused(**changed: Any) -> dict[str, Any]:
    task = {
        "state": "FAILED",
        "reason": "fail: PLANNING -> FAILED (planner.no_plan: the model wrote no plan)",
        "plan_id": None,
        "no_plan": "no capability switches a light off",
    }
    return {**task, **changed}


def test_a_no_plan_with_its_reason_passes() -> None:
    assert script().refusal_failures(refused(), PLANNER_NO_PLAN) == []


@pytest.mark.parametrize(
    "task",
    [
        refused(state="DENIED"),
        refused(reason="fail: PLANNING -> FAILED (planner.malformed: …)"),
        refused(plan_id="7c1e2d3f-0a4b-4c5d-8e6f-000000000145"),
        refused(no_plan=None),
    ],
    ids=["not-failed", "another-code", "a-plan", "no-words"],
)
def test_anything_but_a_no_plan_with_its_words_fails(task: dict[str, Any]) -> None:
    assert script().refusal_failures(task, PLANNER_NO_PLAN) != []


def ledger(spent: str = "1", reserved: str = "0") -> Any:
    return script().spending.Ledger.of(
        {"cap": "30", "spent": spent, "reserved": reserved, "open": 0}
    )


def test_the_spend_grown_by_the_costs_with_nothing_reserved_passes() -> None:
    module = script()
    costs = [Decimal("0.031"), Decimal("0.029")]

    assert module.ledger_failures(module.LEDGER_WORDS, ledger(), ledger(spent="1.06"), costs) == []


@pytest.mark.parametrize(
    ("line", "after"),
    [
        ("speso cresciuto dei costi delle chiamate", ledger(spent="1.5")),
        ("prenotato com'era al passo 1", ledger(spent="1.06", reserved="4.262144")),
    ],
)
def test_each_word_of_spesa_fails_when_it_is_not(line: str, after: Any) -> None:
    costs = [Decimal("0.031"), Decimal("0.029")]

    assert len(script().ledger_failures([line], ledger(), after, costs)) == 1


def test_a_word_outside_the_vocabulary_of_spesa_is_the_guides_error() -> None:
    with pytest.raises(ValueError, match="vocabulary of spesa"):
        script().ledger_failures(["speso dimezzato"], ledger(), ledger(), [])


# ----------------------------------------------------------------------------------------
# The proof as it walks: a no stops it, a plan where none was asked is SKIPPED, step 1 stops
# ----------------------------------------------------------------------------------------


class Ela:
    """An ELA mid-proof: a task, its planning task waiting for a yes, and what the API says."""

    def __init__(
        self,
        task: dict[str, Any],
        child_state: str = "WAITING_APPROVAL",
        child_steps: list[dict[str, Any]] | None = None,
    ) -> None:
        self.task = task
        self.child_state = child_state
        self.child_steps = child_steps or []

    def get(self, path: str) -> Any:
        if path == "/approvals":
            return [{"id": "q-1", "task_id": CHILD, "prompt": "la domanda", "worst_case": WORST}]
        if path == f"/tasks/{CHILD}":
            return {"id": CHILD, "state": self.child_state, "steps": self.child_steps}
        if path == f"/tasks/{TASK}":
            return {"id": TASK, "planning_task_id": CHILD, **self.task}
        raise AssertionError(path)

    def close(self) -> None:
        return None


def a_proof(ela: Ela, answers: list[str]) -> Any:
    module = script()
    asked: list[str] = []

    def ask(question: str) -> str:
        asked.append(question)
        return answers.pop(0) if answers else "s"

    proof = module.Proof(
        api=ela,
        report=module.base.Report(io.StringIO()),
        ask=ask,
        note="prova-m14.2-20261008-101500.md",
        start=ledger(),
    )
    proof.asked = asked
    return proof


def walked(proof: Any, todo: dict[int, list[Any]], task_id: str = TASK) -> list[int]:
    module = script()
    done: list[int] = []

    def one(number: int, its: list[Any]) -> None:
        done.append(number)
        module.a_step(number, its, proof, module.Turn(task_id=task_id))

    module.base.walk(proof.report, todo, one)
    proof.report.verdict()
    return done


def test_a_no_to_the_question_stops_the_proof_and_says_why() -> None:
    module = script()
    proof = a_proof(Ela({"state": "PLANNING"}), ["n"])
    todo = {
        2: [module.base.Block(2, "sì", "uv run ela task approve <id del figlio> --approval x")],
        3: [module.base.Block(3, "occhio", "Mai chiesto?")],
    }

    done = walked(proof, todo)

    assert done == [2], "no step after the no"
    assert not proof.report.ok
    assert any(
        line.startswith("[2] FERMATO: ") and module.SAID_NO in line for line in proof.report.lines
    )


def test_a_yes_runs_the_line_of_the_guide_with_the_planning_task_and_its_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = script()
    ran: list[str] = []

    def run(line: str) -> subprocess.CompletedProcess[str]:
        ran.append(line)
        return subprocess.CompletedProcess(line, 0, "", "")

    monkeypatch.setattr(module.base, "run", run)
    proof = a_proof(Ela({"state": "PLANNING"}, child_state="QUEUED"), ["s"])
    block = module.base.Block(
        2, "sì", "uv run ela task approve <id del figlio> --approval <approval-id>"
    )

    walked(proof, {2: [block]})

    assert ran == [f"uv run ela task approve {CHILD} --approval q-1"]
    assert proof.report.ok
    assert any("la domanda" in line for line in proof.report.lines)


def test_a_valid_plan_where_none_was_asked_is_skipped_and_shown_to_the_eye() -> None:
    """Decision 16: what the model did not give is not ELA's error; the plan goes in the file."""
    module = script()
    proof = a_proof(Ela({"state": "QUEUED", "plan_id": "p", "steps": [step()]}), ["s"])
    todo = {
        5: [
            module.base.Block(5, "rifiuto", PLANNER_NO_PLAN),
            module.base.Block(5, "occhio", "La ragione dice perché?"),
        ]
    }

    walked(proof, todo)

    assert proof.report.skipped_steps == [5]
    assert proof.report.failures == 0, "skipped, never failed"
    assert any("workspace.write_note" in line for line in proof.report.lines), "the plan is written"
    assert [question for question in proof.asked if "ragione" in question] == [], (
        "the eye on the reason is not asked of a plan"
    )


def test_a_no_plan_prints_the_words_of_the_model() -> None:
    module = script()
    proof = a_proof(Ela(refused()), [])

    walked(proof, {5: [module.base.Block(5, "rifiuto", PLANNER_NO_PLAN)]})

    assert proof.report.ok
    assert any("no capability switches a light off" in line for line in proof.report.lines)


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


def test_every_precondition_present_lets_the_proof_go_on() -> None:
    module = script()
    report = module.base.Report(io.StringIO())

    assert module.stopping(report, [("ELA risponde", lambda: True)]) is True
    assert report.stopped is None and report.passes == {1: 1}


# ----------------------------------------------------------------------------------------
# «piano» reads the catalogue of the code, and the one the Planner sent is checked against it
# ----------------------------------------------------------------------------------------


def sent(**changed: Any) -> list[dict[str, Any]]:
    """The planning task's step, carrying the catalogue the Planner sent: one entry, the note."""
    module = script()
    entry = {
        "capability": "workspace.write_note",
        "risk": "LOW",
        "asks_the_user": False,
        "success_conditions": ["note.content_matches", "note.exists"],
        **changed,
    }
    written = (
        f"You are the Planner.\n{module.CATALOGUE_OPENS}{json.dumps([entry])}"
        f"{module.CATALOGUE_CLOSES} (JSON Schema):\n{{}}\n"
    )
    return [{"arguments": {"instructions": written}}]


def planned_against(catalogue: list[dict[str, Any]], *steps: dict[str, Any]) -> Any:
    module = script()
    proof = a_proof(Ela(planned(*steps), child_steps=catalogue), [])
    walked(proof, {2: [module.base.Block(2, "piano", "workspace.write_note")]})
    return proof.report


def test_a_catalogue_sent_with_a_wrong_risk_fails_the_plan_that_agrees_with_it() -> None:
    """Question 3 of the review of the summary: the check was circular. A Planner that derived a
    wrong risk would send it and write it in the plan, and a plan read against what was sent
    would pass. Read against the code, both fail."""
    report = planned_against(sent(risk="SAFE"), step(risk="SAFE"))

    assert report.failures == 1
    (failed,) = [line for line in report.lines if "FALLITO" in line]
    assert "SAFE" in failed and "LOW" in failed


def test_a_catalogue_sent_that_asks_when_the_code_does_not_fails() -> None:
    report = planned_against(sent(asks_the_user=True), step(requires_authorization=True))

    assert report.failures == 1


def test_a_catalogue_sent_with_a_capability_the_code_does_not_have_fails() -> None:
    report = planned_against(sent(capability="home.lights"), step())

    assert report.failures == 1


def test_a_catalogue_sent_as_the_code_says_and_a_plan_inside_it_pass() -> None:
    report = planned_against(sent(), step())

    assert report.failures == 0 and report.ok
