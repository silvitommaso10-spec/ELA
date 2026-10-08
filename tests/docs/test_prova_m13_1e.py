"""Section 25 of the guide and ``scripts/prova_m13_1e.py`` say the same thing (M13.1e, «La prova a
mano»).

The guide is the source of truth, and the script reads it with the reader of M6.3c: this file reads
the section with the script's own functions and asserts that every marker is a kind the script
knows and a step of the section, that every placeholder is one it fills, that every line of its
kinds is in their vocabulary, and that the section keeps what the SPEC promised — no call, no
voice, one question of the eye per surface and per task, the rows each surface shows.

**Every kind that reads the API is fed the answers of the real routes** — step 1, ``sì``,
``guarda``, ``fine``, ``ultimi``, ``misura`` —: ``tests/docs/real_ends.py`` walks steps 2–10 with
the script itself on an ELA in this process, the three no's given from the three surfaces, and
records what the routes answered. **A negative case starts from a real answer and changes it**;
nothing the API says is written here. **Each comparison of the script has its negative case**.
"""

from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
from collections.abc import Callable, Mapping
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from ela.api import companion, console
from ela.cli.tasks import ROLE_WORDS as CLI_ROLE_WORDS
from tests.api.ends import STOP_WORDS
from tests.docs.real_ends import HANDS, Real, Recorded, changed, record, todo_of

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prova_m13_1e.py"
PLACEHOLDER = re.compile(r"<[^>\s][^>]*>")
GOAL = re.compile(r' task create "([^"]+)"')
PLAN_FILE = re.compile(r"--file (docs/examples/\S+)")
NO_CALL = ("model.complete", "voice.speak")
"""The capabilities no plan of the proof has: no spending, no voice (SPEC, «La prova a mano»)."""
ENDING_STEPS = (2, 3, 4, 5, 6)
SIBLINGS = ("prova_m6_3c", "prova_m14_1", "prova_m14_2")
"""The scripts ``prova_m13_1e`` imports. Other test files load them by path and register their own
copies under these names: the script is loaded with new ones, as ``python scripts/prova_m13_1e.py``
imports them, and ``sys.modules`` is given back as it was found (decision 31 of the review of the
proof of M14.2)."""


@cache
def script() -> ModuleType:
    """The script, loaded by path: ``scripts/`` is not a package. Its siblings are imported anew
    for it, once each, whatever another test file registered under their names."""
    found = {name: sys.modules.pop(name, None) for name in SIBLINGS}
    try:
        spec = importlib.util.spec_from_file_location("prova_m13_1e", SCRIPT)
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
    """A test patches the module the script uses, never a second copy of it: the script reads ELA's
    API through ``prova_m6_3c`` itself, through ``prova_m14_1`` and through ``prova_m14_2``."""
    module = script()

    assert module.spending.base is module.base
    assert module.planner.base is module.base
    assert module.planner.spending is module.spending


def words(text: str) -> str:
    """``text`` with its spaces gathered: the guide wraps where it likes, the CLI aligns."""
    return " ".join(text.split())


def guide() -> str:
    return str(script().GUIDE.read_text(encoding="utf-8"))


def section() -> str:
    return str(script().base.section(guide(), script().HEADING))


def marked() -> dict[int, list[Any]]:
    return todo_of(script())


def of_kind(kind: str) -> list[Any]:
    return [block for blocks in marked().values() for block in blocks if block.kind == kind]


def block(number: int, kind: str, body: str) -> Any:
    return script().base.Block(number, kind, body)


# ----------------------------------------------------------------------------------------
# The section and the script: the same kinds, the same placeholders, the same vocabulary
# ----------------------------------------------------------------------------------------


def test_the_section_is_the_one_the_script_reads_and_names_it() -> None:
    module = script()

    assert module.HEADING == "## 25. "
    assert "uv run python scripts/prova_m13_1e.py" in section()
    assert "prova-m13.1e-" in section()
    assert module.default_out().name.startswith("prova-m13.1e-")


def test_every_marker_is_a_kind_of_the_script_and_every_kind_is_used() -> None:
    kinds = {one.kind for blocks in marked().values() for one in blocks}

    assert kinds == set(script().KINDS)


