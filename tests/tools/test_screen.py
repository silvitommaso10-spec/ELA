"""``perception.capture_screen`` (§29, MEDIUM): ELA photographs one display (M10.2, ADR 0029).

The first test in this file is the one that mattered before any permission existed, and it is
the acceptance criterion the milestone put first: **with Screen Recording denied, ELA says so,
does not fail, and never runs the helper.** Not attempting is the behaviour — attempting a
capture from a denied state is how the operating system records a *permanent* denial — so it is
tested by watching the adapter's calls, not by looking for an absent file.

Every negative case asserts two things, as ``test_notes.py`` does: the result names the refusal,
and the store is left exactly as it was. There is no residue, because a half-written photograph
of somebody's screen that nobody knows about is the worst thing this milestone could leave
behind.
"""

from __future__ import annotations

import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ela.domain import ExecutionStatus, RawCapture, RawObservation
from ela.ports import NotAllowedError
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeProbe, FakeScreenCapture
from ela.tools import (
    ARGUMENTS_INVALID,
    CAPTURE_MALFORMED,
    CAPTURE_MISSING,
    PERCEPTION_CAPTURE_SCREEN,
    SCREEN_CAPTURE_FAILED,
    SCREEN_NOT_OBSERVABLE,
    SCREEN_PERMISSION_DENIED,
    SCREEN_STORE_FULL,
    SCREEN_TIMEOUT,
    SCREEN_TOOL_NAME,
    SCREEN_UNSUPPORTED,
    CaptureScreenTool,
    CaptureSettings,
    CaptureStore,
)
from tests.tools.support import allowed
from tests.tools.test_captures import png, write

DECISION = allowed(PERCEPTION_CAPTURE_SCREEN)
PURPOSE = "reading the failing test output"
GRANTED = RawObservation(screen_recording_permission=True)
DENIED = RawObservation(screen_recording_permission=False)
UNREADABLE = RawObservation()


def clock() -> FakeClock:
    """A clock standing where the filesystem stands.

    Every other test in ELA lets ``FakeClock`` start wherever it likes, because nothing else
    compares its time with the world's. A capture's age is read from its own ``mtime``
    (ADR 0029 §1), so here the two must agree — in production they do, and a fake that started in
    the past would make every capture look brand new and the purge look broken.
    """
    return FakeClock(datetime.now(tz=UTC))


def store(directory: Path, **overrides: object) -> CaptureStore:
    return CaptureStore(CaptureSettings(capture_dir=directory, **overrides))  # type: ignore[arg-type]


def tool(
    directory: Path,
    *,
    observed: RawObservation = GRANTED,
    capture: FakeScreenCapture | None = None,
    **overrides: object,
) -> tuple[CaptureScreenTool, FakeScreenCapture, CaptureStore]:
    helper = capture if capture is not None else FakeScreenCapture(payload=png())
    kept = store(directory, **overrides)
    return (
        CaptureScreenTool(kept, helper, FakeProbe([observed]), clock(), FakeIdGenerator()),
        helper,
        kept,
    )


async def run(
    subject: CaptureScreenTool, **arguments: object
) -> tuple[str | None, dict[str, object]]:
    """The tool's result, as ``(error code or None, output)``."""
    result = await subject.execute(DECISION, {"purpose": PURPOSE, **arguments})
    code = None if result.error is None else result.error.code
    return code, dict(result.output)


def held(directory: Path) -> list[str]:
    return sorted(entry.name for entry in directory.iterdir())


# ----------------------------------------------------------------------------------------
# Criterion 3: the permission is missing, and it is a first-class answer
# ----------------------------------------------------------------------------------------


async def test_a_denied_permission_is_reported_and_the_helper_is_never_run(
    tmp_path: Path,
) -> None:
    """The milestone's first acceptance criterion, verifiable with the permission still denied.

    ``helper.calls`` empty is the assertion that matters: ELA does not attempt what it knows it
    may not do, because attempting it is how a permanent denial gets recorded (ADR 0029 §7).
    """
    subject, helper, kept = tool(tmp_path / "captures", observed=DENIED)

    code, output = await run(subject)

    assert code == SCREEN_PERMISSION_DENIED
    assert helper.calls == ()
    assert output == {}
    assert held(kept.directory) == []


