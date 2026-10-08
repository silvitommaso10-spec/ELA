"""Section 26 of the guide and ``scripts/prova_m14_3.py`` say the same thing (M14.3, «La prova a
mano»; M14.6, decision 27).

The guide is the source of truth, and the script reads it with the reader of M6.3c: this file reads
the section with the script's own functions and asserts that every marker is a kind the script knows
and a step of the section, that every placeholder is one it fills, and that every line of its kinds
is in their vocabulary. **Each comparison of the script has its negative case**: a check that only
ever passes proves nothing.

**Every kind that reads the API is fed the answers of the real routes**, recorded once by
``tests/docs/real_guided.py`` on an ELA whose sessions run a script instead of Claude Code and
whose gateway answers as Anthropic streams, with the output of the command line next to them — the
form of ``tests/docs/test_prova_m14_2.py`` (decision 25 of the review of its proof). **A negative
case starts from a real answer and changes it**; nothing the API says is written here.
"""

from __future__ import annotations

import copy
import importlib.util
import io
import json
import re
import subprocess
import sys
from decimal import Decimal
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from ela.cli.errors import UNREACHABLE
from ela.providers.anthropic.models import HAIKU_5_5, MODELS
from ela.providers.anthropic.pricing import worst_cost
from ela.tools.guided import GUIDED_MAX_TOKENS
from tests.composition.support import (  # noqa: F401 — re-exported as a fixture
    _only_the_declared_environment,
)
from tests.docs.real_guided import Real, Recorded, Session, answers_of, record

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prova_m14_3.py"
PLACEHOLDER = re.compile(r"<[^>\s][^>]*>")

SIBLINGS = ("prova_m6_3c", "prova_m14_1", "prova_m14_2")
"""The scripts ``prova_m14_3`` imports, imported anew for it as in ``test_prova_m14_2.py``
(decision 31 of the review of the proof of M14.2): one world, never two copies of a sibling."""


@cache
def script() -> ModuleType:
    found = {name: sys.modules.pop(name, None) for name in SIBLINGS}
    try:
        spec = importlib.util.spec_from_file_location("prova_m14_3", SCRIPT)
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


def guide() -> str:
    return str(script().GUIDE.read_text(encoding="utf-8"))


def section() -> str:
    return str(script().base.section(guide(), script().HEADING))


def flat() -> str:
    return " ".join(section().split())


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


def test_the_script_and_its_siblings_are_one_world() -> None:
    module = script()

    assert module.spending.base is module.base
    assert module.planning.base is module.base
    assert module.planning.spending is module.spending


# ----------------------------------------------------------------------------------------
# The section and the script
# ----------------------------------------------------------------------------------------


def test_every_marker_is_a_kind_the_script_knows_and_belongs_to_a_step_of_the_section() -> None:
    headings = {int(number) for number in re.findall(r"^### (\d+)\. ", section(), re.MULTILINE)}
    found = marked()

    assert found, "section 26 has no marked block: the script would do nothing"
    assert set(found) <= headings
    assert set(found) == set(range(2, 8)), "steps 2 to 7; step 1 is the script's own"
    assert all(block.kind in script().KINDS for blocks in found.values() for block in blocks)
    every_marker = re.findall(r"<!-- prova: (\d+)\.(\w+) -->", section())
    assert len(every_marker) == sum(len(blocks) for blocks in found.values()), (
        "a marker the reader did not take: it is not right above a fenced block"
    )


def test_it_comes_after_section_25_and_before_where_to_look() -> None:
    text = guide()

    assert text.index("## 25. ") < text.index(script().HEADING) < text.index("## Dove guardare")


def test_every_kind_of_the_script_is_used_by_the_section() -> None:
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


def test_five_sessions_are_created_planned_with_a_file_asked_a_yes_and_read() -> None:
    """One task per session, each with its plan from ``docs/examples/``, the session's yes, and
    the ``sessione`` that reads its cost — five of each: what ``spesa`` adds up is every one."""
    module = script()
    created = [line for _, line in lines_of("comando") if module.CREATE in f" {line} "]
    yeses = [line for _, line in lines_of("sì") if module.CHILD not in line]

    assert len(created) == 5 and all(line.endswith(" --json") for line in created), created
    assert len(module.plans_of(marked())) == 5
    assert yeses == [f"uv run ela task approve {module.ID} --approval {module.APPROVAL_ID}"] * 5
    assert len(lines_of("sessione")) == 5


def test_every_run_in_the_background_ends_with_a_fine_in_its_own_step() -> None:
    for number, blocks in marked().items():
        kinds = [block.kind for block in blocks]
        for index, kind in enumerate(kinds):
            if kind == "sfondo":
                assert "fine" in kinds[index:], number
            if kind in ("aspetta", "fine"):
                assert "sfondo" in kinds[:index], number
        assert kinds.count("sfondo") == kinds.count("fine"), number


def test_every_answer_to_a_gesture_comes_after_the_wait_that_names_the_child() -> None:
    for number, blocks in marked().items():
        for index, block in enumerate(blocks):
            if block.kind in ("sì", "no") and script().CHILD in block.lines[0]:
                assert any(one.kind == "aspetta" for one in blocks[:index]), number


def test_every_plan_the_section_sends_is_one_session_on_the_sites_of_the_proof() -> None:
    module = script()
    for plan in module.plans_of(marked()):
        arguments = module.arguments_of(plan)
        assert set(arguments["sites"]) <= set(module.SITES), plan.name
        assert arguments["max_cost_usd"] == "0.60", plan.name


def test_a_plan_that_is_not_one_session_is_refused(tmp_path: Path) -> None:
    other = tmp_path / "other.json"
    other.write_text(
        json.dumps({"steps": [{"required_capabilities": ["browser.read"], "arguments": {}}]})
    )

    with pytest.raises(ValueError, match="is not the plan of one session"):
        script().arguments_of(other)


