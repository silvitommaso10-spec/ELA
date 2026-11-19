"""**No test of a proof script launches a real process it did not mean to** (M13.17, decisions 62
and 68 of its review).

The scripts of the proofs by hand (``scripts/prova_*.py``) launch the lines of the guide with
``cwd`` at the repository: there a ``uv run ela …`` reads the ``.env`` of whoever runs the suite —
the token and the address of the real ELA —, and a ``uv run alembic current`` opens its database.
Their tests replace those launches with doubles; **a launch a double did not reach used to start**:
on 2026-11-19 a ``uv run ela status`` started from the ``make check`` of ``0612dba``, because a
test had found a sibling script in ``sys.modules`` with another ``base`` than the one it patched.

**The guard**, put in front of **every way of starting a program the repository names** — the
list of ``tests/architecture/rules.py`` (``SPAWNING_CALLS``), derived and not written here:

- ``subprocess.Popen._execute_child``, where ``subprocess`` and the subprocesses of asyncio pass;
- every ``os`` function of that list this system has — ``os.system``, ``os.popen``, ``os.fork``,
  ``os.forkpty`` (``pty``), ``os.posix_spawn``, the ``exec`` and ``spawn`` families;
- ``_posixsubprocess.fork_exec``, where ``multiprocessing`` starts a process.

A launch whose stack, in the thread that launches, holds a frame of a proof script **fails loudly
instead of starting**, with :class:`LaunchFromAProof` — a ``BaseException``, so that a script's
``except Exception`` cannot turn it into a step that merely failed. **It is installed once per
process, when the suite is configured** (the consistency reading of the last block of M13.17,
R2): a fixture of a module or of the session that walks a proof is set up before any fixture of a
function, and would run outside a guard that a fixture of a function put in place.

**The scripts covered are derived from** ``scripts/``: every ``scripts/prova_*.py``, read when
the suite starts. A test that launches a real process through a script on purpose — the runner's
own limit, with ``sleep`` — says so with the mark :data:`ALLOWED` and its reason; the hook of
``tests/conftest.py`` lets it through for the time of that test only.
"""

from __future__ import annotations

import functools
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import FrameType
from typing import Any, Final

from tests.architecture.rules import SPAWNING_CALLS

SCRIPTS: Final = Path(__file__).resolve().parents[1] / "scripts"
PROOFS: Final[frozenset[str]] = frozenset(
    os.path.realpath(path) for path in SCRIPTS.glob("prova_*.py")
)
"""Every script of a proof, found in its folder when the suite starts."""
ALLOWED: Final = "launches_through_a_proof_script"
"""The mark of a test that launches a real process through a proof script on purpose."""
OS_LAUNCHERS: Final[tuple[str, ...]] = tuple(
    sorted(
        name.removeprefix("os.")
        for name in SPAWNING_CALLS
        if name.startswith("os.") and hasattr(os, name.removeprefix("os."))
    )
)
"""The functions of ``os`` that start a program, of the repository's list, that this system has."""
GUARDED: Final = "_ela_guarded_against_a_proof"
"""The attribute every function the guard wraps carries: what says it is wrapped."""


class LaunchFromAProof(BaseException):  # noqa: N818 — what happened, not an «Error»
    """A proof script started a real process in a test that had not replaced the launch."""


class _State:
    """Whether the test running now may launch through a proof script: the hook of
    ``tests/conftest.py`` sets it from the test's mark, for that test only."""

    let_through = False


STATE: Final = _State()


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


def guarded(real: Callable[..., Any], *, method: bool = False) -> Callable[..., Any]:
    """``real``, with the check in front of it."""

    @functools.wraps(real)
    def check(*args: Any, **named: Any) -> Any:
        if not STATE.let_through:
            script = from_a_proof(sys._getframe(1))
            if script is not None:
                raise refused(script, args[1] if method and len(args) > 1 else args)
        return real(*args, **named)

    setattr(check, GUARDED, True)
    return check


def install() -> None:
    """Once per process: the check in front of every launcher of :data:`OS_LAUNCHERS`, of
    ``subprocess.Popen._execute_child`` and of ``_posixsubprocess.fork_exec``."""
    popen: Any = subprocess.Popen
    if not getattr(popen._execute_child, GUARDED, False):
        popen._execute_child = guarded(popen._execute_child, method=True)
    for name in OS_LAUNCHERS:
        if not getattr(getattr(os, name), GUARDED, False):
            setattr(os, name, guarded(getattr(os, name)))
    try:
        import _posixsubprocess  # type: ignore[import-not-found]
    except ImportError:  # Windows: there is none
        return
    if not getattr(_posixsubprocess.fork_exec, GUARDED, False):
        _posixsubprocess.fork_exec = guarded(_posixsubprocess.fork_exec)
