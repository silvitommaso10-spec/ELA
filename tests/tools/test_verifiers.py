"""``EchoVerifier`` and ``WriteNoteVerifier`` (spec §63; ADR 0014 §2): what holds, what fails,
and that nothing is ever written.

Every case of the note verifier asserts two things: the answer names the reason, and the
workspace is exactly as it was — same tree, same sizes, same modification times — whether the
verification passed or failed. A verifier that changed the world would be a tool.
"""

from __future__ import annotations

import ast
import hashlib
import inspect as inspect_module
import json
import os
import re
import stat
from datetime import timedelta
from pathlib import Path

import pytest

from ela.domain import (
    ErrorMetadata,
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    ProviderUsage,
)
from ela.ports import ROUTING_UNKNOWN_TASK_TYPE, VERIFICATION_UNKNOWN_CONDITION
from ela.routing import BALANCED, QUALITY, ModelRouter
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeModelProvider
from ela.tools import (
    CAPTURE_CODES,
    CAPTURE_DECLARED_MISMATCH,
    CAPTURE_EXISTS,
    CAPTURE_MATCHES,
    CAPTURE_MISSING,
    CAPTURE_NAME_INVALID,
    CAPTURE_NOT_REGULAR,
    COMMON_FAILURE_CODES,
    CORE_ECHO,
    ECHO_MESSAGE_MATCHES,
    ECHO_MESSAGE_MISMATCH,
    ECHO_VERIFIER_NAME,
    MODEL_ANSWERED,
    MODEL_COMPLETE,
    MODEL_MISROUTED,
    MODEL_NO_ANSWER,
    MODEL_ROUTED_AS_ASKED,
    MODEL_TOOL_NAME,
    MODEL_UNACCOUNTED,
    MODEL_VERIFIER_NAME,
    NOTE_CONTENT_MATCHES,
    NOTE_CONTENT_MISMATCH,
    NOTE_EXISTS,
    NOTE_UNREADABLE,
    NOTES_VERIFIER_NAME,
    PATH_CODES,
    PATH_INVALID,
    PATH_IS_DIRECTORY,
    PATH_MISSING,
    PATH_OUTSIDE_WORKSPACE,
    PATH_SYMLINK,
    PATH_UNREACHABLE,
    PERCEPTION_CAPTURE_SCREEN,
    PERCEPTION_READ_SCREEN_TEXT,
    SCREEN_TOOL_NAME,
    VERIFICATION_ARGUMENTS_INVALID,
    WORKSPACE_WRITE_NOTE,
    CaptureScreenVerifier,
    EchoTool,
    EchoVerifier,
    ModelCompleteVerifier,
    ReadScreenTextVerifier,
    Verifier,
    WriteNoteTool,
    WriteNoteVerifier,
)
from ela.tools.captures import ALREADY_EXPIRED, TEXT_MALFORMED, CaptureProblem, inspect_text
from ela.tools.verifiers import TEXT_DECLARED_MISMATCH, TEXT_EXISTS, TEXT_MATCHES
from tests.domain.examples import EXECUTION_RESULT
from tests.routing.support import routing_for
from tests.tools.support import allowed
from tests.tools.test_captures import png

NOTE = "workspace/notes/briefing.md"
BODY = "# Briefing\n\nSECRET-BODY con caratteri multibyte: àèìòù €\n"
BOTH = (NOTE_EXISTS, NOTE_CONTENT_MATCHES)
HEX_64 = re.compile(r"[0-9a-f]{64}")


def succeeded(capability_id: object, **update: object) -> ExecutionResult:
    base = {
        "capability_id": capability_id,
        "status": ExecutionStatus.SUCCEEDED,
        "error": None,
        "output": {},
    }
    return EXECUTION_RESULT.model_copy(update={**base, **update})


def snapshot(directory: Path) -> set[tuple[str, int | None, int | None]]:
    """Every entry under ``directory`` with size and mtime, to prove nothing changed."""
    found: set[tuple[str, int | None, int | None]] = set()
    if not directory.exists():
        return found
    for path in directory.rglob("*"):
        info = path.lstat()
        regular = stat.S_ISREG(info.st_mode)
        found.add(
            (str(path.relative_to(directory)), info.st_size if regular else None, info.st_mtime_ns)
        )
    return found


def codes(failures: tuple[ErrorMetadata, ...]) -> list[str]:
    return [f.code for f in failures]


# --------------------------------------------------------------------------------------
# EchoVerifier
# --------------------------------------------------------------------------------------


@pytest.fixture
def echo() -> EchoVerifier:
    return EchoVerifier()


def test_echo_verifier_declares_itself(echo: EchoVerifier) -> None:
    assert isinstance(echo, Verifier)
    assert echo.capability_id == CORE_ECHO
    assert echo.name == ECHO_VERIFIER_NAME
    assert echo.conditions == {ECHO_MESSAGE_MATCHES}
    assert echo.failure_codes == COMMON_FAILURE_CODES | {ECHO_MESSAGE_MISMATCH}