def test_a_block_with_no_file_names_no_session() -> None:
    module = script()

    assert module.plans_of({2: [module.base.Block(2, "comando", "uv run ela task run <id>")]}) == []


def test_every_line_of_the_scripts_kinds_is_in_its_vocabulary() -> None:
    module = script()

    for _, line in lines_of("figli"):
        module.wanted(line)
    for _, line in lines_of("aspetta"):
        module.waited(line)
    assert {line for _, line in lines_of("sessione")} == {"SUCCEEDED", "FAILED guided.stopped"}
    assert [line for _, line in lines_of("fascia")] == [module.STEP_2]
    assert {line for _, line in lines_of("spesa")} == set(module.planning.LEDGER_WORDS)


@pytest.mark.parametrize(
    "line",
    ["browser.read", "browser.guided COMPLETED", "browser.read DONE", "browser.read DENIED X"],
)
def test_a_line_of_figli_outside_its_vocabulary_is_the_guides_error(line: str) -> None:
    with pytest.raises(ValueError, match="vocabulary of figli"):
        script().wanted(line)


@pytest.mark.parametrize("line", ["browser.act COMPLETED", "browser.guided WAITING_APPROVAL", "x"])
def test_a_line_of_aspetta_outside_its_vocabulary_is_the_guides_error(line: str) -> None:
    with pytest.raises(ValueError, match="vocabulary of aspetta"):
        script().waited(line)


def test_the_file_is_in_downloads_with_the_name_of_the_milestone() -> None:
    out = script().default_out()

    assert out.parent == Path.home() / "Downloads"
    assert out.name.startswith("prova-m14.3-")


def test_the_sites_of_the_proof_are_the_line_the_section_writes() -> None:
    module = script()

    assert f"ELA_BROWSER_SITES={json.dumps(list(module.SITES))}" in section()
    assert module.sites_missing(list(module.SITES)) == []
    assert module.sites_missing(["example.com", "httpbin.org"]) == ["www.youtube.com"]


# ----------------------------------------------------------------------------------------
# The margin, the route and the binary: the code's, never a number of the script
# ----------------------------------------------------------------------------------------


def test_the_margin_is_five_sessions_at_their_most_and_the_section_writes_it() -> None:
    module = script()
    one_call = worst_cost(MODELS[HAIKU_5_5], output_tokens=GUIDED_MAX_TOKENS)

    assert module.margin(module.plans_of(marked())) == Decimal("3.00")
    assert one_call == Decimal("0.516384")
    assert "5 × 0,60 = 3,00 $" in flat()
    assert "**0,516384 $**" in flat()


def test_a_session_whose_most_is_below_one_call_is_not_reserved() -> None:
    """The gate's own function says no: the margin of a plan the tool would refuse is no margin."""
    module = script()
    (plan, *_) = module.plans_of(marked())
    arguments = {**module.arguments_of(plan), "max_cost_usd": "0.10"}

    with pytest.raises(ValueError, match="guided.cap_below_one_call"):
        module.reserved(arguments)


def test_the_route_of_a_session_is_haiku_5_5_unless_the_env_says_otherwise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = script()

    assert module.route_model() == HAIKU_5_5
    monkeypatch.setenv(
        "ELA_MODEL_ROUTES", json.dumps({"browsing": {"providers": ["anthropic"], "profile": "x"}})
    )
    assert module.route_model() is None
    monkeypatch.setenv(
        "ELA_MODEL_ROUTES",
        json.dumps({"browsing": {"providers": ["anthropic"], "profile": "quality"}}),
    )
    assert module.route_model() not in (None, HAIKU_5_5)


