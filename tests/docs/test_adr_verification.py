"""The tables of ADR 0014 and the verifiers/executor describe the same code.

Same pattern as the other ADR tests: §2 (capability → verifier → name → conditions → failure
codes) against ``verifiers_v01`` and the verifiers' own declarations; §4 (result → verification
→ engine operations → code → task state) against the engine's tables and the executor's
constants. Each table has a distinctive row shape, so no other table test mistakes it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ela.executive import VERIFICATION_EXCEPTION, VERIFICATION_FAILED
from ela.permissions import catalogue_v01
from ela.tasks.engine import OPERATIONS, STEP_OPERATIONS
from ela.testing.fakes import FakeModelRouter
from ela.tools import COMMON_FAILURE_CODES, PATH_CODES, Verifier, verifiers_v01

ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "adr"
ADR_PATH = ADR_DIR / "0014-verification.md"
ADDING_VERIFIERS = "Verifier aggiunti:"
REPLACING_VERIFIERS = "Verifier sostituiti:"
ADDING_ADRS = ((ADR_DIR / "0021-started-protocol-and-model-complete.md", ADDING_VERIFIERS),)
"""ADRs that add a verifier after ADR 0014 (ADR 0021 §10). An ADR is immutable: a verifier that
arrives later is documented by its own ADR, under a label, as a port extended later is."""
REPLACING_ADRS = ((ADR_DIR / "0022-model-router.md", REPLACING_VERIFIERS),)
"""ADRs that change a verifier documented earlier (ADR 0022 §10: ``model.routed_as_asked`` is the
second condition of ``model.complete``). Additions apply first, replacements after, and the
replacing row is the one the code must match."""
VERIFIER_ROW = re.compile(r"^\| `([a-z_.]+)` \| `(\w+)` \| `([\w-]+)` \| (.+?) \| (.+?) \|$")
OUTCOME_ROW = re.compile(
    r"^\| (SUCCEEDED|non SUCCEEDED) \| (.+?) \| (.+?) \| (.+?) \| "
    r"\*{0,2}(EXECUTING|FAILED)\*{0,2} \|$"
)
CODE = re.compile(r"`([^`]+)`")
SHORTHANDS = {"comuni": COMMON_FAILURE_CODES, "percorso": PATH_CODES}
"""Words a codes cell may use for a whole family: the shared codes of ``ela.tools.verify`` and
the seven of ``ela.tools.paths``."""
EXECUTOR_CODES = {VERIFICATION_FAILED, VERIFICATION_EXCEPTION}


def documented_verifiers(text: str) -> dict[str, tuple[str, str, frozenset[str], frozenset[str]]]:
    """capability → (class, name, conditions, failure codes); the shorthands expand."""
    rows = {}
    for line in text.splitlines():
        match = VERIFIER_ROW.match(line)
        if match is None:
            continue
        cid, cls, name, conditions, codes = match.groups()
        expanded = frozenset(CODE.findall(codes))
        for word, family in SHORTHANDS.items():
            if word in codes:
                expanded |= family
        rows[cid] = (cls, name, frozenset(CODE.findall(conditions)), expanded)
    assert rows, "ADR 0014 must contain the verifiers table"
    return rows


def coded_verifiers() -> dict[str, tuple[str, str, frozenset[str], frozenset[str]]]:
    rows = {}
    for verifier in verifiers_v01(root="/tmp/ela-adr-0014", router=FakeModelRouter()).verifiers():
        assert isinstance(verifier, Verifier)
        rows[verifier.capability_id] = (
            type(verifier).__name__,
            verifier.name,
            verifier.conditions,
            verifier.failure_codes,
        )
    return rows


def documented_outcomes(text: str) -> list[tuple[str, str, list[str], set[str], str]]:
    """(result, verification, operations, codes, task state) per row of the §4 table."""
    rows = [
        (result, verification, CODE.findall(operations), set(CODE.findall(code)), state)
        for line in text.splitlines()
        for result, verification, operations, code, state in [
            m.groups() for m in [OUTCOME_ROW.match(line)] if m is not None
        ]
    ]
    assert rows, "ADR 0014 must contain the outcomes table"
    return rows


def section(path: Path, label: str) -> str:
    """The text after ``label`` in ``path``, up to the next heading: the table it introduces."""
    text = path.read_text(encoding="utf-8")
    assert label in text, f"{path.name} must carry the label {label!r}"
    return text.split(label, 1)[1].split("\n#", 1)[0]


def all_documented_verifiers() -> dict[str, tuple[str, str, frozenset[str], frozenset[str]]]:
    """ADR 0014's verifiers, plus what later ADRs add, then what later ADRs replace."""
    union = documented_verifiers(ADR_PATH.read_text(encoding="utf-8"))
    for path, label in ADDING_ADRS:
        for cid, row in documented_verifiers(section(path, label)).items():
            assert cid not in union, f"{cid} is documented in more than one ADR ({path.name})"
            union[cid] = row
    for path, label in REPLACING_ADRS:
        for cid, row in documented_verifiers(section(path, label)).items():
            assert cid in union, f"{cid} is replaced before being documented ({path.name})"
            union[cid] = row
    return union