async def test_echo_verifier_passes_when_the_output_repeats_the_message(echo: EchoVerifier) -> None:
    tool = EchoTool(FakeClock(), FakeIdGenerator())
    result = await tool.execute(allowed(CORE_ECHO), {"message": "ciao"})
    assert await echo.verify((ECHO_MESSAGE_MATCHES,), {"message": "ciao"}, result) == ()


@pytest.mark.parametrize(
    "output", [{"message": "cia"}, {"message": ""}, {}, {"message": 42}], ids=repr
)
async def test_echo_verifier_fails_when_the_output_differs(
    echo: EchoVerifier, output: dict[str, object]
) -> None:
    result = succeeded(CORE_ECHO, output=output)
    failures = await echo.verify((ECHO_MESSAGE_MATCHES,), {"message": "ciao"}, result)
    assert codes(failures) == [ECHO_MESSAGE_MISMATCH]
    (failure,) = failures
    assert failure.retryable is False
    assert failure.details["condition"] == ECHO_MESSAGE_MATCHES
    assert failure.details["expected_length"] == 4
    expected_actual = len(output["message"]) if isinstance(output.get("message"), str) else None
    assert failure.details["actual_length"] == expected_actual
    serialized = json.dumps(failure.model_dump(mode="json"))
    assert "ciao" not in serialized and "cia" not in serialized.replace("ciao", "")


async def test_echo_verifier_refuses_a_message_that_is_not_a_string(echo: EchoVerifier) -> None:
    result = succeeded(CORE_ECHO, output={"message": "1"})
    failures = await echo.verify((ECHO_MESSAGE_MATCHES,), {"message": 1}, result)
    assert codes(failures) == [VERIFICATION_ARGUMENTS_INVALID]


# --------------------------------------------------------------------------------------
# WriteNoteVerifier
# --------------------------------------------------------------------------------------


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


@pytest.fixture
def tool(root: Path) -> WriteNoteTool:
    return WriteNoteTool(root, FakeClock(), FakeIdGenerator())


@pytest.fixture
def verifier(root: Path) -> WriteNoteVerifier:
    return WriteNoteVerifier(root)


async def written(tool: WriteNoteTool, path: str = NOTE, body: str = BODY) -> ExecutionResult:
    result = await tool.execute(allowed(WORKSPACE_WRITE_NOTE), {"path": path, "body": body})
    assert result.status is ExecutionStatus.SUCCEEDED
    return result


async def verify_unchanged(
    verifier: WriteNoteVerifier,
    root: Path,
    conditions: tuple[str, ...],
    arguments: dict[str, object],
    result: ExecutionResult,
) -> tuple[ErrorMetadata, ...]:
    """``verify``, and the proof that the workspace did not change."""
    before = snapshot(root)
    failures = await verifier.verify(conditions, arguments, result)
    assert snapshot(root) == before
    return failures


def test_note_verifier_declares_itself(verifier: WriteNoteVerifier) -> None:
    assert isinstance(verifier, Verifier)
    assert verifier.capability_id == WORKSPACE_WRITE_NOTE
    assert verifier.name == NOTES_VERIFIER_NAME
    assert verifier.conditions == set(BOTH)
    assert verifier.failure_codes == COMMON_FAILURE_CODES | PATH_CODES | {
        NOTE_CONTENT_MISMATCH,
        NOTE_UNREADABLE,
    }


def test_the_root_is_resolved_but_never_created(tmp_path: Path) -> None:
    missing = tmp_path / "nowhere"
    WriteNoteVerifier(missing)
    assert not missing.exists()
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    assert WriteNoteVerifier(link)._root == real.resolve()  # noqa: SLF001


async def test_a_written_note_passes_both_conditions(
    tool: WriteNoteTool, verifier: WriteNoteVerifier, root: Path
) -> None:
    result = await written(tool)
    arguments = {"path": NOTE, "body": BODY}
    assert await verify_unchanged(verifier, root, BOTH, arguments, result) == ()
    assert await verify_unchanged(verifier, root, (NOTE_EXISTS,), arguments, result) == ()
    assert await verify_unchanged(verifier, root, (NOTE_CONTENT_MATCHES,), arguments, result) == ()


async def test_the_comparison_is_with_the_body_not_with_the_tools_output(
    tool: WriteNoteTool, verifier: WriteNoteVerifier, root: Path
) -> None:
    """A tool that reports the right sizes for the wrong content is still caught."""
    result = await written(tool)
    lying = result.model_copy(update={"output": {"path": NOTE, "bytes": len(BODY.encode())}})
    other = {"path": NOTE, "body": BODY + "!"}
    failures = await verify_unchanged(verifier, root, BOTH, other, lying)
    assert codes(failures) == [NOTE_CONTENT_MISMATCH]


async def test_a_deleted_note_is_missing_for_both_conditions(
    tool: WriteNoteTool, verifier: WriteNoteVerifier, root: Path
) -> None:
    result = await written(tool)
    (root / NOTE).unlink()
    failures = await verify_unchanged(verifier, root, BOTH, {"path": NOTE, "body": BODY}, result)
    assert codes(failures) == [PATH_MISSING, PATH_MISSING]
    assert [f.details["condition"] for f in failures] == list(BOTH)
    assert "does not exist" in failures[0].message
    assert all(f.retryable for f in failures)