def test_the_steps_follow_one_another_from_the_second() -> None:
    """Step 1 is the script's own — the preconditions —, written in prose."""
    assert list(marked()) == list(range(2, 11))
    assert "### 1. Prima" in section()


def test_every_placeholder_of_the_section_is_one_the_script_fills() -> None:
    module = script()
    found = {
        placeholder
        for blocks in marked().values()
        for one in blocks
        for placeholder in PLACEHOLDER.findall(one.body)
    }
    filled = set(module.PLACEHOLDERS)

    assert found
    assert {one for one in found if not module.STEP_ID.fullmatch(one)} <= filled


def test_every_placeholder_the_script_fills_is_explained_by_the_section() -> None:
    text = section()

    assert all(f"`{placeholder}`" in text for placeholder in script().PLACEHOLDERS)
    assert "`<id del passo N>`" in text


def test_every_line_of_the_section_is_in_the_vocabulary_of_its_kind() -> None:
    module = script()

    assert [module.watched_word(one) for one in of_kind("guarda")] == ["DENIED", "DENIED"]
    assert [module.wanted_of(one).role for one in of_kind("fine")] == [
        module.LOCAL,
        module.CONSOLE,
        module.COMPANION,
        None,
        None,
    ]
    assert [module.surface_of(one)[0] for one in of_kind("ultimi")] == ["console", "telefono"]


@pytest.mark.parametrize(
    ("kind", "body"),
    [
        ("guarda", "stato SPENTO"),
        ("guarda", "risultato DENIED"),
        ("fine", "operazione cancel\ncodice —"),
        ("fine", "operazione cancel\ncodice —\nha risposto il vicino"),
        ("fine", "operazione cancel\noperazione fail\ncodice —\nha risposto nessuno"),
        ("fine", "operazione cancel\ncodice —\nha risposto nessuno\nchi lo sa"),
        ("ultimi", "orologio 8\n<id del passo 2>"),
        ("ultimi", "console otto\n<id del passo 2>"),
        ("ultimi", "console 8"),
        ("ultimi", "console 8\n<id>"),
    ],
)
def test_a_line_outside_the_vocabulary_of_its_kind_is_refused(kind: str, body: str) -> None:
    """The negative cases of the three readers: a line nobody can read stops the script, never
    passes."""
    module = script()
    reader = {"guarda": module.watched_word, "fine": module.wanted_of, "ultimi": module.surface_of}

    with pytest.raises(ValueError):
        reader[kind](block(9, kind, body))


def test_the_rows_of_each_surface_are_the_ones_its_home_shows() -> None:
    """Decision 8: ``ultimi`` reads as many finished tasks as the surface shows — the code's own
    numbers, which the section writes."""
    shown = {surface: rows for surface, rows, _ in map(script().surface_of, of_kind("ultimi"))}

    assert shown == {"console": console.SHOWN, "telefono": companion.SHOWN}
    assert f"{console.SHOWN} la console, {companion.SHOWN} il telefono" in words(section())


def test_the_last_ones_are_the_tasks_of_the_steps_that_end_one() -> None:
    module = script()
    ending = sorted(one.step for one in of_kind("fine"))

    assert ending == list(ENDING_STEPS)
    assert all(module.surface_of(one)[2] == ending for one in of_kind("ultimi"))


def test_the_eye_asks_one_question_per_surface_and_per_task_after_the_last_ones() -> None:
    """Ten questions in two steps: the console and the phone open once each (SPEC, step 8 and 9)."""
    for step in (8, 9):
        kinds = [one.kind for one in marked()[step]]
        assert kinds == ["ultimi", *["occhio"] * len(ENDING_STEPS)]
    assert len(of_kind("occhio")) == 2 * len(ENDING_STEPS)


def created_goals() -> dict[int, str]:
    found: dict[int, str] = {}
    for one in of_kind("comando"):
        match = GOAL.search(f" {one.body}")
        if match is not None:
            found[one.step] = match.group(1)
    return found


def test_the_console_questions_name_the_goals_the_steps_created() -> None:
    goals = created_goals()

    assert sorted(goals) == list(ENDING_STEPS)
    for one, step in zip(of_kind("occhio")[: len(ENDING_STEPS)], ENDING_STEPS, strict=True):
        assert f"«{goals[step]}»" in one.body


