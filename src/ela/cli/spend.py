"""``ela spend``: what the month has spent under the cap, and what is left (M14.1, ADR 0057).

Read-only, one request. The numbers are the API's, which reads them with the function the gate
judges with (decision I): what is printed here is what a call that spends is compared against.
Nothing is formatted twice — the amounts arrive as the gate writes them, exact.
"""

from __future__ import annotations

from typing import Any, Final

from ela.cli import client
from ela.cli.errors import handled
from ela.cli.output import Json, emit, fields

__all__ = ["NO_CAP", "spend"]

NO_CAP: Final = (
    "none: no call that spends goes out — {setting} in the Core's .env sets it, in {currency}"
)
"""The ``cap`` row without a cap: what that means, and the line that changes it. The name of the
line is the API's, not written here twice (the form of ``ela voice``, M9.6)."""


def _rows(payload: dict[str, Any]) -> list[tuple[str, Any]]:
    currency = payload["currency"]
    cap = payload["cap"]
    left = payload["left"]
    return [
        ("month", f"{payload['month']} (UTC), resets {payload['resets_at']}"),
        (
            "cap",
            NO_CAP.format(setting=payload["cap_setting"], currency=currency)
            if cap is None
            else f"{cap} {currency} ({payload['cap_setting']})",
        ),
        ("spent", f"{payload['spent']} {currency}"),
        (
            "reserved",
            f"{payload['reserved']} {currency} ({payload['open']} open, "
            f"{payload['unknown']} without a known cost)",
        ),
        ("left", None if left is None else f"{left} {currency}"),
    ]


@handled
def spend(as_json: Json = False) -> None:
    """What the month (calendar, UTC) has spent on the model's key, what is held reserved, the
    cap, and what is left.

    ``reserved`` is the worst case of the calls nothing closed — in flight, or ended without an
    outcome, held until the month turns — and of the ones closed without a known cost. A call that
    spends goes out only if spent + reserved + its worst case stays within the cap.
    """
    with client.connect() as api:
        payload = api.get("/spend")
    emit(payload, as_json, fields(_rows(payload)))
