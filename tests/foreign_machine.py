"""L'altra macchina, in locale: un pytest plugin che finge di non essere questo Mac.

Loaded with ``-p tests.foreign_machine`` by ``make check-linux`` and **never** by an ordinary
run. It exists because of a defect that reached ``main`` on 2026-09-08: four tests asserted an
answer that is only true on a machine which can play audio, the developer ran ``make check`` on
one machine, and the second machine — the ubuntu job — said so eleven minutes after the merge.

**The property this makes checkable** is not a property of any single test. It is a property of
the suite: *la suite dice la stessa cosa su due macchine*. Nothing in the text of those four tests
was wrong; the platform dependence was three layers below them, behind the composition root, and
no rule reading their AST could ever have seen it (ADR 0031 §6 searched for ``platform.system()``
in the suite and could not have found them — they do not contain the words). The only faithful
verifier of that property is a second machine. Since 2026-09-18 that machine is the CI on the
branch, which the merge wants green on both runners at the last commit; the point of this file is
to reproduce **here** what the ubuntu job saw when it goes red.

It is imported before collection, so ``skipif(platform.system() != "Darwin")`` sees the other
machine too, exactly as on the runner.

**What it fakes, and it is only this:**

* ``platform.system()`` answers ``Linux``;
* the binaries of Apple that ELA reaches for, as :data:`APPLE_BINARIES` lists them, are absent.

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

**One thing it provides, which is no pretence** (decision 35 of the review after the red CI of
``56c672c``, 2026-11-10): **where the browsers of this machine are.** Pretending to be Linux, the
suite looks for Playwright's browsers where Linux keeps them, and on a Mac they are not there — on
2026-11-10 a run at ``56c672c`` added 104 errors of its own, «the browser this test launches is
not installed on this machine», to the three it was run to reproduce. So when
``PLAYWRIGHT_BROWSERS_PATH`` is not set, this sets it to the folder Playwright uses on the machine
that launches it (:func:`browsers_of`, held to the product's own rule by
``tests/test_foreign_machine_browsers.py``); **one that is set is left as it is**.

**What stays different from the runner, measured on 2026-11-10** (run 42855676471 of the ubuntu
job against ``make check-linux``, both at ``89efd0e``) — the skips each has and the other has not:

* **``/proc``**: the tests that read a process the way only Linux lets one
  (``test_nothing_left_behind.py``, ``test_agent_session.py``) are skipped here by ``sys.platform``,
  which this does not fake, and run there;
* **``GITHUB_ACTIONS``**: ``test_permissions_bite.py`` runs only on a runner;
* **the volume that tells the cases of a name apart**: a runner's does, and four tests of
  ``tests/composition/test_account_settings.py`` are skipped there and run here.

That day both said «168 skipped», four of each kind: **the totals of the skipped can be equal by
chance. Compare the lists, file by file — never the counts.**
"""

from __future__ import annotations

import os
import platform
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import Any, Final

APPLE_BINARIES = frozenset(
    {"/usr/bin/afplay", "/usr/bin/pmset", "/usr/bin/say", "/usr/sbin/screencapture"}
)
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


BROWSERS: Final = "PLAYWRIGHT_BROWSERS_PATH"
"""Where Playwright is told its browsers are, and where ELA looks for them first."""

_real_system = platform.system()
"""The machine that launches this, asked before the answer is replaced below."""


def browsers_of(system: str, environment: Mapping[str, str], home: Path) -> str | None:
    """The folder Playwright keeps its browsers in on ``system`` when nobody tells it another —
    found from the system and the home, never written —, or ``None`` on a system the product has
    no rule for. **The product's own rule** (``registry_folder``, in
    ``ela.infrastructure.machine.browser``), said again here because this file imports nothing of
    the product before it replaces the machine's answers:
    ``tests/test_foreign_machine_browsers.py`` holds the two equal, system by system."""
    if system == "Darwin":
        return str(home / "Library" / "Caches" / "ms-playwright")
    if system == "Linux":
        return str(Path(environment.get("XDG_CACHE_HOME") or home / ".cache") / "ms-playwright")
    return None


def _say_where_the_browsers_are(environment: MutableMapping[str, str]) -> None:
    """Set :data:`BROWSERS` to this machine's folder — **only when it is not there**."""
    if BROWSERS in environment:
        return
    found = browsers_of(_real_system, environment, Path.home())
    if found is not None:
        environment[BROWSERS] = found


_say_where_the_browsers_are(os.environ)
platform.system = lambda: FOREIGN_SYSTEM  # type: ignore[assignment]
os.access = _absent_on_a_foreign_machine  # type: ignore[assignment]
