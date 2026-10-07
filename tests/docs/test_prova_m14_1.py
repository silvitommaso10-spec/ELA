"""§23 and ``scripts/prova_m14_1.py`` say the same thing (M14.1, «La prova a mano»).

The guide is the source of truth, and the script reads it with the reader of M6.3c: this file reads
§23 with the script's own functions and asserts that every marker is a kind the script knows and a
step of the section, that every placeholder is one it fills, and that every line of its six kinds
is in their vocabulary. **Each comparison of the script has its negative case**, on constructed
answers: a check that only ever passes proves nothing. That the questions §23 expects are the ones
ELA asks — the worst case of each plan, in the row ``ela approvals`` prints — is proved in
``tests/api/test_examples.py``, on an ELA with a cap and a key that no socket carries.
"""

from __future__ import annotations

import importlib.util
import io
import re
import sys
from decimal import Decimal
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from ela.providers.anthropic.models import MODELS

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prova_m14_1.py"
PLACEHOLDER = re.compile(r"<[^>\s][^>]*>")
HERE = "6c38f1c5-6cda-5680-8a7a-4f061588deed"
PC = "5ddae87a-0000-4000-8000-000000000001"


@cache
def script() -> ModuleType:
    """The script, loaded by path: ``scripts/`` is not a package."""
    spec = importlib.util.spec_from_file_location("prova_m14_1", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def guide() -> str:
    return str(script().GUIDE.read_text(encoding="utf-8"))


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
    section = script().base.section(guide(), script().HEADING)
    headings = {int(number) for number in re.findall(r"^### (\d+)\. ", section, re.MULTILINE)}
    found = marked()

    assert found, "§23 has no marked block: the script would do nothing"
    assert set(found) <= headings
    assert set(found) == set(range(2, 9)), "steps 2 to 8; step 1 is the script's own"
    assert all(block.kind in script().KINDS for blocks in found.values() for block in blocks)
    every_marker = re.findall(r"<!-- prova: (\d+)\.(\w+) -->", section)
    assert len(every_marker) == sum(len(blocks) for blocks in found.values()), (
        "a marker the reader did not take: it is not right above a fenced block"
    )


def test_every_kind_of_the_script_is_used_by_the_section() -> None:
    """A kind nobody writes is code nobody runs: the vocabulary and the guide move together."""
    used = {block.kind for blocks in marked().values() for block in blocks}

    assert used == set(script().KINDS)


def test_every_placeholder_is_one_the_script_fills() -> None:
    module = script()
    used = {
        found
        for blocks in marked().values()
        for block in blocks
        if block.kind in {"comando", "atteso"}
        for found in PLACEHOLDER.findall(block.body)
    }

    assert used == {module.ID, module.APPROVAL_ID}


def test_the_question_is_printed_before_its_id_is_used() -> None:
    """``<approval-id>`` is the task's question: ``ela approvals`` has shown it to Tommaso first."""
    module = script()
    for number, blocks in marked().items():
        lines = [line for block in blocks if block.kind == "comando" for line in block.lines]
        for at, line in enumerate(lines):
            if module.APPROVAL_ID in line:
                assert "uv run ela approvals" in lines[:at], number


def test_a_task_is_created_with_the_json_the_script_reads_its_id_from() -> None:
    created = [line for _, line in lines_of("comando") if script().CREATE in f" {line} "]

    assert len(created) == 8
    assert all(line.endswith(" --json") for line in created), created


def test_the_plans_the_section_names_are_in_the_repository() -> None:
    plans = [
        line.split("--file ", 1)[1].split()[0]
        for _, line in lines_of("comando")
        if "--file " in line
    ]

    assert plans
    assert all((ROOT / plan).is_file() for plan in plans), plans


def test_the_calls_that_travel_are_declared_trusted_and_the_others_stay() -> None:
    """Step 4 stays on this Mac — no ``--privacy`` —, and steps 5–7 are the PC's."""
    for number, line in lines_of("comando"):
        if script().CREATE in f" {line} ":
            assert ("--privacy TRUSTED" in line) == (number in {5, 6, 7}), (number, line)


def test_every_line_of_the_scripts_kinds_is_in_its_vocabulary() -> None:
    module = script()

    assert {line for _, line in lines_of("tetto")} == set(module.CAPS)
    assert {line for _, line in lines_of("spesa")} == set(module.LEDGER_WORDS)
    assert [line for _, line in lines_of("tace")] == [module.SILENT]
    assert [line for _, line in lines_of("aspetta")] == [module.LAPSE]
    assert {line for _, line in lines_of("richiede")} <= set(module.base.REQUIREMENTS)
    for blocks in marked().values():
        for block in blocks:
            if block.kind == "guarda":
                module.base.sign_of(block)  # raises on a line outside the vocabulary
    for _, line in lines_of("costo"):
        assert line.removesuffix(module.ON_A_NODE).strip() in MODELS, line


def test_the_three_models_of_the_profiles_are_each_called() -> None:
    """Decision 16: Opus 5.5, Sonnet 5.5 and Haiku with the pinned id, each with its cost read."""
    called = {line for number, line in lines_of("costo") if number == 4}

    assert called == {"claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5-20251001"}


def test_the_ctrl_c_is_said_after_the_claim_is_seen_and_before_the_silence_is_checked() -> None:
    """Decision 17: the script tells Tommaso when, from what it reads — the claim's ``STARTED``."""
    kinds = [block.kind for block in marked()[6]]

    assert kinds.index("guarda") < kinds.index("mano") < kinds.index("tace")
    assert kinds.index("tace") < kinds.index("aspetta")
    (look,) = [block for block in marked()[6] if block.kind == "guarda"]
    assert look.lines == ["risultato STARTED su un nodo"]


def test_the_file_is_in_downloads_with_the_name_of_the_milestone() -> None:
    out = script().default_out()

    assert out.parent == Path.home() / "Downloads"
    assert out.name.startswith("prova-m14.1-")


# ----------------------------------------------------------------------------------------
# The comparisons of its own, each with its negative case
# ----------------------------------------------------------------------------------------


def test_the_same_seven_characters_are_the_same_commit() -> None:
    assert script().same_commit("ab87d9d1234567890\n", "AB87D9D") is None


def test_another_commit_is_reported_with_both() -> None:
    why = script().same_commit("ab87d9d1234567890\n", "e482170")

    assert why is not None and "e482170" in why and "ab87d9d" in why


@pytest.mark.parametrize(("typed", "taken"), [("ab87d9d", True), ("ab87d9d M14.1", True)])
def test_seven_hexadecimal_characters_are_a_commit(typed: str, taken: bool) -> None:
    assert script().short_commit(typed) is taken


@pytest.mark.parametrize("typed", ["", "ab87d9", "ghijklm", "si"])
def test_anything_else_is_asked_again(typed: str) -> None:
    assert script().short_commit(typed) is False


@pytest.mark.parametrize(
    ("typed", "amount"),
    [("50", "50"), ("50,50", "50.50"), ("$50", "50"), ("50 USD", "50"), (" 0 ", "0")],
)
def test_an_amount_is_read_as_tommaso_types_it(typed: str, amount: str) -> None:
    assert script().dollars_typed(typed) == Decimal(amount)


@pytest.mark.parametrize("typed", ["", "cinquanta", "-1", "inf", "nan"])
def test_what_is_not_an_amount_is_asked_again(typed: str) -> None:
    assert script().dollars_typed(typed) is None


def test_a_cap_below_the_limit_of_the_organization_passes() -> None:
    assert script().under_the_limit("45", Decimal(50)) is None


@pytest.mark.parametrize(("cap", "limit"), [("50", "50"), ("60", "50"), (None, "50")])
def test_a_cap_at_or_above_the_limit_or_no_cap_fails(cap: str | None, limit: str) -> None:
    assert script().under_the_limit(cap, Decimal(limit)) is not None


def result(
    *,
    status: str = "SUCCEEDED",
    model: str = "claude-haiku-4-5-20251001",
    cost: str | None = "0.000412",
    finish: str | None = "end_turn",
    workspace: str | None = "wrkspc_01",
    device: str = HERE,
) -> dict[str, Any]:
    output: dict[str, Any] = {"model": model, "workspace": workspace}
    if finish is not None:
        output["finish_reason"] = finish
    return {
        "status": status,
        "device_id": device,
        "output": output,
        "usage": {"input_tokens": 20, "output_tokens": 30, "cost": cost, "currency": "USD"},
    }


def call(results: list[dict[str, Any]], **given: Any) -> Any:
    settings = {"on_a_node": False, "here": HERE, "workspaces": [], **given}
    return script().the_call(results, "claude-haiku-4-5-20251001", **settings)


def test_a_call_with_its_model_a_cost_and_a_finish_reason_passes() -> None:
    found = call([{"status": "STARTED"}, result()])

    assert found == script().Call(Decimal("0.000412"), "wrkspc_01", HERE)


def test_a_call_of_the_pc_in_the_workspace_of_the_mac_passes() -> None:
    found = call([result(device=PC)], on_a_node=True, workspaces=["wrkspc_01", "wrkspc_01"])

    assert isinstance(found, script().Call)


@pytest.mark.parametrize(
    ("results", "given"),
    [
        ([{"status": "STARTED"}], {}),
        ([result(model="claude-opus-5-5")], {}),
        ([result(cost=None)], {}),
        ([result(finish=None)], {}),
        ([result()], {"on_a_node": True, "workspaces": ["wrkspc_01"]}),
        (
            [result(device=PC, workspace="wrkspc_02")],
            {"on_a_node": True, "workspaces": ["wrkspc_01"]},
        ),
        ([result(device=PC)], {"on_a_node": True, "workspaces": []}),
        ([result(device=PC)], {"on_a_node": True, "workspaces": ["wrkspc_01", "wrkspc_02"]}),
        ([result(device=PC, workspace=None)], {"on_a_node": True, "workspaces": [None]}),
    ],
    ids=[
        "nothing-answered",
        "another-model",
        "no-cost",
        "no-finish-reason",
        "a-node-call-made-here",
        "another-workspace",
        "no-call-of-the-mac-to-compare",
        "the-mac-in-two-workspaces",
        "no-workspace-at-all",
    ],
)
def test_a_call_that_does_not_say_what_it_cost_or_where_fails(
    results: list[dict[str, Any]], given: dict[str, Any]
) -> None:
    assert isinstance(call(results, **given), str)


def ledger(spent: str = "1", reserved: str = "0", open_: int = 0, cap: str = "30") -> Any:
    return script().Ledger.of({"cap": cap, "spent": spent, "reserved": reserved, "open": open_})


@pytest.mark.parametrize(
    ("line", "after", "cost"),
    [
        ("speso invariato", ledger(reserved="4"), None),
        ("prenotato invariato", ledger(spent="1.5"), None),
        ("speso cresciuto del costo", ledger(spent="1.000412"), Decimal("0.000412")),
        ("una prenotazione aperta in più", ledger(reserved="0.232768", open_=1), None),
    ],
)
def test_each_word_of_spesa_holds_when_it_is_so(line: str, after: Any, cost: Any) -> None:
    assert script().ledger_failures([line], ledger(), after, cost) == []


@pytest.mark.parametrize(
    ("line", "after", "cost"),
    [
        ("speso invariato", ledger(spent="1.01"), None),
        ("prenotato invariato", ledger(reserved="4.065536"), None),
        ("speso cresciuto del costo", ledger(spent="1.5"), Decimal("0.000412")),
        ("speso cresciuto del costo", ledger(spent="1.5"), None),
        ("una prenotazione aperta in più", ledger(open_=1), None),
        ("una prenotazione aperta in più", ledger(reserved="0.2", open_=2), None),
    ],
)
def test_each_word_of_spesa_fails_when_it_is_not(line: str, after: Any, cost: Any) -> None:
    assert len(script().ledger_failures([line], ledger(), after, cost)) == 1


def test_a_word_outside_the_vocabulary_of_spesa_is_the_guides_error() -> None:
    with pytest.raises(ValueError, match="vocabulary of spesa"):
        script().ledger_failures(["speso dimezzato"], ledger(), ledger(), None)


def test_the_small_cap_lets_haiku_through_and_not_opus() -> None:
    """Speso + prenotato + 1: the two worst cases of step 4 fall on its two sides."""
    small = script().small_cap(ledger(spent="0.31", reserved="0"))

    assert small == Decimal("1.31")
    assert Decimal("0.31") + Decimal("4.065536") > small
    assert Decimal("0.31") + Decimal("0.216384") <= small
    assert script().said(Decimal("1.3100")) == "1.31"


def test_only_the_started_record_is_a_node_still_silent() -> None:
    module = script()

    assert module.answered_already([{"status": "STARTED"}]) is False
    assert module.answered_already([{"status": "STARTED"}, {"status": "SUCCEEDED"}]) is True


# ----------------------------------------------------------------------------------------
# The rounds of a step: an answer before the Ctrl-C is not a failure (decision 17)
# ----------------------------------------------------------------------------------------


def a_proof(answers: list[str]) -> Any:
    module = script()
    report = module.base.Report(io.StringIO())
    asked: list[str] = []

    def ask(question: str) -> str:
        asked.append(question)
        return answers.pop(0) if answers else ""

    proof = module.Proof(api=None, report=report, ask=ask)
    proof.asked = asked
    return proof


def test_an_answer_before_the_ctrl_c_redoes_the_step_after_the_node_is_restarted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = script()
    rounds: list[int] = []

    def a_round(number: int, todo: Any, proof: Any, round_: int) -> None:
        rounds.append(round_)
        if round_ == 1:
            raise module.Redo("la risposta è arrivata prima del Ctrl-C")
        proof.report.passed(number, "visto", round_)

    monkeypatch.setattr(module, "a_round", a_round)
    proof = a_proof([])

    module.a_step(6, [], proof)

    assert rounds == [1, 2]
    assert proof.report.ok, "a round redone is not a failure, nor a step skipped"
    assert any("SALTATO al giro 1" in line for line in proof.report.lines)
    assert any("Riaccendi il nodo" in question for question in proof.asked)


def test_three_answers_before_the_ctrl_c_skip_the_step(monkeypatch: pytest.MonkeyPatch) -> None:
    module = script()

    def a_round(number: int, todo: Any, proof: Any, round_: int) -> None:
        raise module.Redo("la risposta è arrivata prima del Ctrl-C")

    monkeypatch.setattr(module, "a_round", a_round)
    proof = a_proof([])

    module.a_step(6, [], proof)

    assert proof.report.skipped_steps == [6]
    assert proof.report.failures == 0, "skipped, never failed: it is not ELA's"
    assert not proof.report.ok
