"""``ela spend``: the month's ledger on the terminal, the gate's own numbers (M14.1, decision I).

One request to ``GET /spend`` and nothing computed here: the amounts are printed as the API writes
them, exact. Without a cap the row says what that means and the line that changes it, and the
command still exits ``0`` — a missing cap is a configuration, not an error of the command.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from ela.cli.errors import OK
from ela.cli.output import EMPTY
from ela.cli.spend import NO_CAP
from ela.domain import ExecutionId, ExecutionResult, ExecutionStatus, WorstCase
from ela.executive.spending import CAP_VARIABLE, month_of
from ela.tools.model import MODEL_COMPLETE
from tests.api.reasons import World, opened
from tests.cli.support import plain


def rows(output: str) -> dict[str, str]:
    """The ``name  value`` block as a mapping: names are one word, values the rest."""
    found: dict[str, str] = {}
    for line in plain(output).splitlines():
        name, _, value = line.partition(" ")
        found[name] = value.strip()
    return found


async def in_flight(w: World, amount: str) -> None:
    await w.ela.results.add(
        ExecutionResult(
            id=ExecutionId(w.ela.ids.new_uuid()),
            created_at=w.ela.clock.now(),
            capability_id=MODEL_COMPLETE,
            status=ExecutionStatus.STARTED,
            worst_case=WorstCase(
                amount=Decimal(amount),
                currency="USD",
                model="claude-sonnet-5-5",
                input_tokens=995904,
                output_tokens=4096,
            ),
        )
    )


async def test_with_a_cap_it_prints_the_month_the_cap_and_what_is_left(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with opened(monkeypatch, tmp_path, **{CAP_VARIABLE: "30"}) as w:
        await in_flight(w, "2.032768")
        answered = await w.cli("spend")
        month = month_of(w.ela.clock.now())

    assert answered.exit_code == OK, answered.stdout
    printed = rows(answered.stdout)
    assert list(printed) == ["month", "cap", "spent", "reserved", "left"]
    assert printed["month"].startswith(f"{month.label} (UTC), resets ")
    assert printed["cap"] == f"30 USD ({CAP_VARIABLE})"
    assert printed["spent"] == "0 USD"
    assert printed["reserved"] == "2.032768 USD (1 open, 0 without a known cost)"
    assert printed["left"] == "27.967232 USD"


async def test_without_a_cap_it_says_nothing_goes_out_names_the_line_and_exits_0(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with opened(monkeypatch, tmp_path) as w:
        answered = await w.cli("spend")

    assert answered.exit_code == OK
    printed = rows(answered.stdout)
    assert printed["cap"] == NO_CAP.format(setting=CAP_VARIABLE, currency="USD")
    assert printed["left"] == EMPTY, "no cap is not an amount left"


async def test_json_is_the_apis_answer_as_it_is(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with opened(monkeypatch, tmp_path, **{CAP_VARIABLE: "30"}) as w:
        answered = await w.cli("spend", "--json")
        served = (await w.client.get("/spend")).json()

    assert json.loads(answered.stdout) == served
