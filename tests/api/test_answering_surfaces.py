"""A surface may answer a question only if it shows everything that question names (M13.1 dec. H).

The rule is **derivable and closed in both directions**, which is the point of it: not a list of
devices somebody has to keep up to date, but a comparison between the fields a question declares
and the fields each answering surface reads. The day a question learns a new fact, every surface
that offers a yes either shows it or stops being an answering surface — and this test is what
makes that a fact rather than an intention.

It holds for ``CRITICAL`` before ``CRITICAL`` exists, which is why it is written as a rule and not
as a paragraph about the iPhone.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from ela.tools.terminal import RUNS

from ela.api.schemas import Asked
from ela.cli.system import QUESTION_FIELDS, _questions
from ela.permissions import FS_READ, FS_WRITE, TERMINAL_RUN
from ela.testing.fakes import (
    FakeClock,
    FakeIdGenerator,
    FakeListening,
    FakeModelRouter,
    FakeProbe,
    FakeProviderRegistry,
    FakeScreenCapture,
    FakeSpeech,
    FakeTextRecognition,
)
from ela.tools import (
    CREATES,
    OVERWRITES,
    READS,
    CaptureSettings,
    CaptureStore,
    production_tools,
)
from tests.tools.terminals import a_launcher, a_terminal

_FAKE_MACHINE: dict[str, object] = {
    "clock": FakeClock(),
    "ids": FakeIdGenerator(),
    "router": FakeModelRouter(),
    "providers": FakeProviderRegistry(),
    "screen": FakeScreenCapture(),
    "probe": FakeProbe(),
    "recognition": FakeTextRecognition(),
    "languages": ("it-IT",),
    "listening": FakeListening(),
    "listen_enabled": True,
    "speech": FakeSpeech(),
    "voice": "Alice",
    "voice_enabled": True,
    "speech_online": FakeSpeech(),
    "voice_id": None,
    "model": "eleven_flash_v2_5",
}
"""A machine that answers, so that the question is about the tools and not about this Mac."""

ROOT = Path(__file__).resolve().parents[2]
ANSWERING = {
    "the Command Center": ROOT / "src" / "ela" / "api" / "console.py",
    "the companion": ROOT / "src" / "ela" / "api" / "companion.py",
}
"""The surfaces that compose the question out of its parts (M12.5 dec. F).

A third one added without a line here answers nothing."""

CLI = ROOT / "src" / "ela" / "cli" / "system.py"
"""And the third is the command line: ``ela task approve`` is the first yes anybody gives.

It is held to the same rule, in the same form. It was **not** until M13.1: M12.5 gave the parts of
the question to the two pages and left ``ela approvals`` with the sentence and the targets, and
nobody noticed until this milestone added two fields to the bag and asked where they had to
appear. What closed it is ``QUESTION_FIELDS``, which the CLI declares and this file compares with
``Asked`` **in both directions**."""

NOT_SHOWN: dict[str, str] = {
    "description": "shown as the capability's own sentence, not as a pair",
    "goal": "shown in the `asked` fragment with the declared arguments",
    "stated": "shown in the `asked` fragment, one `stated` per argument",
    "risk": "shown by the `pair-risk` fragment, which is what represents the level (§29 design)",
    "max_privacy": "shown as «Dove può andare»",
    "grant_uses": "shown as «Durata», together with grant_seconds",
    "grant_seconds": "shown as «Durata», together with grant_uses",
}
"""Fields shown by a fragment of their own rather than by naming the attribute in a pair.

