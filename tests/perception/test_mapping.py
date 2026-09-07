"""``interpret``: what the operating system answered, named — and never in ELA's favour.

The table is exhaustive on purpose. Every branch of the mapping is a branch over data a test can
write down, which is the whole reason the adapter hands over primitives instead of decisions
(ADR 0028 §1): the case no runner can produce — a webcam that exists — is here as three integers.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ela.domain import (
    Observation,
    PermissionState,
    RawObservation,
    SensorCause,
    SensorState,
    SystemPermission,
)
from ela.perception import interpret, unobserved

AT = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


def observe(**raw: object) -> Observation:
    return interpret(RawObservation(**raw), at=AT)


# ----------------------------------------------------------------------------------------
# §11: the three states, and the cause that qualifies each of them
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("count", "in_use", "state", "cause"),
    [
        (None, None, SensorState.OFF, SensorCause.NOT_OBSERVABLE),
        (None, True, SensorState.OFF, SensorCause.NOT_OBSERVABLE),
        (0, None, SensorState.OFF, SensorCause.NO_HARDWARE),
        (0, False, SensorState.OFF, SensorCause.NO_HARDWARE),
        (1, None, SensorState.AVAILABLE, SensorCause.NOT_OBSERVABLE),
        (1, False, SensorState.AVAILABLE, SensorCause.OBSERVED),
        (1, True, SensorState.ACTIVE, SensorCause.OBSERVED),
        (3, True, SensorState.ACTIVE, SensorCause.OBSERVED),
    ],
)
def test_the_microphone_is_named_from_how_many_there_are_and_whether_one_is_running(
    count: int | None, in_use: bool | None, state: SensorState, cause: SensorCause
) -> None:
    """``count is None`` beats everything: not read is not the same as not there."""
    microphone = observe(microphone_count=count, microphone_in_use=in_use).microphone

    assert (microphone.state, microphone.cause) == (state, cause)


@pytest.mark.parametrize(
    ("count", "state", "cause"),
    [
        (None, SensorState.OFF, SensorCause.NOT_OBSERVABLE),
        (0, SensorState.OFF, SensorCause.NO_HARDWARE),
        (1, SensorState.AVAILABLE, SensorCause.NOT_OBSERVABLE),
        (2, SensorState.AVAILABLE, SensorCause.NOT_OBSERVABLE),
    ],
)
def test_the_webcam_is_never_active_because_nobody_can_ask(
    count: int | None, state: SensorState, cause: SensorCause
) -> None:
    """macOS publishes no supported way to ask whether the camera is in use (ADR 0028 §3).

    A present webcam is therefore ``AVAILABLE (NOT_OBSERVABLE)`` and never ``AVAILABLE
    (OBSERVED)``: ELA knows the device is there and does **not** know whether it is on, and the
    cause is what stops the second half from being read as an answer.
    """
    camera = observe(camera_count=count).camera

    assert (camera.state, camera.cause) == (state, cause)


def test_the_two_sensors_share_one_function_and_differ_only_in_the_argument() -> None:
    """The asymmetry is a fact about the input, not a second branch that fakes a resemblance.

    Same counts, and the only difference is that nobody can pass ``in_use`` for a camera.
    """
    seen = observe(camera_count=1, microphone_count=1, microphone_in_use=False)

    assert seen.camera.state == seen.microphone.state == SensorState.AVAILABLE
    assert seen.camera.cause == SensorCause.NOT_OBSERVABLE
    assert seen.microphone.cause == SensorCause.OBSERVED


# ----------------------------------------------------------------------------------------
# The permissions: asking is not requesting, and an unknown answer is never optimistic
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "state"),
    [
        (0, PermissionState.NOT_DETERMINED),
        (1, PermissionState.RESTRICTED),
        (2, PermissionState.DENIED),
        (3, PermissionState.GRANTED),
        (None, PermissionState.NOT_OBSERVABLE),
        (4, PermissionState.NOT_OBSERVABLE),
        (-1, PermissionState.NOT_OBSERVABLE),
        (99, PermissionState.NOT_OBSERVABLE),
    ],
)
def test_an_authorization_status_this_version_does_not_know_is_never_granted(
    status: int | None, state: PermissionState
) -> None:
    """§33: a doubt is not a permission. The four values macOS documents, and everything else."""
    seen = observe(camera_permission=status, microphone_permission=status)

    assert seen.permissions[SystemPermission.CAMERA] == state
    assert seen.permissions[SystemPermission.MICROPHONE] == state


@pytest.mark.parametrize(
    ("allowed", "state"),
    [
        (True, PermissionState.GRANTED),
        (False, PermissionState.DENIED),
        (None, PermissionState.NOT_OBSERVABLE),
    ],
)
def test_screen_recording_is_a_flag_and_unread_is_not_denied(
    allowed: bool | None, state: PermissionState
) -> None:
    assert (
        observe(screen_recording_permission=allowed).permissions[SystemPermission.SCREEN_RECORDING]
        == state
    )


def test_every_permission_is_always_present_so_a_fingerprint_never_loses_a_key() -> None:
    """All three, always: a map that shrank would make a permission look like it had vanished."""
    assert set(observe().permissions) == set(SystemPermission)


# ----------------------------------------------------------------------------------------
# The runner, and the belief before the first look
# ----------------------------------------------------------------------------------------


def test_a_machine_with_nothing_reads_as_nothing_observed() -> None:
    """The CI case, and it costs no hardware to produce: an empty ``RawObservation``."""
    seen = observe()

    assert seen.microphone.state == seen.camera.state == SensorState.OFF
    assert seen.microphone.cause == seen.camera.cause == SensorCause.NOT_OBSERVABLE
    assert seen.display_count is None
    assert seen.idle_seconds is None
    assert set(seen.permissions.values()) == {PermissionState.NOT_OBSERVABLE}


def test_a_runner_with_no_camera_says_no_hardware_and_not_not_observable() -> None:
    """The distinction the milestone exists for: "there is none" is an answer, "I could not
    look" is not, and a reader who is shown ``OFF`` alone cannot tell them apart."""
    seen = observe(camera_count=0, microphone_count=0)

    assert seen.camera.cause == seen.microphone.cause == SensorCause.NO_HARDWARE


@pytest.mark.parametrize("cause", [SensorCause.NOT_LOOKING, SensorCause.NOT_OBSERVABLE])
def test_the_belief_before_looking_is_off_with_the_cause_that_says_why(cause: SensorCause) -> None:
    """``unobserved`` is the fail-safe belief, used before the first tick and after a dead probe."""
    seen = unobserved(cause, at=AT)

    assert seen.observed_at == AT
    assert seen.microphone.state == seen.camera.state == SensorState.OFF
    assert seen.microphone.cause == seen.camera.cause == cause
    assert set(seen.permissions.values()) == {PermissionState.NOT_OBSERVABLE}


def test_the_session_fields_pass_through_untouched() -> None:
    """Nothing is derived from them here: what is measured is what is reported (ADR 0028 §5)."""
    seen = observe(
        display_count=2, display_asleep=True, screen_locked=True, on_console=False, idle_seconds=9.5
    )

    assert (seen.display_count, seen.display_asleep) == (2, True)
    assert (seen.screen_locked, seen.on_console) == (True, False)
    assert seen.idle_seconds == 9.5
