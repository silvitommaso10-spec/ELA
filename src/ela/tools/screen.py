"""``perception.capture_screen`` (spec §10, §20, §29 MEDIUM; M10.2, ADR 0029): ELA photographs
one display, and the photograph stays here.

The first capability that reads **content**. ADR 0028 §9 registered the constraint rather than
shipping it early — "la prima lettura di contenuto nasce con la propria capability MEDIUM, nella
milestone che la introduce e non prima" — and this is that milestone.

Five things happen, in this order, and the order is the design:

1. **The arguments.** ``purpose`` is a non-empty string and ``display`` is a positive integer.
   The Guardian validated the schema already (ADR 0011 §3); a tool checks again because it never
   trusts its caller (§28).
2. **Can this machine capture at all?** :meth:`~ela.ports.ScreenCapturePort.available` — a named
   answer, so "ELA on Linux photographs nothing" is a fact with a test rather than a gap.
3. **May it, right now?** The Screen Recording permission is re-read **at the instant of the
   capture**, not taken from the belief the perception core refreshes every thirty seconds:

       *A periodic belief never decides an action.* A cadenced belief exists to **tell** —
       ``/perception``, ``/diagnostics``, a line of the CLI. The moment something must *happen*,
       the fact is read again (ADR 0029 §7).

   And when the answer is no, **the helper is not run**. That is not an optimisation: attempting
   a capture from a denied state is how a *permanent* denial gets recorded by the operating
   system. ELA says what is missing and what to do about it, which is the only correct thing it
   can do — the permission is granted by a human in System Settings or it does not arrive.
4. **Is there room?** Every capture is also a purge (ADR 0029 §1): retention that depended on the
   perception loop would not be retention, because that loop is off by default. Then the ceilings,
   which **refuse and do not evict** (§15).
5. **The capture**, into a destination this process created and owns. What comes back is an exit
   status, never a pixel: the image goes to the file and nowhere else — not through a pipe, not
   through this process's memory (ADR 0029 §4). Anything short of success removes the file, in a
   ``finally``: the failure mode M10.1 did not have is a half-written photograph of somebody's
   screen that nobody knows about.

The output carries what the artefact *is* — a name, a size, a digest, an expiry — and never a
byte of it. That is not discipline: :data:`~ela.domain.JsonValue` does not admit ``bytes``, so a
tool that tried would not type-check and would not validate (ADR 0029 §2). And the image does not
leave this machine, which architecture rule 35 makes a rule rather than a promise: OCR and
anything that sends it anywhere is M10.3, with a privacy decision of its own.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import ClassVar, Final

from ela.domain import CapabilityId, JsonMapping, ProbeFamily, RawTextLine
from ela.ports import Clock, IdGenerator, PerceptionProbe, ScreenCapturePort
from ela.tools.base import ARGUMENTS_INVALID, Outcome, Tool
from ela.tools.captures import (
    ALREADY_EXPIRED,
    CAPTURE_CODES,
    CAPTURE_UNREADABLE,
    Capture,
    CaptureProblem,
    Retained,
    TextArtefact,
    inspect,
    measure,
    measure_text,
    name_for,
    retained,
    room,
    text_name_for,
)
from ela.tools.notes import DIRECTORY_MODE, FILE_MODE
from ela.tools.settings import CaptureSettings

__all__ = [
    "DEFAULT_DISPLAY",
    "SCREEN_CAPTURE_FAILED",
    "SCREEN_NOT_OBSERVABLE",
    "SCREEN_PERMISSION_DENIED",
    "SCREEN_STORE_FULL",
    "SCREEN_TIMEOUT",
    "SCREEN_TOOL_NAME",
    "SCREEN_UNSUPPORTED",
    "PERCEPTION_CAPTURE_SCREEN",
    "CaptureScreenTool",
    "CaptureStore",
]

PERCEPTION_CAPTURE_SCREEN: Final = CapabilityId("perception.capture_screen")
SCREEN_TOOL_NAME: Final = "perception-screen"

SCREEN_UNSUPPORTED: Final = "screen.unsupported"
"""This operating system has no capture helper ELA knows about. Not retryable: nothing about a
later attempt is different."""
SCREEN_PERMISSION_DENIED: Final = "screen.permission_denied"
"""Screen Recording is not granted. **Not retryable**, and the word is exact: it can succeed
later, but only after a human grants it in System Settings — a process that is not an application
cannot obtain this permission by asking, so retrying on its own changes nothing (ADR 0028 §2)."""
SCREEN_NOT_OBSERVABLE: Final = "screen.not_observable"
"""The permission could not be read at all — the probe timed out or died. A doubt, and a doubt is
not a yes (§33): nothing is attempted. Retryable, because the next read may answer."""
SCREEN_TIMEOUT: Final = "screen.timeout"
SCREEN_CAPTURE_FAILED: Final = "screen.capture_failed"
"""The helper ran and ended badly. The exit status is in the message; what it *means* is not
ELA's to guess — a permission revoked between the preflight and the call, a disk that is full and
a display that went away all land here, and none of them is a claim about the machine."""
SCREEN_STORE_FULL: Final = "screen.store_full"
"""Both ceilings hold captures that have not expired. Retryable: they expire."""

DEFAULT_DISPLAY: Final = 1
"""Which display when the caller does not say: the main one. ``screencapture -D`` is 1-based."""

# The modes are imported from :mod:`ela.tools.notes` rather than restated: literally the same two
# constants as the workspace and the database directory, so "ELA's private files are 0o600" is one
# fact in one place instead of three that agree today. The directory is the barrier that matters —
# the helper creates the file itself, so between its write and this ``chmod`` the file may briefly
# carry the process umask, a declared limit (ADR 0029 §4) that a ``0o700`` directory no other user
# can traverse makes harmless.


class CaptureStore:
    """The directory of screen captures: the writing half of :mod:`ela.tools.captures`.

    Every read — what is held, what a name leads to, whether a file is a capture — is delegated
    to that module, which is read-only by construction and which the verifier uses directly
    (architecture rule 18). What lives here is what writes: creating the directory, tightening a
    file's mode, removing what expired, and removing what a failed capture left.

    Built once by the composition root and shared by the tool, the start-up purge and
    ``/diagnostics`` — the three places that must agree on what "a capture ELA is holding" means.
    """

    __slots__ = ("_settings", "_directory")

    def __init__(self, settings: CaptureSettings) -> None:
        directory = Path(settings.capture_dir).expanduser().absolute()
        directory.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
        self._directory = directory.resolve()
        self._settings = settings

    @property
    def directory(self) -> Path:
        """The resolved directory. Absolute, and never inside the workspace (ADR 0029 §1)."""
        return self._directory

    @property
    def settings(self) -> CaptureSettings:
        return self._settings

    def retained(self) -> tuple[Retained, ...]:
        """Every capture being held, soonest expiry first."""
        return retained(self._directory, self._settings.capture_ttl)

    def room(self) -> str | None:
        """``None`` if another capture fits under both ceilings, else the reason it does not."""
        return room(
            self._directory,
            self._settings.capture_ttl,
            max_count=self._settings.capture_max_count,
            max_bytes=self._settings.capture_max_bytes,
        )

    def inspect(self, name: str) -> Capture | CaptureProblem:
        """What is at ``name`` right now, re-derived from the disk. Reads only."""
        return inspect(self._directory, name, self._settings.capture_ttl)

    def purge(self, now: datetime) -> int:
        """Delete every capture whose expiry has passed; answer with how many went.

        Closed bound, like every expiry in ELA: expiring now is expired. Run at start-up and
        before every capture, and never on a cadence — the perception loop is off by default
        (ADR 0028 §7), and a retention that depends on a loop nobody started is not one.

        A file that vanished between the listing and the unlink is not an error: it is the
        outcome that was asked for.
        """
        gone = 0
        for one in self.retained():
            if one.expires_at <= now:
                try:
                    (self._directory / one.name).unlink()
                except OSError:  # already gone, or not ours to remove: either way, not held
                    continue
                gone += 1
        return gone

    def path_of(self, capture_id: str) -> Path:
        """Where the capture with this id lives. Creates nothing, reads nothing.

        Two callers with two intents, and two names for the same answer: the capture tool calls
        :meth:`reserve` for a path it is about to write, the reading tool asks where an existing
        one *is*. One computation, because a second way to build the path is a second thing that
        could disagree about it — but a method that says "will be written" has no business
        answering "where is it", and a reader should not have to work that out.
        """
        return self._directory / name_for(capture_id)

    def reserve(self, capture_id: str) -> Path:
        """Where a capture with this id will be written. Creates nothing."""
        return self.path_of(capture_id)

    def settle(self, path: Path) -> Capture | CaptureProblem:
        """Tighten the mode of what the helper left, then measure it.

        The ``chmod`` comes first so the window in which the file carries the process umask is as
        short as this code can make it; it is applied through :func:`os.chmod` on a path the
        measurement then re-``lstat``s, so nothing is claimed about a file that is not there.
        """
        # Suppressed rather than branched on: whether the file is there, and whether it is ELA's,
        # is the measurement's answer and not this line's, so a second opinion here would be a
        # branch nothing reads.
        with suppress(OSError):
            os.chmod(path, FILE_MODE)  # noqa: PTH101 - a mode change, not a path construction
        return measure(path, self._settings.capture_ttl)

    def write_text(
        self, capture_id: str, lines: Sequence[RawTextLine]
    ) -> TextArtefact | CaptureProblem:
        """Write the recognition of ``capture_id`` beside its image, then measure it back.

        The parent writes, which is the direction ADR 0029 §4 could not take for the pixels and
        M10.3 dec. 7 argued for here. It buys one thing that milestone had to declare as a limit:
        the file is created by this process at :data:`FILE_MODE`, so it never briefly carries the
        process umask the way a file created by a helper does.

        Written with ``O_EXCL`` on a fresh temporary name and then renamed into place, so a reader
        never sees half a recognition — and measured back from the disk rather than reported from
        memory, because what the tool declares must be what the file says (§20).
        """
        target = self._directory / text_name_for(capture_id)
        payload = b"".join(
            json.dumps({"text": line.text, "confidence": line.confidence}).encode("utf-8") + b"\n"
            for line in lines
        )
        try:
            self._write(target, payload)
        except OSError as error:
            return CaptureProblem(
                CAPTURE_UNREADABLE, f"could not be written: {type(error).__name__}"
            )
        return measure_text(target, self._group_expiry(capture_id))

    def _write(self, target: Path, payload: bytes) -> None:
        """Create, fill, and move into place — never leaving a partial file at the real name."""
        scratch = target.with_name(f"{target.name}.{os.getpid()}.part")
        descriptor = os.open(scratch, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
            os.replace(scratch, target)
        finally:
            with suppress(OSError):
                scratch.unlink(missing_ok=True)

    def _group_expiry(self, capture_id: str) -> datetime:
        """When everything belonging to this capture stops being held. The image's clock."""
        held = {one.name: one.expires_at for one in self.retained()}
        return held.get(name_for(capture_id), ALREADY_EXPIRED)

    def discard(self, path: Path) -> None:
        """Remove what a failed capture left, whatever it was. Never raises.

        The ``finally`` of every capture that did not succeed. The failure mode M10.1 did not
        have is a **partial file** at ``0o600`` on the disk, and a half-written photograph of
        somebody's screen that nobody knows about is the worst residue in this project.
        """
        with suppress(OSError):  # a directory, a permission: it was never ELA's capture
            path.unlink(missing_ok=True)


