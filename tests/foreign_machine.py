"""L'altra macchina, prima del push: un pytest plugin che finge di non essere questo Mac.

Loaded with ``-p tests.foreign_machine`` by ``make check-linux`` and **never** by an ordinary
run. It exists because of a defect that reached ``main`` on 2026-09-08: four tests asserted an
answer that is only true on a machine which can play audio, the developer ran ``make check`` on
one machine, and the second machine — the ubuntu job — said so eleven minutes after the merge.

**The property this makes checkable** is not a property of any single test. It is a property of
the suite: *la suite dice la stessa cosa su due macchine*. Nothing in the text of those four tests
was wrong; the platform dependence was three layers below them, behind the composition root, and
no rule reading their AST could ever have seen it (ADR 0031 §6 searched for ``platform.system()``
in the suite and could not have found them — they do not contain the words). The only faithful
verifier of that property is a second machine, and the point of this file is to reach one
**before** the push instead of eleven minutes after it.

It is imported before collection, so ``skipif(platform.system() != "Darwin")`` sees the other
machine too, exactly as on the runner.

**What it fakes, and it is only this:**

* ``platform.system()`` answers ``Linux``;
* the three binaries of Apple that ELA reaches for are reported absent.

**What it cannot reproduce — read this before trusting it:**

* **It is still CPython on macOS.** Filesystem case-insensitivity, ``/dev/fd`` semantics, signal
  behaviour, the SQLite build, locales and path handling are this machine's.
* **It fakes what is listed above and nothing else.** ``sys.platform``, ``os.uname()`` and a
  ``ctypes`` load of a framework still answer Darwin, so code that asks the machine some *other*
  way is not covered.
* **It proves that nothing depends on Darwin's answers; it does not prove that Linux works.**
  The Linux arm of an adapter is exercised only where a test names it.
* **It says nothing about time.** A runner is slower, and a test that passes here because this
  machine is fast will still fail there.
* **It says nothing about the install.** ``uv`` resolves different wheels on Linux, and that
  half only exists on the real runner.

So: green here means the suite is not *inheriting* the machine. Green there is the one that
counts, and it is still the gate before a merge.
"""

from __future__ import annotations

import os
import platform
from typing import Any

APPLE_BINARIES = frozenset({"/usr/bin/afplay", "/usr/bin/say", "/usr/bin/screencapture"})
"""What ELA reaches for on a Mac. Absent here, as they are on a runner."""

FOREIGN_SYSTEM = "Linux"
"""The other machine of the CI matrix. Named, never asked for (ADR 0031 §3)."""

_real_access = os.access


def _absent_on_a_foreign_machine(path: Any, mode: int, **named: Any) -> bool:
    """``False`` for Apple's binaries, and the truth for everything else."""
    if str(path) in APPLE_BINARIES:
        return False
    result: bool = _real_access(path, mode, **named)
    return result


platform.system = lambda: FOREIGN_SYSTEM  # type: ignore[assignment]
os.access = _absent_on_a_foreign_machine  # type: ignore[assignment]
