"""``docs/GETTING_STARTED.md`` and the code say the same thing (M8.3, ADR 0025 §8).

Two drifts, both found by the user's first hand-run of the guide and neither by a review:

* a **placeholder** written as ``<id>`` and explained nowhere, so it was pasted with the angle
  brackets on. The guide now declares the convention once, in a table; this module keeps that
  table and the guide's code blocks the same set, so a new placeholder cannot arrive unexplained.
* a **risk level** printed in prose — "scrivere è MEDIUM (§29)" — three sections above a sample
  of the audit trail that printed ``LOW``. Wherever the guide names a capability and a risk on
  the same line, this module reads the catalogue and compares.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ela.cli.output import EMPTY, GAP
from ela.cli.tasks import RUN_LABELS
from ela.domain import RiskLevel
from ela.executive.runner import OUTCOMES
from ela.permissions import catalogue_v01
from ela.tasks.engine import OPERATIONS

GUIDE = Path(__file__).resolve().parents[2] / "docs" / "GETTING_STARTED.md"
BLOCK = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
PLACEHOLDER = re.compile(r"<[^<>\s][^<>]*>")
LEGEND_ROW = re.compile(r"^\| `(<[^`]+>)` \| ([^|]+) \| ([^|]+) \|$")
RISKS = "|".join(level.value for level in RiskLevel)


def guide() -> str:
    return GUIDE.read_text(encoding="utf-8")


def declared() -> dict[str, str]:
    """placeholder → what the legend says goes there."""
    rows = {
        match.group(1): match.group(2).strip()
        for line in guide().splitlines()
        if (match := LEGEND_ROW.match(line)) is not None
    }
    assert rows, "the guide must open with the table of its placeholders"
    return rows


def used(text: str) -> set[str]:
    """Every ``<…>`` inside a fenced code block: what a reader actually types."""
    return {found for block in BLOCK.findall(text) for found in PLACEHOLDER.findall(block)}


# ----------------------------------------------------------------------------------------
# The placeholders
# ----------------------------------------------------------------------------------------


def test_every_placeholder_a_reader_would_type_is_explained() -> None:
    assert used(guide()) <= set(declared())


def test_the_legend_explains_nothing_the_guide_stopped_using() -> None:
    """A legend that outlives its placeholder teaches a convention nobody meets."""
    assert set(declared()) <= used(guide())


def test_the_convention_says_the_brackets_are_not_pasted() -> None:
    """The whole debt in one sentence: the user pasted them because nothing said not to."""
    text = guide()
    opening = text.split("## 0.", 1)[0]

    assert "segnaposto" in opening
    assert "non si incollano" in opening


def test_the_first_placeholder_is_also_shown_substituted() -> None:
    """Read once, seen once: the first command with a ``<id>`` is repeated with the real id
    printed two lines above it."""
    text = guide()
    created = re.search(r"^id +([0-9a-f-]{36})$", text, re.MULTILINE)
    assert created is not None

    first = next(block for block in BLOCK.findall(text) if "<id>" in block)
    after = text.index(first) + len(first)
    assert created.group(1) in text[after : after + 400]


def test_a_placeholder_nobody_explained_is_reported() -> None:
    """Negative case: this test is the guard, so it must fail when the guard is needed."""
    invented = guide().replace("uv run ela task run <id>", "uv run ela task run <task-id>", 1)

    assert invented != guide()
    assert not used(invented) <= set(declared())


def test_a_legend_row_that_names_nothing_is_reported() -> None:
    """The other direction: a row for a placeholder the guide does not use."""
    stale = declared() | {"<node-id>": "un nodo"}

    assert not set(stale) <= used(guide())


# ----------------------------------------------------------------------------------------
# The risk levels the guide prints
# ----------------------------------------------------------------------------------------


def test_no_risk_level_in_the_guide_contradicts_the_catalogue() -> None:
    """The debt of the first hand-run: the guide said MEDIUM where §29 says LOW.

    Every line that names a capability **and** a risk is read, prose and sample output alike:
    the guide contradicted itself across two pages, so half a check would have missed it.
    """
    catalogue = {spec.id: spec.risk.value for spec in catalogue_v01().specs()}
    checked = 0

    for line in guide().splitlines():
        for capability, risk in catalogue.items():
            if capability not in line:
                continue
            found = re.findall(rf"\b({RISKS})\b", line)
            if not found:
                continue
            checked += 1
            assert set(found) == {risk}, f"{capability} is {risk} (§29), not {found}: {line}"

    assert checked >= 3, "the guide must still show the risk of a capability somewhere"


def test_a_wrong_risk_in_the_guide_would_be_reported() -> None:
    """Negative case, on the exact sentence that was wrong until M8.3."""
    catalogue = {spec.id: spec.risk.value for spec in catalogue_v01().specs()}
    line = "il secondo scrive un file, e scrivere è MEDIUM (§29)"
    drifted = f"`workspace.write_note` {line}"

    found = re.findall(rf"\b({RISKS})\b", drifted)

    assert found == ["MEDIUM"]
    assert set(found) != {catalogue["workspace.write_note"]}


# ----------------------------------------------------------------------------------------
# The examples the guide points at
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("example", ["first-task.json", "ask-model.json"])
def test_the_guide_points_at_both_examples(example: str) -> None:
    assert example in guide()


def test_the_command_that_reads_an_output_is_in_the_guide() -> None:
    """``ela task results``: without it the model example completes and shows nothing."""
    assert "ela task results" in guide()


# ----------------------------------------------------------------------------------------
# ELA on the PC: the module, never the launcher (M13.3, the manual test of 2026-09-26)
# ----------------------------------------------------------------------------------------

POWERSHELL_BLOCK = re.compile(r"^```powershell\n(.*?)^```", re.MULTILINE | re.DOTALL)
LAUNCHER = "uv run ela "
MODULE = "uv run python -m ela.cli "


def launched_by_the_launcher(text: str) -> list[str]:
    """The PowerShell lines that start ELA through ``ela.exe``, which ``uv sync`` rebuilds."""
    return [
        line.strip()
        for block in POWERSHELL_BLOCK.findall(text)
        for line in block.splitlines()
        if LAUNCHER in line
    ]


def test_no_powershell_block_of_the_guide_launches_the_ela_launcher() -> None:
    """After ``uv sync --locked`` the ``ela.exe`` of the virtualenv is new and unsigned, and Smart
    App Control blocks it (os error 4551, «Un criterio di controllo dell'applicazione ha bloccato il
    file»); ``python -m ela.cli`` runs the same code through a signed interpreter."""
    text = guide()

    assert launched_by_the_launcher(text) == []
    assert any(MODULE in block for block in POWERSHELL_BLOCK.findall(text))


def test_a_powershell_block_that_launches_the_launcher_is_reported() -> None:
    text = "```powershell\nSet-Location $HOME\\ELA\nuv run ela node run --join\n```\n"

    assert launched_by_the_launcher(text) == ["uv run ela node run --join"]


def test_the_guide_says_why_and_says_not_to_turn_smart_app_control_off() -> None:
    text = guide()

    assert "Smart App Control" in text
    assert "4551" in text
    assert "non si riaccende" in text


# ----------------------------------------------------------------------------------------
# What ``ela task run`` prints, as the guide shows it (M6.3b, ADR 0051)
# ----------------------------------------------------------------------------------------


def is_a_run_row(line: str) -> bool:
    """A row of ``ela task run``: one of its labels, then the gap — never a label and one space,
    which is how the ``atteso`` lines of §21 are written (M13.1c)."""
    return any(line.startswith(label + GAP) for label in RUN_LABELS)


def run_blocks(text: str) -> list[str]:
    """Every fenced block that shows the output of ``ela task run``: the ones whose first line is
    one of its rows — ``outcome`` for a whole block, another for a cut one, which is reported as out
    of shape (M13.1c: the two cuts of §16 step 5 sat outside the check of M6.3b for that reason). No
    other command prints these rows; one that did would be reported here, not let through. Marked or
    not: an ``atteso`` block that begins with ``outcome`` is a block of ``run``."""
    found = []
    for block in BLOCK.findall(text):
        body = block.splitlines()[1:-1]
        if body and is_a_run_row(body[0]):
            found.append("\n".join(body))
    return found


def unrecognised_run_blocks(text: str) -> list[str]:
    """Blocks with two or more rows of ``ela task run`` that do not begin with one: a cut that
    begins with ``…`` or with a line of prose would leave the check, and is reported instead
    (M13.1c)."""
    found = []
    for block in BLOCK.findall(text):
        body = block.splitlines()[1:-1]
        if body and not is_a_run_row(body[0]) and sum(map(is_a_run_row, body)) >= 2:
            found.append("\n".join(body))
    return found


def without_its_why(block: str) -> list[str]:
    """A block whose outcome is ``denied`` or ``failed`` says why, in the form ``run`` prints it
    since M13.1c: the summary of the transition that ended the task, which begins with the name of
    an operation of the engine that puts the task in that state (ADR 0055; decision F of the
    session). The operations are read from the engine, not written here."""
    rows = dict(
        (line[: line.index(GAP)].rstrip(), line[line.index(GAP) :].strip())
        for line in block.splitlines()
        if is_a_run_row(line)
    )
    outcome = rows.get("outcome")
    states = {run_outcome.value: state for state, run_outcome in OUTCOMES.items()}
    if outcome not in {"denied", "failed"}:
        return []
    reason = rows.get("reason", EMPTY)
    if reason == EMPTY:
        return [f"{outcome} with no reason: {block!r}"]
    names = {op.name for op in OPERATIONS.values() if op.target is states[outcome]}
    if not any(reason.startswith(f"{name}: ") for name in names):
        return [f"{outcome} whose reason is not a transition's ({sorted(names)}): {reason!r}"]
    return []


def not_what_the_cli_prints(block: str) -> list[str]:
    """What is wrong with one block, measured against the command: its labels, in its order, at its
    width — the four rows it always prints, with nothing taken out."""
    width = max(map(len, RUN_LABELS))
    lines = block.splitlines()
    if len(lines) != len(RUN_LABELS):
        return [f"{len(lines)} rows, the command prints {len(RUN_LABELS)}: {block!r}"]
    return [
        f"{line!r} is not {label!r} at width {width}"
        for line, label in zip(lines, RUN_LABELS, strict=True)
        if not line.startswith(label.ljust(width) + GAP) or not aligned(line[width + len(GAP) :])
    ]


def aligned(value: str) -> bool:
    """A value that starts in the command's column: there, and not one space further."""
    return bool(value) and not value.startswith(" ")


