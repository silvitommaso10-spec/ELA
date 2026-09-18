"""The machine's words for its power, mapped to the domain — the one place that decides (M12.3c).

The readers hand over what the machine said, and nothing else: an adapter reports primitives and the
core decides what they mean (ADR 0028 §1). The two maps and the two functions here are that
decision, inside the coverage gate. The words are P6's, measured on 2026-09-15.
"""

from __future__ import annotations

import pytest

from ela.devices import DRAWING_FROM, POWER_LINE, power_drawn_from, power_on_the_line
from ela.domain import PowerSource

AC, BATTERY, UNKNOWN = PowerSource.AC, PowerSource.BATTERY, PowerSource.UNKNOWN


@pytest.mark.parametrize(
    ("source", "expected"),
    [("AC Power", AC), ("Battery Power", BATTERY), ("UPS Power", UNKNOWN), (None, UNKNOWN)],
)
def test_what_a_mac_draws_from(source: str | None, expected: PowerSource) -> None:
    """A word nobody measured — ``UPS Power`` — is not guessed at: it is worth ``UNKNOWN``."""
    assert power_drawn_from(source) is expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (("Online", 0), AC),
        (("Offline", 0), AC),
        (("Unknown", 0), AC),
        (("Online", 1), AC),
        (("Offline", 1), BATTERY),
        (("Unknown", 1), UNKNOWN),
        (None, UNKNOWN),
    ],
    ids=["desktop", "desktop-offline", "desktop-unknown", "online", "offline", "unknown", "unread"],
)
def test_what_a_pc_runs_on(status: tuple[str, int] | None, expected: PowerSource) -> None:
    """**A desktop without a battery is on AC** (decisione del 2026-09-15), whatever the line says:
    there is nothing else it could be drawing from. The PC of P6 is the first row."""
    assert power_on_the_line(status) is expected


def test_the_maps_name_only_what_was_measured() -> None:
    assert dict(DRAWING_FROM) == {"AC Power": AC, "Battery Power": BATTERY}
    assert dict(POWER_LINE) == {"Online": AC, "Offline": BATTERY}