def test_the_phone_questions_say_the_form_of_decision_2() -> None:
    """Under the ceiling, only ELA's words; the ``TRUSTED`` task of step 4, the whole reason."""
    phone = [one.body for one in marked()[9] if one.kind == "occhio"]

    assert "«deny_by_approval · ha risposto: la riga di comando»" in phone[0]
    assert "«deny_by_approval · ha risposto: la console»" in phone[1]
    assert "(il telefono)" in phone[2] and "<id del passo 4>" not in phone[2]
    assert "«fail · browser.element_missing»" in phone[3]
    assert "«cancel»" in phone[4]
    assert all(f"<id del passo {step}>" in phone[at] for at, step in ((0, 2), (1, 3), (3, 5)))


def test_only_the_phone_s_task_is_trusted() -> None:
    privacy = {
        one.step: "--privacy TRUSTED" in one.body
        for one in of_kind("comando")
        if "create" in one.body
    }

    assert privacy == {2: False, 3: False, 4: True, 5: False, 6: False}


def test_no_plan_of_the_proof_calls_a_model_or_speaks() -> None:
    """No spending and no voice: no plan the section attaches has a step of either."""
    files = {name for one in of_kind("comando") for name in PLAN_FILE.findall(one.body)}
    assert files
    for name in files:
        plan = json.loads((ROOT / name).read_text(encoding="utf-8"))
        used = {
            capability for step in plan["steps"] for capability in step["required_capabilities"]
        }
        assert not used & set(NO_CALL), name
    assert not [one for one in of_kind("comando") if "voice" in one.body]


def test_the_stop_says_the_words_of_the_suite() -> None:
    assert f'--reason "{STOP_WORDS}"' in section()


def test_every_hand_of_the_section_is_given_by_a_page_of_the_recording() -> None:
    """The recording gives each ``mano`` through the page its first words name."""
    hands = of_kind("mano")

    assert [one.step for one in hands] == [3, 4]
    assert all(sum(one.body.startswith(start) for start in HANDS) == 1 for one in hands)


def test_the_watch_waits_a_quarter_of_an_hour_as_the_section_says() -> None:
    assert script().WATCH_SECONDS == 15 * 60
    assert "al più un quarto d'ora" in section()
    assert "nessuno ha risposto in un quarto d'ora: il passo si rifà" in words(section())


def test_the_section_says_what_fine_does_with_a_task_pushed_out() -> None:
    """Decision 10, in the guide's words: the row is SALTATA, the rest compared."""
    text = words(section())

    assert f"gli ultimi {script().FINISHED_LOOK} finiti" in text
    assert "un altro task finito l'ha spinto fuori" in text


# ----------------------------------------------------------------------------------------
# Steps 2–10 on the real routes
# ----------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real(tmp_path_factory: pytest.TempPathFactory) -> Real:
    return record(script(), tmp_path_factory)


def test_steps_2_to_10_pass_on_the_real_routes(real: Real) -> None:
    """The script itself, on the routes and the command line of a real ELA: nothing FALLITO,
    nothing SALTATO, and every ``atteso`` passed."""
    lines = real.lines

    assert not [line for line in lines if "FALLITO" in line or "SALTATO" in line], "\n".join(lines)
    expected = len(of_kind("atteso"))
    assert sum(line.endswith("PASSATO: l'uscita è quella attesa") for line in lines) == expected


def test_each_end_is_the_audit_s_with_who_answered(real: Real) -> None:
    said = {
        2: "deny_by_approval, ha risposto LOCAL",
        3: "deny_by_approval, ha risposto CONSOLE",
        4: "deny_by_approval, ha risposto COMPANION",
        5: "fail, ha risposto nessuno",
        6: "cancel, ha risposto nessuno",
    }

    for step, words in said.items():
        assert f"[{step}] PASSATO: la ragione è il sommario dell'audit: {words}" in real.lines


def test_the_watch_saw_the_hand_of_each_surface(real: Real) -> None:
    for step in (3, 4):
        assert f"[{step}] PASSATO: il task {real.ids[step]} è DENIED" in real.lines
        assert real.waiting[step]["state"] == "WAITING_APPROVAL"


