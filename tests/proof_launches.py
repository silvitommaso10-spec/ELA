"""**No test of a proof script launches a real process it did not mean to** (M13.17, decisions 62
and 68 of its review).

The scripts of the proofs by hand (``scripts/prova_*.py``) launch the lines of the guide with
``cwd`` at the repository: there a ``uv run ela …`` reads the ``.env`` of whoever runs the suite —
the token and the address of the real ELA —, and a ``uv run alembic current`` opens its database.
Their tests replace those launches with doubles; **a launch a double did not reach used to start**:
on 2026-11-19 a ``uv run ela status`` started from the ``make check`` of ``0612dba``, because a
test had found a sibling script in ``sys.modules`` with another ``base`` than the one it patched.

**The guard**: every process the suite starts goes through ``subprocess.Popen._execute_child`` —
``subprocess.run`` and the subprocesses of asyncio included —, and the fixture of
``tests/conftest.py`` puts this check in front of it. A launch whose stack, in the thread that
launches, holds a frame of a proof script **fails loudly instead of starting**, with
:class:`LaunchFromAProof` — a ``BaseException``, so that a script's ``except Exception`` cannot
turn it into a step that merely failed.

**The scripts covered are derived from** ``scripts/``, **never listed here**: every
``scripts/prova_*.py``, read when the suite starts. A test that launches a real process through a
script on purpose — the runner's own limit, with ``sleep`` — says so with :data:`ALLOWED`, and its
reason.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import FrameType
from typing import Final

SCRIPTS: Final = Path(__file__).resolve().parents[1] / "scripts"
PROOFS: Final[frozenset[str]] = frozenset(
    os.path.realpath(path) for path in SCRIPTS.glob("prova_*.py")
)
"""Every script of a proof, found in its folder when the suite starts."""
ALLOWED: Final = "launches_through_a_proof_script"
"""The mark of a test that launches a real process through a proof script on purpose."""


class LaunchFromAProof(BaseException):  # noqa: N818 — what happened, not an «Error»
    """A proof script started a real process in a test that had not replaced the launch."""


def from_a_proof(frame: FrameType | None) -> str | None:
    """The proof script on the stack of ``frame``, nearest first, or ``None``."""
    while frame is not None:
        name = frame.f_code.co_filename
        if name.endswith(".py") and os.path.realpath(name) in PROOFS:
            return name
        frame = frame.f_back
    return None


def refused(script: str, args: object) -> LaunchFromAProof:
    return LaunchFromAProof(
        f"{Path(script).name} launched a real process in a test that had not replaced the "
        f"launch: {args!r}. Replace base.run, base.started or the script's own launch with a "
        f"double, or mark the test {ALLOWED} with its reason."
    )


def calling_frame() -> FrameType | None:
    """The frame that called the launch: what the guard walks from."""
    return sys._getframe(2)
