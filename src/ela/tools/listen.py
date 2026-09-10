"""``perception.listen``: ELA opens the microphone, and writes down words rather than audio.

Four things have to be true before a microphone opens, and they are asked in this order:

1. **Is listening switched on?** ``ELA_LISTEN_ENABLED`` is a convenience and **not the defence**
   (M11.2 dec. K): a default-off flag moves the protection onto an environment variable, which is
   the easiest thing to set and forget, and its steady state is "on" — the first time somebody
   really wants to talk they turn it on and it stays on. The defence is this capability, the
   Guardian, and the ceiling on how long the device stays open.
2. **May ELA, right now?** The microphone's TCC status is re-read **at the instant** and never
   taken from the perception core's belief, which is thirty seconds old (ADR 0029 §7: a periodic
   belief never decides an action). And from a denied state ELA does not open the device — which
   here is not a courtesy inherited from the capture. Measured on 2026-09-09: opening a **refused**
   microphone succeeds, delivers buffers of zeros, and a transcriber turns thirty seconds of zeros
   into «Grazie a tutti.» Without this step a denied permission would produce a transcript of
   words nobody said, inside a result shaped like a success.
3. **Is there room?** The store is purged and the ceilings are asked, exactly as the capture does.
4. **Was there a signal?** That one is not asked here: it is asked in the child, where the samples
   are, and it is what stops the audio before anything interprets it.

What comes back is a transcript in the store and never a byte of audio: the raw material is not
kept (dec. E), so this tool has nothing to discard on failure — there is no half-written recording
of a room to clean up, because there was never a named file at all.
"""

from __future__ import annotations

from typing import ClassVar, Final

from ela.domain import (
    JsonMapping,
    PermissionState,
    ProbeFamily,
    RawTranscript,
)
from ela.perception import AUTHORIZATION_STATUS
from ela.permissions import MAX_LISTEN_SECONDS, PERCEPTION_LISTEN
from ela.ports import (
    LISTEN_DENIED_BY_SYSTEM,
    LISTEN_DISABLED,
    LISTEN_ERROR_CODES,
    LISTEN_PERMISSION_UNREADABLE,
    Clock,
    IdGenerator,
    ListeningPort,
    PerceptionProbe,
)
from ela.tools.base import ARGUMENTS_INVALID, Outcome, Tool
from ela.tools.captures import CAPTURE_CODES, CaptureProblem
from ela.tools.screen import SCREEN_STORE_FULL, CaptureStore

__all__ = ["LISTEN_TOOL_NAME", "PERCEPTION_LISTEN", "ListenTool"]

LISTEN_TOOL_NAME: Final = "listen"

DENIED_MESSAGE: Final = (
    "the microphone is not granted to the process ELA runs under; grant it in System Settings > "
    "Privacy & Security > Microphone, then quit and reopen that application"
)