class CaptureScreenTool(Tool):
    """Photographs one display into the capture store (§29 MEDIUM; ADR 0029).

    ``probe`` is the same :class:`~ela.ports.PerceptionProbe` the perception core uses, and it is
    asked again here rather than read from the core's belief — see the module docstring. The two
    helpers are different processes but inherit the same responsible process, so TCC answers both
    the same; if it ever did not, what remains is a race of milliseconds that lands on
    :data:`SCREEN_CAPTURE_FAILED` instead of on a system prompt.
    """

    error_codes: ClassVar[frozenset[str]] = (
        frozenset(
            {
                ARGUMENTS_INVALID,
                SCREEN_UNSUPPORTED,
                SCREEN_PERMISSION_DENIED,
                SCREEN_NOT_OBSERVABLE,
                SCREEN_TIMEOUT,
                SCREEN_CAPTURE_FAILED,
                SCREEN_STORE_FULL,
            }
        )
        | CAPTURE_CODES
    )
    """There is no ``io.error`` here, and its absence is deliberate: every filesystem failure this
    tool can meet is already classified by :mod:`ela.tools.captures` with a code of its own, so a
    generic one would be a code that cannot fire — worse than no code at all (ADR 0026 §7)."""

    output_keys: ClassVar[frozenset[str]] = frozenset(
        {"capture_id", "path", "bytes", "sha256", "width", "height", "display", "expires_at"}
    )
    """What the artefact *is*, and never a byte of what it shows. ``path`` is the name inside the
    capture store, not an absolute one: the store lives under the user's home, and a home
    directory does not belong in a persisted result either (§57)."""

    idempotent: ClassVar[bool] = False
    """Two captures are two photographs of two instants, and two files. So this runs under the
    STARTED protocol of ADR 0021 §1 and is never run twice for one step — which is also what
    stops a crash between the capture and its record from quietly doubling the content ELA holds.
    """

    def __init__(
        self,
        store: CaptureStore,
        capture: ScreenCapturePort,
        probe: PerceptionProbe,
        clock: Clock,
        ids: IdGenerator,
        *,
        name: str = SCREEN_TOOL_NAME,
    ) -> None:
        super().__init__(PERCEPTION_CAPTURE_SCREEN, clock, ids, name=name)
        self._store = store
        self._capture = capture
        self._probe = probe

    async def _run(self, arguments: JsonMapping) -> Outcome:
        purpose = arguments.get("purpose")
        display = arguments.get("display", DEFAULT_DISPLAY)
        if not isinstance(purpose, str) or not purpose:
            return Outcome({}, ARGUMENTS_INVALID, "purpose must be a non-empty string")
        if not isinstance(display, int) or isinstance(display, bool) or display < 1:
            return Outcome({}, ARGUMENTS_INVALID, "display must be an integer of at least 1")
        refused = await self._refusal()
        if refused is not None:
            return refused
        return await self._photograph(display)

    async def _refusal(self) -> Outcome | None:
        """Everything that has to be true before the helper is allowed to run, in order."""
        if not await self._capture.available():
            return Outcome(
                {},
                SCREEN_UNSUPPORTED,
                "this operating system has no screen capture ELA can use",
            )
        observed = await self._probe.read(frozenset({ProbeFamily.PERMISSIONS}))
        granted = observed.screen_recording_permission
        if granted is None:
            return Outcome(
                {},
                SCREEN_NOT_OBSERVABLE,
                "the Screen Recording permission could not be read; nothing was attempted",
                retryable=True,
            )
        if not granted:
            return Outcome(
                {},
                SCREEN_PERMISSION_DENIED,
                "Screen Recording is not granted to the process ELA runs under; grant it in "
                "System Settings > Privacy & Security > Screen & System Audio Recording, then "
                "quit and reopen that application",
            )
        gone = self._store.purge(self._clock.now())
        del gone  # the purge is the point; how many went is not a fact this call reports
        full = self._store.room()
        if full is not None:
            return Outcome({}, SCREEN_STORE_FULL, full, retryable=True)
        return None

    async def _photograph(self, display: int) -> Outcome:
        """Run the helper into a destination this process owns, and clear up after a failure."""
        capture_id = str(self._ids.new_uuid())
        destination = self._store.reserve(capture_id)
        settled: Capture | None = None
        try:
            report = await self._capture.capture(str(destination), display)
            if report.timed_out:
                return Outcome(
                    {},
                    SCREEN_TIMEOUT,
                    "the capture helper did not answer in time",
                    retryable=True,
                )
            if report.exit_code != 0:
                return Outcome(
                    {},
                    SCREEN_CAPTURE_FAILED,
                    f"the capture helper exited with {report.exit_code}",
                    retryable=True,
                )
            outcome = self._store.settle(destination)
            if isinstance(outcome, CaptureProblem):
                return Outcome({}, outcome.code, outcome.message(destination.name))
            settled = outcome
        finally:
            if settled is None:
                self._store.discard(destination)
        return Outcome(
            {
                "capture_id": capture_id,
                "path": settled.name,
                "bytes": settled.bytes,
                "sha256": settled.sha256,
                "width": settled.size.width,
                "height": settled.size.height,
                "display": display,
                "expires_at": settled.expires_at.isoformat(),
            }
        )
