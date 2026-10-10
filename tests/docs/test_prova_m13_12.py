"""Section 27 of the guide and ``scripts/prova_m13_12.py`` say the same thing (M13.12, «La prova a
mano»; decisions 14 and 21).

The guide is the source of truth, and the script reads it with the reader of M6.3c: this file reads
the section with the script's own functions and asserts that every marker is a kind the script knows
and a step of the section, that every placeholder is one it fills, and that every line of its kinds
is in their vocabulary. **Each comparison of the script has its negative case.**

**Every kind that reads the API is fed the answers of the real routes**, recorded once by
``tests/docs/real_policies.py``, with the output of the command line next to them — the form of
``tests/docs/test_prova_m14_3.py``. A negative case starts from a real answer and changes it.
"""

from __future__ import annotations

import copy
import importlib.util
import io
import re
import subprocess
import sys
from decimal import Decimal
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.composition.support import (  # noqa: F401 — re-exported as a fixture
    _only_the_declared_environment,
)
from tests.docs.real_policies import Real, record

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prova_m13_12.py"
PLACEHOLDER = re.compile(r"<[^>\s][^>]*>")

SIBLINGS = ("prova_m6_3c", "prova_m14_1", "prova_m14_2", "prova_m14_3")
"""The scripts ``prova_m13_12`` imports, imported anew for it: one world, never two copies."""


@cache
def script() -> ModuleType:
    found = {name: sys.modules.pop(name, None) for name in SIBLINGS}
    try:
        spec = importlib.util.spec_from_file_location("prova_m13_12", SCRIPT)
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


def blocks_of(kind: str) -> list[Any]:
    return [block for blocks in marked().values() for block in blocks if block.kind == kind]


def test_the_script_and_its_siblings_are_one_world() -> None:
    module = script()

    assert module.guided.base is module.base
    assert module.guided.spending is module.spending
    assert module.guided.planning is module.planning


# ----------------------------------------------------------------------------------------
# The section and the script
# ----------------------------------------------------------------------------------------


def test_every_marker_is_a_kind_the_script_knows_and_belongs_to_a_step_of_the_section() -> None:
    headings = {int(number) for number in re.findall(r"^### (\d+)\. ", section(), re.MULTILINE)}
    found = marked()

    assert found, "section 27 has no marked block: the script would do nothing"
    assert set(found) <= headings
    assert set(found) == set(range(2, 10)), "steps 2 to 9; step 1 is the script's own"
    assert all(block.kind in script().KINDS for blocks in found.values() for block in blocks)
    every_marker = re.findall(r"<!-- prova: (\d+)\.(\w+) -->", section())
    assert len(every_marker) == sum(len(blocks) for blocks in found.values())


def test_it_comes_after_section_26_and_before_where_to_look() -> None:
    text = guide()
    assert text.index("## 26. ") < text.index("## 27. ") < text.index("## Dove guardare dopo")


def test_every_kind_of_the_script_is_used_by_the_section() -> None:
    used = {block.kind for blocks in marked().values() for block in blocks}
    assert used == set(script().KINDS)


def test_every_placeholder_is_one_the_script_fills() -> None:
    found = {
        one
        for blocks in marked().values()
        for block in blocks
        for one in PLACEHOLDER.findall(block.body)
    }
    assert found <= set(script().PLACEHOLDERS)
    assert script().POLICY in found


def test_the_legend_of_the_guide_explains_the_placeholder_of_the_policy() -> None:
    assert f"| `{script().POLICY}` |" in guide()


def test_every_plan_the_section_sends_is_one_session_on_the_sites_of_the_proof() -> None:
    module = script()
    plans = [
        plan for sessions in module.sessions_by_step(marked()).values() for plan, _ in sessions
    ]

    assert len(plans) == 6
    for plan in plans:
        arguments = module.guided.arguments_of(plan)
        assert set(arguments["sites"]) <= set(module.SITES), plan.name
        assert "task_type" not in arguments, plan.name


def test_the_sessions_that_start_are_those_of_steps_5_and_7() -> None:
    sessions = script().sessions_by_step(marked())

    starting = {number for number, its in sessions.items() for _, asks in its if not asks}
    asking = {number for number, its in sessions.items() for _, asks in its if asks}
    assert starting == {5, 7}
    assert asking == {2, 6, 8}


def block(number: int, kind: str, body: str) -> Any:
    return script().base.Block(number, kind, body)