def test_the_yes_of_step_5_was_asked_and_given(real: Real) -> None:
    assert real.asked[0] == "[5] Rispondi sì? (s/n) "
    assert f"[5] PASSATO: il sì al task {real.ids[5]}" in real.lines


def test_the_last_ones_were_read_before_the_eye(real: Real) -> None:
    assert (
        f"[8] PASSATO: i task dei passi 2, 3, 4, 5, 6 sono fra gli ultimi {console.SHOWN} finiti "
        "che la console mostra"
    ) in real.lines
    assert (
        f"[9] PASSATO: i task dei passi 2, 3, 4, 5, 6 sono fra gli ultimi {companion.SHOWN} finiti "
        "che il telefono mostra"
    ) in real.lines
    assert len(real.asked) == 1 + 2 * len(ENDING_STEPS)


def test_the_eye_is_asked_with_the_ids_of_the_steps(real: Real) -> None:
    phone = [question for question in real.asked if question.startswith("[9]")]

    assert real.ids[2] in phone[0] and real.ids[3] in phone[1]
    assert not [question for question in real.asked if "<id del passo" in question]


def test_the_measure_writes_the_milliseconds_and_no_verdict(real: Real) -> None:
    measured = [line for line in real.lines if line.startswith("    /tasks")]

    assert [line.split(":")[0].strip() for line in measured] == [
        "/tasks",
        "/tasks/finished?limit=10",
    ]
    assert all(" con una ragione; 5 letture, mediana " in line for line in measured)
    assert "    una misura, non un verdetto" in real.lines
    assert not [line for line in real.lines if line.startswith("[10] ")]


def test_the_who_of_the_console_and_the_phone_are_their_rows_of_the_registry(real: Real) -> None:
    """The placeholders ``fine`` fills: the id and the name of the row that answered."""
    rows = {one["id"]: one for one in real.devices}
    for step, role in ((3, "CONSOLE"), (4, "COMPANION")):
        answered = real.tasks[step]["end"]["answered_by"]
        assert rows[answered["identity"]]["role"] == role
        assert f"rejected by {answered['identity']}" in "\n".join(real.lines)
        assert f"| answered by {answered['name']} ({CLI_ROLE_WORDS[role]})" in map(
            words, real.lines
        )


# ----------------------------------------------------------------------------------------
# The comparisons, on a real answer changed: each has its negative case
# ----------------------------------------------------------------------------------------


def proof_on(answers: Mapping[str, Any], said: list[str] | None = None) -> Any:
    module = script()
    asked: list[str] = []

    def ask(question: str) -> str:
        asked.append(question)
        return said.pop(0) if said else "s"

    proof = module.Proof(api=Recorded(answers), report=module.base.Report(io.StringIO()), ask=ask)
    proof.asked = asked
    return proof


def wanted(step: int) -> Any:
    (found,) = [one for one in marked()[step] if one.kind == "fine"]
    return script().wanted_of(found)


def failures_of(real: Real, step: int, **answers: Any) -> list[str]:
    module = script()
    found: list[str] = module.end_failures(
        answers.get("task", real.tasks[step]),
        answers.get("events", real.audits[step]),
        answers.get("devices", real.devices),
        answers.get("finished", real.finished[module.FINISHED_LOOK]["tasks"]),
        answers.get("wanted", wanted(step)),
    )
    return found


def test_the_real_ends_pass_the_comparison(real: Real) -> None:
    assert all(failures_of(real, step) == [] for step in ENDING_STEPS)


def with_end(task: Any, **fields: Any) -> Any:
    return changed(task, end=changed(task["end"], **fields))


def renamed(devices: Any, identity: str, **fields: Any) -> Any:
    return [changed(one, **fields) if one["id"] == identity else one for one in devices]


Negative = Callable[[Real], dict[str, Any]]