def test_verifiers_table_matches_the_code() -> None:
    documented = all_documented_verifiers()
    coded = coded_verifiers()
    assert list(documented) == list(coded)
    for cid, row in documented.items():
        assert row == coded[cid], cid
    assert set(documented) == {spec.id for spec in catalogue_v01().specs()}


def test_adr_0014_documents_the_two_verifiers_that_predate_the_provider() -> None:
    assert set(documented_verifiers(ADR_PATH.read_text(encoding="utf-8"))) == {
        "core.echo",
        "workspace.write_note",
    }
    assert set(documented_verifiers(section(*ADDING_ADRS[0]))) == {"model.complete"}


def test_a_drifted_added_table_is_detected() -> None:
    """The later tables are held to account like the first one, or they would be decoration."""
    coded = coded_verifiers()
    for source, before, after in (
        (ADDING_ADRS[0], "| `model-complete-verifier` |", "| `model-complete-check` |"),
        (REPLACING_ADRS[0], "`model.unaccounted`", "`model.uncounted`"),
        (REPLACING_ADRS[0], "comuni, `model.no_answer`", "`model.no_answer`"),
        (REPLACING_ADRS[0], "`model.answered`, `model.routed_as_asked`", "`model.answered`"),
    ):
        text = section(*source)
        drifted = text.replace(before, after, 1)
        assert drifted != text, before
        assert documented_verifiers(drifted)["model.complete"] != coded["model.complete"], before


def test_the_second_condition_arrives_with_the_router() -> None:
    """Decision 10b of M7.2, split in two: ADR 0021 documents the verifier with one condition,
    ADR 0022 the same verifier with the one the router made possible."""
    added = documented_verifiers(section(*ADDING_ADRS[0]))["model.complete"]
    replaced = documented_verifiers(section(*REPLACING_ADRS[0]))["model.complete"]

    assert added[2] == frozenset({"model.answered"})
    assert replaced[2] == frozenset({"model.answered", "model.routed_as_asked"})
    assert (
        all_documented_verifiers()["model.complete"]
        == replaced
        == coded_verifiers()["model.complete"]
    )


def test_every_outcome_row_names_engine_operations_and_known_codes() -> None:
    rows = documented_outcomes(ADR_PATH.read_text(encoding="utf-8"))
    known = set(OPERATIONS) | set(STEP_OPERATIONS)
    seen: set[str] = set()
    for result, verification, operations, codes, state in rows:
        assert operations and set(operations) <= known, verification
        assert codes <= EXECUTOR_CODES, verification
        seen |= codes
        # a task FAILED is a task the executor failed: ``fail`` after ``fail_step``
        assert (state == "FAILED") == (operations == ["fail_step", "fail"]), verification
        assert (result == "SUCCEEDED") == (verification != "non eseguita"), verification
    assert seen == EXECUTOR_CODES
    by_verification = {v: (ops, state) for _, v, ops, _, state in rows}
    assert by_verification["passata"] == (["complete_step"], "EXECUTING")
    assert by_verification["non eseguita"] == (["fail_step"], "EXECUTING")
    assert by_verification["fallita"] == (["fail_step", "fail"], "FAILED")
    assert by_verification["il verifier solleva"] == (["fail_step", "fail"], "FAILED")


def test_a_drifted_table_is_detected() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")
    coded = coded_verifiers()
    for before, after, cid in [
        ("| `core-echo-verifier` |", "| `core-echo-checker` |", "core.echo"),
        ("| `EchoVerifier` |", "| `EchoChecker` |", "core.echo"),
        ("`note.exists`, ", "", "workspace.write_note"),
        ("`note.unreadable`", "`note.locked`", "workspace.write_note"),
        ("comuni, `echo.message_mismatch`", "`echo.message_mismatch`", "core.echo"),
        (
            "comuni, percorso, `note.content_mismatch`",
            "comuni, `note.content_mismatch`",
            "workspace.write_note",
        ),
    ]:
        drifted = text.replace(before, after, 1)
        assert drifted != text, before
        assert documented_verifiers(drifted)[cid] != coded[cid], before
    renamed = text.replace(
        "| `fail_step`, `fail` | `verification.failed` |",
        "| `fail_step` | `verification.failed` |",
        1,
    )
    assert renamed != text
    with pytest.raises(AssertionError):
        for _, verification, operations, _, state in documented_outcomes(renamed):
            assert (state == "FAILED") == (operations == ["fail_step", "fail"]), verification
    softened = text.replace(
        "| SUCCEEDED | passata | `complete_step` |", "| SUCCEEDED | passata | `complete` |", 1
    )
    assert softened != text
    with pytest.raises(AssertionError):
        rows = documented_outcomes(softened)
        assert {v: ops for _, v, ops, _, _ in rows}["passata"] == ["complete_step"]


def test_a_missing_table_is_detected() -> None:
    with pytest.raises(AssertionError, match="verifiers table"):
        documented_verifiers("nothing")
    with pytest.raises(AssertionError, match="outcomes table"):
        documented_outcomes("nothing")