async def test_the_refusal_says_what_to_do_about_it(tmp_path: Path) -> None:
    """A process that is not an application cannot obtain this permission by asking (ADR 0028
    §2), so the only correct thing ELA can do is say precisely where a human grants it."""
    subject, _, _ = tool(tmp_path / "captures", observed=DENIED)

    result = await subject.execute(DECISION, {"purpose": PURPOSE})

    assert result.error is not None
    assert "Screen & System Audio Recording" in result.error.message
    assert "quit and reopen" in result.error.message


async def test_a_denied_permission_is_a_failed_result_and_not_an_exception(
    tmp_path: Path,
) -> None:
    """§33: the task learns what happened; it does not blow up."""
    subject, _, _ = tool(tmp_path / "captures", observed=DENIED)

    result = await subject.execute(DECISION, {"purpose": PURPOSE})

    assert result.status is ExecutionStatus.FAILED
    assert result.tool_name == SCREEN_TOOL_NAME


async def test_a_denied_permission_is_not_retryable(tmp_path: Path) -> None:
    """It can succeed later, but only after a human acts: retrying on its own changes nothing."""
    subject, _, _ = tool(tmp_path / "captures", observed=DENIED)

    result = await subject.execute(DECISION, {"purpose": PURPOSE})

    assert result.error is not None and not result.error.retryable


async def test_a_permission_that_cannot_be_read_attempts_nothing_either(tmp_path: Path) -> None:
    """A doubt is not a yes (§33). Retryable, because the next read may answer."""
    subject, helper, kept = tool(tmp_path / "captures", observed=UNREADABLE)

    result = await subject.execute(DECISION, {"purpose": PURPOSE})

    assert result.error is not None
    assert result.error.code == SCREEN_NOT_OBSERVABLE
    assert result.error.retryable
    assert helper.calls == ()
    assert held(kept.directory) == []


async def test_the_permission_is_read_at_the_instant_of_the_capture(tmp_path: Path) -> None:
    """ADR 0029 §7: a periodic belief never decides an action.

    The perception core refreshes this permission every thirty seconds. The tool asks again, and
    asks for the permissions family only — the belief is for telling, not for deciding.
    """
    from ela.domain import ProbeFamily

    probe = FakeProbe([GRANTED])
    subject = CaptureScreenTool(
        store(tmp_path / "captures"),
        FakeScreenCapture(payload=png()),
        probe,
        clock(),
        FakeIdGenerator(),
    )

    await subject.execute(DECISION, {"purpose": PURPOSE})

    assert probe.calls == (frozenset({ProbeFamily.PERMISSIONS}),)


# ----------------------------------------------------------------------------------------
# Criterion 5: an operating system that has none of this
# ----------------------------------------------------------------------------------------


async def test_a_machine_with_no_capture_helper_says_so_before_reading_a_permission(
    tmp_path: Path,
) -> None:
    """ADR 0029 §11: a named answer, not a gap — and settled *before* the permission, so a
    machine that could never capture does not read one it has no use for."""
    probe = FakeProbe([GRANTED])
    helper = FakeScreenCapture(there=False)
    subject = CaptureScreenTool(
        store(tmp_path / "captures"), helper, probe, clock(), FakeIdGenerator()
    )

    result = await subject.execute(DECISION, {"purpose": PURPOSE})

    assert result.error is not None
    assert result.error.code == SCREEN_UNSUPPORTED
    assert not result.error.retryable
    assert probe.calls == ()
    assert helper.calls == ()


# ----------------------------------------------------------------------------------------
# Criterion 4: the capture that worked
# ----------------------------------------------------------------------------------------


