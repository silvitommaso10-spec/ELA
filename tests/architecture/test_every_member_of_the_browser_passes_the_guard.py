"""Every member of the browser's ports that asks the driver something passes through **one guard**
(M13.9d, ADR 0072; decision 93 of the review of its SPEC).

The guard is what gives a closing its limit. A member runs in a task of its own; when whoever
waits for it is cancelled — the tool's time, the stop of a task — the task is cancelled and waited
for at most the limit; past it the drivers of that task are killed with what they started, and
the task is waited for at most the limit again. **A member that went around it would wait for a
driver that never answers for ever**, which is what a step did for half an hour on 2026-11-17.

**A closed world.** The members are derived from the ports — :class:`~ela.ports.Browser` and
:class:`~ela.ports.AccountBrowser` —, never listed: each, on the adapter that implements it, is
guarded, or exempt here with its reason. A member added to a port, and an exemption taken away,
make the rule speak. A rule of behaviour and not of the tree, like
``test_every_use_of_a_page_asks_the_boundary.py``: whether the guard does what it says is proved
by the real browsers (``tests/infrastructure/machine/test_a_closing_has_a_limit.py``).
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping

from ela.infrastructure.machine.account import AccountChrome
from ela.infrastructure.machine.browser import GUARDED, PlaywrightBrowser
from ela.ports import AccountBrowser, Browser

EXEMPT: Mapping[str, str] = {
    "installed": "a look at a file: nothing is started, and no driver is asked",
    "another": "says what the gate already knows of another page: no driver is asked",
    "refused_download": "says what the door already knows: no driver is asked",
    "keep": (
        "starts the deadline of the verifier's look, and asks no driver: the close it ends with "
        "is a member of its own, and is guarded"
    ),
    "hold": "marks the page as a task's: no driver is asked",
    "can_show": "asks the system whether a window can be had: no driver is started or asked",
    "occupied": "looks at the folder and at the table of the processes: no driver is asked",
    "linked": "reads a file of the folder: no driver is asked",
    "saved": "counts in the folder: no driver is asked",
    "profiles": "counts in the folder: no driver is asked",
    "window": (
        "the window is a process ELA starts itself, with no driver of Playwright's: its close is "
        "``shut``, with a grace of its own, and ELA's close kills its group"
    ),
    "shut": (
        "ends the window, a process with no driver, told once and killed past its own grace "
        "(ADR 0063 §4): no driver is asked"
    ),
}
"""The members that ask no driver anything, each with its reason."""


def members(port: type) -> list[str]:
    """The members of ``port``, as the port declares them."""
    return sorted(
        name for name, _ in inspect.getmembers(port, inspect.isfunction) if not name.startswith("_")
    )


def unguarded(adapter: type, port: type, exempt: Mapping[str, str]) -> list[str]:
    """The members of ``port`` that ``adapter`` implements without the guard, and that are not
    exempt."""
    return [
        name
        for name in members(port)
        if name not in exempt and not getattr(getattr(adapter, name), GUARDED, False)
    ]


def test_every_member_of_the_two_browsers_passes_the_guard_or_says_why_not() -> None:
    assert unguarded(PlaywrightBrowser, Browser, EXEMPT) == []
    assert unguarded(AccountChrome, AccountBrowser, EXEMPT) == []


def test_every_exemption_is_a_member_of_a_port() -> None:
    """An exemption of a member no port has any more says nothing, and is taken away."""
    assert sorted(set(EXEMPT) - set(members(AccountBrowser))) == []


def test_an_exemption_taken_away_makes_the_rule_speak() -> None:
    """The negative case, for every exemption: without it, its member is named."""
    for name in EXEMPT:
        fewer = {other: why for other, why in EXEMPT.items() if other != name}
        assert unguarded(AccountChrome, AccountBrowser, fewer) == [name]


def test_a_member_added_to_a_port_makes_the_rule_speak() -> None:
    """A port with a member the adapter implements without the guard: named."""

    class Wider(AccountBrowser):  # type: ignore[misc]
        async def a_new_member(self, page: str) -> None: ...

    class Implemented(AccountChrome):
        async def a_new_member(self, page: str) -> None:
            return None

    assert unguarded(Implemented, Wider, EXEMPT) == ["a_new_member"]
