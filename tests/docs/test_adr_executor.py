"""The tables of ADR 0013 and the executor/tools describe the same code.

Same pattern as the other ADR tests: §5 (outcome → engine operation → error code) against the
engine's tables and the executor's constants, §6 (rule → consumes) — **every** such table in
``docs/adr/``, not ADR 0013's alone (M13.1b) — against ``CONSUMING_RULES``,
§11 (capability → tool → name → output → error codes) against ``tools_v01`` and the tools' own
declarations. Each table has a distinctive row shape, so no other table test mistakes it.

An ADR is immutable, so a tool that arrives later is documented by *its* ADR, under the label
``Tool aggiunti:`` (ADR 0021 §9), exactly as a port extended later is
documented under ``Port estesi:``; a tool that *changes* later is documented under
``Tool sostituiti:`` (ADR 0022 §9), and the replacing row wins. Additions apply first, then
replacements — the same order ``test_adr_ports.py`` reads its tables in. The union is what the
code must match, and a capability added twice, or replaced before it exists, is a drift of its
own.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ela.executive import CONSUMING_RULES, GRANT_VANISHED, TOOL_EXCEPTION, TOOL_REFUSED
from ela.permissions import Rule, catalogue_v01
from ela.tasks.engine import OPERATIONS, STEP_OPERATIONS
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeModelProvider
from ela.tools import Tool, tools_v01
from tests.routing.support import routing_for

ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "adr"
ADR_PATH = ADR_DIR / "0013-executor.md"
ADDING_TOOLS = "Tool aggiunti:"
REPLACING_TOOLS = "Tool sostituiti:"
ADDING_ADRS = ((ADR_DIR / "0021-started-protocol-and-model-complete.md", ADDING_TOOLS),)
"""ADRs that add a tool after ADR 0013: the label, then the table, read as ADR 0013's is."""
REPLACING_ADRS = (
    (ADR_DIR / "0022-model-router.md", REPLACING_TOOLS),
    (ADR_DIR / "0045-filesystem-and-high.md", REPLACING_TOOLS),
)
"""ADRs that change a tool documented earlier (ADR 0022 §9: the router gives ``model.complete``
two output keys and the routing codes). A replacement names a capability that already has a row,
and its row is the one the code must match."""
OUTCOME_ROW = re.compile(r"^\| `(ALLOWED|DENIED|REQUIRES_APPROVAL)`(.*?) \| `(\w+)` \| (.+) \|$")
RULE_ROW = re.compile(r"^\| `([A-Z_]+)` \| (sì|no) \|$")
CONSUMING_HEADER = "| Regola | Consuma |"
TOOL_ROW = re.compile(r"^\| `([a-z_.]+)` \| `(\w+)` \| `([\w-]+)` \| (.+?) \| (.+?) \|$")
CODE = re.compile(r"`([^`]+)`")
EXECUTOR_CODES = {GRANT_VANISHED, TOOL_REFUSED, TOOL_EXCEPTION}


def documented_outcomes(text: str) -> list[tuple[str, str, str]]:
    """(outcome and condition, engine operation, code cell) per row of the §5 table."""
    rows = [
        (outcome + condition, operation, code)
        for line in text.splitlines()
        for outcome, condition, operation, code in [
            match.groups() for match in [OUTCOME_ROW.match(line)] if match is not None
        ]
    ]
    assert rows, "ADR 0013 must contain the outcomes table"
    return rows


def documented_consuming_rules(text: str) -> dict[Rule, bool]:
    """The rows of the «Regola | Consuma» table in ``text``: the lines right under its header."""
    lines = text.splitlines()
    assert CONSUMING_HEADER in lines, f"no {CONSUMING_HEADER!r} table here"
    rows: dict[Rule, bool] = {}
    for line in lines[lines.index(CONSUMING_HEADER) + 2 :]:
        match = RULE_ROW.match(line)
        if match is None:
            break
        rows[Rule(match.group(1))] = match.group(2) == "sì"
    assert rows, f"the {CONSUMING_HEADER!r} table has no row a rule can be read from"
    return rows


