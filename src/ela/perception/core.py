"""The first ring of §10: look, name what was seen, notice what changed (M10.1, ADR 0028).

Everything that *decides* lives here, and nothing here touches the operating system. The port
hands over primitives — an ``int`` for an ``AVAuthorizationStatus``, ``None`` for "not read" — and
:func:`interpret` turns them into the vocabulary of §11. That split is not tidiness: no CI runner
has a webcam, so the adapter cannot be covered, and a module that cannot be covered must not be
allowed to decide anything (ADR 0028 §1). Here every branch is a branch over data a test can
write down, including the one that matters most — the one where nothing could be read at all.

Three properties are worth naming because they are easy to lose:

* **A state never travels alone.** :func:`interpret` only ever produces a
  :class:`~ela.domain.SensorStatus`, so ``OFF`` reaches no reader without the cause that says
  whether it is an observation or a fail-safe default.
* **The comparison is discrete, the measurement need not be.** ``idle_seconds`` is carried and
  never compared: a change detector fed a continuous value reports a change every tick and
  therefore reports nothing. See :data:`UNCOMPARED`.
* **A refresh of one family does not erase the others.** The cadences differ, so most ticks read
  a subset; :func:`merge` keeps what was not re-read. Without it a permission would appear to
  "change" every time the microphone was refreshed — the easiest way to get differentiated
  cadences wrong.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Final, NamedTuple

from ela.domain import (
    FAMILY_FIELDS,
    Observation,
    PerceptionChange,
    PermissionState,
    ProbeFamily,
    RawObservation,
    SensorCause,
    SensorState,
    SensorStatus,
    SystemPermission,
)
from ela.perception.settings import PerceptionSettings
from ela.ports import Clock, PerceptionProbe

__all__ = [
    "AUTHORIZATION_STATUS",
    "UNCOMPARED",
    "UNKNOWN",
    "PerceptionCore",
    "PerceptionView",
    "detect",
    "fingerprint",
    "interpret",
    "merge",
    "unobserved",
]

UNCOMPARED: Final[frozenset[str]] = frozenset({"observed_at", "idle_seconds"})
"""Fields of an :class:`~ela.domain.Observation` the change detector does not compare.

``observed_at`` because every observation has a new one, and ``idle_seconds`` because it is a
continuous measurement: quantising it into "present" and "away" would be a threshold, and a
threshold is a decision that belongs to whoever decides (§45), not to whoever observes.

Everything else is compared, and a field added tomorrow is compared **unless somebody puts it
here on purpose** — the fail-safe direction, and a test asserts it.
"""

UNKNOWN: Final = "unknown"
"""How a ``None`` reads in a fingerprint: absent, and saying so."""

AUTHORIZATION_STATUS: Final[Mapping[int, PermissionState]] = MappingProxyType(
    {
        0: PermissionState.NOT_DETERMINED,
        1: PermissionState.RESTRICTED,
        2: PermissionState.DENIED,
        3: PermissionState.GRANTED,
    }
)
"""``AVAuthorizationStatus`` as the framework returns it, named.

