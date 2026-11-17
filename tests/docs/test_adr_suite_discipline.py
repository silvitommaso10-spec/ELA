"""ADR 0069 — the discipline of the suite (M9.5) — held to the tree.

It is a ``Proposta`` until the proof by hand of the branch (decision 81 of the review at
``ad1826c``); the ADR it revises says so on its state line; and **the dated debt it writes**, the
waits no list knew, charged to M9.8, has the smallest defence there is, in the form of ADR 0035 §7:
each of the twenty-two waits is still in its function. The day somebody repairs one, the test
below fails: write the payment in an ADR, and turn this round.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADRS = ROOT / "docs" / "adr"
ADR_PATH = ADRS / "0069-suite-discipline.md"
REVISED_MARK = "**Rivista da ADR 0069 (M9.5)**"
REVISED_ROW = re.compile(r"^- \*\*ADR (\d{4})\b")
THE_DEBT = "### 5. Un debito datato: le attese che nessun elenco conosceva"
CHARGED_TO = "**Debito a carico di M9.8**, dichiarato il **2026-11-17**"


def status_of(text: str) -> str:
    return text.split("- **Stato:**", 1)[1].split("\n- **", 1)[0]


def revised_by_the_list(text: str) -> set[str]:
    """The numbers of the ADRs the list «Righe riviste» of an ADR names, one bullet each."""
    block = text.split("## Conseguenze", 1)[1].split("**Righe riviste**", 1)[1]
    rows = block.split("\n\n", 2)[1]
    return {match.group(1) for line in rows.splitlines() if (match := REVISED_ROW.match(line))}


def revised_by_their_state(mark: str, exclude: Path) -> set[str]:
    return {
        path.name[:4]
        for path in ADRS.glob("[0-9]*.md")
        if path != exclude and mark in status_of(path.read_text(encoding="utf-8"))
    }


def test_it_is_a_proposal_until_the_proof_of_its_branch() -> None:
    said = " ".join(status_of(ADR_PATH.read_text(encoding="utf-8")).split())

    assert said.startswith("**Proposta** il **2026-11-17**")
    assert "la sezione 33 di `docs/GETTING_STARTED.md`" in said


def test_the_adrs_it_revises_say_so_on_their_state_line_and_no_other_does() -> None:
    listed = revised_by_the_list(ADR_PATH.read_text(encoding="utf-8"))

    assert listed == {"0052"}
    assert listed == revised_by_their_state(REVISED_MARK, ADR_PATH)


def test_each_mark_names_a_section_of_this_adr_that_is_there() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")
    sections = set(re.findall(r"^### (\d+)\. ", text, re.MULTILINE))
    for number in revised_by_the_list(text):
        said = status_of((next(ADRS.glob(f"{number}-*.md"))).read_text(encoding="utf-8"))
        named = set(re.findall(r"ADR 0069 §(\d+)", said.split(REVISED_MARK, 1)[1]))
        assert named and named <= sections, number


def test_the_debt_of_m9_8_is_dated_charged_and_its_milestone_is_registered() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")
    section = text.split(THE_DEBT, 1)[1].split("\n### ", 1)[0]
    registration = (ROOT / "docs" / "milestones" / "M9.8.md").read_text(encoding="utf-8")

    assert CHARGED_TO in section
    assert "ADR 0069 §5" in registration and "- **Stato:** **Proposta**" in registration


WAITS_OF_M9_8 = (
    (
        "tests/api/test_server.py",
        "test_a_signal_that_arrives_while_the_loop_sleeps_wakes_it",
        "threading.Timer(0.05, send)",
    ),
    (
        "tests/api/test_server.py",
        "test_a_signal_the_system_hands_to_another_thread_wakes_the_loop_too",
        "threading.Timer(0.05, send)",
    ),
    (
        "tests/composition/test_account_wiring.py",
        "test_a_browser_that_fails_does_not_end_the_close_while_the_other_is_still_settling",
        "timeout=0.5",
    ),
    ("tests/docs/test_prova_m13_10.py", "walked", "time.sleep(0.5)"),
    (
        "tests/infrastructure/machine/test_account_browser.py",
        "test_a_window_that_does_not_close_is_killed_at_the_grace_and_never_left_on_the_folder",
        "asyncio.sleep(0.2)",
    ),
    (
        "tests/infrastructure/machine/test_account_login.py",
        "test_a_page_that_is_still_arriving_is_waited_for_before_it_is_asked_about",
        "call_later(0.2, web.rest.set)",
    ),
    (
        "tests/infrastructure/machine/test_account_window.py",
        "test_a_window_that_does_not_quit_when_told_is_killed_only_once_the_grace_is_over",
        "asyncio.sleep(0.3)",
    ),
    (
        "tests/infrastructure/machine/test_account_window.py",
        "test_the_window_is_told_once_however_many_ask",
        "asyncio.sleep(0.2)",
    ),
    (
        "tests/infrastructure/machine/test_account_window.py",
        "test_a_window_the_command_told_is_not_told_again_by_ela_s_stop",
        "asyncio.sleep(0.2)",
    ),
    (
        "tests/infrastructure/machine/test_account_window.py",
        "test_a_browser_that_dropped_its_lock_and_stays_is_still_the_one_that_was_told",
        "asyncio.sleep(0.2)",
    ),
    (
        "tests/infrastructure/machine/test_account_window.py",
        "test_a_browser_ela_did_not_start_is_not_killed_while_the_grace_lasts",
        "asyncio.sleep(0.4)",
    ),
    (
        "tests/infrastructure/machine/test_account_window.py",
        "test_a_browser_ela_did_not_start_is_told_once_too",
        "asyncio.sleep(0.2)",
    ),
    (
        "tests/infrastructure/machine/test_account_window.py",
        "test_a_stop_during_the_grace_of_a_browser_ela_did_not_start_kills_nobody",
        "asyncio.sleep(0.2)",
    ),
    ("tests/infrastructure/machine/test_browser.py", "appeared", "call_later(0.3, runs_out)"),
    (
        "tests/infrastructure/machine/test_launcher.py",
        "test_a_cancelled_run_kills_the_group_and_goes_away",
        "asyncio.sleep(1.5)",
    ),
    (
        "tests/infrastructure/machine/test_nothing_left_behind.py",
        "test_a_child_that_ends_a_moment_later_is_collected_once_it_has_ended",
        '"0.3"',
    ),
    (
        "tests/infrastructure/machine/test_task_pages.py",
        "test_a_held_page_outlives_the_look_and_the_deadline_of_a_page_nobody_looks_at",
        "asyncio.sleep(0.1)",
    ),
    (
        "tests/infrastructure/machine/test_task_pages.py",
        "test_what_the_gate_refused_while_the_page_waited_is_said_once_and_is_not_the_step_s",
        "300)",
    ),
    (
        "tests/infrastructure/machine/test_task_pages.py",
        "test_the_end_of_the_task_closes_the_page_and_leaves_no_process",
        "asyncio.sleep(0.05)",
    ),
    ("tests/infrastructure/machine/test_the_files_of_a_page.py", "<module>", "}, 4000)"),
    ("tests/node/support.py", "_run", "asyncio.sleep(self._delay)"),
    (
        "tests/tools/test_vault.py",
        "test_whatever_arrives_while_the_vault_is_closing_waits_for_the_closing_to_be_over",
        "asyncio.sleep(0.2)",
    ),
)
"""Each wait of the census outside ADR 0041 §5 — the file, the function, what it waits by — as the
census found them on 2026-11-14 at ``8220b20``. ``<module>`` is a page of the test, written at the
top of its file."""


def where(source: str, function: str) -> str:
    """The source of ``function`` in a module — every function of that name —, or the module."""
    if function == "<module>":
        return source
    found = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == function
    ]
    return "\n".join(ast.get_source_segment(source, node) or "" for node in found)


def gone(sources: dict[str, str]) -> list[tuple[str, str, str]]:
    """The waits of the list that are no longer in their function."""
    return [
        (path, function, wait)
        for path, function, wait in WAITS_OF_M9_8
        if wait not in where(sources[path], function)
    ]


def test_the_waits_no_list_knew_still_wait() -> None:
    """The smallest defence of §5. Failing here is not a regression: the debt is being paid —
    write the payment in an ADR, and turn this round."""
    sources = {path: (ROOT / path).read_text(encoding="utf-8") for path, _, _ in WAITS_OF_M9_8}

    assert len({(path, function) for path, function, _ in WAITS_OF_M9_8}) == 22
    assert gone(sources) == []


def test_a_wait_that_was_repaired_is_seen() -> None:
    """The negative case: one function without its wait."""
    path, function, wait = WAITS_OF_M9_8[-1]
    sources = {path: (ROOT / path).read_text(encoding="utf-8") for path, _, _ in WAITS_OF_M9_8}
    sources[path] = sources[path].replace(wait, "asyncio.Event().wait()")

    assert gone(sources) == [(path, function, wait)]
