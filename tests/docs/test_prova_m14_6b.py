"""§31 and ``scripts/prova_m14_6b.py`` say the same thing (M14.6b, «La prova a mano»).

The guide is the source of truth, and the script reads it with the reader of M6.3c: this file reads
§31 with the script's own functions and asserts that every marker is a kind the script knows and a
step of the section, that every placeholder is one it fills, that every line of its kinds is in
their vocabulary, and that what steps 3 and 4 expect is what ELA's code says. **Each comparison of
the script has its negative case**, on constructed answers: a check that only ever passes proves
nothing. That ELA answers the plans of steps 3 and 4 as the section expects is proved in
``tests/api/test_examples.py``, on an ELA with a cap and a key that no socket carries.
"""

from __future__ import annotations

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

from ela.domain import ErrorMetadata, WorstCase
from ela.executive.spending import worst_said
from ela.ports import PROVIDER_UNKNOWN_MODEL_HINT
from ela.providers.anthropic.models import HAIKU_5_5, MODELS
from ela.providers.anthropic.pricing import PRICES, worst_cost
from ela.providers.anthropic.settings import DEFAULT_MAX_OUTPUT_TOKENS
from ela.tools.model import placed
from tests.domain.examples import HAIKU_4_5_ID

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prova_m14_6b.py"
PLACEHOLDER = re.compile(r"<[^>\s][^>]*>")
TASK = "6d1c0b2e-0000-4000-8000-000000000001"
RESULT = "6d1c0b2e-0000-4000-8000-000000000002"


@cache
def script() -> ModuleType:
    """The script, loaded by path: ``scripts/`` is not a package."""
    spec = importlib.util.spec_from_file_location("prova_m14_6b", SCRIPT)
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


def lines_of(kind: str, step: int | None = None) -> list[str]:
    return [
        line
        for number, blocks in marked().items()
        for block in blocks
        if block.kind == kind and (step is None or number == step)
        for line in block.lines
    ]


def flat(text: str) -> str:
    return " ".join(text.split())


# ----------------------------------------------------------------------------------------
# The section and the script: kinds, steps, placeholders, vocabulary
# ----------------------------------------------------------------------------------------


def test_every_marker_is_a_kind_the_script_knows_and_belongs_to_a_step_of_the_section() -> None:
    module = script()
    section = guide().split(module.HEADING, 1)[1].split("\n## ", 1)[0]
    headings = {int(number) for number in re.findall(r"^### (\d+)\. ", section, re.MULTILINE)}

    assert marked(), "§31 has no marked block"
    for number, blocks in marked().items():
        assert number in headings, number
        for block in blocks:
            assert block.kind in module.KINDS, (number, block.kind)
    assert headings == {1, 2, 3, 4}
    assert set(marked()) == {2, 3, 4}, "step 1 is the script's own"


def test_every_kind_of_the_script_is_used_by_the_section() -> None:
    used = {block.kind for blocks in marked().values() for block in blocks}

    assert used == set(script().KINDS)


def test_every_placeholder_is_one_the_script_fills() -> None:
    module = script()
    for blocks in marked().values():
        for block in blocks:
            for found in PLACEHOLDER.findall(block.body):
                assert found in module.PLACEHOLDERS, found


def test_every_line_of_the_scripts_kinds_is_in_its_vocabulary() -> None:
    assert script().outside_vocabulary(marked()) == []


@pytest.mark.parametrize(
    ("kind", "line"),
    [
        ("spesa", "speso dimezzato"),
        ("costo", HAIKU_4_5_ID),
        ("ricalcolo", "fascia alta"),
        ("ottobre", HAIKU_5_5),
        ("ottobre", ""),
        ("costo", f"{HAIKU_5_5}\n{HAIKU_5_5}"),
    ],
    ids=["spesa", "costo", "ricalcolo", "ottobre", "ottobre-empty", "costo-two-lines"],
)
def test_a_line_outside_the_vocabulary_of_its_kind_is_found(kind: str, line: str) -> None:
    module = script()
    block = module.base.Block(9, kind, f"{line}\n")

    (wrong,) = module.outside_vocabulary({9: [block]})
    assert wrong.startswith(f"9.{kind}: ")


def test_the_plans_the_section_sends_are_the_two_of_the_spec() -> None:
    sent = [line for line in lines_of("comando") if "--file" in line]

    assert [line.split("--file", 1)[1].strip() for line in sent] == [
        "docs/examples/ask-model-gone.json",
        "docs/examples/ask-model-routine.json",
    ]