async def test_a_capture_reports_what_the_artefact_is_and_never_a_pixel(tmp_path: Path) -> None:
    import hashlib

    data = png()
    subject, helper, kept = tool(tmp_path / "captures", capture=FakeScreenCapture(payload=data))

    code, output = await run(subject)

    assert code is None
    assert set(output) == set(CaptureScreenTool.output_keys)
    assert output["bytes"] == len(data)
    assert output["sha256"] == hashlib.sha256(data).hexdigest()
    assert output["width"] == 2560
    assert output["height"] == 1664
    assert output["display"] == 1
    assert output["path"] == f"{output['capture_id']}.png"
    assert helper.calls == ((str(kept.directory / str(output["path"])), 1),)


async def test_the_output_carries_the_name_and_not_a_path_under_the_home(tmp_path: Path) -> None:
    """§57: the store lives under the user's home, and a home directory does not belong in a
    persisted result any more than a pixel does."""
    subject, _, _ = tool(tmp_path / "captures")

    _, output = await run(subject)

    assert "/" not in str(output["path"])
    assert str(tmp_path) not in str(output)


async def test_the_capture_is_private_in_a_private_directory(tmp_path: Path) -> None:
    subject, _, kept = tool(tmp_path / "captures")

    _, output = await run(subject)

    target = kept.directory / str(output["path"])
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(kept.directory.stat().st_mode) == 0o700


async def test_the_display_the_caller_asked_for_is_the_one_the_helper_is_given(
    tmp_path: Path,
) -> None:
    subject, helper, _ = tool(tmp_path / "captures")

    _, output = await run(subject, display=3)

    assert output["display"] == 3
    assert helper.calls[0][1] == 3


async def test_the_expiry_the_result_declares_is_the_one_the_purge_will_apply(
    tmp_path: Path,
) -> None:
    subject, _, kept = tool(tmp_path / "captures")

    _, output = await run(subject)

    assert output["expires_at"] == kept.retained()[0].expires_at.isoformat()


# ----------------------------------------------------------------------------------------
# The arguments, checked again because a tool never trusts its caller (§28)
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("purpose", [None, "", 42, {"why": "because"}])
async def test_a_purpose_that_is_not_a_non_empty_string_is_refused_before_any_io(
    tmp_path: Path, purpose: object
) -> None:
    subject, helper, kept = tool(tmp_path / "captures")

    result = await subject.execute(DECISION, {"purpose": purpose})

    assert result.error is not None and result.error.code == ARGUMENTS_INVALID
    assert helper.calls == ()
    assert held(kept.directory) == []


@pytest.mark.parametrize("display", [0, -1, "1", 1.0, True])
async def test_a_display_that_is_not_a_positive_integer_is_refused(
    tmp_path: Path, display: object
) -> None:
    """``True`` is an ``int`` in Python and is not a display: the check says so on purpose."""
    subject, helper, _ = tool(tmp_path / "captures")

    code, _ = await run(subject, display=display)

    assert code == ARGUMENTS_INVALID
    assert helper.calls == ()


# ----------------------------------------------------------------------------------------
# What the helper leaves behind, and the residue that must not survive it
# ----------------------------------------------------------------------------------------


async def test_a_helper_that_exits_badly_leaves_no_residue(tmp_path: Path) -> None:
    subject, _, kept = tool(
        tmp_path / "captures",
        capture=FakeScreenCapture(payload=png()[:10], report=RawCapture(exit_code=1)),
    )

    result = await subject.execute(DECISION, {"purpose": PURPOSE})

    assert result.error is not None
    assert result.error.code == SCREEN_CAPTURE_FAILED
    assert "1" in result.error.message
    assert result.error.retryable
    assert held(kept.directory) == []


async def test_a_helper_that_is_killed_for_overstaying_leaves_no_residue(tmp_path: Path) -> None:
    """The failure mode M10.1 did not have: a partial file at ``0o600`` on the disk."""
    subject, _, kept = tool(
        tmp_path / "captures",
        capture=FakeScreenCapture(
            payload=png()[:12], report=RawCapture(exit_code=-1, timed_out=True)
        ),
    )

    result = await subject.execute(DECISION, {"purpose": PURPOSE})

    assert result.error is not None
    assert result.error.code == SCREEN_TIMEOUT
    assert result.error.retryable
    assert held(kept.directory) == []


