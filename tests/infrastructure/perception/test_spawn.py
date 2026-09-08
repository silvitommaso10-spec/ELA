"""``spawn``: start a command, wait, and kill it if it overstays.

Plain ``asyncio`` that knows nothing about macOS, so it runs on every runner — which is the whole
reason it was pulled out of the helper: the part that can be exercised anywhere should be, and
what is left unexercisable shrinks to one file.
"""

from __future__ import annotations

import asyncio
import hashlib
import sys
import tempfile
from pathlib import Path

import pytest

from ela.infrastructure.perception import TIMED_OUT, spawn
from ela.infrastructure.perception.darwin import (
    SPEECH_FILE_PREFIX,
    spawn_with_audio,
    sweep_speech_files,
)


async def test_a_command_that_answers_gives_its_code_and_its_output() -> None:
    code, output = await spawn([sys.executable, "-c", "print('{}')"], 10)

    assert (code, output.strip()) == (0, "{}")


async def test_a_command_that_fails_gives_a_non_zero_code() -> None:
    code, _ = await spawn([sys.executable, "-c", "raise SystemExit(3)"], 10)

    assert code == 3


async def test_a_command_that_overstays_is_killed_and_reported_as_timed_out() -> None:
    """The failure mode pyobjc could not have covered: not an exception, an answer that never
    comes (ADR 0028 §2). The wait is the process's own, so nothing here polls a clock."""
    code, output = await spawn([sys.executable, "-c", "import time; time.sleep(30)"], 0.05)

    assert (code, output) == (TIMED_OUT, "")


async def test_output_that_is_not_utf8_does_not_raise() -> None:
    """A child that dies mid-write can leave a broken byte sequence behind; that is the adapter's
    problem to name, not an exception to propagate."""
    code, output = await spawn(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xff\\xfe')"], 10
    )

    assert code == 0
    assert output


async def test_a_cancelled_wait_kills_the_child_instead_of_orphaning_it() -> None:
    """Cancelling the caller must not leave the helper running (M11.1, criterio 9).

    ``asyncio.wait_for`` cancels the coroutine that reads the child's pipes; it does not touch
    the child, so the natural spelling leaves a process that keeps going after the caller gave
    up. For the probe that is a stray reader; for the voice it is **ELA that does not stop
    talking when it has been told to stop**, which is the worse half of the problem decision F
    postponed to the barge-in.

    Written as a marker file the child creates *after* the moment it should already be dead: if
    the kill happened, the file never appears.
    """
    with tempfile.TemporaryDirectory() as directory:
        marker = Path(directory) / "still-alive"
        child = (
            "import pathlib, time\n"
            "time.sleep(0.6)\n"
            f"pathlib.Path({str(marker)!r}).write_text('x')\n"
        )
        task = asyncio.create_task(spawn([sys.executable, "-c", child], 30))
        await asyncio.sleep(0.15)  # long enough for the child to exist, short enough to be early
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.9)  # past the instant the child would have written

        assert not marker.exists(), "the child outlived the cancelled call"


async def test_the_child_receives_the_bytes_through_a_file_with_no_name() -> None:
    """``spawn_with_audio``: the audio exists for the child and for nobody else (ADR 0034 §7).

    The child is asked to read its argument and report two things — what it read, and whether the
    path it was given can be found in the directory the file was made in. The second is the whole
    decision: ``/dev/fd/N`` opens the inode, and the inode has no name.
    """
    with tempfile.TemporaryDirectory() as directory:
        child = (
            "import os, sys\n"
            "path = sys.argv[1]\n"
            "data = open(path, 'rb').read()\n"
            f"listed = os.listdir({directory!r})\n"
            "print(data.decode(), len(listed))\n"
        )
        code, output = await spawn_with_audio(
            [sys.executable, "-c", child], b"audio-bytes", 10, directory=directory
        )

    assert code == 0
    assert output.split() == ["audio-bytes", "0"], "the directory must be empty while it plays"