Each line is a claim somebody made on purpose; a field that arrives without one fails the test
below, which is the whole mechanism: silence is not an answer.
"""


@pytest.mark.parametrize("surface", sorted(ANSWERING), ids=lambda name: name.split()[-1])
def test_an_answering_surface_reads_every_field_a_question_names(surface: str) -> None:
    source = ANSWERING[surface].read_text(encoding="utf-8")
    unread = [
        field
        for field in Asked.model_fields
        if field not in NOT_SHOWN and not re.search(rf"\bfound\.{field}\b", source)
    ]

    assert not unread, (
        f"{surface} offers a yes to a question that names {unread} and never shows "
        f"{'them' if len(unread) > 1 else 'it'}. Either show the field, or add a line to "
        "NOT_SHOWN saying where it is shown instead, or stop offering the answer on that "
        "surface (M13.1 dec. H)."
    )


def test_the_command_line_declares_exactly_the_fields_a_question_names() -> None:
    """Closed in both directions, like the pages (dec. H).

    One way: a field added to the question tomorrow without a line in ``QUESTION_FIELDS`` fails
    here, so a surface cannot quietly stop showing what it answers. The other way: a name in
    ``QUESTION_FIELDS`` that the question does not have is a claim about nothing, and the
    behavioural test below is what keeps the declaration honest — a declared field that no row
    renders does not survive it.
    """
    assert set(Asked.model_fields) == QUESTION_FIELDS, {
        "not shown by `ela approvals`": sorted(set(Asked.model_fields) - QUESTION_FIELDS),
        "claimed and not in the question": sorted(QUESTION_FIELDS - set(Asked.model_fields)),
    }


def test_every_field_a_question_names_reaches_the_block_the_user_reads() -> None:
    """And it is really rendered, not only declared: one distinctive value per field.

    ``QUESTION_FIELDS`` is a promise; this is the measure of it. Each value below is unique, so a
    row that dropped one — or that rendered the same thing twice — shows up as an absence.
    """
    question = {
        "id": "9f2c1e30-0000-4000-8000-000000000001",
        "task_id": "55ed2ab5-94aa-581f-9468-c4d247d9fe04",
        "capability_id": "fs.write",
        "description": "DESCRIZIONE-DELLA-CAPABILITY",
        "risk": "HIGH",
        "max_privacy": "CLOUD_ALLOWED",
        "grant_uses": 1,
        "grant_seconds": 1800,
        "expires_at": "2026-09-21T10:44:00+00:00",
        "goal": "OBIETTIVO-DELLO-STEP",
        "stated": ["purpose: SCOPO-DICHIARATO"],
        "targets": ["ELA/prova.md"],
        "target": "/Users/tommaso/Documenti/ELA/prova.md",
        "does": "FRASE-DELLA-CAPABILITY",
        "label": "ETICHETTA-DEL-TOOL",
        "runs": "/FILE/A/CUI/PORTA",
        "arguments": ["ARGOMENTO-UNO", "ARGOMENTO DUE"],
        "folder": "/CARTELLA/DI/LAVORO",
        "timeout_seconds": 42,
        "expect_exit": 7,
        "prompt": "LA-FRASE-DELLA-DOMANDA",
    }

    shown = _questions([question])

    for name, appears in {
        "description": "DESCRIZIONE-DELLA-CAPABILITY",
        "risk": "HIGH",
        "max_privacy": "CLOUD_ALLOWED",
        "goal": "OBIETTIVO-DELLO-STEP",
        "stated": "SCOPO-DICHIARATO",
        "grant_uses": "1 use",
        "grant_seconds": "30 minutes",
        "target": "/Users/tommaso/Documenti/ELA/prova.md",
        "does": "FRASE-DELLA-CAPABILITY",
        "label": "ETICHETTA-DEL-TOOL",
        "runs": "/FILE/A/CUI/PORTA",
        "arguments": '["ARGOMENTO-UNO", "ARGOMENTO DUE"]',
        "folder": "/CARTELLA/DI/LAVORO",
        "timeout_seconds": "42 s",
        "expect_exit": "7",
    }.items():
        assert appears in shown, f"`ela approvals` does not show {name} (M13.1 dec. H)"
    assert set(Asked.model_fields) == QUESTION_FIELDS, "and the two lists are the same list"


def test_a_question_about_no_file_leaves_its_two_facts_absent_and_not_wrong() -> None:
    """``None`` is «this question is not about a file», and an absence says it (dec. G)."""
    shown = _questions(
        [
            {
                "id": "9f2c1e30-0000-4000-8000-000000000002",
                "task_id": "55ed2ab5-94aa-581f-9468-c4d247d9fe04",
                "capability_id": "core.echo",
                "targets": [],
                "prompt": "una domanda che non parla di file",
            }
        ]
    )

    assert CREATES not in shown and OVERWRITES not in shown and READS not in shown
    assert RUNS not in shown
    assert "target" in shown, "the row is there and says nothing, which is the truth about it"
    assert "file" not in shown, "and its name is not a word a capability could inherit false"


@pytest.mark.parametrize("surface", sorted(ANSWERING) + ["the command line"])
def test_no_surface_owns_a_sentence_about_files(surface: str) -> None:
    """dec. G, blocker 2 of the proof by hand: the phrase belongs to the **capability**.

    A read was told it «overwrites a file that is already there», because one surface held one
    table of two phrases and applied it to whatever filled the column. The repair is not a third
    phrase in the same table: it is that **no surface holds any of them**. They travel with the
    question, written by the tool that would do the thing.

    Closed over the three surfaces and over the sentences the capabilities really use, so a
    capability added tomorrow cannot inherit another's words.
    """
    source = (ANSWERING.get(surface) or CLI).read_text(encoding="utf-8")

    for sentence in (CREATES, OVERWRITES, READS, RUNS):
        assert sentence not in source, (
            f"{surface} holds «{sentence}». A phrase about what a call does belongs to the "
            "capability that does it, or the next capability inherits words that are false "
            "about it (M13.1 dec. G)."
        )


async def test_the_sentences_are_the_ones_the_capabilities_write(tmp_path: Path) -> None:
    """And the closed world on the other side: which capabilities fill ``does``, and with what.

    Every production tool is asked what it would do, with arguments that are valid for it. The
    two that touch a file and the one that runs a program answer with their own sentence; the eight
    that do not answer nothing — so a ninth that started answering would show up here without a
    line.
    """
    root = tmp_path.resolve() / "files"
    root.mkdir()
    (root / "ELA").mkdir()
    (root / "ELA" / "c.md").write_text("x", encoding="utf-8")
    captures = CaptureStore(CaptureSettings(capture_dir=tmp_path / "captures"))
    tools = production_tools(
        root=tmp_path / "workspace",
        **_FAKE_MACHINE,
        captures=captures,
        fs_root=root,
        terminal=a_terminal(root, "bin/echo"),
        launcher=a_launcher(),
    )
    arguments = {
        FS_READ: {"path": "ELA/c.md", "purpose": "x"},
        FS_WRITE: {"path": "ELA/c.md", "body": "y", "overwrite": True},
        TERMINAL_RUN: {"program": "bin/echo", "args": [], "purpose": "x"},
    }

    said = {
        tool.capability_id: (await tool.prospect(arguments.get(tool.capability_id, {}))).target
        for tool in tools.tools()
    }

    assert {cid: found.does for cid, found in said.items() if found is not None} == {
        FS_READ: READS,
        FS_WRITE: OVERWRITES,
        TERMINAL_RUN: RUNS,
    }


def test_the_claims_are_about_fields_that_exist() -> None:
    """A claim left behind by a field that went away would excuse the next one silently."""
    assert set(NOT_SHOWN) <= set(Asked.model_fields), set(NOT_SHOWN) - set(Asked.model_fields)


def test_the_rule_can_fail() -> None:
    """The negative case: a surface that shows nothing is refused by the same comparison.

    Without this, a regex that stopped matching would make the rule vacuously true — the shape
    ADR 0026 §7 calls a defence that cannot fire.
    """
    silent = "def answer(): return 'sì'"
    unread = [
        field
        for field in Asked.model_fields
        if field not in NOT_SHOWN and not re.search(rf"\bfound\.{field}\b", silent)
    ]

    assert unread, "the comparison no longer detects a surface that shows nothing"