async def test_a_helper_that_exits_zero_and_writes_nothing_is_not_a_capture(
    tmp_path: Path,
) -> None:
    """§20: sending is not succeeding. The exit code alone is never the answer."""
    subject, _, kept = tool(tmp_path / "captures", capture=FakeScreenCapture(payload=None))

    code, output = await run(subject)

    assert code == CAPTURE_MISSING
    assert output == {}
    assert held(kept.directory) == []


async def test_a_helper_that_exits_zero_and_writes_junk_is_not_a_capture(tmp_path: Path) -> None:
    subject, _, kept = tool(
        tmp_path / "captures", capture=FakeScreenCapture(payload=b"<!doctype html>")
    )

    code, _ = await run(subject)

    assert code == CAPTURE_MALFORMED
    assert held(kept.directory) == []


async def test_a_failure_removes_only_what_this_capture_left(tmp_path: Path) -> None:
    """Discarding a failure is not a purge: the captures already held stay."""
    directory = tmp_path / "captures"
    directory.mkdir()
    write(directory, "9c858901-8a57-4791-81fe-4c455b099bc9.png", png())
    subject, _, kept = tool(directory, capture=FakeScreenCapture(payload=None))

    await subject.execute(DECISION, {"purpose": PURPOSE})

    assert held(kept.directory) == ["9c858901-8a57-4791-81fe-4c455b099bc9.png"]


# ----------------------------------------------------------------------------------------
# The store: every capture is a purge, and the ceilings refuse
# ----------------------------------------------------------------------------------------


async def test_a_capture_purges_what_expired(tmp_path: Path) -> None:
    directory = tmp_path / "captures"
    directory.mkdir()
    write(directory, "9c858901-8a57-4791-81fe-4c455b099bc9.png", png(), age=timedelta(hours=1))
    subject, _, kept = tool(directory)

    _, output = await run(subject)

    assert held(kept.directory) == [str(output["path"])]


async def test_a_capture_keeps_what_has_not_expired(tmp_path: Path) -> None:
    directory = tmp_path / "captures"
    directory.mkdir()
    write(directory, "9c858901-8a57-4791-81fe-4c455b099bc9.png", png(), age=timedelta(seconds=1))
    subject, _, kept = tool(directory)

    _, output = await run(subject)

    assert held(kept.directory) == sorted(
        ["9c858901-8a57-4791-81fe-4c455b099bc9.png", str(output["path"])]
    )


async def test_the_count_ceiling_refuses_and_does_not_evict(tmp_path: Path) -> None:
    """ADR 0029 §15: deleting one somebody may still be reading is acting on something else."""
    directory = tmp_path / "captures"
    directory.mkdir()
    write(directory, "9c858901-8a57-4791-81fe-4c455b099bc9.png", png())
    subject, helper, kept = tool(directory, capture_max_count=1)

    result = await subject.execute(DECISION, {"purpose": PURPOSE})

    assert result.error is not None
    assert result.error.code == SCREEN_STORE_FULL
    assert result.error.retryable
    assert helper.calls == ()
    assert held(kept.directory) == ["9c858901-8a57-4791-81fe-4c455b099bc9.png"]


async def test_the_byte_ceiling_refuses_too(tmp_path: Path) -> None:
    directory = tmp_path / "captures"
    directory.mkdir()
    data = png()
    write(directory, "9c858901-8a57-4791-81fe-4c455b099bc9.png", data)
    subject, helper, _ = tool(directory, capture_max_bytes=len(data))

    code, _ = await run(subject)

    assert code == SCREEN_STORE_FULL
    assert helper.calls == ()


async def test_a_ceiling_reached_only_by_expired_captures_still_has_room(tmp_path: Path) -> None:
    """The purge runs first, so what the ceilings count is what has not expired."""
    directory = tmp_path / "captures"
    directory.mkdir()
    write(directory, "9c858901-8a57-4791-81fe-4c455b099bc9.png", png(), age=timedelta(hours=1))
    subject, _, _ = tool(directory, capture_max_count=1)

    code, _ = await run(subject)

    assert code is None