NEGATIVES: dict[str, tuple[int, Negative, str]] = {
    "a reason that is not the summary": (
        2,
        lambda r: {"task": with_end(r.tasks[2], reason="deny_by_approval: composta qui")},
        "la ragione è",
    ),
    "no end": (6, lambda r: {"task": changed(r.tasks[6], end=None)}, "non ha una ragione"),
    "no event closed it": (
        6,
        lambda r: {
            "events": [one for one in r.audits[6] if one["payload"].get("new_state") is None]
        },
        "nessun evento d'audit",
    ),
    "another operation": (
        6,
        lambda r: {"task": with_end(r.tasks[6], operation="expire")},
        "end dice l'operazione",
    ),
    "a code nobody wrote": (
        6,
        lambda r: {"task": with_end(r.tasks[6], reason_code="spending.cap")},
        "end dice il codice",
    ),
    "the code of the failure lost": (
        5,
        lambda r: {"task": with_end(r.tasks[5], reason_code=None)},
        "end dice il codice",
    ),
    "another role": (
        4,
        lambda r: {
            "task": with_end(
                r.tasks[4], answered_by=changed(r.tasks[4]["end"]["answered_by"], role="CONSOLE")
            )
        },
        "ha risposto un 'CONSOLE'",
    ),
    "somebody answered a stop": (
        6,
        lambda r: {"task": with_end(r.tasks[6], answered_by=r.tasks[2]["end"]["answered_by"])},
        "il passo dice nessuno",
    ),
    "nobody answered a no": (
        3,
        lambda r: {"task": with_end(r.tasks[3], answered_by=None)},
        "nessuno ha risposto",
    ),
    "the command line with another name": (
        2,
        lambda r: {
            "task": with_end(
                r.tasks[2], answered_by=changed(r.tasks[2]["end"]["answered_by"], name="local")
            )
        },
        "la riga di comando è",
    ),
    "a name the registry does not have": (
        3,
        lambda r: {
            "devices": renamed(
                r.devices, r.tasks[3]["end"]["answered_by"]["identity"], name="un altro nome"
            )
        },
        "si chiama 'un altro nome'",
    ),
    "a row revoked": (
        4,
        lambda r: {
            "devices": renamed(
                r.devices,
                r.tasks[4]["end"]["answered_by"]["identity"],
                revoked_at="2026-10-08T10:00:00Z",
            )
        },
        "è revocato",
    ),
    "a row of another role": (
        3,
        lambda r: {
            "devices": renamed(r.devices, r.tasks[3]["end"]["answered_by"]["identity"], role="NODE")
        },
        "è un 'NODE'",
    ),
    "an identity the registry does not have": (
        3,
        lambda r: {
            "devices": [
                one
                for one in r.devices
                if one["id"] != r.tasks[3]["end"]["answered_by"]["identity"]
            ]
        },
        "il registro non ha",
    ),
    "the event names another answerer": (
        3,
        lambda r: {
            "events": [
                changed(one, payload=changed(one["payload"], responded_by="user"))
                for one in r.audits[3]
            ]
        },
        "l'evento dice che ha risposto 'user'",
    ),
    "the finished row says another end": (
        5,
        lambda r: {
            "finished": [
                with_end(one, reason="altro") if one["id"] == r.ids[5] else one
                for one in r.finished[script().FINISHED_LOOK]["tasks"]
            ]
        },
        "la riga di GET /tasks/finished",
    ),
    "the block wants another code": (
        6,
        lambda r: {"wanted": changed_wanted(6, code="execution.stopped")},
        "il passo 'execution.stopped'",
    ),
}


def changed_wanted(step: int, **fields: Any) -> Any:
    from dataclasses import replace

    return replace(wanted(step), **fields)


@pytest.mark.parametrize("case", sorted(NEGATIVES))
def test_a_real_end_changed_fails_the_comparison(real: Real, case: str) -> None:
    step, change, words = NEGATIVES[case]

    found = failures_of(real, step, **change(real))

    assert any(words in one for one in found), found


def test_fine_on_the_real_routes_fills_who_answered_and_fails_on_a_changed_answer(
    real: Real,
) -> None:
    module = script()
    (fine,) = [one for one in marked()[3] if one.kind == "fine"]
    proof = proof_on(real.answers(3))
    turn = module.Turn(task_id=real.ids[3])

    module.an_end(3, fine, turn, proof)

    assert proof.report.failures == 0, proof.report.lines
    answered = real.tasks[3]["end"]["answered_by"]
    assert turn.who == module.Answerer(answered["identity"], answered["name"])
    assert module.filled("<id di chi ha risposto> <nome di chi ha risposto>", turn, proof) == (
        f"{answered['identity']} {answered['name']}"
    )

    answers = real.answers(3)
    answers[f"/tasks/{real.ids[3]}"] = with_end(real.tasks[3], reason="altro")
    failing = proof_on(answers)
    module.an_end(3, fine, module.Turn(task_id=real.ids[3]), failing)
    assert failing.report.failures == 1