PLAN = "uv run ela task plan <id> --file docs/examples/policy-youtube.json"


def test_a_plan_with_no_question_after_it_starts_and_one_with_it_asks() -> None:
    module = script()
    starts = {5: [block(5, "comando", PLAN), block(5, "atteso", "outcome completed")]}
    asks = {2: [block(2, "comando", PLAN), block(2, "atteso", "outcome waiting_approval")]}
    alone = {7: [block(7, "comando", PLAN), block(7, "sfondo", "uv run ela task run <id>")]}

    assert module.sessions_by_step(starts) == {5: [(ROOT / PLAN.split()[-1], False)]}
    assert module.sessions_by_step(asks) == {2: [(ROOT / PLAN.split()[-1], True)]}
    assert module.sessions_by_step(alone) == {7: [(ROOT / PLAN.split()[-1], False)]}
    assert module.sessions_by_step({3: [block(3, "comando", "uv run ela policy list")]}) == {}


def test_the_margin_is_step_by_step_and_the_section_writes_it() -> None:
    """Step 8 asks the most: the two sessions started before it, and its own question."""
    module = script()
    sessions = module.sessions_by_step(marked())
    needed = module.needed_by_step(sessions, module.priced)

    assert module.the_most(needed) == (8, Decimal("3.30"))
    assert needed[6] == Decimal("3.10")
    assert "**3,30 $**" in flat()
    every = sum((module.priced(plan) for its in sessions.values() for plan, _ in its), Decimal(0))
    assert every == Decimal("7.50"), "the sum of the plans, which the margin is not"


def test_a_session_that_asks_counted_as_started_would_ask_for_more() -> None:
    module = script()
    one, two = ROOT / "a.json", ROOT / "b.json"
    price = {one: Decimal("1.10"), two: Decimal("2.00")}.__getitem__

    asking = module.needed_by_step({2: [(two, True)], 5: [(one, False)], 8: [(one, True)]}, price)
    started = module.needed_by_step({2: [(two, False)], 5: [(one, False)], 8: [(one, True)]}, price)

    assert module.the_most(asking) == (8, Decimal("2.20"))
    assert module.the_most(started) == (8, Decimal("4.20"))


def test_every_line_of_the_scripts_kinds_is_in_its_vocabulary() -> None:
    module = script()

    assert [module.policy_line(one) for b in blocks_of("policy") for one in b.lines] == [
        ("LIVE", 0),
        ("LIVE", 1),
        ("LIVE", 2),
        ("REVOKED", 2),
    ]
    assert [b.lines for b in blocks_of("console")] == [[module.BY_A_CONSOLE]]
    assert [b.lines for b in blocks_of("nessuna")] == [[module.NONE_LIVE]]
    whys = [one for b in blocks_of("perché") for one in b.lines]
    assert whys[0] == module.NOBODY
    assert all(module.POLICY in one for one in whys[1:])
    (creation,) = blocks_of("crea")
    (line,) = creation.lines
    assert module.CONFIRM not in line


@pytest.mark.parametrize("line", ["LIVE", "LIVE one", "ALIVE 1", "LIVE 1 2"])
def test_a_line_of_policy_outside_its_vocabulary_is_the_guides_error(line: str) -> None:
    with pytest.raises(ValueError, match="vocabulary of policy"):
        script().policy_line(line)


def test_the_file_is_in_downloads_with_the_name_of_the_milestone() -> None:
    out = script().default_out()
    assert out.parent == Path.home() / "Downloads"
    assert out.name.startswith("prova-m13.12-")


def test_the_migration_it_wants_is_the_head_of_the_tree() -> None:
    versions = sorted(path.name for path in (ROOT / "migrations" / "versions").glob("0*.py"))
    assert versions[-1].startswith("0015_")
    assert script().MIGRATION == "0015 (head)"
    assert "`0015 (head)`" in section()


def test_the_margin_says_both_numbers_when_it_is_short() -> None:
    module = script()

    assert module.margin_short("3.30", 8, Decimal("3.30")) is None
    said = module.margin_short("3.29", 8, Decimal("3.30"))
    assert said is not None and "3.29" in said and "3.30" in said and "passo 8" in said
    assert module.margin_short(None, 8, Decimal("3.30")) is not None


# ----------------------------------------------------------------------------------------
# The world, recorded
# ----------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real(tmp_path_factory: pytest.TempPathFactory) -> Real:
    return record(tmp_path_factory)


