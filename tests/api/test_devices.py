"""``/devices`` (spec §16; ADR 0024 §5): the nodes, with an availability that is *derived*.

``/diagnostics`` names them in one word each; this route says what the registry knows, which is
what somebody asking "why is this task waiting" has to be able to read.
"""

from __future__ import annotations

from datetime import timedelta

from httpx import AsyncClient

from ela.composition import Ela
from ela.devices.local import LOCAL_DEVICE_ID
from ela.domain import DeviceCapability, DeviceCapabilityName


async def test_the_local_node_is_there_and_ela_is_it(client: AsyncClient, ela: Ela) -> None:
    nodes = (await client.get("/devices")).json()

    assert [node["id"] for node in nodes] == [str(LOCAL_DEVICE_ID)]
    assert nodes[0]["available"] is True
    assert nodes[0]["last_seen_at"] is not None
    assert set(nodes[0]["available_tools"]) == {tool.name for tool in ela.tools.tools()}


async def test_a_node_nobody_has_heard_from_is_not_available(client: AsyncClient, ela: Ela) -> None:
    """Derived, never the stored column (architecture rule 20): silence past the TTL is silence."""
    node = await ela.devices.get(LOCAL_DEVICE_ID)
    long_ago = node.created_at - ela.settings.devices.heartbeat_ttl - timedelta(seconds=1)
    await ela.devices.update(node.model_copy(update={"last_seen_at": long_ago}))

    nodes = (await client.get("/devices")).json()

    assert nodes[0]["available"] is False


async def test_the_node_says_what_it_is(client: AsyncClient) -> None:
    node = (await client.get("/devices")).json()[0]

    assert node["name"]
    assert node["os"]
    assert node["status"]
    assert node["privacy"]
    assert isinstance(node["capabilities"], list)


async def test_the_traits_of_a_node_are_reported_one_by_one(client: AsyncClient, ela: Ela) -> None:
    """A trait is a property of the node (§16), not a capability the Guardian rules on — and one
    that is present but *unavailable* is a different fact from one that is not there."""
    node = await ela.devices.get(LOCAL_DEVICE_ID)
    traits = (
        DeviceCapability(name=DeviceCapabilityName("camera"), available=True),
        DeviceCapability(name=DeviceCapabilityName("gpu.cuda"), available=False),
    )
    await ela.devices.update(node.model_copy(update={"capabilities": traits}))

    reported = (await client.get("/devices")).json()[0]["capabilities"]

    assert reported == [
        {"name": "camera", "available": True},
        {"name": "gpu.cuda", "available": False},
    ]
