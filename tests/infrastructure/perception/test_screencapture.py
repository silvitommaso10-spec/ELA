"""The screen-capture adapter, tested without a Mac and without a permission (ADR 0029 §3, §11).

The helper is Apple's binary, so what there is to test here is not what it photographs — that is
the smoke test's business, and only on a granted machine — but what this adapter does with every
way the helper can end: cleanly, badly, killed for overstaying, or not there at all. All four are
things a fake spawn produces on any runner.

The port's hardest promise is **it does not fail, it reports**, and the second hardest is that it
says nothing about what the ending *means*: "exit code 1" is a revoked permission, a full disk and
a display that went away, and choosing between them is not an adapter's job (architecture rule 34).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path

import pytest

from ela.domain import RawCapture
from ela.infrastructure.perception import (
    SCREENCAPTURE,
    TIMED_OUT,
    ScreenCaptureCommand,
    UnsupportedScreenCapture,
)

DESTINATION = "/tmp/ela-test/3f2504e0-4f89-41d3-9a0c-0305e82c3301.png"  # noqa: S108


def answering(code: int) -> tuple[ScreenCaptureCommand, list[Sequence[str]]]:
    """A capture whose helper ends exactly like this, and the argv it was asked to run."""
    seen: list[Sequence[str]] = []

    async def spawn(argv: Sequence[str], timeout: float) -> tuple[int, str]:
        del timeout
        seen.append(argv)
        return code, ""

    return ScreenCaptureCommand(timeout=timedelta(seconds=1), runner=spawn), seen


async def test_the_helper_is_asked_for_a_silent_png_of_one_display() -> None:
    """``-x`` matters beyond tidiness: ELA photographing the screen must not sound like the user
    did it. ``-t png`` fixes the format the caller reads back; ``-D`` is 1-based."""
    capture, seen = answering(0)

    await capture.capture(DESTINATION, 3)

    assert seen == [[SCREENCAPTURE, "-x", "-t", "png", "-D", "3", DESTINATION]]


async def test_the_binary_is_absolute_and_never_found_on_the_path() -> None:
    """What photographs the user's screen is not decided by an environment variable."""
    assert SCREENCAPTURE.startswith("/")


async def test_a_clean_ending_is_reported_as_one() -> None:
    capture, _ = answering(0)

    assert await capture.capture(DESTINATION, 1) == RawCapture(exit_code=0)


async def test_a_bad_ending_is_reported_without_being_interpreted() -> None:
    """Rule 34: the adapter carries the number and never says what it means."""
    capture, _ = answering(1)

    assert await capture.capture(DESTINATION, 1) == RawCapture(exit_code=1)


async def test_a_child_killed_by_a_signal_is_reported_as_a_bad_ending() -> None:
    capture, _ = answering(-6)

    assert await capture.capture(DESTINATION, 1) == RawCapture(exit_code=-6)


async def test_a_helper_that_overstays_is_reported_as_timed_out() -> None:
    """ "It did not answer" and "it answered badly" are different facts, and only the first says
    nothing at all about the machine."""
    capture, _ = answering(TIMED_OUT)

    report = await capture.capture(DESTINATION, 1)

    assert report == RawCapture(exit_code=TIMED_OUT, timed_out=True)


async def test_a_helper_that_vanished_between_the_check_and_the_call_reports_nothing() -> None:
    """The race the port promises not to raise on: it does not fail, it reports."""

    async def missing(argv: Sequence[str], timeout: float) -> tuple[int, str]:
        del argv, timeout
        raise FileNotFoundError(SCREENCAPTURE)

    capture = ScreenCaptureCommand(timeout=timedelta(seconds=1), runner=missing)

    assert await capture.capture(DESTINATION, 1) == RawCapture()


async def test_the_adapter_writes_nothing_itself(tmp_path: Path) -> None:
    """Whether anything was written is the caller's to read from the artefact it owns (§20)."""
    capture, _ = answering(0)

    await capture.capture(str(tmp_path / "shot.png"), 1)

    assert list(tmp_path.iterdir()) == []


# ----------------------------------------------------------------------------------------
# available(): a named answer, so it can be given before the permission is read
# ----------------------------------------------------------------------------------------


async def test_a_helper_that_is_not_there_is_not_available(tmp_path: Path) -> None:
    capture = ScreenCaptureCommand(
        timeout=timedelta(seconds=1), binary=str(tmp_path / "screencapture")
    )

    assert not await capture.available()


async def test_a_helper_that_is_not_executable_is_not_available(tmp_path: Path) -> None:
    binary = tmp_path / "screencapture"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o600)

    capture = ScreenCaptureCommand(timeout=timedelta(seconds=1), binary=str(binary))

    assert not await capture.available()


async def test_a_directory_is_not_a_helper(tmp_path: Path) -> None:
    """``os.access`` says yes to a directory it can enter: the second check is what refuses it."""
    capture = ScreenCaptureCommand(timeout=timedelta(seconds=1), binary=str(tmp_path))

    assert not await capture.available()


async def test_an_executable_file_is_available(tmp_path: Path) -> None:
    binary = tmp_path / "screencapture"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o700)

    capture = ScreenCaptureCommand(timeout=timedelta(seconds=1), binary=str(binary))

    assert await capture.available()


# ----------------------------------------------------------------------------------------
# The operating systems that have none of this
# ----------------------------------------------------------------------------------------


async def test_an_unsupported_system_is_not_available() -> None:
    assert not await UnsupportedScreenCapture().available()


async def test_an_unsupported_system_captures_nothing_and_writes_nothing(
    tmp_path: Path,
) -> None:
    """ADR 0028's reason, applied again: "ELA on Linux photographs nothing" is a thing with a
    name, a test and an error code the user can read, not a gap somebody discovers."""
    target = tmp_path / "shot.png"

    assert await UnsupportedScreenCapture().capture(str(target), 1) == RawCapture()
    assert not target.exists()


async def test_the_unsupported_capture_is_frozen() -> None:
    subject = UnsupportedScreenCapture()
    with pytest.raises(AttributeError):
        subject.extra = 1  # type: ignore[attr-defined]