def adr_documents() -> list[tuple[str, str]]:
    """Every ADR, as (file name, text), in the order of its number — the order of time."""
    return [
        (path.name, path.read_text(encoding="utf-8"))
        for path in sorted(ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md"))
    ]


def consuming_answers(
    documents: list[tuple[str, str]],
) -> tuple[dict[Rule, tuple[bool, str]], list[str]]:
    """What every «Regola | Consuma» table of ``documents`` says, the most recent winning.

    An ADR is immutable, so a later one adds its rows under the same header (ADR 0045 §3 did, for
    ``APPROVAL_EVERY_USE``); until M13.1b only ADR 0013's was read, and the row ADR 0045 added was
    a promise no test held. When two tables disagree about a rule, the later ADR is the decision
    in force — and the disagreement is returned, so the message can say which one was overridden.
    """
    answers: dict[Rule, tuple[bool, str]] = {}
    overridden: list[str] = []
    for name, text in documents:
        if CONSUMING_HEADER not in text.splitlines():
            continue
        for rule, consumes in documented_consuming_rules(text).items():
            earlier = answers.get(rule)
            if earlier is not None and earlier[0] != consumes:
                overridden.append(
                    f"{rule.value}: {earlier[1]} says {_word(earlier[0])}, {name} says "
                    f"{_word(consumes)} — the most recent wins"
                )
            answers[rule] = (consumes, name)
    return answers, overridden


def _word(consumes: bool) -> str:
    return "sì" if consumes else "no"


def consuming_message(answers: dict[Rule, tuple[bool, str]], overridden: list[str]) -> str:
    rows = [f"  {rule.value}: {_word(c)} ({source})" for rule, (c, source) in answers.items()]
    return "\n".join(
        [
            "the «Regola | Consuma» tables of docs/adr/, read in order — when two disagree the "
            "most recent ADR wins:",
            *rows,
            *(f"  overridden: {line}" for line in overridden),
        ]
    )


def documented_tools(text: str) -> dict[str, tuple[str, str, frozenset[str], frozenset[str]]]:
    rows = {
        cid: (cls, name, frozenset(CODE.findall(output)), frozenset(CODE.findall(codes)))
        for line in text.splitlines()
        for cid, cls, name, output, codes in [
            m.groups() for m in [TOOL_ROW.match(line)] if m is not None
        ]
    }
    assert rows, "ADR 0013 must contain the tools table"
    return rows


def section(path: Path, label: str) -> str:
    """The text after ``label`` in ``path``, up to the next heading: the table it introduces."""
    text = path.read_text(encoding="utf-8")
    assert label in text, f"{path.name} must carry the label {label!r}"
    rest = text.split(label, 1)[1]
    return rest.split("\n#", 1)[0]


def all_documented_tools() -> dict[str, tuple[str, str, frozenset[str], frozenset[str]]]:
    """ADR 0013's tools, plus what later ADRs add, then what later ADRs replace."""
    union = documented_tools(ADR_PATH.read_text(encoding="utf-8"))
    for path, label in ADDING_ADRS:
        for cid, row in documented_tools(section(path, label)).items():
            assert cid not in union, f"{cid} is documented in more than one ADR ({path.name})"
            union[cid] = row
    for path, label in REPLACING_ADRS:
        for cid, row in documented_tools(section(path, label)).items():
            assert cid in union, f"{cid} is replaced before being documented ({path.name})"
            union[cid] = row
    return union


def coded_tools() -> dict[str, tuple[str, str, frozenset[str], frozenset[str]]]:
    router, providers = routing_for(FakeModelProvider(FakeClock(), FakeIdGenerator()))
    registry = tools_v01(
        root="/tmp/ela-adr-0013",
        clock=FakeClock(),
        ids=FakeIdGenerator(),
        router=router,
        providers=providers,
    )
    rows = {}
    for tool in registry.tools():
        assert isinstance(tool, Tool)
        rows[tool.capability_id] = (
            type(tool).__name__,
            tool.name,
            tool.output_keys,
            tool.error_codes,
        )
    return rows


def test_every_outcome_row_names_an_engine_operation_and_a_known_code() -> None:
    rows = documented_outcomes(ADR_PATH.read_text(encoding="utf-8"))
    operations = set(OPERATIONS) | set(STEP_OPERATIONS)
    seen_codes: set[str] = set()
    for condition, operation, code in rows:
        assert operation in operations, condition
        codes = set(CODE.findall(code))
        assert codes <= EXECUTOR_CODES, condition
        seen_codes |= codes
    assert seen_codes == EXECUTOR_CODES
    by_outcome = {condition.split("`")[0]: operation for condition, operation, _ in rows}
    assert by_outcome["DENIED"] == "deny_by_decision"
    assert by_outcome["REQUIRES_APPROVAL"] == "request_approval"
    assert [operation for condition, operation, _ in rows if condition.startswith("ALLOWED")] == [
        "request_approval",
        "fail_step",
        "fail_step",
        "fail_step",
        "fail_step",
        "complete_step",
    ]


def test_consuming_rules_match_every_table_of_the_adrs() -> None:
    answers, overridden = consuming_answers(adr_documents())
    message = consuming_message(answers, overridden)

    assert {rule for rule, (consumes, _) in answers.items() if consumes} == CONSUMING_RULES, message
    assert {rule for rule, (consumes, _) in answers.items() if not consumes} == {
        Rule.ALLOW,
        Rule.ALLOW_WITHIN_SCOPE,
    }, message


def test_the_tables_that_state_a_consumption_are_the_ones_expected() -> None:
    """Two today: ADR 0013 §6 and the row ADR 0045 §3 added. A third is found by the glob."""
    holding = [name for name, text in adr_documents() if CONSUMING_HEADER in text.splitlines()]
    assert holding == ["0013-executor.md", "0045-filesystem-and-high.md"]


def test_a_drifted_consuming_table_is_detected() -> None:
    """The negative cases, on the union and not on ADR 0013 alone (M13.1b).

    The old case softened ADR 0013's table and checked it against ``CONSUMING_RULES``. Once the
    set was derived, ADR 0013 alone differed from it anyway, so that case passed with or without
    the softening — a negative case that could no longer fail.
    """
    documents = adr_documents()
    consuming = {rule for rule, (c, _) in consuming_answers(documents)[0].items() if c}
    assert consuming == CONSUMING_RULES

    softened = [
        (
            name,
            text.replace(
                "| `APPROVAL_UNLESS_AUTHORIZED` | sì |", "| `APPROVAL_UNLESS_AUTHORIZED` | no |", 1
            ),
        )
        for name, text in documents
    ]
    assert softened != documents
    assert {r for r, (c, _) in consuming_answers(softened)[0].items() if c} != CONSUMING_RULES

    the_high_row_softened = [
        (name, text.replace("| `APPROVAL_EVERY_USE` | sì |", "| `APPROVAL_EVERY_USE` | no |", 1))
        for name, text in documents
    ]
    assert the_high_row_softened != documents
    answers, _ = consuming_answers(the_high_row_softened)
    assert answers[Rule.APPROVAL_EVERY_USE] == (False, "0045-filesystem-and-high.md")
    assert {r for r, (c, _) in answers.items() if c} != CONSUMING_RULES


def test_when_two_tables_disagree_the_most_recent_wins_and_says_so() -> None:
    earlier = ("0013-executor.md", f"{CONSUMING_HEADER}\n|---|---|\n| `ALLOW` | sì |\n")
    later = ("0099-later.md", f"{CONSUMING_HEADER}\n|---|---|\n| `ALLOW` | no |\n")

    answers, overridden = consuming_answers([earlier, later])

    assert answers[Rule.ALLOW] == (False, "0099-later.md")
    assert overridden == [
        "ALLOW: 0013-executor.md says sì, 0099-later.md says no — the most recent wins"
    ]
    assert "overridden: ALLOW" in consuming_message(answers, overridden)


def test_tools_table_matches_the_code() -> None:
    documented = all_documented_tools()
    coded = coded_tools()
    assert list(documented) == list(coded)
    for cid, row in documented.items():
        assert row == coded[cid], cid
    assert set(documented) == {spec.id for spec in catalogue_v01().specs()}


def test_adr_0013_documents_the_two_tools_that_predate_the_provider() -> None:
    """The split is the point: ADR 0013 is not rewritten when a tool arrives (ADR 0021 §9)."""
    assert set(documented_tools(ADR_PATH.read_text(encoding="utf-8"))) == {
        "core.echo",
        "workspace.write_note",
    }
    added = documented_tools(section(*ADDING_ADRS[0]))
    assert set(added) == {"model.complete"}


def test_a_drifted_added_table_is_detected() -> None:
    """The later tables are held to account like the first one, or they would be decoration."""
    coded = coded_tools()
    for source, before, after in (
        (ADDING_ADRS[0], "| `model-complete` |", "| `model-completion` |"),
        (REPLACING_ADRS[0], "| `model-complete` |", "| `model-completion` |"),
        (REPLACING_ADRS[0], "`routing.unknown_task_type`, ", ""),
        (REPLACING_ADRS[0], "`profile`, `skipped`", "`profile`"),
    ):
        text = section(*source)
        drifted = text.replace(before, after, 1)
        assert drifted != text, before
        assert documented_tools(drifted)["model.complete"] != coded["model.complete"], before


def test_the_replacing_table_is_the_one_the_code_must_match() -> None:
    """ADR 0021's row for ``model.complete`` is the M7.2 one and stays as it was written; what
    the code answers to is ADR 0022's."""
    added = documented_tools(section(*ADDING_ADRS[0]))["model.complete"]
    replaced = documented_tools(section(*REPLACING_ADRS[0]))["model.complete"]

    assert added != replaced
    assert all_documented_tools()["model.complete"] == replaced
    assert coded_tools()["model.complete"] == replaced


def test_a_drifted_table_is_detected() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")
    coded = coded_tools()
    for before, after, cid in [
        ("| `core-echo` | `message` |", "| `core-echo` | `text` |", "core.echo"),
        ("| `EchoTool` |", "| `PrintTool` |", "core.echo"),
        ("`path.symlink`, ", "", "workspace.write_note"),
    ]:
        drifted = text.replace(before, after, 1)
        assert drifted != text, before
        assert documented_tools(drifted)[cid] != coded[cid], before
    renamed = text.replace(
        "| `fail_step` | `grant_vanished` |", "| `fail_task` | `grant_vanished` |", 1
    )
    assert renamed != text
    with pytest.raises(AssertionError):
        rows = documented_outcomes(renamed)
        assert all(op in set(OPERATIONS) | set(STEP_OPERATIONS) for _, op, _ in rows)


def test_a_missing_table_is_detected() -> None:
    with pytest.raises(AssertionError, match="outcomes table"):
        documented_outcomes("nothing")
    with pytest.raises(AssertionError, match=r"no '\| Regola \| Consuma \|' table here"):
        documented_consuming_rules("nothing")
    with pytest.raises(AssertionError, match="has no row a rule can be read from"):
        documented_consuming_rules(f"{CONSUMING_HEADER}\n|---|---|\nnot a row\n")
    with pytest.raises(AssertionError, match="tools table"):
        documented_tools("nothing")