def test_every_run_block_of_the_guide_is_what_the_cli_prints() -> None:
    """§6 once showed two ids under ``steps executed`` and said right below that the second had not
    run (M6.3b): a block of the guide is the command's output, so the label that changes in the
    command changes here or the suite stops."""
    blocks = run_blocks(guide())

    assert blocks
    assert [problem for block in blocks for problem in not_what_the_cli_prints(block)] == []


def test_no_block_of_the_guide_cuts_a_run_without_being_seen() -> None:
    assert unrecognised_run_blocks(guide()) == []


def test_every_denied_or_failed_block_of_the_guide_says_why() -> None:
    """Decision F of M13.1c: since then ``denied`` and ``failed`` always carry their why, and the
    guide shows it — §19 step 2 showed ``reason —`` after the user's no until M13.1c."""
    blocks = run_blocks(guide())

    assert [problem for block in blocks for problem in without_its_why(block)] == []


def test_a_denied_block_with_an_empty_reason_is_reported() -> None:
    width = max(map(len, RUN_LABELS))
    values = ("denied", EMPTY, "DENIED", EMPTY, EMPTY)
    block = "\n".join(
        f"{label.ljust(width)}{GAP}{value}" for label, value in zip(RUN_LABELS, values, strict=True)
    )

    assert without_its_why(block) != []


