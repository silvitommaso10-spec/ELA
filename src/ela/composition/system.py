"""What a running ELA takes from the system: a clock, a source of ids, and what the machine runs on.

Until M8.1 the only implementations of the first two ports were the fakes in :mod:`ela.testing`,
which no production module may import (contract 5): ELA could be tested but not run. These are
the two the composition root builds, and they are as small as the ports are — a real clock and a
real source of ids, with no policy of their own.

M12.3c adds the third, the power source, and it is **chosen by naming the system** (ADR 0031 §3):
``pmset`` on Darwin, ``powershell.exe`` on Windows, nobody elsewhere. The readers hand over the
machine's words (``ela.infrastructure.machine``), ``ela.devices.local`` says what they are worth,
and what is here only puts the two together — so a node and ``local`` read the same machine the
same way.

M13.2 adds the limits of what a launch passes to a program, chosen the same way: ``execve``'s on a
POSIX system — the total, and on Linux one more for a single argument —, the command line of
``CreateProcess`` on Windows, where ``os.sysconf`` does not exist.

M13.4 adds what ELA takes **away** from its own environment before the browser's Node driver can
inherit it (decision 4 of the review of 2026-09-30; ADR 0052 §14).

M13.9 adds the one thing ELA says of **itself**: where its own command is, for the line that
opens the vault (decision 98) — named with certainty, or not at all.
"""

from __future__ import annotations

import os
import platform
import sys
from collections.abc import Awaitable, Callable, MutableMapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from uuid import UUID, uuid4

from ela.devices import power_drawn_from, power_on_the_line
from ela.domain import PowerSource, ProbeFamily
from ela.infrastructure.machine import (
    PMSET,
    POWERSHELL,
    Spawn,
    pmset_source,
    power_status,
    spawn,
    spawn_powershell,
)
from ela.ports import (
    PROFILE_PROCESS,
    PROFILE_STEP,
    PROFILE_WINDOW,
    AccountBrowser,
    BrowserError,
    BrowserUnsupported,
    PerceptionProbe,
    ProfileUndeclared,
)
from ela.tools.base import NotNow
from ela.tools.terminal import ArgumentLimits

__all__ = [
    "LINUX_PAGES_IN_ONE_ARGUMENT",
    "DRIVER_WRITES",
    "NODE_PREFIX",
    "SIGNING_IN",
    "WINDOWS_COMMAND_LINE",
    "PowerReading",
    "SystemClock",
    "UuidGenerator",
    "WindowSwitch",
    "a_session_of_the_screen",
    "argument_limits",
    "own_command",
    "power_nobody_reads",
    "power_of_a_mac",
    "power_of_a_pc",
    "power_reading",
    "while_the_user_signs_in",
    "without_node_variables",
]


class SystemClock:
    """The wall clock, always **aware and in UTC** (ADR 0003 §4).

    Never ``datetime.now()`` without a timezone: a naive instant compared with a stored one is a
    comparison between two different questions, and the domain refuses to hold one at all.
    """

    __slots__ = ()

    def now(self) -> datetime:
        return datetime.now(UTC)


class UuidGenerator:
    """Random ids (``uuid4``): no host address, no sequence, nothing to correlate (§57)."""

    __slots__ = ()

    def new_uuid(self) -> UUID:
        return uuid4()


PowerReading = Callable[[], Awaitable[PowerSource]]
"""What this machine runs on, read **now** (M12.3c).

A ``Callable`` and not a port, the shape of ``Spawn``: what reads the machine is composition, and
the port count does not move. Asked by both things that write a heartbeat — a node on every sign
of life, ``local`` at start-up and on every run — and never cached: a laptop is unplugged in the
middle of a session, and a reading kept from an hour ago is a fact nobody observed.
"""


async def power_of_a_mac(run: Spawn = spawn, binary: str = PMSET) -> PowerSource:
    """``pmset -g batt``, through the Mac's map. ``run`` and ``binary`` are what a test names."""
    return power_drawn_from(await pmset_source(run, binary))


async def power_of_a_pc(run: Spawn = spawn_powershell, binary: str = POWERSHELL) -> PowerSource:
    """``PowerStatus`` through ``powershell.exe``, through the PC's map — started without the
    ``PSModulePath`` a PowerShell 7 would hand it (M12.3d)."""
    return power_on_the_line(await power_status(run, binary))


async def power_nobody_reads() -> PowerSource:
    """A system ELA has no reader for: ``UNKNOWN``, said out loud and worth zero points.

    A function with a name rather than an absent argument, for the reason ``UnsupportedSpeech`` is a
    class: "ELA on Linux does not know what it runs on" is a thing with a test, not a gap.
    """
    return PowerSource.UNKNOWN