def test_the_script_touches_neither_the_env_nor_the_database_nor_ela_serve() -> None:
    """Decision 13: it reads ELA through the API and the CLI. No setting of the ``.env`` is read
    by the script itself, nothing of the persistence is imported, and no line starts ELA."""
    source = SCRIPT.read_text(encoding="utf-8")

    assert "composition.settings" not in source
    assert "persistence" not in source and "sqlite" not in source
    assert all("serve" not in line.split() for line in lines_of("comando") + lines_of("schermo"))
    assert "tetto" not in script().KINDS


def test_the_file_is_in_downloads_with_the_name_of_the_milestone() -> None:
    out = script().default_out()

    assert out.parent == Path.home() / "Downloads"
    assert out.name.startswith("prova-m14.6b-") and out.suffix == ".txt"


# ----------------------------------------------------------------------------------------
# What steps 3 and 4 expect is what the code says
# ----------------------------------------------------------------------------------------


def test_the_reason_step_3_expects_is_the_gate_s_with_where_the_hint_is() -> None:
    """The provider's words, the place the tool adds (ADR 0067 §3), and the gate's frame —
    the same sentence ``tests/api/test_examples.py`` reads from the run of the same plan."""
    refused = ErrorMetadata(
        code=PROVIDER_UNKNOWN_MODEL_HINT, message=f"no model for hint {HAIKU_4_5_ID!r}"
    )
    said = placed(refused, None, HAIKU_4_5_ID).message
    reason = (
        f"deny_by_cap: EXECUTING -> DENIED (this call cannot be bounded: "
        f"{PROVIDER_UNKNOWN_MODEL_HINT}: {said})"
    )

    assert f"reason {reason}" in [flat(line) for line in lines_of("atteso", 3)]


def test_the_question_step_4_expects_is_the_worst_case_of_the_cheap_route() -> None:
    model = MODELS[HAIKU_5_5]
    output = DEFAULT_MAX_OUTPUT_TOKENS
    worst = WorstCase(
        amount=worst_cost(model, output_tokens=output),
        currency="USD",
        model=HAIKU_5_5,
        input_tokens=model.context_window - output,
        output_tokens=output,
    )

    assert f"worst case {worst_said(worst)}" in [flat(line) for line in lines_of("atteso", 4)]
    assert worst.amount == script().NEEDED
    assert "0,508192 $" in guide().split(script().HEADING, 1)[1].split("\n## ", 1)[0]


def test_the_cost_is_read_on_the_cheap_model_and_october_on_the_model_that_left() -> None:
    assert lines_of("costo") == [HAIKU_5_5]
    assert lines_of("ottobre") == [HAIKU_4_5_ID]
    assert HAIKU_4_5_ID not in MODELS


def test_the_eye_of_step_3_is_the_only_one_and_comes_after_the_screen() -> None:
    """Answer 24: one ``occhio``, at step 3, on the reason of the refusal."""
    eyes = [
        (number, block)
        for number, blocks in marked().items()
        for block in blocks
        if block.kind == "occhio"
    ]
    kinds = [block.kind for block in marked()[3]]

    assert [number for number, _ in eyes] == [3]
    assert kinds.index("schermo") < kinds.index("occhio")
    assert "model_hint" in eyes[0][1].body


# ----------------------------------------------------------------------------------------
# ``ottobre``: finding the call, and reading it
# ----------------------------------------------------------------------------------------


def answered(**update: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": RESULT,
        "status": "SUCCEEDED",
        "output": {"model": HAIKU_4_5_ID, "output": "il testo del modello"},
        "usage": {"input_tokens": 40, "output_tokens": 55, "cost": "0.000315"},
    }
    result.update(update)
    return result


def october(**update: Any) -> dict[str, Any]:
    task: dict[str, Any] = {"id": TASK, "created_at": "2026-10-07T19:30:00Z", "state": "COMPLETED"}
    task.update(update)
    return task


def test_a_call_of_october_on_the_model_with_its_cost_is_found() -> None:
    found = script().an_october_call([october()], lambda _: [answered()], HAIKU_4_5_ID)

    assert found == (october(), answered())


@pytest.mark.parametrize(
    ("task", "result"),
    [
        (october(created_at="2026-11-02T09:00:00Z"), answered()),
        (october(), answered(output={"model": HAIKU_5_5})),
        (october(), answered(usage={"input_tokens": 1, "output_tokens": 1, "cost": None})),
        (october(), answered(status="FAILED")),
    ],
    ids=["another-month", "another-model", "no-cost", "not-answered"],
)
def test_anything_else_is_not_a_call_of_october(
    task: dict[str, Any], result: dict[str, Any]
) -> None:
    assert script().an_october_call([task], lambda _: [result], HAIKU_4_5_ID) is None


def printed(stdout: str, code: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["ela"], code, stdout, "")


def test_what_the_cli_prints_of_the_results_is_what_the_api_gave() -> None:
    assert script().printed_results_failures(printed(json.dumps([answered()])), answered()) == []