def test_the_purge_is_a_closed_bound(tmp_path: Path) -> None:
    """Expiring now is expired, like every expiry in ELA."""
    directory = tmp_path / "captures"
    directory.mkdir()
    write(directory, "9c858901-8a57-4791-81fe-4c455b099bc9.png", png(), age=timedelta(seconds=300))
    kept = store(directory)

    assert kept.purge(kept.retained()[0].expires_at) == 1
    assert held(kept.directory) == []


def test_the_purge_leaves_what_is_not_a_capture_alone(tmp_path: Path) -> None:
    directory = tmp_path / "captures"
    directory.mkdir()
    (directory / "somebody-elses-file.txt").write_text("mine", encoding="utf-8")
    kept = store(directory)

    assert kept.purge(datetime(2100, 1, 1, tzinfo=UTC)) == 0
    assert held(directory) == ["somebody-elses-file.txt"]


def test_the_purge_of_a_capture_that_cannot_be_removed_does_not_raise(tmp_path: Path) -> None:
    """A file that went away between the listing and the unlink is the outcome asked for."""
    directory = tmp_path / "captures"
    directory.mkdir()
    kept = store(directory)
    write(directory, "9c858901-8a57-4791-81fe-4c455b099bc9.png", png(), age=timedelta(hours=1))
    directory.chmod(0o500)
    try:
        assert kept.purge(datetime(2100, 1, 1, tzinfo=UTC)) == 0
    finally:
        directory.chmod(0o700)


def test_discarding_something_that_is_not_a_file_does_not_raise(tmp_path: Path) -> None:
    kept = store(tmp_path / "captures")
    (kept.directory / "adir").mkdir()

    kept.discard(kept.directory / "adir")
    kept.discard(kept.directory / "never-was.png")

    assert (kept.directory / "adir").is_dir()


def test_settling_something_that_is_not_there_reports_instead_of_raising(tmp_path: Path) -> None:
    """The ``chmod`` is suppressed and the measurement gives the answer — one opinion, not two."""
    kept = store(tmp_path / "captures")

    problem = kept.settle(kept.directory / "9c858901-8a57-4791-81fe-4c455b099bc9.png")

    assert not isinstance(problem, tuple)
    assert getattr(problem, "code", None) == CAPTURE_MISSING


def test_the_store_reports_what_it_is_holding(tmp_path: Path) -> None:
    directory = tmp_path / "captures"
    directory.mkdir()
    write(directory, "9c858901-8a57-4791-81fe-4c455b099bc9.png", png())
    kept = store(directory)

    assert [one.name for one in kept.retained()] == ["9c858901-8a57-4791-81fe-4c455b099bc9.png"]
    assert kept.inspect("9c858901-8a57-4791-81fe-4c455b099bc9.png") is not None


def test_the_store_is_created_private(tmp_path: Path) -> None:
    kept = store(tmp_path / "deep" / "captures")

    assert stat.S_IMODE(kept.directory.stat().st_mode) == 0o700


# ----------------------------------------------------------------------------------------
# The contract every tool shares
# ----------------------------------------------------------------------------------------


async def test_the_tool_refuses_a_decision_about_another_capability(tmp_path: Path) -> None:
    from ela.tools import CORE_ECHO

    subject, helper, _ = tool(tmp_path / "captures")

    with pytest.raises(NotAllowedError):
        await subject.execute(allowed(CORE_ECHO), {"purpose": PURPOSE})
    assert helper.calls == ()


async def test_the_capture_is_not_idempotent(tmp_path: Path) -> None:
    """Two captures are two photographs of two instants, and two files (ADR 0021 §1)."""
    assert CaptureScreenTool.idempotent is False


async def test_there_is_no_generic_io_error_among_the_codes() -> None:
    """ADR 0029 §12: every filesystem failure this tool can meet already has a code of its own,
    so a generic one would be a code that cannot fire — worse than none (ADR 0026 §7)."""
    assert "io.error" not in CaptureScreenTool.error_codes
