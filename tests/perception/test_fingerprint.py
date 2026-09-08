"""The fingerprint: what a change is measured on, and the one field that is measured and not
compared (ADR 0028 §5).

The property under test is the one that keeps the whole ring from being noise. A change detector
fed a continuous value reports a change every tick and therefore reports nothing; the answer is
*not* to quantise ``idle_seconds`` — that would be a threshold, and a threshold is a decision
belonging to whoever decides (§45) — but to carry the measurement and leave it out of the
comparison.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ela.domain import Observation, RawObservation, SensorCause, SensorState
from ela.perception import UNCOMPARED, UNKNOWN, detect, fingerprint, interpret

AT = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
FULL = RawObservation(
    camera_count=1,
    microphone_count=1,
    microphone_in_use=False,
    display_count=1,
    display_asleep=False,
    screen_locked=False,
    on_console=True,
    idle_seconds=0.5,
    camera_permission=3,
    microphone_permission=2,
    screen_recording_permission=False,
)


def test_every_field_of_an_observation_is_either_compared_or_declared_uncompared() -> None:
    """The partition is derived, not written twice — so a field added tomorrow is covered.

    And it is covered in the **fail-safe** direction: a new field is compared unless somebody
    puts it in ``UNCOMPARED`` on purpose. Forgetting produces noise, which is visible; the other
    default would produce silence, which is not.
    """
    keys = set(fingerprint(interpret(FULL, at=AT)))
    roots = {key.partition(".")[0] for key in keys}

    assert roots | UNCOMPARED == set(Observation.model_fields)
    assert not roots & UNCOMPARED


def test_the_two_uncompared_fields_are_the_two_that_must_not_be_compared() -> None:
    """``observed_at`` moves on every look; ``idle_seconds`` moves on every look *and* is the
    one behavioural measurement, kept as a number so nobody's threshold is baked in here."""
    assert {"observed_at", "idle_seconds"} == UNCOMPARED


def test_two_observations_that_differ_only_in_idle_seconds_produce_no_change() -> None:
    """The test that proves decision 5: the measurement travels, and it is not an event."""
    before = interpret(FULL, at=AT)
    after = interpret(FULL.model_copy(update={"idle_seconds": 903.25}), at=AT + timedelta(hours=1))

    assert after.idle_seconds == 903.25
    assert detect(before, after) == ()


def test_the_time_of_an_observation_is_not_a_change_either() -> None:
    assert detect(interpret(FULL, at=AT), interpret(FULL, at=AT + timedelta(days=1))) == ()


def test_a_sensor_renders_with_its_cause_because_the_two_are_one_fact() -> None:
    """A webcam that stops being observable *is* a change, though the state reads ``AVAILABLE``
    on both sides. Fingerprinting the state alone would hide it."""
    seen = fingerprint(interpret(FULL, at=AT))

    assert seen["microphone"] == f"{SensorState.AVAILABLE.value} ({SensorCause.OBSERVED.value})"
    assert seen["camera"] == f"{SensorState.AVAILABLE.value} ({SensorCause.NOT_OBSERVABLE.value})"


def test_the_permissions_are_flattened_one_key_each() -> None:
    """Per permission and not as one blob: "something in the permissions changed" is not an
    answer anybody can act on."""
    seen = fingerprint(interpret(FULL, at=AT))

    assert seen["permissions.CAMERA"] == "GRANTED"
    assert seen["permissions.MICROPHONE"] == "DENIED"
    assert seen["permissions.SCREEN_RECORDING"] == "DENIED"


@pytest.mark.parametrize(
    "field", ["display_count", "display_asleep", "screen_locked", "on_console"]
)
def test_an_unread_session_field_reads_as_unknown_and_not_as_a_value(field: str) -> None:
    """``None`` is "not read", and it must not render as ``False`` or ``0`` — which are answers."""
    seen = fingerprint(interpret(FULL.model_copy(update={field: None}), at=AT))

    assert seen[field] == UNKNOWN


def test_the_fingerprint_cannot_be_mutated_by_whoever_receives_it() -> None:
    with pytest.raises(TypeError):
        fingerprint(interpret(FULL, at=AT))["microphone"] = "ACTIVE (OBSERVED)"  # type: ignore[index]


# ----------------------------------------------------------------------------------------
# The applications family: a sequence is compared, and compared readably (M10.3 dec. 4)
# ----------------------------------------------------------------------------------------


def test_a_sequence_is_flattened_sorted_and_joined_rather_than_repred() -> None:
    """Two properties in one line, and both matter for a different reason.

    **Sorted**, because the order in which macOS happens to list the running applications is not a
    fact about the world: comparing on it would make the detector report itself. **Joined**, so
    the resulting change is something a person can read instead of two Python literals.
    """
    observation = interpret(RawObservation(running_bundle_ids=("com.b", "com.a")), at=AT)

    assert fingerprint(observation)["running_bundle_ids"] == "com.a,com.b"


def test_the_same_applications_in_a_different_order_are_not_a_change() -> None:
    before = interpret(RawObservation(running_bundle_ids=("com.a", "com.b")), at=AT)
    after = interpret(RawObservation(running_bundle_ids=("com.b", "com.a")), at=AT)

    assert detect(before, after) == ()


def test_switching_application_is_a_change_and_says_which_way() -> None:
    """``frontmost_bundle_id`` changes whenever the user switches window, and is compared anyway.

    The criterion that excluded ``idle_seconds`` was about a *continuous* measurement. This one is
    discrete, it has a before and an after, and "the user moved to Mail" is exactly the change
    §44 exists to notice.
    """
    before = interpret(RawObservation(frontmost_bundle_id="com.apple.Terminal"), at=AT)
    after = interpret(RawObservation(frontmost_bundle_id="com.apple.mail"), at=AT)

    (change,) = detect(before, after)

    assert (change.field, change.before, change.after) == (
        "frontmost_bundle_id",
        "com.apple.Terminal",
        "com.apple.mail",
    )


def test_launching_an_application_is_a_change() -> None:
    before = interpret(RawObservation(running_bundle_ids=("com.a",)), at=AT)
    after = interpret(RawObservation(running_bundle_ids=("com.a", "com.b")), at=AT)

    (change,) = detect(before, after)

    assert (change.field, change.before, change.after) == (
        "running_bundle_ids",
        "com.a",
        "com.a,com.b",
    )


def test_applications_never_read_is_unknown_and_not_an_empty_list() -> None:
    """``None`` means *not read* and must not render as "no applications are running": the two are
    different facts, and only one of them is an observation (M10.3 dec. 8, ADR 0028 §3)."""
    keys = fingerprint(interpret(RawObservation(), at=AT))

    assert keys["running_bundle_ids"] == UNKNOWN
    assert keys["frontmost_bundle_id"] == UNKNOWN
    assert keys["window_count"] == UNKNOWN
    assert (
        fingerprint(interpret(RawObservation(running_bundle_ids=()), at=AT))["running_bundle_ids"]
        == ""
    )