def test_a_failed_block_with_the_reason_of_before_is_reported() -> None:
    """The form ``run`` printed until M13.1c: the error alone, without the transition."""
    width = max(map(len, RUN_LABELS))
    values = ("failed", "fs.overwrite_mismatch: something is there now", "FAILED", EMPTY, EMPTY)
    block = "\n".join(
        f"{label.ljust(width)}{GAP}{value}" for label, value in zip(RUN_LABELS, values, strict=True)
    )

    assert without_its_why(block) != []


def test_a_failed_block_with_the_reason_of_a_transition_passes() -> None:
    width = max(map(len, RUN_LABELS))
    reason = "fail: EXECUTING -> FAILED (fs.overwrite_mismatch: something is there now)"
    values = ("failed", reason, "FAILED", EMPTY, EMPTY)
    block = "\n".join(
        f"{label.ljust(width)}{GAP}{value}" for label, value in zip(RUN_LABELS, values, strict=True)
    )

    assert without_its_why(block) == []


def test_a_marked_block_that_begins_with_outcome_is_a_run_block() -> None:
    """The marker of a hand test does not exempt a block that has the form of an output: §21 and §22
    write their expected runs whole, and the check confronts them."""
    text = "<!-- prova: 4.atteso -->\n```\noutcome        denied\nreason         —\n```\n"

    (block,) = run_blocks(text)
    assert without_its_why(block) != []


