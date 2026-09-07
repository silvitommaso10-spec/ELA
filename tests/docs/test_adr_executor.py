"""The tables of ADR 0013 and the executor/tools describe the same code.

Same pattern as the other ADR tests: §5 (outcome → engine operation → error code) against the
engine's tables and the executor's constants, §6 (rule → consumes) against ``CONSUMING_RULES``,
§11 (capability → tool → name → output → error codes) against ``tools_v01`` and the tools' own
declarations. Each table has a distinctive row shape, so no other table test mistakes it.

An ADR is immutable, so a tool that arrives later is documented by *its* ADR, under the label
``Tool aggiunti:`` (ADR 0021 §9), exactly as a port extended later is
documented under ``Port estesi:``. The union of the tables is what the code must match, and a
capability documented twice is a drift of its own.
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

ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "adr"
ADR_PATH = ADR_DIR / "0013-executor.md"
ADDING_TOOLS = "Tool aggiunti:"
ADDING_ADRS = ((ADR_DIR / "0021-started-protocol-and-model-complete.md", ADDING_TOOLS),)
"""ADRs that add a tool after ADR 0013: the label, then the table, read as ADR 0013's is."""
OUTCOME_ROW = re.compile(r"^\| `(ALLOWED|DENIED|REQUIRES_APPROVAL)`(.*?) \| `(\w+)` \| (.+) \|$")
RULE_ROW = re.compile(r"^\| `([A-Z_]+)` \| (sì|no) \|$")
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
    rows = {
        Rule(rule): answer == "sì"
        for line in text.splitlines()
        for rule, answer in [m.groups() for m in [RULE_ROW.match(line)] if m is not None]
    }
    assert rows, "ADR 0013 must contain the consuming-rules table"
    return rows


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
    """ADR 0013's tools plus the ones later ADRs add, in the order they were introduced."""
    union = documented_tools(ADR_PATH.read_text(encoding="utf-8"))
    for path, label in ADDING_ADRS:
        for cid, row in documented_tools(section(path, label)).items():
            assert cid not in union, f"{cid} is documented in more than one ADR ({path.name})"
            union[cid] = row
    return union


def coded_tools() -> dict[str, tuple[str, str, frozenset[str], frozenset[str]]]:
    registry = tools_v01(
        root="/tmp/ela-adr-0013",
        clock=FakeClock(),
        ids=FakeIdGenerator(),
        provider=FakeModelProvider(FakeClock(), FakeIdGenerator()),
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


def test_consuming_rules_match_the_code() -> None:
    documented = documented_consuming_rules(ADR_PATH.read_text(encoding="utf-8"))
    assert {rule for rule, consumes in documented.items() if consumes} == CONSUMING_RULES
    assert {rule for rule, consumes in documented.items() if not consumes} == {
        Rule.ALLOW,
        Rule.ALLOW_WITHIN_SCOPE,
    }


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
    """The later table is held to account like the first one, or it would be decoration."""
    path, label = ADDING_ADRS[0]
    text = section(path, label)
    coded = coded_tools()
    for before, after in (
        ("| `model-complete` |", "| `model-completion` |"),
        ("`provider.no_output`, ", ""),
    ):
        drifted = text.replace(before, after, 1)
        assert drifted != text, before
        assert documented_tools(drifted)["model.complete"] != coded["model.complete"], before


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
    softened = text.replace(
        "| `APPROVAL_UNLESS_AUTHORIZED` | sì |", "| `APPROVAL_UNLESS_AUTHORIZED` | no |", 1
    )
    assert softened != text
    consuming = {r for r, c in documented_consuming_rules(softened).items() if c}
    assert consuming != CONSUMING_RULES
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
    with pytest.raises(AssertionError, match="consuming-rules table"):
        documented_consuming_rules("nothing")
    with pytest.raises(AssertionError, match="tools table"):
        documented_tools("nothing")