def short_of(real: Real) -> str:
    (policy,) = real.policies_live["policies"]
    return str(policy["short"])


def test_the_route_of_the_policies_is_in_the_schema_the_script_reads(real: Real) -> None:
    assert script().POLICIES_ROUTE in real.openapi["paths"]


def outputs_of(real: Real) -> dict[int, list[str]]:
    """What the commands before each ``atteso`` of the section printed, step by step."""
    return {
        2: [real.none.waiting_output, real.approvals_output, real.none.cancel_output],
        3: ["\n".join(real.refusals)],
        4: [real.list_output],
        5: [real.covered_output, real.show_output],
        6: [
            real.above.waiting_output,
            real.above.cancel_output,
            real.outside.waiting_output,
            real.outside.cancel_output,
        ],
        8: [real.revoke_output, real.revoked.waiting_output, real.revoked.cancel_output],
    }


def expected_of(number: int, real: Real) -> list[list[str]]:
    return [
        [one.replace(script().POLICY, short_of(real)) for one in found.lines]
        for found in marked()[number]
        if found.kind == "atteso"
    ]


def test_every_atteso_is_what_the_command_line_printed(real: Real) -> None:
    module = script()
    outputs = outputs_of(real)

    assert {number for number, its in marked().items() if any(b.kind == "atteso" for b in its)} == (
        set(outputs)
    )
    for number, printed in outputs.items():
        expected = expected_of(number, real)
        assert len(expected) == len(printed), number
        for lines, output in zip(expected, printed, strict=True):
            assert module.base.missing(lines, output) == [], (number, lines, output)


def test_an_atteso_against_another_output_is_missing_its_lines(real: Real) -> None:
    module = script()
    (listed,) = expected_of(4, real)

    assert module.base.missing(listed, real.preview_output) != []
    assert module.base.missing(expected_of(3, real)[0], "\n".join(real.refusals[:3])) != []


def whys_of(real: Real) -> list[list[str]]:
    return [
        [str(line) for one in asked.question for line in one.get("why") or []]
        for asked in (real.none, real.above, real.outside, real.revoked)
    ]


def test_the_why_of_every_question_is_the_one_the_section_expects(real: Real) -> None:
    module = script()
    expected = [
        one.replace(module.POLICY, short_of(real)) for b in blocks_of("perché") for one in b.lines
    ]

    for line, why in zip(expected, whys_of(real), strict=True):
        assert module.why_failures(line, why)[0] == [], (line, why)


def test_a_why_that_is_not_the_one_expected_fails(real: Real) -> None:
    module = script()
    _, above, outside, revoked = whys_of(real)
    expected_above = f"max_cost_usd 2.00 is above the 1.10 of policy {short_of(real)}"

    assert module.why_failures(module.NOBODY, above)[0]
    assert module.why_failures(expected_above, outside)[0]
    assert module.why_failures(expected_above.replace(short_of(real), "00000000"), above)[0]
    assert module.why_failures(module.NOBODY, [])[0]
    covering = [f"policy {short_of(real)} covers this call: this step asks again for the yes"]
    assert module.why_failures(module.NOBODY, covering)[0]


def test_from_the_second_round_only_ended_policies_are_accepted_for_none(real: Real) -> None:
    """Decision 21: the policies of the rounds before, revoked or expired, and never a live one."""
    module = script()
    _, above, _, revoked = whys_of(real)
    expired = [f"policy {short_of(real)} expired on 2026-10-10"]

    assert module.why_failures(module.NOBODY, revoked) == (
        [],
        module.why_failures(module.NOBODY, expired)[1],
    )
    assert module.why_failures(module.NOBODY, [*revoked, *above])[0]
    assert module.why_failures(module.NOBODY, [module.NOBODY])[1].startswith("al primo giro")


def test_the_states_of_the_policy_are_read_from_its_list(real: Real) -> None:
    module = script()
    live, used, revoked = (
        real.policies_live["policies"][0],
        real.policies_used["policies"][0],
        real.policies_revoked["policies"][0],
    )

    assert module.policy_failures("LIVE 0", live) == []
    assert module.policy_failures("LIVE 1", used) == []
    assert module.policy_failures("REVOKED 1", revoked) == []
    assert module.policy_failures("LIVE 1", live)
    assert module.policy_failures("REVOKED 1", used)
    assert module.policy_failures("LIVE 0", None)