@pytest.mark.parametrize(
    ("done", "said"),
    [
        (printed("[]", 1), "esce con 1"),
        (printed("non json"), "non stampa JSON"),
        (printed("[]"), "non stampa il risultato"),
        (
            printed(json.dumps([{"id": RESULT, "output": {"model": "x"}, "usage": {"cost": "1"}}])),
            "il modello 'x'",
        ),
        (
            printed(
                json.dumps(
                    [{"id": RESULT, "output": {"model": HAIKU_4_5_ID}, "usage": {"cost": "0.1"}}]
                )
            ),
            "il costo 0.1",
        ),
    ],
    ids=["exit", "not-json", "missing", "model", "cost"],
)
def test_a_cli_that_says_otherwise_is_found(
    done: subprocess.CompletedProcess[str], said: str
) -> None:
    failures = script().printed_results_failures(done, answered())

    assert failures and said in "; ".join(failures)


def test_show_answers_with_the_state_and_neither_model_nor_cost() -> None:
    module = script()
    shown = printed(f"id  {TASK}\nstate  COMPLETED\nreason  —\n")

    assert module.shown_failures(shown, "COMPLETED", HAIKU_4_5_ID, Decimal("0.000315")) == []


@pytest.mark.parametrize(
    ("done", "said"),
    [
        (printed("", 2), "esce con 2"),
        (printed("state FAILED\n"), "non dice lo stato COMPLETED"),
        (printed(f"state COMPLETED\nmodel {HAIKU_4_5_ID}\n"), f"nomina {HAIKU_4_5_ID}"),
        (printed("state COMPLETED\ncost 0.000315\n"), "dice il costo 0.000315"),
    ],
    ids=["exit", "state", "model", "cost"],
)
def test_a_show_that_says_too_much_or_too_little_is_found(
    done: subprocess.CompletedProcess[str], said: str
) -> None:
    failures = script().shown_failures(done, "COMPLETED", HAIKU_4_5_ID, Decimal("0.000315"))

    assert failures and said in "; ".join(failures)


class NoOctober:
    """The API of a database without the rows of October."""

    def get(self, path: str) -> Any:
        assert path == "/tasks", path
        return []


def test_without_a_task_of_october_the_step_is_skipped_with_why_and_nothing_fails() -> None:
    """Answer 28: not a precondition that stops — SALTATO, with the reason written, and the proof
    goes on. A proof with a SALTATO has not passed (decision B of M6.3c)."""
    module = script()
    report = module.Report(io.StringIO())
    proof = module.Proof(NoOctober(), report, lambda _: "s")
    block = module.base.Block(2, "ottobre", f"{HAIKU_4_5_ID}\n")

    module.an_october(2, block, proof)

    assert report.skipped_steps == [2] and report.failures == 0
    assert any("SALTATO" in line and HAIKU_4_5_ID in line for line in report.lines)
    assert not report.ok


# ----------------------------------------------------------------------------------------
# ``ricalcolo``: the cost at the low tier of the list
# ----------------------------------------------------------------------------------------


def cheap_call(
    tokens_in: int = 30, tokens_out: int = 20, cost: str | None = None
) -> dict[str, Any]:
    price = PRICES[HAIKU_5_5]
    written = (price.input * tokens_in + price.output * tokens_out) / Decimal(1_000_000)
    return {
        "status": "SUCCEEDED",
        "output": {"model": HAIKU_5_5},
        "usage": {
            "input_tokens": tokens_in,
            "output_tokens": tokens_out,
            "cached_input_tokens": None,
            "cost": str(written) if cost is None else cost,
        },
    }


def test_a_cost_the_low_tier_gives_on_the_call_s_tokens_passes() -> None:
    assert script().low_tier_failures(cheap_call()) == []


@pytest.mark.parametrize(
    ("found", "said"),
    [
        (None, "non ha una chiamata"),
        ({"output": {"model": "claude-opus-5-5"}, "usage": {}}, "non ha una fascia bassa"),
        ({"output": {"model": HAIKU_5_5}, "usage": {"input_tokens": None}}, "non ha i token"),
        (cheap_call(tokens_in=100_001), "sopra la fascia bassa"),
        (cheap_call(cost="0.5"), "la fascia bassa dà"),
        (
            {**cheap_call(), "usage": {**cheap_call()["usage"], "cost": None}},
            "non ha un costo",
        ),
    ],
    ids=["no-call", "no-tiers", "no-tokens", "above-the-bound", "another-cost", "no-cost"],
)
def test_a_call_the_low_tier_does_not_price_is_found(
    found: dict[str, Any] | None, said: str
) -> None:
    failures = script().low_tier_failures(found)

    assert failures and said in "; ".join(failures)