def test_the_binary_is_ready_only_when_it_can_be_launched(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from ela.infrastructure.machine import agent

    module = script()
    binary = tmp_path / "claude"
    monkeypatch.setattr(agent, "bundled_binary", lambda: binary)
    assert not module.binary_ready()
    binary.write_text("")
    binary.chmod(0o600)
    assert not module.binary_ready()
    binary.chmod(0o700)
    assert module.binary_ready()


# ----------------------------------------------------------------------------------------
# The world, recorded
# ----------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real(tmp_path_factory: pytest.TempPathFactory) -> Real:
    return record(tmp_path_factory)


def sessions_of(real: Real) -> dict[str, Session]:
    return {
        "youtube": real.youtube,
        "outside": real.outside,
        "refused": real.refused,
        "accepted": real.accepted,
        "stopped": real.stopped,
    }


def proof_on(
    real: Real, answers: dict[str, Any], said: list[str] | None = None, start: Any = None
) -> Any:
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
        start=module.spending.Ledger.of(real.spend_start if start is None else start),
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


def changed(answer: Any, **fields: Any) -> Any:
    copied = copy.deepcopy(answer)
    copied.update(fields)
    return copied


def ended_of(session: Session) -> Any:
    (found,) = [one for one in session.results if one["status"] != "STARTED"]
    return found


def with_ended(session: Session, **fields: Any) -> list[Any]:
    """The session's real results, with the result that closed it changed."""
    results = copy.deepcopy(session.results)
    for one in results:
        if one["status"] != "STARTED":
            one.update(fields)
    return results


def with_output(session: Session, **fields: Any) -> list[Any]:
    results = copy.deepcopy(session.results)
    for one in results:
        if one["status"] != "STARTED":
            one["output"].update(fields)
    return results


class Running:
    """``ela task run`` in the background, as ``subprocess.Popen`` answers for it: still running
    (``code`` ``None``), or over, with what it printed."""

    def __init__(self, printed: str = "", code: int | None = 0) -> None:
        self.printed = printed
        self.returncode = code

    def poll(self) -> int | None:
        return self.returncode

    def communicate(self) -> tuple[str, None]:
        return self.printed, None


def test_the_route_of_the_gateway_is_in_the_schema_the_script_reads(real: Real) -> None:
    assert script().SESSION_ROUTE in real.openapi["paths"]


def test_the_children_are_found_where_the_room_puts_them(real: Real) -> None:
    for name, session in sessions_of(real).items():
        (step,) = session.detail["steps"]
        looks = ended_of(session)["output"]["looks"]
        ids = script().gesture_ids(session.task, step["id"], looks)
        assert set(ids) == set(session.children) | set(session.missing), name
        assert session.children, name


# Step 1 -----------------------------------------------------------------------------------


def step_1(real: Real, **changed_answers: Any) -> dict[str, Any]:
    answers = {
        "/health": real.health,
        "/openapi.json": real.openapi,
        "/diagnostics": real.diagnostics,
        "/spend": real.spend_start,
    }
    return {**answers, **changed_answers}


def preconditions_on(
    answers: dict[str, Any], monkeypatch: pytest.MonkeyPatch, *, ready: bool = True
) -> Any:
    """Step 1 with its API the recorded one; the commit, the migration and the binary as the Mac of
    the proof has them — they are not the API's, and have their own cases."""
    module = script()
    monkeypatch.setattr(module.base, "Api", lambda: Recorded(answers))
    monkeypatch.setattr(module.planning, "on_origin", lambda: None)
    monkeypatch.setattr(module.planning, "migrated", lambda: True)
    monkeypatch.setattr(module, "binary_ready", lambda: ready)
    monkeypatch.setenv("ELA_BROWSER_SITES", json.dumps(list(module.SITES)))
    report = module.base.Report(io.StringIO())
    module.preconditions(report, module.plans_of(marked()))
    return report


def test_step_1_goes_on_with_what_the_real_routes_answer(
    real: Real, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = preconditions_on(step_1(real), monkeypatch)

    assert report.stopped is None, report.lines
    assert report.passes == {1: 11}


def test_exactly_the_margin_left_is_enough(real: Real, monkeypatch: pytest.MonkeyPatch) -> None:
    report = preconditions_on(
        step_1(real, **{"/spend": changed(real.spend_start, left="3.00")}), monkeypatch
    )

    assert report.stopped is None, report.lines


NOT_AS_THE_PROOF_WANTS: dict[str, tuple[str, Any, str]] = {
    "no-guided-capability": (
        "/diagnostics",
        lambda real: changed(
            real.diagnostics,
            capabilities=[
                one for one in real.diagnostics["capabilities"] if one != "browser.guided"
            ],
        ),
        "il Core gira dal codice del branch: browser.guided è nel catalogo di /diagnostics",
    ),
    "no-gateway-route": (
        "/openapi.json",
        lambda real: changed(
            real.openapi,
            paths={
                path: one
                for path, one in real.openapi["paths"].items()
                if path != script().SESSION_ROUTE
            },
        ),
        "lo schema dell'API ha /sessions/{session}/v1/messages",
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
        lambda real: changed(real.spend_start, left="2.99"),
        "restano almeno 3.00 USD, 5 sessioni al loro costo massimo",
    ),
}


@pytest.mark.parametrize(
    ("path", "answer", "what"),
    list(NOT_AS_THE_PROOF_WANTS.values()),
    ids=list(NOT_AS_THE_PROOF_WANTS),
)
def test_step_1_stops_on_an_answer_that_is_not_what_the_proof_wants(
    real: Real, monkeypatch: pytest.MonkeyPatch, path: str, answer: Any, what: str
) -> None:
    report = preconditions_on(step_1(real, **{path: answer(real)}), monkeypatch)

    assert report.stopped == (1, f"la prova richiede «{what}», e non è così"), report.lines


def test_step_1_stops_without_the_binary(real: Real, monkeypatch: pytest.MonkeyPatch) -> None:
    report = preconditions_on(step_1(real), monkeypatch, ready=False)

    assert report.stopped is not None and "il binario di Claude Code" in report.stopped[1]


def test_step_1_stops_when_a_site_of_the_proof_is_not_declared(
    real: Real, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = script()
    monkeypatch.setattr(module.base, "Api", lambda: Recorded(step_1(real)))
    monkeypatch.setattr(module.planning, "on_origin", lambda: None)
    monkeypatch.setattr(module.planning, "migrated", lambda: True)
    monkeypatch.setattr(module, "binary_ready", lambda: True)
    monkeypatch.setenv("ELA_BROWSER_SITES", json.dumps(["example.com", "httpbin.org"]))
    report = module.base.Report(io.StringIO())

    assert not module.preconditions(report, module.plans_of(marked()))
    assert report.stopped is not None and "sono fra i siti dichiarati" in report.stopped[1]


def test_step_1_stops_when_the_route_goes_elsewhere(
    real: Real, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(script(), "route_model", lambda: "claude-sonnet-5-5")

    report = preconditions_on(step_1(real), monkeypatch)

    assert report.stopped is not None and "la rotta di una sessione" in report.stopped[1]


def test_step_1_stops_when_the_margin_cannot_be_computed(monkeypatch: pytest.MonkeyPatch) -> None:
    module = script()

    def refused(plans: Any) -> Decimal:
        raise ValueError("the gate would reserve nothing")

    monkeypatch.setattr(module, "margin", refused)
    report = module.base.Report(io.StringIO())

    assert not module.preconditions(report, [])
    assert report.stopped is not None and "il margine" in report.stopped[1]


# «atteso» and «fine»: what the command line printed -----------------------------------


def test_the_question_it_expects_is_the_one_ela_approvals_prints(real: Real) -> None:
    """Step 2's ``atteso`` after ``ela approvals``: every fact of the question, in its order."""
    module = script()
    (wanted,) = [
        block.lines
        for block in marked()[2]
        if block.kind == "atteso" and block.lines[0].startswith("capability")
    ]

    assert module.base.missing(wanted, real.approvals_output) == []
    assert module.base.missing(wanted, real.approvals_output.replace("0.6 USD", "0.5 USD"))


def test_every_outcome_it_expects_is_one_the_runs_print(real: Real) -> None:
    module = script()
    printed = {
        "waiting": real.youtube.waiting_output,
        "completed": real.youtube.run_output,
        "refused": real.refused.run_output,
        "accepted": real.accepted.answer_output,
        "cancelled": real.stopped.run_output,
    }
    for line in ("outcome waiting_approval",):
        assert module.base.missing([line], printed["waiting"]) == []
    for name in ("completed", "refused", "accepted"):
        assert module.base.missing(["outcome completed"], printed[name]) == [], name
    assert module.base.missing(["outcome cancelled"], printed["cancelled"]) == []
    expected = {line for kind in ("atteso", "fine") for _, line in lines_of(kind)}
    assert {
        "outcome waiting_approval",
        "outcome completed",
        "outcome cancelled",
    } <= expected


# «sì» and «no» ---------------------------------------------------------------------------


SESSION_YES = "uv run ela task approve <id> --approval <approval-id>"
CHILD_NO = "uv run ela task deny <id del figlio> --approval <approval-id>"
CHILD_YES = (
    "uv run ela task approve <id del figlio> --approval <approval-id>\n"
    "uv run ela task run <id del figlio>"
)


def ran_with(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    ran: list[str] = []

    def run(line: str) -> subprocess.CompletedProcess[str]:
        ran.append(line)
        return subprocess.CompletedProcess(line, 0, "", "")

    monkeypatch.setattr(script().base, "run", run)
    return ran


def test_the_yes_to_a_session_shows_its_question_and_runs_the_line(
    real: Real, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = script()
    ran = ran_with(monkeypatch)
    session = real.youtube
    (question,) = session.question
    proof = proof_on(
        real, {"/approvals": session.question, f"/tasks/{session.task}": session.queued}, ["s"]
    )

    walked_on(proof, {2: [block(2, "sì", SESSION_YES)]}, module.Turn(task_id=session.task))

    assert ran == [f"uv run ela task approve {session.task} --approval {question['id']}"]
    assert proof.report.ok, proof.report.lines
    for shown in (
        f"    | frase: {question['phrase']}",
        f"    | siti: {question['sites']}",
        f"    | modello: {HAIKU_5_5}",
        f"    | costo massimo: {question['max_cost']}",
        f"    | gesti: {question['looks']}",
        f"    | che cosa esce: {question['sends']}",
    ):
        assert shown in proof.report.lines


def test_a_session_still_waiting_after_the_yes_fails(
    real: Real, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran_with(monkeypatch)
    session = real.youtube
    waiting = changed(session.queued, state="WAITING_APPROVAL")
    proof = proof_on(real, {"/approvals": session.question, f"/tasks/{session.task}": waiting})

    walked_on(proof, {2: [block(2, "sì", SESSION_YES)]}, script().Turn(task_id=session.task))

    assert proof.report.failures == 1


def test_a_no_to_the_question_stops_the_proof_and_says_why(
    real: Real, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = script()
    ran = ran_with(monkeypatch)
    session = real.youtube
    proof = proof_on(real, {"/approvals": session.question}, ["n"])
    todo = {2: [block(2, "sì", SESSION_YES)], 3: [block(3, "occhio", "Mai chiesto?")]}

    done = walked_on(proof, todo, module.Turn(task_id=session.task))

    assert done == [2] and ran == []
    assert any(
        line.startswith("[2] FERMATO: ") and module.SAID_NO in line for line in proof.report.lines
    )


def test_a_task_without_its_question_stops_the_proof(real: Real) -> None:
    proof = proof_on(real, {"/approvals": []})

    walked_on(proof, {2: [block(2, "sì", SESSION_YES)]}, script().Turn(task_id=real.youtube.task))

    assert proof.report.failures == 1 and proof.report.stopped is not None
    assert proof.asked == []


def test_the_no_to_a_gesture_names_the_child_and_its_question(
    real: Real, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = script()
    ran = ran_with(monkeypatch)
    session = real.refused
    (question,) = session.asking
    proof = proof_on(
        real, {"/approvals": session.asking, f"/tasks/{session.child}": session.child_answered}
    )
    turn = module.Turn(task_id=session.task, child_id=session.child)

    walked_on(proof, {5: [block(5, "no", CHILD_NO)]}, turn)

    assert ran == [f"uv run ela task deny {session.child} --approval {question['id']}"]
    assert proof.report.ok, proof.report.lines
    assert proof.asked == ["[5] Rispondi no? (s/n) "]
    assert f"    | indirizzo: {question['address']}" in proof.report.lines
    assert f"    | testo atteso: {question['expect']}" in proof.report.lines
    assert not [line for line in proof.report.lines if line.startswith("    | frase:")]


def test_a_gesture_not_denied_after_the_no_fails(
    real: Real, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran_with(monkeypatch)
    session = real.refused
    proof = proof_on(
        real,
        {
            "/approvals": session.asking,
            f"/tasks/{session.child}": changed(session.child_answered, state="QUEUED"),
        },
    )
    turn = script().Turn(task_id=session.task, child_id=session.child)

    walked_on(proof, {5: [block(5, "no", CHILD_NO)]}, turn)

    assert proof.report.failures == 1


def test_the_yes_to_a_gesture_runs_both_lines_and_leaves_the_end_to_the_atteso(
    real: Real, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = script()
    ran = ran_with(monkeypatch)
    session = real.accepted
    (question,) = session.asking
    proof = proof_on(
        real, {"/approvals": session.asking, f"/tasks/{session.child}": session.child_asking}
    )
    turn = module.Turn(task_id=session.task, child_id=session.child)

    walked_on(proof, {5: [block(5, "sì", CHILD_YES)]}, turn)

    assert ran == [
        f"uv run ela task approve {session.child} --approval {question['id']}",
        f"uv run ela task run {session.child}",
    ]
    assert proof.report.ok, proof.report.lines


def test_the_state_after_an_answer() -> None:
    module = script()

    assert module.after_answer(True, False) == "QUEUED"
    assert module.after_answer(True, True) is None
    assert module.after_answer(False, True) == "DENIED"


# «sfondo», «aspetta» and «fine» -----------------------------------------------------------


def test_a_run_in_the_background_is_started_with_its_task(monkeypatch: pytest.MonkeyPatch) -> None:
    module = script()
    started: list[str] = []
    monkeypatch.setattr(module.base, "started", lambda line: started.append(line) or Running())
    proof = proof_on_nothing()
    turn = module.Turn(task_id="t-1")

    module.a_block(5, block(5, "sfondo", "uv run ela task run <id>"), turn, proof)

    assert started == ["uv run ela task run t-1"]
    assert turn.background is not None and turn.background_line == "uv run ela task run t-1"


def proof_on_nothing() -> Any:
    module = script()
    return module.Proof(
        api=Recorded({}),
        report=module.base.Report(io.StringIO()),
        ask=lambda question: "s",
        start=module.spending.Ledger(cap="30", spent=Decimal(0), reserved=Decimal(0), open=0),
    )


def test_the_wait_finds_the_child_that_asks(real: Real) -> None:
    module = script()
    session = real.refused
    proof = proof_on(
        real, {"/approvals": session.asking, f"/tasks/{session.child}": session.child_asking}
    )
    turn = module.Turn(task_id=session.task, background=Running(code=None))

    walked_on(proof, {5: [block(5, "aspetta", "browser.act WAITING_APPROVAL")]}, turn)

    assert turn.child_id == session.child
    assert proof.report.ok, proof.report.lines


def test_a_child_of_another_task_is_not_the_one_awaited(real: Real) -> None:
    """A question of a ``browser.act`` of another session is not this one's: the wait goes on, and
    here the session is over — SKIPPED, the model never asked."""
    module = script()
    session = real.refused
    proof = proof_on(
        real, {"/approvals": session.asking, f"/tasks/{session.child}": session.child_asking}
    )
    turn = module.Turn(task_id=real.accepted.task, background=Running("outcome completed\n"))

    walked_on(proof, {5: [block(5, "aspetta", "browser.act WAITING_APPROVAL")]}, turn)

    assert turn.child_id is None
    assert proof.report.skipped_steps == [5] and proof.report.failures == 0


def test_a_session_over_before_the_gesture_asked_is_skipped_and_the_step_ends(real: Real) -> None:
    module = script()
    proof = proof_on(real, {"/approvals": []})
    turn = module.Turn(task_id=real.refused.task, background=Running("outcome completed\n"))
    todo = {
        5: [
            block(5, "aspetta", "browser.act WAITING_APPROVAL"),
            block(5, "no", CHILD_NO),
        ]
    }

    walked_on(proof, todo, turn)

    assert proof.report.skipped_steps == [5] and proof.report.failures == 0
    assert proof.asked == [], "no answer after a wait that found nothing"
    assert not proof.report.ok


def test_the_end_of_the_background_is_read_like_an_atteso(real: Real) -> None:
    module = script()
    proof = proof_on(real, {})
    turn = module.Turn(task_id=real.refused.task, background=Running(real.refused.run_output))

    walked_on(proof, {5: [block(5, "fine", "outcome completed")]}, turn)

    assert proof.report.ok, proof.report.lines
    assert turn.background is None and turn.last == real.refused.run_output


def test_an_end_that_is_not_the_one_expected_fails(real: Real) -> None:
    module = script()
    proof = proof_on(real, {})
    turn = module.Turn(task_id=real.stopped.task, background=Running(real.stopped.run_output))

    walked_on(proof, {6: [block(6, "fine", "outcome completed")]}, turn)

    assert proof.report.failures == 1


def test_an_end_where_ela_answered_nothing_interrupts_the_proof() -> None:
    module = script()
    proof = proof_on_nothing()
    turn = module.Turn(task_id="t-1", background=Running("", UNREACHABLE), background_line="x")
    turn.background_line = "uv run ela task run t-1"

    walked_on(proof, {5: [block(5, "fine", "outcome completed")]}, turn)

    assert proof.report.lost_at == 5


def test_an_end_without_a_run_in_the_background_is_the_guides_error() -> None:
    module = script()

    with pytest.raises(ValueError, match="fine without sfondo"):
        module.a_block(5, block(5, "fine", "x"), module.Turn(), proof_on_nothing())


def test_a_run_left_in_the_background_is_named_in_the_file(real: Real) -> None:
    module = script()
    proof = proof_on(real, {"/approvals": []}, ["n"])
    turn = module.Turn(task_id=real.youtube.task, background=Running(code=None))

    walked_on(proof, {2: [block(2, "sì", SESSION_YES)]}, turn)

    assert any("gira ancora" in line for line in proof.report.lines)


# «sessione» ------------------------------------------------------------------------------


SESSION_LINES = {
    "youtube": "SUCCEEDED",
    "outside": "SUCCEEDED",
    "refused": "SUCCEEDED",
    "accepted": "SUCCEEDED",
    "stopped": "FAILED guided.stopped",
}


def session_proof(real: Real, session: Session, results: Any = None, spend: Any = None) -> Any:
    answers = {
        f"/tasks/{session.task}/results": session.results if results is None else results,
        "/spend": real.spend_end if spend is None else spend,
    }
    return proof_on(real, answers, start=real.spend_end)


@pytest.mark.parametrize("name", list(SESSION_LINES))
def test_every_session_of_the_proof_passes_with_its_cost(real: Real, name: str) -> None:
    module = script()
    session = sessions_of(real)[name]
    proof = session_proof(real, session)

    walked_on(
        proof, {2: [block(2, "sessione", SESSION_LINES[name])]}, module.Turn(task_id=session.task)
    )

    assert proof.report.ok, proof.report.lines
    assert proof.costs == [Decimal(ended_of(session)["usage"]["cost"])]
    assert (
        f"    la risposta del modello: {ended_of(session)['output']['text']!r}"
        in proof.report.lines
    )


def test_the_sessions_of_the_section_are_the_recorded_ones() -> None:
    assert [line for _, line in lines_of("sessione")] == [
        SESSION_LINES[name] for name in ("youtube", "outside", "refused", "accepted", "stopped")
    ]


def wrong_sessions(real: Real) -> dict[str, tuple[Session, str, Any, Any]]:
    youtube, stopped = real.youtube, real.stopped
    return {
        "status": (youtube, "FAILED", None, None),
        "code": (stopped, "FAILED guided.duration", None, None),
        "a-code-where-none": (stopped, "FAILED", None, None),
        "no-cost": (youtube, "SUCCEEDED", with_ended(youtube, usage=None), None),
        "model": (youtube, "SUCCEEDED", with_output(youtube, model="claude-sonnet-5-5"), None),
        "unknown": (youtube, "SUCCEEDED", with_output(youtube, unknown_calls=1), None),
        "left-running": (youtube, "SUCCEEDED", with_output(youtube, closed=False), None),
        "open": (youtube, "SUCCEEDED", None, changed(real.spend_end, open=1)),
        "only-started": (
            youtube,
            "SUCCEEDED",
            [one for one in youtube.results if one["status"] == "STARTED"],
            None,
        ),
        "started-twice": (
            youtube,
            "SUCCEEDED",
            [*youtube.results, youtube.results[0]],
            None,
        ),
    }


@pytest.mark.parametrize(
    "case",
    [
        "status",
        "code",
        "a-code-where-none",
        "no-cost",
        "model",
        "unknown",
        "left-running",
        "open",
        "only-started",
        "started-twice",
    ],
)
def test_a_session_that_is_not_as_the_line_says_fails(real: Real, case: str) -> None:
    session, line, results, spend = wrong_sessions(real)[case]
    proof = session_proof(real, session, results, spend)

    walked_on(proof, {2: [block(2, "sessione", line)]}, script().Turn(task_id=session.task))

    assert proof.report.failures == 1, proof.report.lines


# «figli» ---------------------------------------------------------------------------------


FAMILY_LINES = {
    "youtube": "browser.read COMPLETED",
    "outside": "browser.read DENIED SCOPE",
    "refused": "browser.act DENIED",
    "accepted": "browser.act COMPLETED",
    "stopped": "browser.act CANCELLED",
}


def family_on(real: Real, session: Session, line: str, **changed_answers: Any) -> Any:
    proof = proof_on(real, {**answers_of(session), **changed_answers})
    walked_on(proof, {4: [block(4, "figli", line)]}, script().Turn(task_id=session.task))
    return proof


@pytest.mark.parametrize("name", list(FAMILY_LINES))
def test_the_children_of_every_session_pass(real: Real, name: str) -> None:
    proof = family_on(real, sessions_of(real)[name], FAMILY_LINES[name])

    assert proof.report.ok, proof.report.lines


def test_the_children_of_the_section_are_the_recorded_ones() -> None:
    assert [line for _, line in lines_of("figli")] == [
        FAMILY_LINES[name] for name in ("youtube", "outside", "refused", "accepted", "stopped")
    ]


def only_child(session: Session) -> tuple[str, Any]:
    (found,) = session.children.items()
    return found


def test_a_child_not_written_by_the_session_fails(real: Real) -> None:
    session = real.youtube
    one, child = only_child(session)
    hand = changed(
        child, plan_author={"by": "HAND", "result_id": None, "session": None, "model": None}
    )

    proof = family_on(real, session, FAMILY_LINES["youtube"], **{f"/tasks/{one}": hand})

    assert proof.report.failures == 1


def test_a_child_outside_the_sites_of_the_session_fails(real: Real) -> None:
    session = real.youtube
    one, child = only_child(session)
    wide = copy.deepcopy(child)
    wide["steps"][0]["within"] = None

    proof = family_on(real, session, FAMILY_LINES["youtube"], **{f"/tasks/{one}": wide})

    assert proof.report.failures == 1


def test_a_reading_that_asks_fails(real: Real) -> None:
    session = real.youtube
    one, child = only_child(session)
    asking = copy.deepcopy(child)
    asking["steps"][0]["requires_authorization"] = True

    proof = family_on(real, session, FAMILY_LINES["youtube"], **{f"/tasks/{one}": asking})

    assert proof.report.failures == 1


def test_a_child_that_is_not_a_gesture_fails(real: Real) -> None:
    session = real.youtube
    one, child = only_child(session)
    other = copy.deepcopy(child)
    other["steps"][0]["required_capabilities"] = ["fs.read"]

    assert script().child_failures(other, session.detail["steps"][0]["id"], ["www.youtube.com"])


def test_a_denial_by_another_rule_fails(real: Real) -> None:
    proof = family_on(real, real.outside, "browser.read DENIED CATALOGUE")

    assert proof.report.failures == 1


def test_a_denial_whose_rule_the_audit_does_not_say_fails(real: Real) -> None:
    session = real.outside
    one, _ = only_child(session)
    silent = [event for event in session.audits[one] if event["event_type"] != "PERMISSION_DECIDED"]

    proof = family_on(real, session, FAMILY_LINES["outside"], **{f"/audit?task_id={one}": silent})

    assert proof.report.failures == 1


def test_a_child_in_another_state_fails(real: Real) -> None:
    proof = family_on(real, real.refused, "browser.act COMPLETED")

    assert proof.report.failures == 1


def test_a_gesture_the_model_never_asked_for_is_skipped(real: Real) -> None:
    proof = family_on(real, real.youtube, "browser.act COMPLETED")

    assert proof.report.skipped_steps == [4] and proof.report.failures == 0


def test_the_rule_is_the_last_decision_s() -> None:
    module = script()
    decided = {"event_type": "PERMISSION_DECIDED", "payload": {"rule": "SCOPE"}}

    assert module.rule_of([decided]) == "SCOPE"
    assert module.rule_of([{"event_type": "TASK_CREATED", "payload": {}}]) is None
    assert module.rule_of([{"event_type": "PERMISSION_DECIDED", "payload": {}}]) is None


# «fascia» --------------------------------------------------------------------------------


def tier_on(real: Real, results: Any) -> Any:
    module = script()
    proof = proof_on(real, {f"/tasks/{real.youtube.task}/results": results})
    proof.ids[2] = real.youtube.task
    walked_on(proof, {3: [block(3, "fascia", module.STEP_2)]}, module.Turn())
    return proof


def test_the_calls_recomputed_at_the_low_tier_are_the_cost_the_ledger_wrote(real: Real) -> None:
    proof = tier_on(real, real.youtube.results)

    assert proof.report.ok, proof.report.lines


def test_the_low_tier_is_the_price_list_s() -> None:
    module = script()

    assert module.low_tier([["claude-haiku-5-5", 1_000_000, 0, 1]]) == Decimal("0.10")
    assert module.low_tier([["claude-haiku-5-5", 0, 1_000_000, 1]]) == Decimal("0.50")
    assert module.low_tier([["claude-haiku-5-5", 1, 1, 1]]) == Decimal("0.0000006")


def per_call_changed(real: Real, **index_call: Any) -> Any:
    calls = copy.deepcopy(ended_of(real.youtube)["output"]["per_call"])
    for index, call in index_call.items():
        calls[int(index.removeprefix("call"))] = call
    return with_output(real.youtube, per_call=calls)


WRONG_TIERS = {
    "above-the-bound": lambda real: per_call_changed(
        real, call0=["claude-haiku-5-5", 100_001, 40, 1188]
    ),
    "another-model": lambda real: per_call_changed(
        real, call0=["claude-haiku-4-5", 1200, 40, 1188]
    ),
    "no-bytes": lambda real: per_call_changed(real, call0=["claude-haiku-5-5", 1200, 40, None]),
    "no-calls": lambda real: with_output(real.youtube, per_call=[]),
    "unknown": lambda real: with_output(real.youtube, unknown_calls=1),
    "no-cost": lambda real: with_ended(real.youtube, usage=None),
    "another-cost": lambda real: with_ended(
        real.youtube, usage={**ended_of(real.youtube)["usage"], "cost": "0.0014"}
    ),
}


@pytest.mark.parametrize("case", list(WRONG_TIERS))
def test_a_session_not_at_the_low_tier_fails(real: Real, case: str) -> None:
    proof = tier_on(real, WRONG_TIERS[case](real))

    assert proof.report.failures == 1, proof.report.lines


def test_a_task_without_the_session_s_result_fails_the_tier(real: Real) -> None:
    started = [one for one in real.youtube.results if one["status"] == "STARTED"]

    proof = tier_on(real, started)

    assert proof.report.failures == 1


def test_exactly_the_bound_is_still_the_low_tier(real: Real) -> None:
    calls = [["claude-haiku-5-5", 100_000, 40, 1188]]
    cost = script().low_tier(calls)
    results = with_output(real.youtube, per_call=calls)
    for one in results:
        if one["status"] != "STARTED":
            one["usage"]["cost"] = str(cost)

    proof = tier_on(real, results)

    assert proof.report.ok, proof.report.lines


# «spesa» ---------------------------------------------------------------------------------


def costs_of(real: Real) -> list[Decimal]:
    return [Decimal(ended_of(session)["usage"]["cost"]) for session in sessions_of(real).values()]


def test_the_spend_grown_by_the_five_sessions_with_nothing_reserved_passes(real: Real) -> None:
    module = script()
    proof = proof_on(real, {"/spend": real.spend_end})
    proof.costs.extend(costs_of(real))
    lines = "\n".join(line for _, line in lines_of("spesa"))

    walked_on(proof, {7: [block(7, "spesa", lines)]}, module.Turn())

    assert proof.report.ok, proof.report.lines


def test_a_session_missing_from_the_costs_fails_the_spend(real: Real) -> None:
    module = script()
    proof = proof_on(real, {"/spend": real.spend_end})
    proof.costs.extend(costs_of(real)[:-1])
    lines = "\n".join(line for _, line in lines_of("spesa"))

    walked_on(proof, {7: [block(7, "spesa", lines)]}, module.Turn())

    assert proof.report.failures == 1


# The rest --------------------------------------------------------------------------------


def test_a_kind_the_section_does_not_have_is_the_guides_error() -> None:
    module = script()

    with pytest.raises(ValueError, match="is not a kind of the section"):
        module.a_block(2, block(2, "piano", "x"), module.Turn(), proof_on_nothing())


def test_a_command_that_creates_a_task_names_it_and_forgets_the_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = script()

    def run(line: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(line, 0, json.dumps({"id": "t-2"}), "")

    monkeypatch.setattr(module.base, "run", run)
    turn = module.Turn(task_id="t-1", child_id="c-1")

    module.a_block(
        5, block(5, "comando", 'uv run ela task create "x" --json'), turn, proof_on_nothing()
    )

    assert (turn.task_id, turn.child_id) == ("t-2", None)


def test_an_eye_asks_and_writes_the_answer() -> None:
    module = script()
    proof = proof_on_nothing()
    proof.ask = lambda question: "n"

    module.a_block(2, block(2, "occhio", "Si vede?"), module.Turn(), proof)

    assert proof.report.refused == [2]


def test_the_placeholders_are_filled_from_the_turn_and_the_steps_before() -> None:
    module = script()
    proof = proof_on_nothing()
    proof.ids[2] = "t-2"
    turn = module.Turn(task_id="t-5", child_id="c-5", approval_id="a-5")

    filled = module.filled("<id> <id del figlio> <approval-id> <id del passo 2>", turn, proof)

    assert filled == "t-5 c-5 a-5 t-2"
    assert module.filled("<id>", module.Turn(), proof) == "<id>"


def test_main_writes_the_file_and_stops_at_step_1_when_a_precondition_falls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = script()

    def fallen(report: Any, plans: Any) -> bool:
        report.stop(1, "la prova richiede «ELA risponde», e non è così")
        return False

    monkeypatch.setattr(module, "preconditions", fallen)
    out = tmp_path / "prova.txt"

    code = module.main(["--out", str(out)])

    assert code == 1
    written = out.read_text(encoding="utf-8")
    assert "La prova a mano di M14.3 e M14.6" in written
    assert "La prova non è passata" in written


def test_the_expected_lines_are_read_in_what_the_block_before_printed(real: Real) -> None:
    module = script()
    proof = proof_on_nothing()
    turn = module.Turn(task_id="t-1", last=real.youtube.waiting_output)

    module.a_block(2, block(2, "atteso", "outcome waiting_approval"), turn, proof)
    module.a_block(2, block(2, "atteso", "outcome completed"), turn, proof)

    assert sum(proof.report.passes.values()) == 1 and proof.report.failures == 1


def test_a_step_with_two_capabilities_is_no_gesture(real: Real) -> None:
    module = script()
    one, child = only_child(real.youtube)
    two = copy.deepcopy(child)
    two["steps"][0]["required_capabilities"] = ["browser.read", "browser.act"]

    assert module.capability_of(two) is None
    assert module.capability_of(changed(child, steps=[])) is None


def test_the_question_of_another_task_is_not_this_one_s(real: Real) -> None:
    module = script()
    every = [*real.refused.asking, *real.youtube.question]
    api = Recorded({"/approvals": every})

    assert module.question_of(api, real.youtube.task) == real.youtube.question[0]
    assert module.question_of(api, "nobody") is None


def test_the_wait_skips_the_questions_of_other_capabilities(real: Real) -> None:
    module = script()
    session = real.refused
    api = Recorded(
        {
            "/approvals": [*real.youtube.question, *session.asking],
            f"/tasks/{session.child}": session.child_asking,
        }
    )

    assert module.asking_child(api, session.task, "browser.act") == session.child
    assert f"/tasks/{real.youtube.task}" not in api.asked


class Later(Recorded):
    """An API whose questions arrive at the second look: the gesture asks while the script waits."""

    def __init__(self, answers: dict[str, Any], first: Any) -> None:
        super().__init__(answers)
        self.first = first

    def get(self, path: str) -> Any:
        if path == "/approvals" and self.first is not None:
            first, self.first = self.first, None
            self.asked.append(path)
            return first
        return super().get(path)


def test_the_wait_looks_again_until_the_gesture_asks(
    real: Real, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = script()
    monkeypatch.setattr(module, "WAIT", 0)
    session = real.refused
    proof = proof_on_nothing()
    proof.api = Later(
        {"/approvals": session.asking, f"/tasks/{session.child}": session.child_asking}, []
    )
    turn = module.Turn(task_id=session.task, background=Running(code=None))

    module.a_block(5, block(5, "aspetta", "browser.act WAITING_APPROVAL"), turn, proof)

    assert turn.child_id == session.child
    assert proof.api.asked.count("/approvals") == 2


def test_a_gesture_refused_before_its_child_is_counted_and_not_found(real: Real) -> None:
    """A look the result counts with no child — arguments ELA cannot plan —: ``GET /tasks/<id>``
    answers 404, and the line is read on the children that are there."""
    session = real.youtube
    more = with_output(session, looks=ended_of(session)["output"]["looks"] + 1)

    proof = family_on(
        real, session, FAMILY_LINES["youtube"], **{f"/tasks/{session.task}/results": more}
    )

    assert proof.report.ok, proof.report.lines
    assert len([path for path in proof.api.asked if path.startswith("/tasks/")]) == 4


def test_a_refusal_that_is_not_a_404_is_not_an_absent_child() -> None:
    module = script()

    class Failing:
        def get(self, path: str) -> Any:
            raise module.ApiRefusal(500, "internal", "no")

    with pytest.raises(module.ApiRefusal):
        module.existing(Failing(), "t-1")


def test_main_walks_the_section_with_the_ledger_of_its_start(
    real: Real, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = script()
    api = Recorded({"/spend": real.spend_start})
    walked: list[Any] = []
    monkeypatch.setattr(module, "preconditions", lambda report, plans: True)
    monkeypatch.setattr(module.base, "Api", lambda: api)
    monkeypatch.setattr(module.base, "walk", lambda report, todo, one: walked.append(sorted(todo)))

    code = module.main(["--out", str(tmp_path / "prova.txt")])

    assert walked == [list(range(2, 8))]
    assert code == 0, "the walk is the test's: nothing failed"