class ListenTool(Tool):
    """Opens the microphone for a stated number of seconds and stores what was said.

    ``probe`` is the same :class:`~ela.ports.PerceptionProbe` the perception core uses, asked
    again here rather than read from the core's belief — see the module docstring.
    """

    error_codes: ClassVar[frozenset[str]] = (
        frozenset(
            {
                ARGUMENTS_INVALID,
                LISTEN_DISABLED,
                LISTEN_DENIED_BY_SYSTEM,
                LISTEN_PERMISSION_UNREADABLE,
                SCREEN_STORE_FULL,
            }
        )
        | LISTEN_ERROR_CODES
        | CAPTURE_CODES
    )
    """Everything this tool can answer with. The port's vocabulary travels through unchanged: a
    caller must be able to tell "the microphone is refused" from "there is nothing here to hear
    with" without knowing which adapter produced the answer (ADR 0020 §7)."""

    output_keys: ClassVar[frozenset[str]] = frozenset(
        {
            "transcript_id",
            "path",
            "bytes",
            "sha256",
            "segments",
            "characters",
            "seconds_recorded",
            "peak",
            "language",
            "confidence_min",
            "confidence_median",
            "expires_at",
        }
    )
    """What the transcript *is*, and not one word of what it says. ``characters`` is how much of a
    recording became words — a fact about the listening — while the words themselves live in a
    file with a five-minute life and never in a persisted ``ExecutionResult`` (§57, ADR 0029 §2).

    ``peak`` is reported on purpose even when it is fine: it is the number that says a signal
    existed, and a reader who wants to know whether ELA heard a room or a dead input can see it.
    """

    idempotent: ClassVar[bool] = False
    """Two recordings are two rooms at two instants. So this runs under the STARTED protocol, and
    a crash between the recording and its record cannot quietly double what ELA holds."""

    def __init__(
        self,
        store: CaptureStore,
        listening: ListeningPort,
        probe: PerceptionProbe,
        clock: Clock,
        ids: IdGenerator,
        *,
        enabled: bool = True,
        name: str = LISTEN_TOOL_NAME,
    ) -> None:
        super().__init__(PERCEPTION_LISTEN, clock, ids, name=name)
        self._store = store
        self._listening = listening
        self._probe = probe
        self._enabled = enabled

    async def _run(self, arguments: JsonMapping) -> Outcome:
        purpose = arguments.get("purpose")
        seconds = arguments.get("seconds")
        if not isinstance(purpose, str) or not purpose:
            return Outcome({}, ARGUMENTS_INVALID, "purpose must be a non-empty string")
        if (
            not isinstance(seconds, int)
            or isinstance(seconds, bool)
            or not 1 <= seconds <= MAX_LISTEN_SECONDS
        ):
            return Outcome(
                {},
                ARGUMENTS_INVALID,
                f"seconds must be an integer between 1 and {MAX_LISTEN_SECONDS}",
            )
        refused = await self._refusal()
        if refused is not None:
            return refused
        return await self._hear(seconds)

    async def _refusal(self) -> Outcome | None:
        """Everything that has to be true before a microphone opens, in order."""
        if not self._enabled:
            return Outcome(
                {},
                LISTEN_DISABLED,
                "listening is switched off; set ELA_LISTEN_ENABLED to turn it back on",
            )
        observed = await self._probe.read(frozenset({ProbeFamily.PERMISSIONS}))
        status = observed.microphone_permission
        granted = (
            PermissionState.NOT_OBSERVABLE
            if status is None
            else AUTHORIZATION_STATUS.get(status, PermissionState.NOT_OBSERVABLE)
        )
        if granted is PermissionState.NOT_OBSERVABLE:
            return Outcome(
                {},
                LISTEN_PERMISSION_UNREADABLE,
                "the microphone permission could not be read; nothing was attempted",
                retryable=True,
            )
        if granted is not PermissionState.GRANTED:
            return Outcome({}, LISTEN_DENIED_BY_SYSTEM, DENIED_MESSAGE)
        gone = self._store.purge(self._clock.now())
        del gone  # the purge is the point; how many went is not a fact this call reports
        full = self._store.room()
        if full is not None:
            return Outcome({}, SCREEN_STORE_FULL, full, retryable=True)
        return None

    async def _hear(self, seconds: int) -> Outcome:
        """Open the device, and turn what came back into an artefact or into a named failure."""
        heard = await self._listening.listen(seconds)
        if heard.error is not None:
            return Outcome({}, heard.error, _message(heard), retryable=heard.retryable)
        transcript_id = str(self._ids.new_uuid())
        written = self._store.write_transcript(transcript_id, heard.segments)
        if isinstance(written, CaptureProblem):
            return Outcome({}, written.code, written.message(f"{transcript_id}.heard.jsonl"))
        probabilities = sorted(
            token.probability for segment in heard.segments for token in segment.tokens
        )
        return Outcome(
            {
                "transcript_id": transcript_id,
                "path": written.name,
                "bytes": written.bytes,
                "sha256": written.sha256,
                "segments": written.segments,
                "characters": written.characters,
                "seconds_recorded": heard.recorded_seconds,
                "peak": heard.peak,
                "language": heard.language,
                "confidence_min": probabilities[0] if probabilities else None,
                "confidence_median": (
                    probabilities[len(probabilities) // 2] if probabilities else None
                ),
                "expires_at": written.expires_at.isoformat(),
            }
        )


def _message(heard: RawTranscript) -> str:
    """What to tell whoever asked, for a failure the adapter has already named.

    The denial gets the sentence that says what to do about it: nothing ELA can do fixes a
    permission, so the only useful answer is where the human has to click (ADR 0028 §2).
    """
    if heard.error == LISTEN_DENIED_BY_SYSTEM:
        return DENIED_MESSAGE
    return f"the listening ended with {heard.error}"
