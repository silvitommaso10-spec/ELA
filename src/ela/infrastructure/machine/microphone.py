"""The recorder: opens this Mac's microphone and writes what it hears into a descriptor.

Run as ``python -m ela.infrastructure.machine.microphone <seconds> <fd>``. It writes a WAV into
the descriptor it is given — never into a path, because it is never told one — and prints one JSON
object on stdout saying how it went. Nothing here decides anything (architecture rule 34): it
carries numbers, and what they mean is the adapter's business.

**Why ``AudioQueue`` through ``ctypes``, and not a compiled helper** (M11.2 dec. B). No binary of
Apple's records from the command line — measured: ``/usr/bin`` has ``say``, ``afplay``, ``afinfo``
and ``afconvert`` and nothing else — so ADR 0029 §3's escape, where the child is somebody else's
signed binary and rule 33 becomes true by construction, is not available here. The child comes
back to being ours, and of the three APIs that work, ``AudioQueue`` is the only one that is plain
C and therefore the only one this file can drive while importing nothing but the standard library.

The other road was a compiled Swift helper, and TCC decided against it: the grant is bound to the
**identity of the binary**, so every rebuild invalidates the permission — measured on 2026-09-08,
replacing an executable inside its bundle returned the state to ``notDetermined``. That is a
property of the installed product, not a nuisance of development.

**The risk this file carries, and where it lands.** A callback from C into Python inside a run
loop is the most fragile thing in this repository, and a mistake in ``ctypes`` does not raise —
it takes the process down. That is precisely the risk ADR 0028 §2 bought the isolated subprocess
for: what dies here is a child, and a child that dies is already a case with a name.

And **it carries its own deadline**, which is not redundant with the parent's: a subprocess
outlives its parent — ``launchd`` adopts it — so if ELA is killed mid-recording, this is the only
thing that closes the microphone. The longest an orphaned microphone can live is the ceiling plus
this margin.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
import os
import struct
import sys
import threading
import time
from typing import Any, Final

FORMAT_LINEAR_PCM: Final = 0x6C70636D
"""``'lpcm'`` as a four-character code, which is how CoreAudio spells it."""
FORMAT_FLAGS_SIGNED_PACKED: Final = 0xC
"""``kAudioFormatFlagIsSignedInteger | kAudioFormatFlagIsPacked``."""
SAMPLE_RATE: Final = 16000
"""What the transcriber wants, asked of the driver directly rather than resampled afterwards:
a conversion is a second place for the audio to exist."""
BITS_PER_SAMPLE: Final = 16
CHANNELS: Final = 1
BUFFER_BYTES: Final = 8192
BUFFER_COUNT: Final = 3
HEADER_BYTES: Final = 44
"""A canonical WAV header: written first with zero sizes, rewritten at the end with the real
ones — the file has to be readable by something that seeks."""
GRACE_SECONDS: Final = 0.2
"""A margin on the sleep, not on the recording: ``AudioQueueStop`` waits for the queue to hand
over what it has already captured, so this only covers the last partial buffer. It is small on
purpose — an extra second of microphone is an extra second of a room, and the caller asked for a
number of seconds rather than about that many."""


class _AudioStreamBasicDescription(ctypes.Structure):
    _fields_ = (
        ("sample_rate", ctypes.c_double),
        ("format_id", ctypes.c_uint32),
        ("format_flags", ctypes.c_uint32),
        ("bytes_per_packet", ctypes.c_uint32),
        ("frames_per_packet", ctypes.c_uint32),
        ("bytes_per_frame", ctypes.c_uint32),
        ("channels_per_frame", ctypes.c_uint32),
        ("bits_per_channel", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32),
    )


class _AudioQueueBuffer(ctypes.Structure):
    _fields_ = (
        ("capacity", ctypes.c_uint32),
        ("audio_data", ctypes.c_void_p),
        ("byte_size", ctypes.c_uint32),
        ("user_data", ctypes.c_void_p),
        ("packet_description_capacity", ctypes.c_uint32),
        ("packet_descriptions", ctypes.c_void_p),
        ("packet_description_count", ctypes.c_uint32),
    )


_BufferPointer = ctypes.POINTER(_AudioQueueBuffer)
_InputCallback = ctypes.CFUNCTYPE(
    None,
    ctypes.c_void_p,
    ctypes.c_void_p,
    _BufferPointer,
    ctypes.c_void_p,
    ctypes.c_uint32,
    ctypes.c_void_p,
)


def _header(data_bytes: int) -> bytes:
    """A 44-byte WAV header for ``data_bytes`` of PCM."""
    byte_rate = SAMPLE_RATE * CHANNELS * BITS_PER_SAMPLE // 8
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_bytes,
        b"WAVE",
        b"fmt ",
        16,
        1,
        CHANNELS,
        SAMPLE_RATE,
        byte_rate,
        CHANNELS * BITS_PER_SAMPLE // 8,
        BITS_PER_SAMPLE,
        b"data",
        data_bytes,
    )


def _write_all(fd: int, payload: bytes) -> None:
    """``os.write`` may write less than it was given, and a short write truncates the recording."""
    written = 0
    while written < len(payload):
        written += os.write(fd, payload[written:])


class _Recorder:
    """The state one recording needs, and the only thing the C callback may touch."""

    def __init__(self, fd: int) -> None:
        self.fd = fd
        self.bytes_written = 0
        self.peak = 0
        self.lock = threading.Lock()

    def take(self, buffer: _AudioQueueBuffer) -> None:
        """One buffer of samples: to the descriptor, and its loudest sample remembered.

        The peak is computed **here**, where the samples are, and it is the whole reason this
        number exists: a refused microphone delivers buffers of zeros with every return code
        saying success, and a transcriber turns silence into words nobody said. Whether there was
        a signal has to be decided before anything interprets it.
        """
        size = int(buffer.byte_size)
        if size <= 0:
            return
        raw = ctypes.string_at(buffer.audio_data, size)
        samples = memoryview(raw).cast("h")
        loudest = 0
        for sample in samples:
            magnitude = -sample if sample < 0 else sample
            if magnitude > loudest:
                loudest = magnitude
        with self.lock:
            _write_all(self.fd, raw)
            self.bytes_written += size
            if loudest > self.peak:
                self.peak = loudest


def record(seconds: float, fd: int) -> dict[str, Any]:
    """Open the microphone for ``seconds``, writing into ``fd``. Never raises for the caller."""
    library = ctypes.util.find_library("AudioToolbox")
    if library is None:  # pragma: no cover - macOS always has it; Linux never gets here
        return {"opened": False, "reason": "no_audio_toolbox"}
    toolbox = ctypes.CDLL(library)

    recorder = _Recorder(fd)
    _write_all(fd, _header(0))

    def on_buffer(
        user_data: ctypes.c_void_p,
        queue: ctypes.c_void_p,
        buffer: Any,
        started_at: ctypes.c_void_p,
        packet_count: ctypes.c_uint32,
        packets: ctypes.c_void_p,
    ) -> None:
        del user_data, started_at, packet_count, packets
        recorder.take(buffer.contents)
        toolbox.AudioQueueEnqueueBuffer(queue, buffer, 0, None)

    callback = _InputCallback(on_buffer)
    described = _AudioStreamBasicDescription(
        float(SAMPLE_RATE),
        FORMAT_LINEAR_PCM,
        FORMAT_FLAGS_SIGNED_PACKED,
        CHANNELS * BITS_PER_SAMPLE // 8,
        1,
        CHANNELS * BITS_PER_SAMPLE // 8,
        CHANNELS,
        BITS_PER_SAMPLE,
        0,
    )
    queue = ctypes.c_void_p()
    opened = int(
        toolbox.AudioQueueNewInput(
            ctypes.byref(described), callback, None, None, None, 0, ctypes.byref(queue)
        )
    )
    if opened != 0:
        return {"opened": False, "reason": "new_input", "status": opened}

    started_at = time.monotonic()
    for _ in range(BUFFER_COUNT):
        buffer = ctypes.c_void_p()
        toolbox.AudioQueueAllocateBuffer(queue, BUFFER_BYTES, ctypes.byref(buffer))
        toolbox.AudioQueueEnqueueBuffer(queue, buffer, 0, None)
    started = int(toolbox.AudioQueueStart(queue, None))
    if started != 0:
        toolbox.AudioQueueDispose(queue, True)
        return {"opened": False, "reason": "start", "status": started}

    time.sleep(seconds + GRACE_SECONDS)
    toolbox.AudioQueueStop(queue, True)
    toolbox.AudioQueueDispose(queue, True)
    elapsed = time.monotonic() - started_at

    with recorder.lock:
        written, peak = recorder.bytes_written, recorder.peak
    os.lseek(fd, 0, os.SEEK_SET)
    _write_all(fd, _header(written))
    return {
        "opened": True,
        "peak": peak,
        "bytes": written,
        "recorded_seconds": round(min(elapsed, written / (SAMPLE_RATE * 2)), 3),
    }


def main(argv: list[str]) -> int:
    """``argv[1]`` is how many seconds, ``argv[2]`` the descriptor. The answer goes to stdout."""
    seconds, fd = float(argv[1]), int(argv[2])
    json.dump(record(seconds, fd), sys.stdout)
    return 0


if __name__ == "__main__":  # pragma: no cover - the entry point of the child process
    sys.exit(main(sys.argv))