Anything outside this table is :attr:`~ela.domain.PermissionState.NOT_OBSERVABLE` and never
``GRANTED``: a value this version does not understand is a doubt, and a doubt is not a permission
(§33).
"""


class PerceptionView(NamedTuple):
    """What ELA currently believes, and what changed when it last looked.

    Not a domain entity — it is not persisted and crosses no port, so it stays a value of
    :mod:`ela.perception` (the criterion of ADR 0026 §2).
    """

    observation: Observation
    changes: tuple[PerceptionChange, ...]


def _sensor(count: int | None, in_use: bool | None) -> SensorStatus:
    """A §11 status from "how many are there" and "is one in use", with the cause (ADR 0028 §3).

    The microphone and the webcam share this function and differ only in what they can pass:
    ``in_use`` is a real reading for the microphone (CoreAudio, no permission needed) and always
    ``None`` for the webcam, because macOS publishes no supported way to ask. The asymmetry is
    therefore a fact about the *argument*, not a second branch pretending the two are alike.
    """
    if count is None:
        return SensorStatus(state=SensorState.OFF, cause=SensorCause.NOT_OBSERVABLE)
    if count == 0:
        return SensorStatus(state=SensorState.OFF, cause=SensorCause.NO_HARDWARE)
    if in_use is None:
        return SensorStatus(state=SensorState.AVAILABLE, cause=SensorCause.NOT_OBSERVABLE)
    state = SensorState.ACTIVE if in_use else SensorState.AVAILABLE
    return SensorStatus(state=state, cause=SensorCause.OBSERVED)


def _tcc(status: int | None) -> PermissionState:
    """An ``AVAuthorizationStatus`` named; unread or unknown is never optimistic."""
    if status is None:
        return PermissionState.NOT_OBSERVABLE
    return AUTHORIZATION_STATUS.get(status, PermissionState.NOT_OBSERVABLE)


def _flag(allowed: bool | None) -> PermissionState:
    """A yes/no permission named; ``None`` is not observable, not denied."""
    if allowed is None:
        return PermissionState.NOT_OBSERVABLE
    return PermissionState.GRANTED if allowed else PermissionState.DENIED


def interpret(raw: RawObservation, *, at: datetime) -> Observation:
    """Name what the operating system answered (§11), without ever guessing in ELA's favour."""
    return Observation(
        observed_at=at,
        microphone=_sensor(raw.microphone_count, raw.microphone_in_use),
        camera=_sensor(raw.camera_count, None),
        permissions={
            SystemPermission.CAMERA: _tcc(raw.camera_permission),
            SystemPermission.MICROPHONE: _tcc(raw.microphone_permission),
            SystemPermission.SCREEN_RECORDING: _flag(raw.screen_recording_permission),
        },
        display_count=raw.display_count,
        display_asleep=raw.display_asleep,
        screen_locked=raw.screen_locked,
        on_console=raw.on_console,
        idle_seconds=raw.idle_seconds,
    )


def unobserved(cause: SensorCause, *, at: datetime) -> Observation:
    """The belief ELA holds when it has not looked: everything ``OFF``, and ``cause`` says why.

    Used twice, and both times it is the fail-safe answer rather than a claim: before the first
    tick (``NOT_LOOKING``), and after a tick that could not read anything (``NOT_OBSERVABLE``).
    """
    return interpret(RawObservation(), at=at).model_copy(
        update={
            "microphone": SensorStatus(state=SensorState.OFF, cause=cause),
            "camera": SensorStatus(state=SensorState.OFF, cause=cause),
        }
    )


def merge(
    previous: RawObservation, fresh: RawObservation, families: frozenset[ProbeFamily]
) -> RawObservation:
    """``fresh`` for the fields of ``families``, ``previous`` for every other field.

    What keeps three cadences from lying: a tick that refreshes only the sensors must not report
    that the permissions became unreadable, because nobody asked about them.
    """
    refreshed = {field for family in families for field in FAMILY_FIELDS[family]}
    return RawObservation(
        **{
            name: getattr(fresh if name in refreshed else previous, name)
            for name in RawObservation.model_fields
        }
    )


def fingerprint(observation: Observation) -> Mapping[str, str]:
    """The discrete part of an observation, flattened to strings — what a change is measured on.

    Derived from the model's own fields minus :data:`UNCOMPARED`, so it cannot fall behind the
    model. A sensor renders with its cause (``AVAILABLE (OBSERVED)``) because the two are one
    fact: a webcam that stops being observable *is* a change worth reporting, even though the
    state either side of it reads ``AVAILABLE``.
    """
    keys: dict[str, str] = {}
    for name in observation.__class__.model_fields:
        if name in UNCOMPARED:
            continue
        value = getattr(observation, name)
        if isinstance(value, SensorStatus):
            keys[name] = f"{value.state.value} ({value.cause.value})"
        elif isinstance(value, Mapping):
            for permission, state in value.items():
                keys[f"{name}.{permission.value}"] = state.value
        else:
            keys[name] = UNKNOWN if value is None else str(value)
    return MappingProxyType(keys)


