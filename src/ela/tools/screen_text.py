"""Reads the text out of a capture ELA already has, and never sends it anywhere (M10.3, ADR 0030).

This is the third ring of §10 — *analysis only when necessary* — in the only form that costs
neither a new permission nor a byte leaving the machine. macOS's Vision framework recognises text
with **no TCC grant at all** (measured from a process that was its own responsible process) and
answers identically with the network denied, so what this tool produces is content the user's
machine derived from content the user's machine already held.

**It does not photograph.** It takes a ``capture_id`` the capture capability produced, which is
what makes three things free rather than built:

* the Screen Recording permission was spent by the capture, so nothing here preflights one and
  nothing here can cause a permanent denial to be recorded (ADR 0029 §7);
* the TTL is applied by the purge that runs before this writes, so an expired capture is simply
  ``capture.missing`` and there is no "expired" branch to keep in step with the purge;
* the integrity of the image is read with :func:`~ela.tools.captures.inspect`, the same call the
  capture's verifier makes — and it is **necessary**, not tidy: a truncated PNG makes Vision
  answer *successfully* with zero lines, so "no text" is only true if the file was whole.

**Why the reading is refused when a language is unknown.** An unsupported language does not fail
either: Vision answers ``ok=True`` with zero observations. A typo in ``ELA_OCR_LANGUAGES`` would
therefore report "this screen contains no text", forever and silently. The two facts are split
before they are handed on — the criterion of ADR 0030 §8, the twin of ADR 0026 §7 — so a caller
that receives zero lines has received an observation and not a misconfiguration.

Architecture rule 35 covers this module: nothing here names a router, a provider registry or an
HTTP client, and the rule was extended to cover it **in the commit before this file existed**. The
order is the point — the text is the easier thing to send away, so the defence exists before the
thing it defends.
"""

from __future__ import annotations

from typing import ClassVar, Final

from ela.domain import CapabilityId, JsonMapping
from ela.ports import Clock, IdGenerator, TextRecognitionPort
from ela.tools.base import ARGUMENTS_INVALID, Outcome, Tool
from ela.tools.captures import (
    CAPTURE_CODES,
    CaptureProblem,
    TextArtefact,
    is_capture_name,
    name_for,
    text_name_for,
)
from ela.tools.screen import CaptureStore

__all__ = [
    "PERCEPTION_READ_SCREEN_TEXT",
    "TEXT_LANGUAGE_UNSUPPORTED",
    "TEXT_RECOGNITION_FAILED",
    "TEXT_TIMEOUT",
    "TEXT_TOOL_NAME",
    "TEXT_UNSUPPORTED",
    "ReadScreenTextTool",
]

PERCEPTION_READ_SCREEN_TEXT: Final = CapabilityId("perception.read_screen_text")
TEXT_TOOL_NAME: Final = "perception-screen-text"

TEXT_UNSUPPORTED: Final = "text.unsupported"
"""This operating system has no text recognition ELA can use. Not an error condition so much as
an answer with a name — the same shape ADR 0028 gave ``UnsupportedProbe``."""
TEXT_LANGUAGE_UNSUPPORTED: Final = "text.language_unsupported"
"""A configured language is not one this macOS can recognise, and **nothing was read**.

The code exists because without it the answer would have been an empty recognition, which is a
different fact wearing the same clothes (ADR 0030 §8)."""
TEXT_TIMEOUT: Final = "text.timeout"
TEXT_RECOGNITION_FAILED: Final = "text.recognition_failed"


