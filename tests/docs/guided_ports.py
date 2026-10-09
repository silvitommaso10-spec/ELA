"""The ports ADR 0060 introduced (M14.3): what the tests of the ADRs before it take away to keep
counting what their ADR saw. Read from ADR 0060's table, never written twice."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from tests.docs.test_adr_ports import INTRODUCING, documented_ports

GUIDED_ADR: Final = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0060-guided-browser.md"
GUIDED_PORTS: Final = frozenset(
    documented_ports(GUIDED_ADR.read_text(encoding="utf-8"), INTRODUCING)
)
assert GUIDED_PORTS, "ADR 0060 introduces ports"