async def test_an_altered_note_exists_but_its_content_does_not_match(
    tool: WriteNoteTool, verifier: WriteNoteVerifier, root: Path
) -> None:
    result = await written(tool)
    altered = "something else\n"
    (root / NOTE).write_text(altered, encoding="utf-8")
    failures = await verify_unchanged(verifier, root, BOTH, {"path": NOTE, "body": BODY}, result)
    assert codes(failures) == [NOTE_CONTENT_MISMATCH]
    (failure,) = failures
    assert failure.details == {
        "condition": NOTE_CONTENT_MATCHES,
        "expected_bytes": len(BODY.encode("utf-8")),
        "actual_bytes": len(altered.encode("utf-8")),
    }
    assert failure.retryable is True
    serialized = json.dumps(failure.model_dump(mode="json"))
    assert "SECRET-BODY" not in serialized
    assert "something else" not in serialized
    assert HEX_64.search(serialized) is None  # no hash in what may reach the log (decision F)
    assert NOTE in serialized  # the target, yes


async def test_the_hash_of_the_encoded_body_is_what_is_compared(
    tool: WriteNoteTool, verifier: WriteNoteVerifier, root: Path
) -> None:
    result = await written(tool)
    on_disk = hashlib.sha256((root / NOTE).read_bytes()).hexdigest()
    assert on_disk == hashlib.sha256(BODY.encode("utf-8")).hexdigest()
    same_text_other_bytes = BODY.encode("utf-8").decode("utf-8")  # identical: passes
    arguments = {"path": NOTE, "body": same_text_other_bytes}
    assert await verify_unchanged(verifier, root, BOTH, arguments, result) == ()
    (root / NOTE).write_bytes(BODY.encode("utf-16"))  # same text, other bytes: fails
    failures = await verify_unchanged(verifier, root, (NOTE_CONTENT_MATCHES,), arguments, result)
    assert codes(failures) == [NOTE_CONTENT_MISMATCH]


async def test_a_directory_at_the_path_is_missing(
    tool: WriteNoteTool, verifier: WriteNoteVerifier, root: Path
) -> None:
    result = await written(tool)
    (root / NOTE).unlink()
    (root / NOTE).mkdir()
    failures = await verify_unchanged(verifier, root, BOTH, {"path": NOTE, "body": BODY}, result)
    assert codes(failures) == [PATH_IS_DIRECTORY, PATH_IS_DIRECTORY]
    assert "is a directory" in failures[0].message


@pytest.mark.parametrize("inside", [True, False], ids=["link-inside", "link-outside"])
async def test_a_link_at_the_path_is_missing_and_its_target_is_not_read(
    tool: WriteNoteTool, verifier: WriteNoteVerifier, root: Path, tmp_path: Path, inside: bool
) -> None:
    result = await written(tool)
    target = (root / "workspace" / "notes" / "real.md") if inside else (tmp_path / "elsewhere.md")
    target.write_text(BODY, encoding="utf-8")
    (root / NOTE).unlink()
    (root / NOTE).symlink_to(target)
    failures = await verify_unchanged(verifier, root, BOTH, {"path": NOTE, "body": BODY}, result)
    code = PATH_SYMLINK if inside else PATH_OUTSIDE_WORKSPACE  # the tool's code too
    assert codes(failures) == [code, code]
    # a link pointing outside resolves outside; one pointing inside is caught as a link
    expected = "symbolic link" if inside else "resolves outside the workspace"
    assert expected in failures[0].message
    assert target.read_text(encoding="utf-8") == BODY


async def test_a_link_in_an_intermediate_directory_is_missing(
    tool: WriteNoteTool, verifier: WriteNoteVerifier, root: Path, tmp_path: Path
) -> None:
    result = await written(tool)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "briefing.md").write_text(BODY, encoding="utf-8")
    (root / NOTE).unlink()
    (root / "workspace" / "notes").rmdir()
    (root / "workspace" / "notes").symlink_to(elsewhere)
    failures = await verify_unchanged(verifier, root, BOTH, {"path": NOTE, "body": BODY}, result)
    assert codes(failures) == [PATH_OUTSIDE_WORKSPACE, PATH_OUTSIDE_WORKSPACE]
    assert "resolves outside the workspace" in failures[0].message
    # the same link pointing inside the workspace is still a link, and still missing
    inside = root / "inside"
    inside.mkdir()
    (inside / "briefing.md").write_text(BODY, encoding="utf-8")
    (root / "workspace" / "notes").unlink()
    (root / "workspace" / "notes").symlink_to(inside)
    failures = await verify_unchanged(verifier, root, BOTH, {"path": NOTE, "body": BODY}, result)
    assert codes(failures) == [PATH_SYMLINK, PATH_SYMLINK]
    assert "symbolic link" in failures[0].message


@pytest.mark.parametrize(
    "path", ["../x.md", "/etc/x.md", "a//b.md", "a\\b.md", "", "./a.md", "a/../b.md"], ids=repr
)
async def test_a_path_with_the_wrong_shape_is_missing(
    tool: WriteNoteTool, verifier: WriteNoteVerifier, root: Path, path: str
) -> None:
    result = await written(tool)
    failures = await verify_unchanged(verifier, root, BOTH, {"path": path, "body": BODY}, result)
    assert codes(failures) == [PATH_INVALID, PATH_INVALID]
    assert "relative path" in failures[0].message


