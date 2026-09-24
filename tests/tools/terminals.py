"""The terminal of a test that launches nothing, for the callers of the production registries.

``production_tools`` builds ``terminal.run`` like every other tool (M13.2), so whoever calls it
names the terminal it wants. Most tests want none: no program declared —
``ELA_TERMINAL_PROGRAMS=[]``, an answer and not a doubt — and a launcher that records what it would
have been handed.
"""

from __future__ import annotations

from pathlib import Path

from ela.tools.programs import Programs
from ela.tools.terminal import Terminal

from ela.testing.fakes import FakeLauncher


def a_terminal(root: Path, *programs: str) -> Terminal:
    """The terminal of the guide's scope under ``root``, with ``programs`` fixed now."""
    return Terminal(
        programs=Programs.fixed(programs),
        root=root,
        scope="ELA",
        timeout_seconds=120,
        output_max_bytes=65536,
        home="/Users/tu",
        temporary="/tmp/tu",
        argument_limit=1 << 20,
    )


def no_programs() -> Programs:
    return Programs.fixed(())


def a_launcher() -> FakeLauncher:
    return FakeLauncher()