def power_reading(system: str) -> PowerReading:
    """The reader for the system named, which is what ``platform.system()`` answers.

    An ``if`` per system and never a ternary (architecture rule 37): the arm a conditional
    expression does not take costs the branch gate nothing, and each arm here is proved by a test
    that names it.
    """
    if system == "Darwin":
        return power_of_a_mac
    if system == "Windows":
        return power_of_a_pc
    return power_nobody_reads


WINDOWS_COMMAND_LINE: Final = 32767
"""The longest command line ``CreateProcess`` takes, in characters. The terminal does not run on a
PC before M13.3 (ADR 0047 §13); the number is here so that ``build`` starts there, and it is the
real one, not a placeholder."""


LINUX_PAGES_IN_ONE_ARGUMENT: Final = 32
"""``MAX_ARG_STRLEN`` is ``PAGE_SIZE * 32`` (``include/uapi/linux/binfmts.h``): one argument, its
closing NUL included, whatever the total allows — 128 KiB with pages of 4 KiB."""


def argument_limits(system: str) -> ArgumentLimits:
    """What a launch may pass to a program on the system named (ADR 0047 §5): an ``if`` per system,
    as :func:`power_reading`, so the arm this suite does not run on is proved by name.

    macOS has no limit of its own for one argument — measured on 2026-09-24: one argument of
    1 048 412 bytes starts, and the kernel's count is ELA's to the byte —, so there ``one`` is the
    total, as it is for a system nobody measured.
    """
    if system == "Windows":
        return ArgumentLimits(total=WINDOWS_COMMAND_LINE, one=WINDOWS_COMMAND_LINE)
    total = os.sysconf("SC_ARG_MAX")
    if system == "Linux":
        return ArgumentLimits(
            total=total, one=os.sysconf("SC_PAGESIZE") * LINUX_PAGES_IN_ONE_ARGUMENT
        )
    return ArgumentLimits(total=total, one=total)


NODE_PREFIX: Final = "NODE_"
"""What makes a variable Node's (decision 4 of the review of 2026-09-30). Playwright's driver is a
Node process that inherits ELA's environment, and it is the driver that fetches the document of the
main frame: ``NODE_TLS_REJECT_UNAUTHORIZED=0`` or ``NODE_EXTRA_CA_CERTS`` in the shell that starts
ELA made a page with an invalid certificate open (M4-ter). **A prefix and not a list of names**: the
variable Node reads tomorrow is one nobody here has heard of."""


DRIVER_WRITES: Final = ("DEBUG", "PWDEBUG")
"""What makes the driver **write what it is told** (M13.9, decision 22; ADR 0063, which revises
ADR 0052 §14). Measured: with ``DEBUG=pw:api`` or ``pw:protocol`` in ELA's environment the driver
writes the value of every ``fill`` on its stderr, and with ``DEBUG_FILE`` into a file — and since
M13.9 a ``fill`` may carry a password of the vault. Prefixes, like ``NODE_``: ``DEBUG_FILE``,
``DEBUG_COLORS`` and whatever the ``debug`` library reads tomorrow go with them."""


def without_node_variables(environment: MutableMapping[str, str]) -> tuple[str, ...]:
    """Remove from ``environment`` every variable whose name begins with ``NODE_`` — and, since
    M13.9, with ``DEBUG`` or ``PWDEBUG`` (:data:`DRIVER_WRITES`) —, and return the names in order:
    **never the values**, which may be a path or a secret."""
    prefixes = (NODE_PREFIX, *DRIVER_WRITES)
    removed = tuple(sorted(name for name in environment if name.startswith(prefixes)))
    for name in removed:
        del environment[name]
    return removed


OWN_COMMAND: Final = "ela"
"""The name ELA's command line is installed under (``[project.scripts]``)."""


def own_command(executable: str | None = None, system: str | None = None) -> Path | None:
    """The command this ELA runs with, **named with certainty or not at all** (M13.9, decision
    98): the one installed **beside the interpreter that runs this process**. ``None`` when
    there is none there — ELA started some other way —: nothing is guessed, and nothing is
    looked for in a ``PATH``.

    Measured on 2026-10-11, with ``ps`` on a running ELA started by ``uv run ela serve``: the
    Core is ``<environment>/bin/python3 <environment>/bin/ela serve``. **The interpreter is
    taken as it is named, never resolved**: the interpreter of a virtual environment is a link
    to the one it was made from, and the command is beside the link, not where it leads. On
    Windows the command carries its extension, in the environment's folder of scripts — beside
    its interpreter all the same.

    It is the right half of the line ELA prints for a locked vault, so it is the program that
    receives the key of the vault: a bare name there would be whichever program a ``PATH`` finds
    first, which is what ADR 0063 refuses for the vault's own program.
    """
    interpreter = Path(sys.executable if executable is None else executable)
    if not interpreter.is_absolute():
        return None
    name = OWN_COMMAND
    if (platform.system() if system is None else system) == "Windows":
        name = f"{OWN_COMMAND}.exe"
    found = interpreter.parent / name
    if found.is_file() and os.access(found, os.X_OK):
        return found
    return None