def detect(before: Observation, after: Observation) -> tuple[PerceptionChange, ...]:
    """What is no longer what it was, in key order. Empty when nothing discrete moved."""
    was, now = fingerprint(before), fingerprint(after)
    return tuple(
        PerceptionChange(field=key, before=was.get(key, UNKNOWN), after=now[key])
        for key in sorted(now)
        if was.get(key, UNKNOWN) != now[key]
    )


class PerceptionCore:
    """ELA's belief about the machine it runs on, and the loop that keeps it current (§10).

    Holds exactly two observations: the current one and the previous one, and the second only so
    the first can be compared with something. **The perception is not the memory** — a ring of
    recent changes would be an undeclared history, and structured memory is §21, with rules this
    module does not have and must not improvise (importance, confidence, expiry, privacy).

    Writes nothing to the audit log, and that is a property with a test rather than an omission:
    an observed change is not a decision of ELA's, and the audit records what ELA decides, not
    what the world does (ADR 0028 §10). The day ELA *causes* a state to change — turning the
    microphone on — that is a choice and it will be recorded.
    """

    __slots__ = (
        "_changes",
        "_clock",
        "_current",
        "_due_at",
        "_previous",
        "_probe",
        "_raw",
        "_settings",
    )

    def __init__(self, probe: PerceptionProbe, clock: Clock, settings: PerceptionSettings) -> None:
        now = clock.now()
        self._probe = probe
        self._clock = clock
        self._settings = settings
        self._raw = RawObservation()
        self._current = unobserved(SensorCause.NOT_LOOKING, at=now)
        self._previous = self._current
        self._changes: tuple[PerceptionChange, ...] = ()
        self._due_at: dict[ProbeFamily, datetime] = dict.fromkeys(ProbeFamily, now)

    @property
    def view(self) -> PerceptionView:
        """What ELA believes now, with the changes its last look produced."""
        return PerceptionView(self._current, self._changes)

    async def tick(self) -> tuple[PerceptionChange, ...]:
        """Look at whatever is due, and answer with what changed.

        Nothing due is not an error and not a reason to spawn anything: the cadence *is* the
        freshness contract, so a second read inside the interval answers what the first one saw,
        with the ``observed_at`` that says when that was.
        """
        now = self._clock.now()
        if not self._settings.perception_enabled:
            return self._believe(unobserved(SensorCause.NOT_LOOKING, at=now))
        families = frozenset(family for family in ProbeFamily if self._due_at[family] <= now)
        if not families:
            return ()
        fresh = await self._probe.read(families)
        self._raw = merge(self._raw, fresh, families)
        for family in families:
            self._due_at[family] = now + self._settings.interval(family)
        return self._believe(interpret(self._raw, at=now))

    async def run(self) -> None:
        """Tick on the configured cadence until cancelled. Returns at once if the loop is off.

        A probe that raises breaks its own contract — the port promises a value, never an
        exception — so the loop neither trusts it nor dies with it: the belief becomes
        ``NOT_OBSERVABLE`` and the next tick tries again. The failure lands where somebody looks,
        which is worth more than a log line nobody reads.
        """
        if not self._settings.loop_enabled:
            return
        while True:
            try:
                await self.tick()
            except Exception:  # noqa: BLE001 — whatever the probe did, perception stays up
                self._believe(unobserved(SensorCause.NOT_OBSERVABLE, at=self._clock.now()))
            await asyncio.sleep(self._settings.loop_interval.total_seconds())

    def _believe(self, observation: Observation) -> tuple[PerceptionChange, ...]:
        """Adopt ``observation`` as the current belief and remember what it changed."""
        self._previous = self._current
        self._current = observation
        self._changes = detect(self._previous, observation)
        return self._changes
