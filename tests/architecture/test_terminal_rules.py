"""Three rules M13.2 writes down, each with the case that makes it fail (ADR 0047).

* **No module that builds an ``AuditEvent`` reads ``ASKED``** (decision 10): the facts of a
  question — the arguments of a command among them — live beside the question in the table of the
  approvals, and the audit is the log that is never redacted. Verified on the tree at ``1c24ec1``
  before the decision leaned on it; this is what keeps it true.
* **The three surfaces that answer render through one function** (decision 13): the command line,
  the Command Center and the companion call ``ela.domain.visible``, and no other module of ``ela``
  holds the characters it makes visible — a copy is how two surfaces stop agreeing.
* **The numbers of ``TOOL_EXECUTED`` are written by one function** (decision 10, Domanda 2): the
  only value the key ``numbers`` of a payload may take is a call of ``audited_numbers``, the
  function that lets through integers and nothing else.

Each reads the source with ``ast`` and is run against a fabricated module that breaks it: a rule
that only ever passes proves nothing (CLAUDE.md, «Qualità»).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "ela"
SURFACES = (
    PACKAGE / "cli" / "system.py",
    PACKAGE / "cli" / "tasks.py",
    PACKAGE / "api" / "console.py",
    PACKAGE / "api" / "companion.py",
)
"""The modules that put a question or a result in front of a person: the approvals and the results
of the command line, and the approval pages of the two surfaces that answer."""
RENDERING = PACKAGE / "domain.py"
BIDI_AND_INVISIBLE = ("202a", "202b", "202c", "202d", "202e", "2066", "2069", "200b", "feff")
"""Spelled as a module would spell them, in lower or upper case, to find a copy of the table."""


def modules() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py"))


def tree(source: str) -> ast.Module:
    return ast.parse(source)


# ----------------------------------------------------------------------------------------
# Rule: what builds the audit does not read the question's facts
# ----------------------------------------------------------------------------------------


def builds_audit_events(module: ast.Module) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name | ast.Attribute)
        and (node.func.id if isinstance(node.func, ast.Name) else node.func.attr) == "AuditEvent"
        for node in ast.walk(module)
    )


def reads_asked(module: ast.Module) -> list[int]:
    """The lines that *read* the bag — ``x[ASKED]`` loaded, ``x.get(ASKED)`` — never the write
    ``{ASKED: ...}`` the executor does when it composes the question."""
    found = []
    for node in ast.walk(module):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.ctx, ast.Load)
            and _names_asked(node.slice)
        ):
            found.append(node.lineno)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and _names_asked(node.args[0])
        ):
            found.append(node.lineno)
    return found


def _names_asked(node: ast.expr) -> bool:
    return (isinstance(node, ast.Name) and node.id == "ASKED") or (
        isinstance(node, ast.Constant) and node.value == "asked"
    )


def asked_readers_that_build_the_audit(sources: dict[str, str]) -> list[str]:
    offenders = []
    for name, source in sources.items():
        module = tree(source)
        if builds_audit_events(module) and reads_asked(module):
            offenders.append(name)
    return offenders


def test_no_module_that_builds_an_audit_event_reads_the_facts_of_a_question() -> None:
    sources = {
        str(path.relative_to(PACKAGE)): path.read_text(encoding="utf-8") for path in modules()
    }

    assert asked_readers_that_build_the_audit(sources) == []


def test_the_rule_of_the_question_s_facts_can_fail() -> None:
    offender = (
        "def record(approval, audit):\n"
        "    arguments = approval.metadata.get(ASKED)\n"
        "    audit.append(AuditEvent(payload={'arguments': arguments}))\n"
    )
    writer = "def ask():\n    return Approval(metadata={ASKED: {}})\nAuditEvent()\n"

    assert asked_readers_that_build_the_audit({"offender.py": offender}) == ["offender.py"]
    assert asked_readers_that_build_the_audit({"writer.py": writer}) == []


# ----------------------------------------------------------------------------------------
# Rule: one rendering for the three surfaces
# ----------------------------------------------------------------------------------------


def calls_visible(source: str) -> bool:
    module = tree(source)
    imported = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "ela.domain"
        and any(alias.name in {"visible", "listed"} for alias in node.names)
        for node in ast.walk(module)
    )
    called = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"visible", "listed"}
        for node in ast.walk(module)
    )
    return imported and called


def holds_a_copy(source: str) -> bool:
    lowered = source.lower()
    return any(point in lowered for point in BIDI_AND_INVISIBLE)


@pytest.mark.parametrize("surface", SURFACES, ids=lambda path: path.name)
def test_every_surface_renders_through_the_one_function(surface: Path) -> None:
    assert calls_visible(surface.read_text(encoding="utf-8")), surface


def test_no_module_but_the_domain_holds_the_characters_it_makes_visible() -> None:
    copies = [
        str(path.relative_to(PACKAGE))
        for path in modules()
        if path != RENDERING and holds_a_copy(path.read_text(encoding="utf-8"))
    ]

    assert copies == []
    assert holds_a_copy(RENDERING.read_text(encoding="utf-8")), "the table must be somewhere"


def test_the_rule_of_the_one_rendering_can_fail() -> None:
    silent = "def show(text):\n    return text\n"
    copied = "def show(text):\n    return text.replace('\\u202e', '')\n"

    assert not calls_visible(silent)
    assert holds_a_copy(copied)


# ----------------------------------------------------------------------------------------
# Rule: the numbers of TOOL_EXECUTED come from one function
# ----------------------------------------------------------------------------------------


def numbers_not_from_the_function(source: str) -> list[int]:
    found = []
    for node in ast.walk(tree(source)):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values, strict=True):
            named = (isinstance(key, ast.Constant) and key.value == "numbers") or (
                isinstance(key, ast.Name) and key.id == "NUMBERS"
            )
            if named and not (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "audited_numbers"
            ):
                found.append(node.lineno)
    return found


def test_the_numbers_of_a_payload_are_always_the_one_function_s() -> None:
    offenders = {
        str(path.relative_to(PACKAGE)): lines
        for path in modules()
        if (lines := numbers_not_from_the_function(path.read_text(encoding="utf-8")))
    }

    assert offenders == {}


def test_the_numbers_are_written_somewhere_at_all() -> None:
    """The positive half: the executor does write them, through the function."""
    executor = (PACKAGE / "executive" / "executor.py").read_text(encoding="utf-8")

    assert "audited_numbers(" in executor
    assert "NUMBERS" in executor


def test_the_rule_of_the_numbers_can_fail() -> None:
    forged = "payload = {'numbers': {'count': result.output['args']}}\n"
    honest = "payload = {NUMBERS: audited_numbers(tool.audit_numbers, result.output)}\n"

    assert numbers_not_from_the_function(forged) == [1]
    assert numbers_not_from_the_function(honest) == []