async def test_nothing_is_left_behind_when_the_child_has_finished() -> None:
    with tempfile.TemporaryDirectory() as directory:
        await spawn_with_audio([sys.executable, "-c", "pass"], b"x" * 4096, 10, directory=directory)

        assert list(Path(directory).iterdir()) == []


async def test_an_audio_larger_than_one_write_arrives_whole() -> None:
    """``os.write`` may write less than it is given, and a short write is a truncated sentence:
    a failure that would look like the provider's and be ours."""
    audio = bytes(range(256)) * 4096  # 1 MiB, past any single-write buffer worth trusting
    with tempfile.TemporaryDirectory() as directory:
        child = (
            "import hashlib, sys\n"
            "data = open(sys.argv[1], 'rb').read()\n"
            "print(len(data), hashlib.sha256(data).hexdigest())\n"
        )
        code, output = await spawn_with_audio(
            [sys.executable, "-c", child], audio, 30, directory=directory
        )

    assert code == 0
    assert output.split() == [str(len(audio)), hashlib.sha256(audio).hexdigest()]


async def test_a_player_that_overstays_is_killed_and_reported_as_timed_out() -> None:
    with tempfile.TemporaryDirectory() as directory:
        code, _ = await spawn_with_audio(
            [sys.executable, "-c", "import time; time.sleep(30)"], b"x", 0.05, directory=directory
        )

        assert code == TIMED_OUT
        assert list(Path(directory).iterdir()) == [], "a killed child still frees the file"


async def test_a_cancelled_playback_kills_the_child_and_frees_the_audio() -> None:
    """The promise of ADR 0033 §4 on the new path: cancelling the call stops the sound.

    Measured against ``afplay`` itself during the reconnaissance (rc −9, silence); here it is the
    same shape with a child any runner has, plus the half only this function can break — the
    descriptor is closed, so the audio is gone even though nobody deleted anything.
    """
    with tempfile.TemporaryDirectory() as directory:
        marker = Path(directory) / "still-playing"
        child = (
            "import pathlib, time\n"
            "time.sleep(0.6)\n"
            f"pathlib.Path({str(marker)!r}).write_text('x')\n"
        )
        task = asyncio.create_task(
            spawn_with_audio([sys.executable, "-c", child], b"x", 30, directory=directory)
        )
        await asyncio.sleep(0.15)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.9)

        assert not marker.exists(), "the player outlived the cancelled call"


def test_the_sweep_finds_what_a_crash_in_one_syscall_would_leave() -> None:
    """The floor is swept at start-up, and only the voice's own prefix is swept (ADR 0034 §7)."""
    with tempfile.TemporaryDirectory() as directory:
        room = Path(directory)
        leftover = room / f"{SPEECH_FILE_PREFIX}abc123.tmp"
        leftover.write_bytes(b"audio nobody will ever hear")
        somebody_elses = room / "ela.db"
        somebody_elses.write_bytes(b"not the voice's")

        assert sweep_speech_files(room) == 1
        assert not leftover.exists()
        assert somebody_elses.exists()


def test_the_sweep_of_a_directory_that_is_not_there_is_not_an_error() -> None:
    """ELA starts before the directory exists, and a start-up that fails on a missing folder is a
    start-up that fails for nothing."""
    with tempfile.TemporaryDirectory() as directory:
        assert sweep_speech_files(Path(directory) / "not-yet") == 0


def test_the_sweep_survives_a_file_it_cannot_delete() -> None:
    """A leftover somebody else holds is not a reason to refuse to start (§33)."""
    with tempfile.TemporaryDirectory() as directory:
        room = Path(directory)
        (room / f"{SPEECH_FILE_PREFIX}gone").write_bytes(b"x")

        def vanish(self: Path) -> None:
            raise OSError("busy")

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(Path, "unlink", vanish)
            assert sweep_speech_files(room) == 0
