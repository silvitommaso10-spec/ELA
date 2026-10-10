"""The ports ADR 0060 introduced (M14.3), and the ones ADR 0063 did (M13.9): what the tests of the
ADRs before them take away to keep counting what their ADR saw. Read from the ADRs' own tables,
never written twice."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from tests.docs.test_adr_ports import INTRODUCING, documented_ports

GUIDED_ADR: Final = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0060-guided-browser.md"
GUIDED_PORTS: Final = frozenset(
    documented_ports(GUIDED_ADR.read_text(encoding="utf-8"), INTRODUCING)
)
assert GUIDED_PORTS, "ADR 0060 introduces ports"

ACCOUNTS_ADR: Final = GUIDED_ADR.with_name("0063-browser-with-your-accounts.md")
ACCOUNT_PORTS: Final = frozenset(
    documented_ports(ACCOUNTS_ADR.read_text(encoding="utf-8"), INTRODUCING)
)
"""The ports ADR 0063 introduced (M13.9), read from its table in the same way: what the tests of
ADR 0060 and of the ADRs before it take away too."""
assert ACCOUNT_PORTS, "ADR 0063 introduces ports"
