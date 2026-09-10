"""Where ELA opens this Mac's microphone, and hands back words instead of audio.

Two children behind one port (M11.2 dec. F): :mod:`ela.infrastructure.machine.microphone` records
into a file that has no name, and a transcriber reads that file. Neither the recording nor its
path ever reaches the Core — what crosses the boundary is a
:class:`~ela.domain.RawTranscript`, and that is decision E made structural rather than promised.

**Nothing here decides what an answer means for a task** (architecture rule 34): the adapter names
failures from the closed vocabulary of :data:`~ela.ports.LISTEN_ERROR_CODES` and carries numbers.
What it *does* decide, because only it can, is whether there was a signal at all — and it decides
that before the transcriber ever runs.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Final

from ela.domain import RawHeardSegment, RawHeardToken, RawTranscript
from ela.infrastructure.machine.darwin import (
    MICROPHONE_MODULE,
    TIMED_OUT,
    SpawnThroughNamelessAudio,
    spawn_through_nameless_audio,
)
from ela.ports import (
    LISTEN_FAILED,
    LISTEN_LANGUAGE_UNSUPPORTED,
    LISTEN_NO_INPUT_DEVICE,
    LISTEN_NO_SIGNAL,
    LISTEN_TIMEOUT,
    LISTEN_TRANSCRIPTION_FAILED,
    LISTEN_TRANSCRIPTION_UNAVAILABLE,
    LISTEN_UNSUPPORTED,
)

__all__ = ["DarwinListening", "UnsupportedListening", "digest_of"]

RECORD_MARGIN_SECONDS: Final = 5.0
"""How much longer than the recording the parent waits before killing the child.

The child has a deadline of its own as well, and the two are not redundant: a subprocess outlives
its parent, so if ELA is killed mid-recording the child's own deadline is the only thing that
closes the microphone. This one covers the ordinary case, that one covers the crash."""

_CHUNK: Final = 1 << 20


def digest_of(path: Path) -> str:
    """The sha256 of ``path``, or ``""`` if it cannot be read.

    Measured: 413 ms for a 574 MB model, 1 ms for the binary. Paid on the first question about a
    given file and then remembered against its size and mtime, so a swapped file is hashed again
    and an unchanged one is not.
    """
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(_CHUNK):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


class UnsupportedListening:
    """Hears nothing, and says which of the two missing things it looked for.

    "ELA on Linux hears nothing" is a thing with a name, a test and a line in ``/diagnostics``,
    rather than a gap somebody discovers (the reason ADR 0028 gave ``UnsupportedProbe`` one).
    """

    __slots__ = ()

    async def available(self) -> bool:
        return False

    async def listen(self, seconds: int) -> RawTranscript:
        del seconds
        return RawTranscript(error=LISTEN_UNSUPPORTED)


class DarwinListening:
    """Records and transcribes on this machine (:class:`~ela.ports.ListeningPort`).

    ``spawn`` arrives as a dependency, for the reason every other adapter here takes one: a
    timeout, a child killed by a signal, a recorder that opened nothing and a transcriber that
    wrote nonsense are all things a test can produce with no microphone and no permission at all.

    The transcriber is named by **absolute path with its digest declared**, never resolved through
    ``PATH`` — what decides what ELA believes was said must not be chosen by an environment
    variable, which is ADR 0029 §3's rule for what photographs the screen, applied to what listens
    to the room.
    """

    __slots__ = (
        "_binary",
        "_digests",
        "_directory",
        "_expected",
        "_language",
        "_model",
        "_spawn",
        "_transcribe_timeout",
    )

    def __init__(
        self,
        *,
        binary: Path,
        model: Path,
        expected: tuple[str, str],
        language: str,
        transcribe_timeout: float,
        directory: Path | None = None,
        spawn: SpawnThroughNamelessAudio = spawn_through_nameless_audio,
    ) -> None:
        self._binary = binary
        self._model = model
        self._expected = expected
        self._language = language
        self._transcribe_timeout = transcribe_timeout
        self._directory = directory
        self._spawn = spawn
        self._digests: dict[tuple[str, int, int], str] = {}

    async def available(self) -> bool:
        """Whether both files are there and are the ones ELA was told to expect."""
        return all(
            self._trusted(path, expected)
            for path, expected in (
                (self._binary, self._expected[0]),
                (self._model, self._expected[1]),
            )
        )

    def _trusted(self, path: Path, expected: str) -> bool:
        try:
            stat = path.stat()
        except OSError:
            return False
        key = (str(path), stat.st_size, int(stat.st_mtime_ns))
        if key not in self._digests:
            self._digests[key] = digest_of(path)
        return self._digests[key] == expected

    def _argv(self, audio: str, prefix: str) -> list[str]:
        """The transcriber's command line. Its flags live here and nowhere else."""
        return [
            str(self._binary),
            "-m",
            str(self._model),
            "-f",
            audio,
            "-l",
            self._language,
            "-np",
            "-oj",
            "-ojf",
            "-of",
            prefix,
        ]

    async def listen(self, seconds: int) -> RawTranscript:
        """Open the microphone for ``seconds``, and answer with what was heard."""
        if not await self.available():
            return RawTranscript(error=LISTEN_TRANSCRIPTION_UNAVAILABLE)
        recorded, report = await self._spawn(
            [sys.executable, "-m", MICROPHONE_MODULE, str(seconds)],
            self._argv,
            _heard_something,
            seconds + RECORD_MARGIN_SECONDS,
            self._transcribe_timeout,
            directory=str(self._directory) if self._directory is not None else None,
        )
        return self._read(recorded, report)

    def _read(self, recorded: tuple[int, str], report: tuple[int, str] | None) -> RawTranscript:
        """Turn what the two children left behind into primitives, deciding nothing about it."""
        code, said = recorded
        if code == TIMED_OUT:
            return RawTranscript(timed_out=True, error=LISTEN_TIMEOUT, retryable=True)
        opening = _parsed(said)
        if code != 0 or opening is None:
            return RawTranscript(exit_code=code, error=LISTEN_FAILED, retryable=True)
        if not opening.get("opened", False):
            return RawTranscript(exit_code=code, error=LISTEN_NO_INPUT_DEVICE)
        peak = int(opening.get("peak", 0))
        heard = float(opening.get("recorded_seconds", 0.0))
        if report is None:
            return RawTranscript(
                exit_code=code, recorded_seconds=heard, peak=peak, error=LISTEN_NO_SIGNAL
            )
        return self._transcribed(report, heard, peak)

    def _transcribed(self, report: tuple[int, str], heard: float, peak: int) -> RawTranscript:
        code, written = report
        if code == TIMED_OUT:
            return RawTranscript(
                timed_out=True,
                recorded_seconds=heard,
                peak=peak,
                error=LISTEN_TIMEOUT,
                retryable=True,
            )
        parsed = _parsed(written)
        if code != 0 or parsed is None:
            return RawTranscript(
                exit_code=code,
                recorded_seconds=heard,
                peak=peak,
                error=LISTEN_TRANSCRIPTION_FAILED,
                retryable=True,
            )
        language = str(parsed.get("result", {}).get("language", "")) or None
        if language is not None and language != self._language:
            return RawTranscript(
                exit_code=code,
                recorded_seconds=heard,
                peak=peak,
                language=language,
                error=LISTEN_LANGUAGE_UNSUPPORTED,
            )
        return RawTranscript(
            exit_code=code,
            recorded_seconds=heard,
            peak=peak,
            language=language,
            segments=_segments(parsed),
        )


