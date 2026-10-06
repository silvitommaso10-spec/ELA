"""A node does not spend beyond what the Core reserved (M14.1, proposal 5; ADR 0057).

The order of a call that spends carries the worst case the Core reserved for it. Before acting, the
node asks **its own** tool what the call can cost here — its route, its ``max_tokens``, its prices
— and does not call when that is more, or when it cannot say. The envelope says the request was
**not sent** (``usage.sent`` false), which is the fact that closes the reservation at zero in the
month's ledger. The node has no cap of its own (decision B): it keeps to the Core's number.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ela.composition.node import NodeWorld
from ela.domain import CapabilityId, ErrorMetadata, ExecutionStatus, ProviderUsage, WorstCase
from ela.node import envelope_of
from ela.ports import SPENDING_OVER_RESERVATION
from ela.testing.fakes import FakeTool
from ela.tools import ToolRegistry
from tests.node.support import order, world
from tests.tools.support import allowed

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
SOON = NOW + timedelta(seconds=120)
ECHO = CapabilityId("core.echo")
RESERVED = WorstCase(
    amount=Decimal("0.25"), currency="USD", model="m", input_tokens=900, output_tokens=100
)
SPENT = ProviderUsage(input_tokens=10, output_tokens=5, cost=Decimal("0.002"), currency="USD")


def spending(tmp_path: Path, bound: WorstCase | ErrorMetadata | None) -> tuple[NodeWorld, FakeTool]:
    """A node whose ``core.echo`` spends, and says ``bound`` is the most it costs here."""
    built = world(tmp_path)
    tool = FakeTool(
        ECHO, built.clock, built.ids, output={"message": "ciao"}, idempotent=False, usage=SPENT
    )
    tool.bound = bound
    return replace(built, tools=ToolRegistry((tool,))), tool


def reserved(worst: WorstCase | None = RESERVED) -> dict[str, Any]:
    given = order(
        expires_at=SOON,
        decision=allowed(ECHO).model_dump(mode="json"),
        arguments={"message": "ciao"},
    )
    if worst is not None:
        given["worst_case"] = worst.model_dump(mode="json")
    return given


async def test_a_call_within_the_reservation_is_made(tmp_path: Path) -> None:
    built, tool = spending(tmp_path, RESERVED.model_copy(update={"amount": Decimal("0.2")}))

    envelope = await envelope_of(built, reserved())

    assert envelope["form"] == "result" and envelope["status"] == ExecutionStatus.SUCCEEDED.value
    assert len(tool.calls) == 1
    assert ProviderUsage.model_validate(envelope["usage"]).sent


async def test_the_same_worst_case_as_the_cores_is_within_it(tmp_path: Path) -> None:
    """``≤``, as the cap's own rule: a node with the Core's table computes the Core's number."""
    built, tool = spending(tmp_path, RESERVED)

    await envelope_of(built, reserved())

    assert len(tool.calls) == 1


@pytest.mark.parametrize(
    ("here", "reservation", "said"),
    [
        pytest.param(
            RESERVED.model_copy(update={"amount": Decimal("0.26"), "output_tokens": 200}),
            RESERVED,
            "up to 0.26 on this call, and the Core reserved 0.25",
            id="a-larger-max-tokens-or-a-dearer-route",
        ),
        pytest.param(
            RESERVED.model_copy(update={"amount": None}),
            RESERVED,
            "has no price for m, and the Core reserved 0.25",
            id="a-model-this-node-cannot-price",
        ),
        pytest.param(
            ErrorMetadata(code="provider.unavailable", message="no key"),
            RESERVED,
            "cannot bound this call (provider.unavailable: no key), and the Core reserved 0.25",
            id="a-call-this-node-cannot-bound",
        ),
        pytest.param(
            RESERVED,
            None,
            "up to 0.25 on this call, and the Core reserved nothing",
            id="no-reservation",
        ),
    ],
)
async def test_a_call_beyond_the_reservation_is_not_made(
    tmp_path: Path,
    here: WorstCase | ErrorMetadata,
    reservation: WorstCase | None,
    said: str,
) -> None:
    built, tool = spending(tmp_path, here)

    envelope = await envelope_of(built, reserved(reservation))

    assert tool.calls == (), "the provider is never called"
    assert envelope["form"] == "result"
    assert envelope["status"] == ExecutionStatus.FAILED.value
    error = ErrorMetadata.model_validate(envelope["error"])
    assert error.code == SPENDING_OVER_RESERVATION
    assert said in (error.message or "")
    usage = ProviderUsage.model_validate(envelope["usage"])
    assert not usage.sent and usage.cost is None, "not sent: the ledger closes it at zero"


async def test_a_tool_that_spends_nothing_is_never_stopped_here(tmp_path: Path) -> None:
    """No reservation in the order, and a tool that says ``None``: the M12 order, unchanged."""
    built, tool = spending(tmp_path, None)

    envelope = await envelope_of(built, reserved(None))

    assert envelope["status"] == ExecutionStatus.SUCCEEDED.value
    assert len(tool.calls) == 1