async def test_a_path_under_a_file_cannot_be_reached(
    tool: WriteNoteTool, verifier: WriteNoteVerifier, root: Path
) -> None:
    """A component that is a regular file: the OS refuses, the verifier says so, no exception."""
    result = await written(tool)
    under_a_file = f"{NOTE}/x.md"
    failures = await verify_unchanged(
        verifier, root, BOTH, {"path": under_a_file, "body": BODY}, result
    )
    assert codes(failures) == [PATH_UNREACHABLE, PATH_UNREACHABLE]
    assert "cannot be reached: NotADirectoryError" in failures[0].message


async def test_a_missing_root_holds_no_note(tmp_path: Path) -> None:
    verifier = WriteNoteVerifier(tmp_path / "nowhere")
    result = succeeded(WORKSPACE_WRITE_NOTE, output={"path": NOTE, "bytes": 3})
    failures = await verifier.verify(BOTH, {"path": NOTE, "body": "hi\n"}, result)
    assert codes(failures) == [PATH_MISSING, PATH_MISSING]
    assert not (tmp_path / "nowhere").exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads everything")
async def test_an_unreadable_note_exists_but_cannot_be_verified(
    tool: WriteNoteTool, verifier: WriteNoteVerifier, root: Path
) -> None:
    result = await written(tool)
    (root / NOTE).chmod(0o000)
    try:
        failures = await verify_unchanged(
            verifier, root, BOTH, {"path": NOTE, "body": BODY}, result
        )
    finally:
        (root / NOTE).chmod(0o600)
    assert codes(failures) == [NOTE_UNREADABLE]
    (failure,) = failures
    assert failure.details["condition"] == NOTE_CONTENT_MATCHES
    assert "PermissionError" in failure.message
    assert failure.retryable is True


async def test_a_note_replaced_by_a_directory_between_the_checks_and_the_read_is_unreadable(
    tool: WriteNoteTool, verifier: WriteNoteVerifier, root: Path
) -> None:
    """The ``fstat`` after ``open`` is the net behind ``lstat``: probed on the read itself."""
    await written(tool)
    with pytest.raises(OSError, match="not a regular file"):
        WriteNoteVerifier._read(root / "workspace" / "notes")  # noqa: SLF001
    assert WriteNoteVerifier._read(root / NOTE) == BODY.encode("utf-8")  # noqa: SLF001


@pytest.mark.parametrize(
    "arguments", [{"path": 1, "body": BODY}, {"path": NOTE, "body": None}, {}], ids=repr
)
async def test_arguments_that_are_not_strings_are_refused(
    tool: WriteNoteTool, verifier: WriteNoteVerifier, root: Path, arguments: dict[str, object]
) -> None:
    result = await written(tool)
    failures = await verify_unchanged(verifier, root, BOTH, arguments, result)
    assert codes(failures) == [VERIFICATION_ARGUMENTS_INVALID, VERIFICATION_ARGUMENTS_INVALID]