def _heard_something(said: str) -> bool:
    """Whether the recording carries any signal at all — the gate before the transcriber.

    ``peak == 0`` is not a threshold: it is the fact that no sample differed from silence. It is
    what a refused microphone produces (measured 2026-09-09: every return code says success and
    every buffer is zeros), and what a muted or dead input produces, and handing either to a
    transcriber produces words nobody said.
    """
    opening = _parsed(said)
    return opening is not None and int(opening.get("peak", 0)) > 0


def _parsed(payload: str) -> dict[str, Any] | None:
    """The JSON a child printed, or ``None`` if it printed something else."""
    try:
        loaded = json.loads(payload)
    except ValueError:
        return None
    return loaded if isinstance(loaded, dict) else None


def _segments(parsed: dict[str, Any]) -> tuple[RawHeardSegment, ...]:
    """The transcript, with the decoder's probability kept per token.

    Per token and not per segment because that is what the engine gives, and it is worth keeping:
    it says *which word* it was unsure of. Nothing is filtered on it — a threshold is a decision
    and belongs to whoever decides (§45).
    """
    segments = parsed.get("transcription", [])
    if not isinstance(segments, list):
        return ()
    return tuple(
        RawHeardSegment(
            text=str(segment.get("text", "")),
            start_ms=max(0, int(segment.get("offsets", {}).get("from", 0))),
            end_ms=max(0, int(segment.get("offsets", {}).get("to", 0))),
            tokens=tuple(
                RawHeardToken(
                    text=str(token["text"]), probability=min(1.0, max(0.0, float(token["p"])))
                )
                for token in segment.get("tokens", [])
                if isinstance(token, dict) and "p" in token and "text" in token
            ),
        )
        for segment in segments
        if isinstance(segment, dict)
    )