def pushed_out(real: Real, step: int) -> Any:
    """The real last finished, without the task of ``step``: others finished after it."""
    answer = real.finished[script().FINISHED_LOOK]
    return changed(answer, tasks=[one for one in answer["tasks"] if one["id"] != real.ids[step]])


def fine_on(real: Real, step: int, **paths: Any) -> Any:
    """``fine`` of ``step`` on the real answers, with some routes answering otherwise."""
    module = script()
    (fine,) = [one for one in marked()[step] if one.kind == "fine"]
    answers = real.answers(step)
    if "finished" in paths:
        answers[f"/tasks/finished?limit={module.FINISHED_LOOK}"] = paths["finished"]
    if "task" in paths:
        answers[f"/tasks/{real.ids[step]}"] = paths["task"]
    proof = proof_on(answers)
    proof.turn = module.Turn(task_id=real.ids[step])
    module.an_end(step, fine, proof.turn, proof)
    return proof


def test_a_task_pushed_out_of_the_finished_skips_its_row_and_the_rest_is_compared(
    real: Real,
) -> None:
    """Decision 10 of the review of the summary: the part of ``fine`` that reads the row of
    ``GET /tasks/finished`` is SALTATA, with the reason, as ``ultimi`` of decision 8; the route
    of the task, the audit and the registry are compared all the same."""
    proof = fine_on(real, 3, finished=pushed_out(real, 3))

    assert proof.report.failures == 0, proof.report.lines
    assert proof.report.skipped_steps == [3]
    (skipped,) = [line for line in proof.report.lines if line.startswith("[3] SALTATO: ")]
    assert real.ids[3] in skipped
    assert "un altro task finito l'ha spinto fuori" in skipped
    assert (
        "[3] PASSATO: la ragione è il sommario dell'audit: deny_by_approval, ha risposto CONSOLE"
    ) in proof.report.lines
    assert proof.turn.who is not None


def test_a_task_pushed_out_still_fails_on_what_the_rest_finds(real: Real) -> None:
    proof = fine_on(
        real, 3, finished=pushed_out(real, 3), task=with_end(real.tasks[3], reason="altro")
    )

    assert proof.report.failures == 1
    assert proof.report.skipped_steps == [3]


def test_the_comparison_of_a_task_pushed_out_is_the_comparison_of_the_rest(real: Real) -> None:
    """The pure part: no row, no failure for the row — and the sentence of the skip."""
    module = script()
    finished = pushed_out(real, 5)["tasks"]

    assert failures_of(real, 5, finished=finished) == []
    said = module.pushed_out_of_finished(real.tasks[5], finished)
    assert said is not None and "un altro task finito l'ha spinto fuori" in said
    assert (
        module.pushed_out_of_finished(real.tasks[5], real.finished[module.FINISHED_LOOK]["tasks"])
        is None
    )


# «guarda» ---------------------------------------------------------------------------------


