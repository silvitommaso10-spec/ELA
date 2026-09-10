"""The recorder as a real process, on the machine that has one (M11.2, ADR 0036 §6).

Two properties no fake can carry, and both are about a microphone that nobody is holding any
more. They run on macOS only — declared with a ``skipif`` so the skip appears in the summary
rather than as an ``if`` inside the test that quietly asserts nothing (ADR 0031 §6).

They do **not** need a granted microphone: a refused one opens just the same and delivers zeros,
which is precisely the measurement this milestone is built on. What is under test is the process,
not the sound.
"""

from __future__ import annotations

import asyncio
import ctypes
import json
import os
import platform
import struct
import subprocess
import sys
import time

import pytest

from ela.infrastructure.machine import microphone
from ela.infrastructure.machine.darwin import MICROPHONE_MODULE, spawn_through_nameless_audio

darwin_only = pytest.mark.skipif(
    platform.system() != "Darwin", reason="the recorder is macOS's AudioQueue"
)


def never_transcribe(_: str) -> bool:
    return False


@darwin_only
async def test_the_recorder_answers_with_numbers_and_writes_no_named_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The contract, not the sound: it opened or it did not, and it says which."""
    recorded, report = await spawn_through_nameless_audio(
        [sys.executable, "-m", MICROPHONE_MODULE, "1"],
        lambda audio, prefix: ["/usr/bin/true"],
        never_transcribe,
        30.0,
        30.0,
        directory=str(tmp_path),
    )

    assert report is None, "the gate said no, so nothing interpreted the audio"
    code, said = recorded
    assert code == 0
    answer = json.loads(said)
    assert set(answer) >= {"opened", "peak", "bytes", "recorded_seconds"}
    assert isinstance(answer["peak"], int)
    assert list(tmp_path.iterdir()) == [], "the audio never wore a name"


@darwin_only
async def test_a_cancelled_call_closes_the_microphone(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """ADR 0033 §4 with the sign reversed, and graver.

    An orphaned ``say`` is ELA still talking; an orphaned recorder is **ELA still listening after
    being told to stop**, and nobody hears that happen.
    """
    started = asyncio.get_running_loop().create_future()

    async def listen() -> None:
        started.set_result(True)
        await spawn_through_nameless_audio(
            [sys.executable, "-m", MICROPHONE_MODULE, "20"],
            lambda audio, prefix: ["/usr/bin/true"],
            never_transcribe,
            60.0,
            60.0,
            directory=str(tmp_path),
        )

    task = asyncio.create_task(listen())
    await started
    await asyncio.sleep(1.5)
    before = _recorders()
    assert before, "the recorder has to be running for the cancellation to mean anything"

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.5)

    assert _recorders() == (), "a cancelled call left a microphone open"
    assert list(tmp_path.iterdir()) == []


@darwin_only
def test_the_child_carries_its_own_deadline_and_outlives_nobody(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A subprocess outlives its parent — ``launchd`` adopts it — so the child closes itself.

    This is why the longest an orphaned microphone can live is the ceiling plus the child's own
    margin, which is a number rather than "until somebody notices".
    """
    target = tmp_path / "heard.wav"
    handle = os.open(target, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        child = subprocess.Popen(  # noqa: S603
            [sys.executable, "-m", MICROPHONE_MODULE, "1", str(handle)],
            pass_fds=(handle,),
            stdout=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 20
        while child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.2)
        assert child.poll() is not None, "the child did not close on its own deadline"
    finally:
        os.close(handle)


def _recorders() -> tuple[int, ...]:
    """The recorder processes alive right now, by the module they were started with."""
    listing = subprocess.run(  # noqa: S603
        ["/bin/ps", "-Ao", "pid,command"], capture_output=True, text=True, check=False
    )
    return tuple(
        int(line.split()[0])
        for line in listing.stdout.splitlines()
        if MICROPHONE_MODULE in line and "ps -Ao" not in line
    )


def test_the_loudest_possible_sample_does_not_report_a_peak_that_cannot_exist() -> None:
    """A bug found by speaking into it: ``abs(-32768)`` is 32768, and no sample can be that.

    Signed 16-bit runs from −32768 to 32767, so the negative end has one more step than the
    positive one and taking its magnitude overflows the range by exactly one. It never mattered to
    the gate — anything above zero is a signal — but it is a number ELA *reports*, in a result
    somebody reads, and a peak of 32768 says the audio went past a ceiling that does not exist.

    Found on the real machine at criterion 3: a voice at 85% input gain clipped, and the result
    said 32768.
    """
    samples = struct.pack("<3h", 0, -32768, 100)
    raw = ctypes.create_string_buffer(samples, len(samples))
    buffer = microphone._AudioQueueBuffer(  # noqa: SLF001 — the callback's own state is the unit
        capacity=len(samples),
        audio_data=ctypes.cast(raw, ctypes.c_void_p).value,
        byte_size=len(samples),
    )
    recorder = microphone._Recorder(os.open(os.devnull, os.O_WRONLY))  # noqa: SLF001
    try:
        recorder.take(buffer)
    finally:
        os.close(recorder.fd)

    assert recorder.peak == 32767


def test_a_buffer_with_nothing_in_it_is_not_a_signal() -> None:
    """The other end of the same number: an empty buffer leaves the peak alone."""
    recorder = microphone._Recorder(os.open(os.devnull, os.O_WRONLY))  # noqa: SLF001
    try:
        recorder.take(microphone._AudioQueueBuffer(capacity=0, byte_size=0))  # noqa: SLF001
    finally:
        os.close(recorder.fd)

    assert recorder.peak == 0
    assert recorder.bytes_written == 0