def test_a_cut_run_block_is_found_by_any_of_its_rows_and_reported() -> None:
    """The two cuts of §16 step 5 began with ``reason`` and sat outside the check of M6.3b."""
    width = max(map(len, RUN_LABELS))
    text = f"```\n{'reason'.ljust(width)}{GAP}x\n{'state'.ljust(width)}{GAP}FAILED\n```\n"

    (block,) = run_blocks(text)
    assert not_what_the_cli_prints(block) != []


def test_a_cut_run_block_that_begins_with_an_ellipsis_is_reported() -> None:
    width = max(map(len, RUN_LABELS))
    text = f"```\n…\n{'reason'.ljust(width)}{GAP}x\n{'state'.ljust(width)}{GAP}FAILED\n```\n"

    assert run_blocks(text) == []
    assert unrecognised_run_blocks(text) != []


def test_the_atteso_lines_of_a_hand_test_are_not_run_rows() -> None:
    """``state CANCELLED``, one space: what ``scripts/prova_m6_3c.py`` looks for, word by word."""
    text = "<!-- prova: 2.atteso -->\n```\nstate CANCELLED\n```\n"

    assert run_blocks(text) == []
    assert unrecognised_run_blocks(text) == []


def test_a_run_block_with_the_old_label_is_reported() -> None:
    block = (
        "outcome         waiting_approval\n"
        "reason          —\n"
        "state           WAITING_APPROVAL\n"
        "steps executed  9c5b8f26-1a2b-4c3d-8e4f-000000000001"
    )

    assert not_what_the_cli_prints(block) != []


def test_a_run_block_aligned_to_another_width_is_reported() -> None:
    block = "\n".join(f"{label}  x" for label in RUN_LABELS)

    assert not_what_the_cli_prints(block) != []


def test_a_run_block_with_a_row_taken_out_is_reported() -> None:
    width = max(map(len, RUN_LABELS))
    block = "\n".join(f"{label.ljust(width)}{GAP}x" for label in RUN_LABELS[:-1])

    assert not_what_the_cli_prints(block) != []


def test_a_run_block_is_found_by_its_first_row() -> None:
    text = "prima\n\n```\noutcome  denied\nreason   no\n```\n\n```\nid  1\n```\n"

    assert run_blocks(text) == ["outcome  denied\nreason   no"]