def watch(real: Real, answer: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Step 3 from its ``guarda`` on, with ``GET /tasks/<id>`` answering ``answer``."""
    module = script()
    monkeypatch.setattr(module, "WATCH_SECONDS", 0)
    monkeypatch.setattr(module, "WATCH_PAUSE", 0)
    blocks = marked()[3]
    after = blocks[[one.kind for one in blocks].index("guarda") :]
    proof = proof_on({f"/tasks/{real.ids[3]}": answer, **real.answers(3)})
    proof.api.answers[f"/tasks/{real.ids[3]}"] = answer
    module.a_step(3, after, proof, module.Turn(task_id=real.ids[3]))
    return proof


def test_the_watch_passes_on_the_task_the_hand_denied(
    real: Real, monkeypatch: pytest.MonkeyPatch
) -> None:
    proof = watch(real, real.tasks[3], monkeypatch)

    assert f"[3] PASSATO: il task {real.ids[3]} è DENIED" in proof.report.lines


def test_the_watch_fails_on_another_end_and_the_step_goes_no_further(
    real: Real, monkeypatch: pytest.MonkeyPatch
) -> None:
    proof = watch(real, changed(real.tasks[3], state="CANCELLED"), monkeypatch)

    assert proof.report.failures == 1
    assert f"[3] FALLITO: il task {real.ids[3]} è finito CANCELLED, non DENIED" in (
        proof.report.lines
    )
    assert proof.api.asked == [f"/tasks/{real.ids[3]}"]


def test_a_watch_nobody_answered_in_time_skips_the_step_and_goes_no_further(
    real: Real, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decision 9 of the review of the summary: nobody acted within ``WATCH_SECONDS`` — the human
    step not done, like lesson S of M13.1c —: SALTATO, never FALLITO, and the step is done again.
    The words are the decision's, written here and not read from the script."""
    proof = watch(real, real.waiting[3], monkeypatch)

    assert proof.report.failures == 0
    assert proof.report.skipped_steps == [3]
    (skipped,) = [line for line in proof.report.lines if line.startswith("[3] SALTATO: ")]
    assert real.ids[3] in skipped and "WAITING_APPROVAL" in skipped
    assert skipped.endswith("nessuno ha risposto in un quarto d'ora: il passo si rifà")
    assert proof.api.asked == [f"/tasks/{real.ids[3]}"]


# «sì» and the question of a command ---------------------------------------------------------


def a_yes_on(real: Real, approvals: Any, said: list[str]) -> Any:
    module = script()
    (yes,) = of_kind("sì")
    proof = proof_on({"/approvals": approvals}, said)
    with pytest.raises(module.base.Stop) as stopped:
        module.a_yes(5, yes, module.Turn(task_id=real.ids[3]), proof)
    return proof, str(stopped.value)


def test_the_yes_shows_the_task_s_own_question_and_a_no_stops(real: Real) -> None:
    """The real question of step 3's task, while it waited: shown, and a «n» stops the proof."""
    proof, why = a_yes_on(real, real.approvals, ["n"])

    question = next(one for one in real.approvals if one["task_id"] == real.ids[3])
    assert f"    | {question['prompt']}" in proof.report.lines
    assert why == script().SAID_NO


def test_the_yes_without_a_question_fails_and_stops(real: Real) -> None:
    proof, why = a_yes_on(
        real, [one for one in real.approvals if one["task_id"] != real.ids[3]], []
    )

    assert proof.report.failures == 1
    assert why == script().NO_QUESTION


def test_a_command_with_the_question_and_no_question_stops(real: Real) -> None:
    module = script()
    proof = proof_on({"/approvals": []})

    with pytest.raises(module.base.Stop):
        module.commands(
            2, ["uv run ela task deny <id> --approval <approval-id>"], module.Turn("x"), proof
        )

    assert proof.report.failures == 1


# «ultimi» ---------------------------------------------------------------------------------


def last_ones(real: Real, step: int, finished: Any) -> Any:
    module = script()
    blocks = marked()[step]
    surface, shown, _ = module.surface_of(blocks[0])
    proof = proof_on({f"/tasks/finished?limit={shown}": finished}, [])
    proof.ids.update(real.ids)
    module.a_step(step, blocks, proof)
    return proof


@pytest.mark.parametrize("step", [8, 9])
def test_the_last_ones_on_the_real_list_pass_and_the_eye_is_asked(real: Real, step: int) -> None:
    shown = script().surface_of(marked()[step][0])[1]

    proof = last_ones(real, step, real.finished[shown])

    assert proof.report.skipped_steps == []
    assert len(proof.asked) == len(ENDING_STEPS)


@pytest.mark.parametrize("step", [8, 9])
def test_a_task_pushed_out_skips_the_step_and_asks_no_eye(real: Real, step: int) -> None:
    """Decision 8: another task finished after the proof's, and the oldest of them left the list:
    SALTATO, with the task and the surface, never FALLITO."""
    shown = script().surface_of(marked()[step][0])[1]
    answer = real.finished[shown]
    pushed = changed(answer, tasks=[one for one in answer["tasks"] if one["id"] != real.ids[2]])

    proof = last_ones(real, step, pushed)

    assert proof.report.skipped_steps == [step]
    assert proof.report.failures == 0
    assert proof.asked == []
    assert any(real.ids[2] in line and "SALTATO" in line for line in proof.report.lines)


def test_a_step_without_its_task_is_named() -> None:
    assert script().pushed_out([], [7], {}) == ["il passo 7 non ha un task"]


# «misura» ---------------------------------------------------------------------------------


def test_the_measure_counts_the_reasons_of_the_real_answers(real: Real) -> None:
    module = script()
    every = real.finished[module.FINISHED_LOOK]
    reasons = sum(1 for one in every["tasks"] if one["end"] is not None)

    said = module.measured([3.0, 1.0, 2.0], every)

    assert said.startswith(f"{len(every['tasks'])} task, {reasons} con una ragione; 3 letture")
    assert "mediana 2.0 ms (da 1.0 a 3.0)" in said
    assert module.measured([1.0], []) == (
        "0 task, 0 con una ragione; 1 letture, mediana 1.0 ms (da 1.0 a 1.0); nessuna ragione"
    )


# Step 1 -----------------------------------------------------------------------------------


def step_1(
    real: Real,
    monkeypatch: pytest.MonkeyPatch,
    *,
    shell: bool = True,
    sites: tuple[str, ...] = ("example.com",),
    **answers: Any,
) -> tuple[bool, Any]:
    """Step 1 on what the real routes answered, with the world outside ELA as the proof wants."""
    module = script()
    recorded = {
        "/health": real.health,
        "/openapi.json": real.openapi,
        "/devices": real.devices,
        **answers,
    }
    monkeypatch.setattr(module.base, "Api", lambda: Recorded(recorded))
    monkeypatch.setattr(module.planner, "on_origin", lambda: None)
    monkeypatch.setattr(module.planner, "migrated", lambda: True)
    monkeypatch.setattr(module, "shell_installed", lambda: shell)
    monkeypatch.setenv("ELA_BROWSER_SITES", json.dumps(sites))
    report = module.base.Report(io.StringIO())
    return module.preconditions(report), report


def test_step_1_passes_on_the_real_routes(real: Real, monkeypatch: pytest.MonkeyPatch) -> None:
    ok, report = step_1(real, monkeypatch)

    assert ok, report.lines
    assert sum(" PASSATO: " in line for line in report.lines) == 8


def without_end_out(openapi: Any) -> Any:
    schemas = {name: one for name, one in openapi["components"]["schemas"].items()}
    del schemas["EndOut"]
    return changed(openapi, components=changed(openapi["components"], schemas=schemas))


def of_role(devices: Any, role: str, **fields: Any) -> Any:
    return [changed(one, **fields) if one["role"] == role else one for one in devices]


REVOKED = "2026-10-08T10:00:00Z"
FALLING: dict[str, tuple[Callable[[Real], dict[str, Any]], str]] = {
    "an older Core": (
        lambda r: {"/openapi.json": without_end_out(r.openapi)},
        "lo schema ha EndOut",
    ),
    "example.com not declared": (lambda r: {"sites": ("httpbin.org",)}, "example.com è fra"),
    "no shell": (lambda r: {"shell": False}, "lo shell di Chromium"),
    "the console revoked": (
        lambda r: {"/devices": of_role(r.devices, "CONSOLE", revoked_at=REVOKED)},
        "una console, non revocata",
    ),
    "the phone revoked": (
        lambda r: {"/devices": of_role(r.devices, "COMPANION", revoked_at=REVOKED)},
        "un telefono TRUSTED",
    ),
    "a phone that sees every task": (
        lambda r: {"/devices": of_role(r.devices, "COMPANION", privacy="LOCAL_ONLY")},
        "un telefono TRUSTED",
    ),
}
"""One case for each precondition read from the API, the settings or the disk; the commit and the
migration are ``prova_m14_2``'s, and have their cases in its tests."""


@pytest.mark.parametrize("case", sorted(FALLING))
def test_step_1_stops_at_the_first_precondition_that_falls(
    real: Real, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    change, said = FALLING[case]

    ok, report = step_1(real, monkeypatch, **change(real))

    assert not ok
    assert report.stopped is not None and said in report.stopped[1], report.lines
    assert report.lines[-1].startswith("[1] FERMATO: ")