def test_the_policy_a_console_created_and_revoked_is_found(real: Real) -> None:
    module = script()
    policies = real.console_policies["policies"]
    proof = str(real.policies_live["policies"][0]["id"])

    assert module.console_failures(policies, [proof]) == []
    only_the_proofs = [one for one in policies if one["id"] == proof]
    assert module.console_failures(only_the_proofs, [proof])
    still_live = copy.deepcopy(policies)
    for one in still_live:
        one["state"] = "LIVE"
    assert module.console_failures(still_live, [proof])
    by_the_core = copy.deepcopy(policies)
    for one in by_the_core:
        one["created_by"]["role"] = "LOCAL"
    assert module.console_failures(by_the_core, [proof])


def test_the_short_id_is_read_from_the_creation_and_never_from_the_preview(real: Real) -> None:
    module = script()

    assert module.created_short(real.created_output) == short_of(real)
    assert module.created_short(real.preview_output) is None
    assert module.NOT_CREATED in real.preview_output


def test_live_counts_only_the_live_ones(real: Real) -> None:
    module = script()

    assert len(module.live(real.policies_live["policies"])) == 1
    assert module.live(real.after_preview["policies"]) == []
    assert module.live(real.policies_revoked["policies"]) == []


# ----------------------------------------------------------------------------------------
# The kinds, on the recorded answers
# ----------------------------------------------------------------------------------------


class Answers:
    """An API that answers what the real one answered, by path: a list per path, each answer once
    and the last for ever; and the posts it was sent."""

    def __init__(self, answers: dict[str, list[Any]]) -> None:
        self.answers = {path: list(found) for path, found in answers.items()}
        self.posted: list[str] = []

    def get(self, path: str) -> Any:
        found = self.answers.get(path)
        if not found:
            raise AssertionError(f"the script asked {path}, which this test did not record")
        return copy.deepcopy(found.pop(0) if len(found) > 1 else found[0])

    def post(self, path: str, body: Any = None) -> Any:
        self.posted.append(path)
        return {}

    def close(self) -> None:
        return None


def proof_on(real: Real, answers: dict[str, list[Any]], said: list[str] | None = None) -> Any:
    module = script()

    def ask(question: str) -> str:
        return said.pop(0) if said else "s"

    return module.Proof(
        api=Answers(answers),
        report=module.base.Report(io.StringIO()),
        ask=ask,
        start=module.spending.Ledger.of(real.spend_start),
    )


def walked(proof: Any, todo: dict[int, list[Any]], turn: Any = None) -> None:
    module = script()

    def one(number: int, its: list[Any]) -> None:
        module.a_step(number, its, proof, turn)

    module.base.walk(proof.report, todo, one)


def test_none_live_passes_and_a_policy_born_where_it_should_not_is_revoked(real: Real) -> None:
    clean = proof_on(real, {"/policies": [real.policies_empty]})
    walked(clean, {3: [block(3, "nessuna", script().NONE_LIVE)]})
    born = proof_on(real, {"/policies": [real.policies_live]})
    walked(born, {3: [block(3, "nessuna", script().NONE_LIVE)]})

    assert clean.report.ok, clean.report.lines
    assert born.report.failures == 1
    (policy,) = real.policies_live["policies"]
    assert born.api.posted == [f"/policies/{policy['id']}/revoke"]


def creation_on(
    real: Real,
    monkeypatch: pytest.MonkeyPatch,
    policies: list[Any],
    said: list[str],
    created: str | None = None,
) -> tuple[Any, list[str]]:
    module = script()
    ran: list[str] = []

    def run(line: str) -> subprocess.CompletedProcess[str]:
        ran.append(line)
        printed = real.preview_output if module.CONFIRM not in line else created
        return subprocess.CompletedProcess(line, 0, printed or real.created_output, "")

    monkeypatch.setattr(module.base, "run", run)
    proof = proof_on(real, {"/policies": policies}, said)
    (creation,) = blocks_of("crea")
    walked(proof, {4: [creation]})
    return proof, ran