class ReadScreenTextTool(Tool):
    """Recognises the text in one capture, into an artefact beside it (§29 MEDIUM; ADR 0030).

    The recognition lands in the capture store under the **same stem** as the image, which is the
    whole of the shared lifetime: there is no index saying which text belongs to which capture,
    because the name is the link, and no text can outlive its image because the expiry is read
    from the image's ``mtime`` (:func:`~ela.tools.captures._group_expiry`).
    """

    error_codes: ClassVar[frozenset[str]] = (
        frozenset(
            {
                ARGUMENTS_INVALID,
                TEXT_UNSUPPORTED,
                TEXT_LANGUAGE_UNSUPPORTED,
                TEXT_TIMEOUT,
                TEXT_RECOGNITION_FAILED,
            }
        )
        | CAPTURE_CODES
    )
    """No ``text.store_full``, and the absence is argued rather than forgotten: the ceilings ask
    how many screens ELA is holding, and reading one does not make it two. A recognition is
    admitted with the capture it belongs to, so a code refusing it here could not fire (ADR 0026
    §7)."""

    output_keys: ClassVar[frozenset[str]] = frozenset(
        {
            "capture_id",
            "path",
            "bytes",
            "sha256",
            "lines",
            "characters",
            "confidence_min",
            "confidence_median",
            "languages",
            "region",
            "expires_at",
        }
    )
    """What the artefact *is*, and not one character of what it says. ``characters`` is how much
    of the screen became text, which is a fact about the reading; the text itself lives in a file
    with a five-minute life and never in a persisted ``ExecutionResult`` (§57, ADR 0029 §2)."""

    idempotent: ClassVar[bool] = False
    """Reading the same capture twice writes the file twice. It is not free of effect, so it runs
    under the STARTED protocol like the capture — and there is no cache, because at 232 ms a
    second index of what ELA has already read would cost more than it saves."""

    def __init__(
        self,
        store: CaptureStore,
        recognition: TextRecognitionPort,
        clock: Clock,
        ids: IdGenerator,
        *,
        languages: tuple[str, ...],
        name: str = TEXT_TOOL_NAME,
    ) -> None:
        super().__init__(PERCEPTION_READ_SCREEN_TEXT, clock, ids, name=name)
        self._store = store
        self._recognition = recognition
        self._languages = languages

    async def _run(self, arguments: JsonMapping) -> Outcome:
        capture_id = arguments.get("capture_id")
        purpose = arguments.get("purpose")
        if not isinstance(purpose, str) or not purpose:
            return Outcome({}, ARGUMENTS_INVALID, "purpose must be a non-empty string")
        if not isinstance(capture_id, str) or not is_capture_name(name_for(capture_id)):
            return Outcome({}, ARGUMENTS_INVALID, "capture_id must be an id this store issued")
        region = _region(arguments.get("region"))
        if isinstance(region, str):
            return Outcome({}, ARGUMENTS_INVALID, region)
        if not await self._recognition.available():
            return Outcome(
                {}, TEXT_UNSUPPORTED, "this operating system has no text recognition ELA can use"
            )
        return await self._read(capture_id, region)

    async def _read(self, capture_id: str, region: tuple[float, ...] | None) -> Outcome:
        """Purge, check the image is whole, recognise, write beside it."""
        self._store.purge(self._clock.now())
        name = name_for(capture_id)
        found = self._store.inspect(name)
        if isinstance(found, CaptureProblem):
            # Reached for an expired capture too, and that is the design: the purge above is what
            # applies the TTL, so "it expired" arrives as "it is not there" with no second branch.
            return Outcome({}, found.code, found.message(name))
        report = await self._recognition.recognise(
            str(self._store.path_of(capture_id)),
            languages=self._languages,
            region=_flip(region),
        )
        if report.unsupported_languages:
            return Outcome(
                {},
                TEXT_LANGUAGE_UNSUPPORTED,
                "this macOS cannot recognise "
                f"{', '.join(report.unsupported_languages)}; nothing was read",
            )
        if report.killed:
            return Outcome(
                {}, TEXT_TIMEOUT, "the recognition helper did not answer in time", retryable=True
            )
        if report.exit_code != 0:
            return Outcome(
                {},
                TEXT_RECOGNITION_FAILED,
                f"the recognition helper exited with {report.exit_code}",
                retryable=True,
            )
        written = self._store.write_text(capture_id, report.lines)
        if isinstance(written, CaptureProblem):
            return Outcome({}, written.code, written.message(text_name_for(capture_id)))
        confidences = sorted(line.confidence for line in report.lines)
        return self._reported(capture_id, written, confidences, region)

    def _reported(
        self,
        capture_id: str,
        written: TextArtefact,
        confidences: list[float],
        region: tuple[float, ...] | None,
    ) -> Outcome:
        """The metadata, and never the text.

        The confidences are summarised here and kept **per line** in the artefact: a summary is
        what a result should carry, and dropping the per-line value would have meant choosing a
        threshold, which belongs to whoever decides (§45).
        """
        return Outcome(
            {
                "capture_id": capture_id,
                "path": written.name,
                "bytes": written.bytes,
                "sha256": written.sha256,
                "lines": written.lines,
                "characters": written.characters,
                "confidence_min": confidences[0] if confidences else None,
                "confidence_median": (confidences[len(confidences) // 2] if confidences else None),
                "languages": list(self._languages),
                "region": list(region) if region is not None else None,
                "expires_at": written.expires_at.isoformat(),
            }
        )


def _region(value: object) -> tuple[float, ...] | None | str:
    """The region as the caller wrote it — top-left — or why it is not a region.

    Top-left because a capability's schema is ELA's vocabulary and not a framework's: somebody
    asking for "the top half of the screen" is thinking in screen coordinates. The flip to
    Vision's bottom-left origin is :func:`_flip`, and both live here, inside the coverage gate,
    because a flipped rectangle does not raise — it returns the text of the wrong half.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        return "region must be an object with x, y, width and height"
    if set(value) != {"x", "y", "width", "height"}:
        return "region must have exactly x, y, width and height"
    numbers = []
    for key in ("x", "y", "width", "height"):
        number = value[key]
        if isinstance(number, bool) or not isinstance(number, int | float):
            return f"region.{key} must be a number"
        if not 0.0 <= float(number) <= 1.0:
            return f"region.{key} must be between 0 and 1"
        numbers.append(float(number))
    x, y, width, height = numbers
    if width == 0 or height == 0:
        return "region must have a width and a height above zero"
    if x + width > 1.0 or y + height > 1.0:
        return "region must fit inside the image"
    return (x, y, width, height)


def _flip(region: tuple[float, ...] | None) -> tuple[float, ...] | None:
    """A top-left rectangle as the bottom-left one Vision expects.

    One subtraction, and the only reason it is a named function with a test is that getting it
    wrong is silent: the recognition succeeds and reads the mirror image of the region asked for.
    """
    if region is None:
        return None
    x, y, width, height = region
    return (x, 1.0 - y - height, width, height)
