"""The two readers of the power source against the real machine that has the binary (M12.3c).

Each is declared with its ``skipif`` (ADR 0031 §6), and ``test_power.py`` already proves what ELA
does where the binary is missing. Nothing here asserts **which** source: whether this Mac is plugged
in is a fact of the afternoon, not of the code. What is asserted is that the answer has the shape
the reader reads.
"""

from __future__ import annotations

import platform

import pytest

from ela.infrastructure.machine.darwin import pmset_source
from ela.infrastructure.machine.windows import power_status


@pytest.mark.skipif(platform.system() != "Darwin", reason="pmset(1) is macOS's")
async def test_pmset_answers_in_words_the_reader_can_read() -> None:
    assert await pmset_source() is not None


@pytest.mark.skipif(platform.system() != "Windows", reason="PowerStatus is Windows's")
async def test_powershell_answers_in_words_the_reader_can_read() -> None:
    answered = await power_status()

    assert answered is not None
    line, batteries = answered
    assert line in {"Online", "Offline", "Unknown"}
    assert batteries >= 0
