"""``detect``: what is no longer what it was, and nothing else (§10, second half of the ring)."""

from __future__ import annotations

from datetime import UTC, datetime

from hypothesis import given, settings

from ela.domain import PerceptionChange, RawObservation, SensorCause
from ela.perception import detect, fingerprint, interpret, unobserved
from tests.domain.strategies import observations

AT = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
IDLE = RawObservation(camera_count=1, microphone_count=1, microphone_in_use=False)


def test_nothing_moved_is_an_empty_tuple() -> None:
    assert detect(interpret(IDLE, at=AT), interpret(IDLE, at=AT)) == ()


def test_the_microphone_going_on_is_one_change_with_both_sides_named() -> None:
    """What §11 exists for, in the smallest form it can take."""
    before = interpret(IDLE, at=AT)
    after = interpret(IDLE.model_copy(update={"microphone_in_use": True}), at=AT)

    assert detect(before, after) == (
        PerceptionChange(
            field="microphone", before="AVAILABLE (OBSERVED)", after="ACTIVE (OBSERVED)"
        ),
    )


def test_a_permission_granted_is_a_change_on_its_own_key() -> None:
    before = interpret(IDLE.model_copy(update={"screen_recording_permission": False}), at=AT)
    after = interpret(IDLE.model_copy(update={"screen_recording_permission": True}), at=AT)

    ((change,),) = (detect(before, after),)
    assert (change.field, change.before, change.after) == (
        "permissions.SCREEN_RECORDING",
        "DENIED",
        "GRANTED",
    )


def test_the_first_look_after_the_fail_safe_belief_reports_what_it_found() -> None:
    """ELA starts believing nothing and says so; the first tick is therefore a change.

    That is the honest shape: "I now know things I did not know" is exactly what happened.
    """
    changes = detect(unobserved(SensorCause.NOT_LOOKING, at=AT), interpret(IDLE, at=AT))

    assert {change.field for change in changes} == {"camera", "microphone"}
    assert all(change.before.endswith(f"({SensorCause.NOT_LOOKING.value})") for change in changes)


def test_changes_come_back_in_key_order() -> None:
    """Stable output: a list that reordered itself between two runs would read as churn."""
    before = interpret(IDLE, at=AT)
    after = interpret(IDLE.model_copy(update={"microphone_in_use": True, "camera_count": 0}), at=AT)

    assert [change.field for change in detect(before, after)] == ["camera", "microphone"]


@given(observations)
@settings(deadline=None)
def test_an_observation_never_differs_from_itself(one: object) -> None:
    assert detect(one, one) == ()  # type: ignore[arg-type]


@given(observations, observations)
@settings(deadline=None)
def test_a_change_is_reported_exactly_when_the_fingerprints_disagree(
    before: object, after: object
) -> None:
    """The definition, asserted rather than trusted: nothing is dropped and nothing is invented."""
    disagreeing = {
        key
        for key, value in fingerprint(after).items()  # type: ignore[arg-type]
        if fingerprint(before)[key] != value  # type: ignore[arg-type]
    }

    assert {change.field for change in detect(before, after)} == disagreeing  # type: ignore[arg-type]
