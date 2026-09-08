"""``GET /perception`` and the one line perception adds to ``/diagnostics`` (ADR 0028 §8).

The division between the two routes is the thing worth asserting, because it is a decision and
not a layout: a missing permission is *wiring* — what ELA can do on this machine — and belongs
next to ``providers`` and ``tools``; the state of the microphone is *the world* and does not.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from ela.api import create_app
from ela.composition import Ela
from ela.domain import SensorCause, SensorState, SystemPermission
from tests.api.support import AUTHORIZED, BASE

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
    """§57 on the wire: state, never content. The fields are exactly these and nothing else.

    A closed list rather than a "no forbidden word appears" check, because the failure this
    guards against is a field somebody *adds*, and only a closed list notices an addition. M10.3
    added three and had to come here to say so, which is the mechanism working.

    The three are state: *that* an application is running, *which* one is in front, *how many*
    windows there are. What is deliberately absent is the window title — it costs the same Screen
    Recording grant a screenshot costs (measured) and it carries a URL or a document name, so it
    is content and does not travel this route (architecture rule 36).
    """
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
        "running_bundle_ids",
        "frontmost_bundle_id",
        "window_count",
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

    assert set(block) == {"enabled", "watching", "observed_at", "permissions", "captures"}
    assert set(block["permissions"]) == {p.value for p in SystemPermission}
    # What ELA is holding of the user's, right now (M10.2, ADR 0029 §15): §57 makes it a question
    # that must be answerable, and a store of screenshots only the filesystem knows about is
    # exactly what must not exist. Still not the world — this reads ELA's own state.
    assert set(block["captures"]) == {
        "retained",
        "bytes",
        "ttl_seconds",
        "max_count",
        "max_bytes",
    }
    assert block["captures"]["retained"] == 0


async def test_diagnostics_does_not_look(client: AsyncClient) -> None:
    """It says what ELA is wired to, and whatever watches ELA calls it: it must stay free.

    Two calls, one ``observed_at``: nothing was observed in between.
    """
    first = (await client.get("/diagnostics")).json()["perception"]["observed_at"]
    second = (await client.get("/diagnostics")).json()["perception"]["observed_at"]

    assert first == second


# --------------------------------------------------------------------------------------
# The capture store in /diagnostics, and the purge at start-up (M10.2, ADR 0029 §1, §15)
# --------------------------------------------------------------------------------------


CAPTURE = "3f2504e0-4f89-41d3-9a0c-0305e82c3301.png"


def _png() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + (16).to_bytes(4, "big")
        + (9).to_bytes(4, "big")
        + b"\x00" * 16
    )


async def test_diagnostics_says_what_ela_is_holding_of_the_users(ela: Ela) -> None:
    """§57 makes "what content are you keeping of mine, right now" a question that must be
    answerable, and a store of screenshots only the filesystem knows about is what must not
    exist. It reads ELA's own state, so ``/diagnostics`` still does not observe the world."""
    data = _png()
    (ela.captures.directory / CAPTURE).write_bytes(data)

    app = create_app(ela)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED) as client,
    ):
        block = (await client.get("/diagnostics")).json()["perception"]["captures"]

    assert block["retained"] == 1
    assert block["bytes"] == len(data)
    assert block["ttl_seconds"] == ela.settings.captures.capture_ttl_seconds
    assert block["max_count"] == ela.settings.captures.capture_max_count
    assert block["max_bytes"] == ela.settings.captures.capture_max_bytes


async def test_a_start_up_purges_what_expired(ela: Ela) -> None:
    """The only moment ELA is certain to reach (ADR 0029 §1): a capture also purges before it
    writes, but a retention that only ran when somebody took a screenshot would keep the last one
    for as long as ELA is left alone."""
    old = ela.captures.directory / CAPTURE
    old.write_bytes(_png())
    stamp = (datetime.now(tz=UTC) - timedelta(hours=1)).timestamp()
    os.utime(old, (stamp, stamp))

    app = create_app(ela)
    async with app.router.lifespan_context(app):
        pass

    assert not old.exists()


async def test_a_start_up_keeps_what_has_not_expired(ela: Ela) -> None:
    fresh = ela.captures.directory / CAPTURE
    fresh.write_bytes(_png())

    app = create_app(ela)
    async with app.router.lifespan_context(app):
        pass

    assert fresh.is_file()