def test_the_creation_shows_the_preview_and_creates_only_after_a_yes(
    real: Real, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = script()
    proof, ran = creation_on(real, monkeypatch, [real.after_preview, real.policies_live], ["s"])
    (line,) = blocks_of("crea")[0].lines

    assert ran == [line, line + module.CONFIRM]
    assert proof.report.ok, proof.report.lines
    (policy,) = real.policies_live["policies"]
    assert proof.policy == (policy["id"], policy["short"])


def test_a_no_to_the_creation_stops_the_proof(real: Real, monkeypatch: pytest.MonkeyPatch) -> None:
    module = script()
    proof, ran = creation_on(real, monkeypatch, [real.after_preview], ["n"])

    assert len(ran) == 1 and proof.policy is None
    assert proof.report.stopped == (4, module.SAID_NO)


def test_a_preview_that_created_fails_and_stops(
    real: Real, monkeypatch: pytest.MonkeyPatch
) -> None:
    proof, ran = creation_on(real, monkeypatch, [real.policies_live], ["s"])

    assert len(ran) == 1
    assert proof.report.failures == 1 and proof.report.stopped is not None


def test_a_creation_that_printed_no_policy_fails_and_stops(
    real: Real, monkeypatch: pytest.MonkeyPatch
) -> None:
    proof, _ = creation_on(
        real, monkeypatch, [real.after_preview, real.policies_live], ["s"], created="not created"
    )

    assert proof.report.failures == 1 and proof.report.stopped is not None
    assert proof.policy is None


def test_the_why_kind_reads_the_question_of_the_task(real: Real) -> None:
    module = script()
    asked = proof_on(real, {"/approvals": [real.none.question]})
    walked(
        asked, {2: [block(2, "perché", module.NOBODY)]}, module.guided.Turn(task_id=real.none.task)
    )
    wrong = proof_on(real, {"/approvals": [real.above.question]})
    walked(
        wrong, {2: [block(2, "perché", module.NOBODY)]}, module.guided.Turn(task_id=real.above.task)
    )

    assert asked.report.ok, asked.report.lines
    assert f"    | why I ask: {module.NOBODY}" in asked.report.lines
    assert wrong.report.failures == 1


def test_the_policy_kind_reads_the_policy_of_step_4(real: Real) -> None:
    module = script()
    (policy,) = real.policies_used["policies"]
    proof = proof_on(real, {"/policies?all=true": [real.policies_used]})
    proof.policy = (policy["id"], policy["short"])
    walked(proof, {5: [block(5, "policy", "LIVE 1")]})
    wrong = proof_on(real, {"/policies?all=true": [real.policies_used]})
    wrong.policy = proof.policy
    walked(wrong, {5: [block(5, "policy", "LIVE 0")]})
    none = proof_on(real, {})
    walked(none, {5: [block(5, "policy", "LIVE 0")]})

    assert proof.report.ok, proof.report.lines
    assert wrong.report.failures == 1 and none.report.failures == 1
    assert module.filled(f"policy {module.POLICY}", module.guided.Turn(), proof) == (
        f"policy {policy['short']}"
    )
    assert module.filled(module.POLICY, module.guided.Turn(), none) == module.POLICY


def test_the_console_kind_wants_no_question_waiting_and_a_revoked_policy(real: Real) -> None:
    module = script()
    (mine,) = real.policies_live["policies"]
    line = module.BY_A_CONSOLE

    def on(approvals: Any, said: list[str]) -> Any:
        proof = proof_on(
            real, {"/approvals": [approvals], "/policies?all=true": [real.console_policies]}, said
        )
        proof.policy = (mine["id"], mine["short"])
        walked(proof, {9: [block(9, "console", line)]})
        return proof

    passed, waiting, refused = on([], ["s"]), on(real.none.question, ["s"]), on([], ["n"])

    assert passed.report.ok, passed.report.lines
    assert waiting.report.failures == 1
    assert refused.report.refused == [9]
    with pytest.raises(ValueError, match="vocabulary of console"):
        walked(proof_on(real, {}), {9: [block(9, "console", "una policy qualunque")]})


def test_a_kind_the_section_does_not_have_is_the_guides_error(real: Real) -> None:
    with pytest.raises(ValueError, match="not a kind of the section"):
        walked(proof_on(real, {}), {2: [block(2, "fascia", "<id>")]})


def test_step_1_stops_on_a_live_policy(real: Real, monkeypatch: pytest.MonkeyPatch) -> None:
    module = script()
    monkeypatch.setattr(module.base, "Api", lambda: Answers({"/policies": [real.policies_live]}))
    said = module.no_live_policy()
    monkeypatch.setattr(module.base, "Api", lambda: Answers({"/policies": [real.policies_empty]}))

    assert said is not None and short_of(real) in said
    assert module.no_live_policy() is None
