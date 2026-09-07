"""``GET /perception`` and the one line perception adds to ``/diagnostics`` (ADR 0028 §8).

The division between the two routes is the thing worth asserting, because it is a decision and
not a layout: a missing permission is *wiring* — what ELA can do on this machine — and belongs
next to ``providers`` and ``tools``; the state of the microphone is *the world* and does not.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from ela.domain import SensorCause, SensorState, SystemPermission

pytestmark = pytest.mark.usefixtures("_perception_on")


@pytest.fixture
def _perception_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """On, but with no loop: exactly the default an installed ELA has (ADR 0028 §7)."""
    monkeypatch.setenv("ELA_PERCEPTION_ENABLED", "true")


async def perception(client: AsyncClient) -> dict[str, Any]:
    answer = await client.get("/perception")
    assert answer.status_code == 200
    return dict(answer.json())


async def test_the_route_needs_the_token_like_every_other(anonymous: AsyncClient) -> None:
    assert (await anonymous.get("/perception")).status_code == 401


async def test_a_sensor_always_arrives_with_its_cause(client: AsyncClient) -> None:
    """The property the whole model exists for: no schema anywhere carries a bare state.

    A reader shown ``OFF`` alone has been told something ELA does not know (ADR 0028 §3).
    """
    seen = await perception(client)

    for sensor in ("microphone", "camera"):
        assert set(seen[sensor]) == {"state", "cause"}
        assert seen[sensor]["state"] in set(SensorState)
        assert seen[sensor]["cause"] in set(SensorCause)


async def test_all_three_permissions_are_reported(client: AsyncClient) -> None:
    assert set((await perception(client))["permissions"]) == {p.value for p in SystemPermission}


async def test_the_answer_says_whether_ela_is_watching_and_when_it_last_looked(
    client: AsyncClient,
) -> None:
    """An answer without its age would be read as current, and perception ages."""
    seen = await perception(client)

    assert seen["enabled"] is True
    assert seen["watching"] is False
    assert seen["observed_at"]


async def test_idle_seconds_arrives_as_a_number_or_not_at_all(client: AsyncClient) -> None:
    """Never as "present" or "away": that is a threshold, and a threshold belongs to whoever
    decides (§45, ADR 0028 §5)."""
    idle = (await perception(client))["idle_seconds"]

    assert idle is None or isinstance(idle, int | float)


async def test_the_answer_carries_no_content_of_any_kind(client: AsyncClient) -> None:
    """§57 on the wire: state, never content. The fields are exactly these and nothing else."""
    assert set(await perception(client)) == {
        "enabled",
        "watching",
        "observed_at",
        "microphone",
        "camera",
        "permissions",
        "display_count",
        "display_asleep",
        "screen_locked",
        "on_console",
        "idle_seconds",
        "changes",
    }


# ----------------------------------------------------------------------------------------
# /diagnostics: the wiring half, and the promise that it costs nothing
# ----------------------------------------------------------------------------------------


async def test_diagnostics_carries_the_permissions_and_not_the_sensors(
    client: AsyncClient,
) -> None:
    answer = await client.get("/diagnostics")
    block = answer.json()["perception"]

    assert set(block) == {"enabled", "watching", "observed_at", "permissions"}
    assert set(block["permissions"]) == {p.value for p in SystemPermission}


async def test_diagnostics_does_not_look(client: AsyncClient) -> None:
    """It says what ELA is wired to, and whatever watches ELA calls it: it must stay free.

    Two calls, one ``observed_at``: nothing was observed in between.
    """
    first = (await client.get("/diagnostics")).json()["perception"]["observed_at"]
    second = (await client.get("/diagnostics")).json()["perception"]["observed_at"]

    assert first == second