class WindowSwitch:
    """Whether the browser with the user's accounts has a window (M13.9, ADR 0063; decisions 18a
    and 34).

    **The user's, and nobody else's**: it is no argument of any capability and no tool decides
    it. A state of a running ELA — flipped by a route of the user's, read by the browser's adapter
    at each launch, holding from then on — and **off at every start**: a browser that appears
    while somebody is typing takes the keyboard, so a window is something the user asked for
    today.
    """

    def __init__(self) -> None:
        self._shown = False

    @property
    def shown(self) -> bool:
        return self._shown

    def show(self) -> None:
        self._shown = True

    def hide(self) -> None:
        self._shown = False


SIGNING_IN: Final = {
    PROFILE_WINDOW: "the window of ELA's browser where you sign in by hand is open",
    PROFILE_PROCESS: (
        "a browser ELA did not start now is open on the profile of its browser, and you may be "
        "signing in there"
    ),
}
"""Who holds the profile while a hand may be on it, and the reason ELA gives for not looking: its
own window, and a browser the folder's lock names that this ELA did not start — a window left by
an ELA that was killed is the same window, and the lock is all that is left to name it. A step of
ELA's own is not here: nobody is typing a password into a page ELA drives."""
NO_HAND: Final = frozenset({PROFILE_STEP})
"""The holders that let ELA look and listen — said by name, so that a holder the port comes to
answer with and nobody wrote a sentence for is a doubt, and not «nobody» (fail-safe)."""


def a_session_of_the_screen(probe: PerceptionProbe) -> Callable[[], Awaitable[bool]]:
    """The one question the browser with the user's accounts is handed about this machine
    (M13.9, decision 143 of the review of 2026-10-13): «is this process inside a session of the
    screen?», answered by reading the session **at each call** with the probe the perception
    already reads with — the family of the session, and nothing else.

    A login of ELA's is started in a window, and a process outside a session of the screen can
    be given none. **A session that was read is a session** — locked or not, in front or not: a
    window can be made in it. What the probe reads of the session it reads from the session's own
    dictionary, so where there is none — or the probe did not answer — it reads nothing: **a
    doubt, and a doubt is «no»** (fail-safe). The port promises not to raise; a probe that breaks
    the promise is the same doubt.

    *Measured from inside the user's session, where it says yes. The case with no session is not
    built on the machine this was written on: it is what the system's documentation says of the
    reading, and what the tests hand in.*"""

    async def there() -> bool:
        try:
            read = await probe.read(frozenset({ProbeFamily.SESSION}))
        except Exception:  # noqa: BLE001 — a probe that broke its promise: a doubt, not a window
            return False
        return read.on_console is not None

    return there


def while_the_user_signs_in(accounts: AccountBrowser) -> NotNow:
    """The one question the tools that look at the screen or listen are handed (M13.9, ADR 0063
    §7; decision 41): «not now?», answered by looking at who holds the profile **at each call**.

    ELA reads nothing of the window through the browser — no driver, no pipe, no port —, and the
    screen and the microphone would be another road to what is typed there. The tools do not
    learn what the window is: they get the reason, or ``None``.

    Where no folder is declared, or the system is not one the browser runs on, no window of
    ELA's can be open and the answer is ``None``. **Any other failure to look is a doubt, and a
    doubt refuses** (fail-safe): a folder is declared, and ELA cannot say whether a hand is on it.
    So is a holder this module has no sentence for: only the holders of :data:`NO_HAND` let ELA
    look.
    """

    async def not_now() -> str | None:
        try:
            holder = await accounts.occupied()
        except (ProfileUndeclared, BrowserUnsupported):
            return None
        except BrowserError as doubt:
            return (
                "whether the window of ELA's browser where you sign in by hand is open could "
                f"not be read ({doubt})"
            )
        if holder is None or holder in NO_HAND:
            return None
        return SIGNING_IN.get(
            holder,
            f"the profile of ELA's browser is held by something ELA has no word for ({holder}), "
            "and you may be signing in there",
        )

    return not_now