async def test_a_root_that_is_a_link_reads_the_real_directory(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    tool = WriteNoteTool(link, FakeClock(), FakeIdGenerator())
    result = await written(tool)
    verifier = WriteNoteVerifier(link)
    assert await verifier.verify(BOTH, {"path": NOTE, "body": BODY}, result) == ()
    assert (real / NOTE).is_file()


async def test_an_unknown_condition_is_refused_before_any_read(
    tool: WriteNoteTool, verifier: WriteNoteVerifier, root: Path
) -> None:
    result = await written(tool)
    (root / NOTE).unlink()  # even a missing note is not looked at
    failures = await verify_unchanged(
        verifier, root, (NOTE_EXISTS, "note.is_poetry"), {"path": NOTE, "body": BODY}, result
    )
    assert codes(failures) == [VERIFICATION_UNKNOWN_CONDITION]


# --------------------------------------------------------------------------------------
# ``ModelCompleteVerifier`` (ADR 0021 §6, ADR 0022 §10)
# --------------------------------------------------------------------------------------


ANSWERED = (MODEL_ANSWERED,)
ROUTED = (MODEL_ROUTED_AS_ASKED,)
MODEL_ARGUMENTS = {"input": "Riassumi le email della riunione."}
MODEL_USAGE = ProviderUsage(input_tokens=12, output_tokens=34)


def completion(**update: object) -> ExecutionResult:
    """A SUCCEEDED ``model.complete`` result, then ``update`` applied."""
    base = ExecutionResult(
        id=ExecutionId(FakeIdGenerator().new_uuid()),
        created_at=FakeClock().now(),
        capability_id=MODEL_COMPLETE,
        status=ExecutionStatus.SUCCEEDED,
        tool_name=MODEL_TOOL_NAME,
        output={
            "output": "una sintesi",
            "provider": "fake",
            "model": "fake-model",
            "finish_reason": "end_turn",
            "profile": BALANCED,
            "skipped": [],
        },
        usage=MODEL_USAGE,
    )
    return base.model_copy(update=update)


@pytest.fixture
def model_router() -> ModelRouter:
    """The real router over one provider named ``fake``: the same policy the tool would use."""
    router, _ = routing_for(FakeModelProvider(FakeClock(), FakeIdGenerator()))
    return router


@pytest.fixture
def model_verifier(model_router: ModelRouter) -> ModelCompleteVerifier:
    return ModelCompleteVerifier(model_router)


async def test_a_completion_with_a_text_a_source_and_a_usage_passes(
    model_verifier: ModelCompleteVerifier,
) -> None:
    assert await model_verifier.verify(ANSWERED, MODEL_ARGUMENTS, completion()) == ()
    assert model_verifier.name == MODEL_VERIFIER_NAME
    assert model_verifier.capability_id == MODEL_COMPLETE


@pytest.mark.parametrize(
    ("output", "missing"),
    [
        ({"provider": "fake", "model": "m"}, ["output"]),
        ({"output": "x", "model": "m"}, ["provider"]),
        ({"output": "x", "provider": "fake"}, ["model"]),
        ({"output": "", "provider": "fake", "model": "m"}, ["output"]),
        ({"output": "x", "provider": 3, "model": "m"}, ["provider"]),
        ({}, ["output", "provider", "model"]),
    ],
    ids=["no-text", "no-provider", "no-model", "empty-text", "provider-not-a-string", "nothing"],
)
async def test_an_answer_that_names_no_source_does_not_pass(
    model_verifier: ModelCompleteVerifier, output: dict[str, object], missing: list[str]
) -> None:
    """The verifier does not trust the tool's word, and a claim with nothing behind it is not
    a verification (§63)."""
    failures = await model_verifier.verify(ANSWERED, MODEL_ARGUMENTS, completion(output=output))
    assert codes(failures) == [MODEL_NO_ANSWER]
    assert list(failures[0].details["missing"]) == missing
    assert failures[0].details["condition"] == MODEL_ANSWERED


async def test_a_completion_that_cannot_be_accounted_for_does_not_pass(
    model_verifier: ModelCompleteVerifier,
) -> None:
    """§32 asks that a provider call be accounted for: a success with no usage is not."""
    failures = await model_verifier.verify(ANSWERED, MODEL_ARGUMENTS, completion(usage=None))
    assert codes(failures) == [MODEL_UNACCOUNTED]
    assert failures[0].retryable is False


async def test_arguments_without_an_input_are_refused(
    model_verifier: ModelCompleteVerifier,
) -> None:
    failures = await model_verifier.verify(ANSWERED, {"input": 3}, completion())
    assert codes(failures) == [VERIFICATION_ARGUMENTS_INVALID]


async def test_the_verifier_never_names_the_answer_it_read(
    model_verifier: ModelCompleteVerifier,
) -> None:
    """A failure says what is missing, never what was there (§57)."""
    private_text = "il numero di conto è 1234"
    failures = await model_verifier.verify(
        ANSWERED,
        {"input": private_text},
        completion(output={"output": private_text, "provider": "fake"}),
    )
    reported = json.dumps([failure.model_dump(mode="json") for failure in failures])
    assert private_text not in reported


async def test_the_verifier_makes_no_second_call(
    model_verifier: ModelCompleteVerifier,
) -> None:
    """It holds no provider at all: asking again would charge again and send the content out a
    second time (§57). The only world it looks at is the result — and a router, which reads a
    table and a declared status and calls nobody (ADR 0022 §7)."""
    assert not any("provider" in name for name in vars(model_verifier))


# --------------------------------------------------------------------------------------
# ``model.routed_as_asked`` (ADR 0022 §10, decision 10b of M7.2)
# --------------------------------------------------------------------------------------


async def test_a_call_that_went_where_the_policy_says_passes(
    model_verifier: ModelCompleteVerifier,
) -> None:
    """The route is recomputed from the **arguments**, not read from what the tool wrote."""
    routed = completion(output={**dict(completion().output), "profile": QUALITY})

    assert (
        await model_verifier.verify(ROUTED, {**MODEL_ARGUMENTS, "task_type": "coding"}, routed)
        == ()
    )
    assert await model_verifier.verify(ROUTED, MODEL_ARGUMENTS, completion()) == ()


async def test_an_explicit_hint_is_what_the_condition_expects(
    model_verifier: ModelCompleteVerifier,
) -> None:
    """The hint wins in the router (ADR 0022 §3), so it wins here too: the verifier asks the same
    question the tool asked, or it would fail every call that carried a hint."""
    hinted = completion(output={**dict(completion().output), "profile": "cheap"})
    arguments = {**MODEL_ARGUMENTS, "task_type": "coding", "model_hint": "cheap"}

    assert await model_verifier.verify(ROUTED, arguments, hinted) == ()


@pytest.mark.parametrize(
    ("output", "expected", "actual"),
    [
        ({"provider": "somebody-else"}, "fake", "somebody-else"),
        ({"profile": "cheap"}, BALANCED, BALANCED),
    ],
    ids=["another-provider", "another-profile"],
)
async def test_a_call_that_went_elsewhere_does_not_pass(
    model_verifier: ModelCompleteVerifier,
    output: dict[str, object],
    expected: str,
    actual: str,
) -> None:
    """§33: a call answered by somebody the policy did not choose is not a verified call, even
    when the answer is perfectly good."""
    result = completion(output={**dict(completion().output), **output})

    failures = await model_verifier.verify(ROUTED, MODEL_ARGUMENTS, result)

    assert codes(failures) == [MODEL_MISROUTED]
    assert failures[0].details["condition"] == MODEL_ROUTED_AS_ASKED
    assert failures[0].details["expected_provider"] == "fake"
    assert failures[0].retryable is False


async def test_a_policy_that_cannot_route_the_call_any_more_does_not_pass(
    model_verifier: ModelCompleteVerifier,
) -> None:
    """A run that cannot be justified today is not a run that was verified: the condition fails
    with the routing code in the details, rather than passing for lack of an opinion."""
    failures = await model_verifier.verify(
        ROUTED, {**MODEL_ARGUMENTS, "task_type": "telepathy"}, completion()
    )

    assert codes(failures) == [MODEL_MISROUTED]
    assert failures[0].details["routing_error"] == ROUTING_UNKNOWN_TASK_TYPE


async def test_routing_arguments_of_the_wrong_type_are_refused(
    model_verifier: ModelCompleteVerifier,
) -> None:
    failures = await model_verifier.verify(
        ROUTED, {**MODEL_ARGUMENTS, "task_type": 7}, completion()
    )

    assert codes(failures) == [VERIFICATION_ARGUMENTS_INVALID]


async def test_the_misrouting_failure_never_names_the_content(
    model_verifier: ModelCompleteVerifier,
) -> None:
    """A failure names providers and profiles — configuration — never the user's text (§57)."""
    private_text = "il numero di conto è 1234"
    result = completion(output={**dict(completion().output), "provider": "somebody-else"})

    failures = await model_verifier.verify(ROUTED, {"input": private_text}, result)

    reported = json.dumps([failure.model_dump(mode="json") for failure in failures])
    assert private_text not in reported


async def test_both_conditions_are_checked_and_both_can_fail(
    model_verifier: ModelCompleteVerifier,
) -> None:
    """``verify`` answers per condition: a result that neither answered nor went where it should
    fails twice, and each failure names its own condition."""
    result = completion(output={"provider": "somebody-else"})

    failures = await model_verifier.verify(
        (MODEL_ANSWERED, MODEL_ROUTED_AS_ASKED), MODEL_ARGUMENTS, result
    )

    assert codes(failures) == [MODEL_NO_ANSWER, MODEL_MISROUTED]


async def test_an_unknown_condition_is_refused(model_verifier: ModelCompleteVerifier) -> None:
    failures = await model_verifier.verify(
        (MODEL_ANSWERED, "model.is_true"), MODEL_ARGUMENTS, completion()
    )
    assert codes(failures) == [VERIFICATION_UNKNOWN_CONDITION]
    assert ModelCompleteVerifier.failure_codes == COMMON_FAILURE_CODES | {
        MODEL_NO_ANSWER,
        MODEL_UNACCOUNTED,
        MODEL_MISROUTED,
    }
    assert ModelCompleteVerifier.conditions == {MODEL_ANSWERED, MODEL_ROUTED_AS_ASKED}


# --------------------------------------------------------------------------------------
# CaptureScreenVerifier (M10.2, ADR 0029 §9)
# --------------------------------------------------------------------------------------


CAPTURE_NAME = "3f2504e0-4f89-41d3-9a0c-0305e82c3301.png"
CAPTURE_TTL = timedelta(seconds=300)
CAPTURE_BOTH = (CAPTURE_EXISTS, CAPTURE_MATCHES)


def captured(directory: Path, name: str = CAPTURE_NAME, **update: object) -> ExecutionResult:
    """A SUCCEEDED ``perception.capture_screen`` result describing what is in ``directory``.

    Built from the disk, so the happy case is genuinely consistent and every failure below is one
    field deliberately made to disagree with the file.
    """
    data = (directory / name).read_bytes() if (directory / name).is_file() else b""
    output: dict[str, object] = {
        "capture_id": name.removesuffix(".png"),
        "path": name,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "width": 2560,
        "height": 1664,
        "display": 1,
        "expires_at": "2026-09-08T15:05:00+00:00",
    }
    return succeeded(
        PERCEPTION_CAPTURE_SCREEN,
        tool_name=SCREEN_TOOL_NAME,
        output={**output, **update},
    )


@pytest.fixture
def captures(tmp_path: Path) -> Path:
    directory = tmp_path / "captures"
    directory.mkdir()
    return directory


@pytest.fixture
def capture_verifier(captures: Path) -> CaptureScreenVerifier:
    return CaptureScreenVerifier(captures, CAPTURE_TTL)


def test_capture_verifier_declares_itself(capture_verifier: CaptureScreenVerifier) -> None:
    assert capture_verifier.capability_id == PERCEPTION_CAPTURE_SCREEN
    assert capture_verifier.conditions == {CAPTURE_EXISTS, CAPTURE_MATCHES}
    assert capture_verifier.failure_codes == (
        COMMON_FAILURE_CODES | CAPTURE_CODES | {CAPTURE_DECLARED_MISMATCH}
    )


async def test_a_captured_screen_passes_both_conditions(
    captures: Path, capture_verifier: CaptureScreenVerifier
) -> None:
    (captures / CAPTURE_NAME).write_bytes(png())

    assert await capture_verifier.verify(CAPTURE_BOTH, {}, captured(captures)) == ()


async def test_a_capture_that_was_purged_fails_both_conditions(
    captures: Path, capture_verifier: CaptureScreenVerifier
) -> None:
    """The declared limit of ADR 0029 §9, made visible: verify inside the TTL or find nothing."""
    result = captured(captures)

    assert codes(await capture_verifier.verify(CAPTURE_BOTH, {}, result)) == [
        CAPTURE_MISSING,
        CAPTURE_MISSING,
    ]


async def test_a_name_the_store_never_issued_is_refused_before_the_disk(
    capture_verifier: CaptureScreenVerifier,
) -> None:
    """The name arrives from a persisted result, so it is checked as a name and not as a path."""
    result = captured(Path("/nowhere"), path="../ela.db")

    assert codes(await capture_verifier.verify((CAPTURE_EXISTS,), {}, result)) == [
        CAPTURE_NAME_INVALID
    ]


async def test_a_link_where_the_capture_should_be_is_not_the_capture(
    captures: Path, capture_verifier: CaptureScreenVerifier
) -> None:
    real = captures / "9c858901-8a57-4791-81fe-4c455b099bc9.png"
    real.write_bytes(png())
    (captures / CAPTURE_NAME).symlink_to(real)

    assert codes(await capture_verifier.verify((CAPTURE_EXISTS,), {}, captured(captures))) == [
        CAPTURE_NOT_REGULAR
    ]


async def test_an_output_without_a_name_is_refused(
    capture_verifier: CaptureScreenVerifier,
) -> None:
    result = captured(Path("/nowhere"), path=42)

    assert codes(await capture_verifier.verify(CAPTURE_BOTH, {}, result)) == [
        VERIFICATION_ARGUMENTS_INVALID,
        VERIFICATION_ARGUMENTS_INVALID,
    ]


@pytest.mark.parametrize(
    ("field", "wrong"),
    [("bytes", 1), ("sha256", "0" * 64), ("width", 1024), ("height", 768)],
)
async def test_a_capture_that_is_not_what_the_result_describes_fails_the_match(
    captures: Path, capture_verifier: CaptureScreenVerifier, field: str, wrong: object
) -> None:
    """The comparison is against the **output**, and that is not "trusting the tool's word":
    ``purpose`` and ``display`` determine no pixel, so the claim *is* what is under test and the
    disk is the source of truth (§20, ADR 0029 §9)."""
    (captures / CAPTURE_NAME).write_bytes(png())
    result = captured(captures, **{field: wrong})

    failures = await capture_verifier.verify((CAPTURE_MATCHES,), {}, result)

    assert codes(failures) == [CAPTURE_DECLARED_MISMATCH]
    assert field in failures[0].message


async def test_the_mismatch_names_the_fields_and_never_prints_two_digests(
    captures: Path, capture_verifier: CaptureScreenVerifier
) -> None:
    """Two hashes in a message are two fingerprints of the user's screen in the trail (§57)."""
    data = png()
    (captures / CAPTURE_NAME).write_bytes(data)
    result = captured(captures, sha256="0" * 64)

    failures = await capture_verifier.verify((CAPTURE_MATCHES,), {}, result)

    assert hashlib.sha256(data).hexdigest() not in failures[0].message
    assert "0" * 64 not in failures[0].message


async def test_the_verifier_writes_nothing_and_leaves_the_mode_alone(
    captures: Path, capture_verifier: CaptureScreenVerifier
) -> None:
    """Rule 18 reads the AST; this reads the disk before and after."""
    (captures / CAPTURE_NAME).write_bytes(png())
    (captures / CAPTURE_NAME).chmod(0o644)
    before = snapshot(captures)

    await capture_verifier.verify(CAPTURE_BOTH, {}, captured(captures))

    assert snapshot(captures) == before
    assert stat.S_IMODE((captures / CAPTURE_NAME).stat().st_mode) == 0o644


async def test_an_unknown_condition_is_refused_by_the_capture_verifier(
    capture_verifier: CaptureScreenVerifier,
) -> None:
    failures = await capture_verifier.verify(
        (CAPTURE_EXISTS, "capture.is_beautiful"), {}, captured(Path("/nowhere"))
    )
    assert codes(failures) == [VERIFICATION_UNKNOWN_CONDITION]


# ----------------------------------------------------------------------------------------
# ``perception.read_screen_text``: the disk against the declaration (ADR 0030 §14)
# ----------------------------------------------------------------------------------------


def jsonl_bytes(*lines: tuple[str, float]) -> bytes:
    return "".join(
        json.dumps({"text": text, "confidence": confidence}) + "\n" for text, confidence in lines
    ).encode("utf-8")


TEXT_ID = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"


def text_result(tmp_path: Path, data: bytes, **override: object) -> ExecutionResult:
    """A capture, its recognition, and the result the tool would have reported for it.

    Built from the disk, so the happy case is genuinely consistent and every failure below is one
    field deliberately made to disagree with the file.
    """
    (tmp_path / f"{TEXT_ID}.png").write_bytes(png())
    (tmp_path / f"{TEXT_ID}.jsonl").write_bytes(data)
    parsed = [json.loads(line) for line in data.decode().splitlines()]
    output: dict[str, object] = {
        "capture_id": TEXT_ID,
        "path": f"{TEXT_ID}.jsonl",
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "lines": len(parsed),
        "characters": sum(len(one["text"]) for one in parsed),
        **override,
    }
    return succeeded(PERCEPTION_READ_SCREEN_TEXT, output=output)


@pytest.mark.parametrize("condition", [TEXT_EXISTS, TEXT_MATCHES])
async def test_a_recognition_the_tool_wrote_verifies(tmp_path: Path, condition: str) -> None:
    data = jsonl_bytes(("Riunione trimestrale", 1.0), ("Budget", 0.9))
    verifier = ReadScreenTextVerifier(tmp_path, timedelta(seconds=300))

    assert await verifier.verify((condition,), {}, text_result(tmp_path, data)) == ()


@pytest.mark.parametrize(
    "override,differing",
    [
        ({"bytes": 1}, "bytes"),
        ({"sha256": "0" * 64}, "sha256"),
        ({"lines": 99}, "lines"),
        ({"characters": 99}, "characters"),
    ],
    ids=["bytes", "sha256", "lines", "characters"],
)
async def test_a_declaration_the_disk_contradicts_is_caught(
    tmp_path: Path, override: dict[str, object], differing: str
) -> None:
    """The comparison is against the **output** and not the arguments, and that is not the
    "trusting the tool's word" mistake: ``purpose`` and ``region`` determine no character, so
    there is no intent to compare with. What is under test *is* the claim."""
    data = jsonl_bytes(("Riunione", 1.0))
    verifier = ReadScreenTextVerifier(tmp_path, timedelta(seconds=300))

    (failure,) = await verifier.verify((TEXT_MATCHES,), {}, text_result(tmp_path, data, **override))

    assert failure.code == TEXT_DECLARED_MISMATCH
    assert differing in failure.message
    assert "Riunione" not in failure.message  # names what differs, never the values


async def test_a_recognition_that_is_not_json_lines_is_malformed(tmp_path: Path) -> None:
    verifier = ReadScreenTextVerifier(tmp_path, timedelta(seconds=300))
    result = text_result(tmp_path, jsonl_bytes(("x", 1.0)))
    (tmp_path / f"{TEXT_ID}.jsonl").write_bytes(b"half an ans")

    (failure,) = await verifier.verify((TEXT_EXISTS,), {}, result)

    assert failure.code == TEXT_MALFORMED


async def test_a_recognition_whose_capture_is_gone_has_already_expired(tmp_path: Path) -> None:
    """The shared lifetime, seen from the verifier: no image, no expiry to inherit, and the
    artefact reads as gone rather than as merely old."""
    verifier = ReadScreenTextVerifier(tmp_path, timedelta(seconds=300))
    result = text_result(tmp_path, jsonl_bytes(("x", 1.0)))
    (tmp_path / f"{TEXT_ID}.png").unlink()

    found = inspect_text(tmp_path, f"{TEXT_ID}.jsonl", timedelta(seconds=300))

    assert not isinstance(found, CaptureProblem)
    assert found.expires_at == ALREADY_EXPIRED
    assert await verifier.verify((TEXT_EXISTS,), {}, result) == ()  # readable, and already expired


async def test_a_path_that_is_not_a_string_is_refused_before_the_disk(tmp_path: Path) -> None:
    verifier = ReadScreenTextVerifier(tmp_path, timedelta(seconds=300))

    (failure,) = await verifier.verify(
        (TEXT_EXISTS,), {}, succeeded(PERCEPTION_READ_SCREEN_TEXT, output={"path": 7})
    )

    assert failure.code == VERIFICATION_ARGUMENTS_INVALID


def test_the_verifier_cannot_recognise_anything_even_if_it_wanted_to() -> None:
    """Verifying is not redoing, and here that is structural rather than disciplined.

    What the verifier cannot say — that the text is what was on the screen — is a declared limit,
    and the reason it cannot drift into saying it is that **it is never given a recogniser**: its
    constructor takes a directory and a retention, so there is nothing to call. Asserted on the
    signature rather than on the source text, because a docstring that mentions recognising is
    exactly what this class should be allowed to have.
    """
    parameters = inspect_module.signature(ReadScreenTextVerifier.__init__).parameters

    assert set(parameters) == {"self", "directory", "ttl", "name"}
    assert not [
        node
        for node in ast.walk(ast.parse(inspect_module.getsource(ReadScreenTextVerifier)))
        if isinstance(node, ast.Attribute) and node.attr == "recognise"
    ]
