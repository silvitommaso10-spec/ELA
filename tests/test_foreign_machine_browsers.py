"""``make check-linux`` finds the browsers of the machine that launches it, by itself (decision 35
of the review after the red CI of ``56c672c``, 2026-11-10).

Pretending to be Linux, the suite looks for Playwright's browsers where Linux keeps them — and on
a Mac they are not there. On 2026-11-10 ``make check-linux`` at ``56c672c`` added 104 errors of its
own to the three it was run to reproduce («the browser this test launches is not installed on this
machine»), until ``PLAYWRIGHT_BROWSERS_PATH`` was set by hand. A trap is not written down where
one remembers it: it is taken away. The plugin sets the variable itself, **when it is not there**,
to the folder Playwright uses on the machine that launches it — found from the system and the
home, never written — and **leaves one that is there as it is**.

**The plugin is read or run in a process of its own, never imported here**
(``tests/test_foreign_machine_list.py`` says why): each case below asks a fresh interpreter what the
variable is once the plugin is in.

The real system is read from ``sys.platform``, which the plugin does not fake: this module says
the same under ``make check-linux``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Final

import pytest

from ela.infrastructure.machine.browser import registry_folder

REPO: Final = Path(__file__).resolve().parent.parent
VARIABLE: Final = "PLAYWRIGHT_BROWSERS_PATH"
REAL: Final = {"darwin": "Darwin", "linux": "Linux"}.get(sys.platform, "Windows")
"""The system of the machine that runs this, as ``platform.system()`` names it when nobody
pretends."""

TOLD: Final = (
    "import json, os\n"
    "import tests.foreign_machine\n"
    f"print(json.dumps(os.environ.get({VARIABLE!r})))\n"
)
RULE: Final = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "import tests.foreign_machine as plugin\n"
    "home, cases = Path.home(), json.loads(sys.argv[1])\n"
    "print(json.dumps([plugin.browsers_of(system, named, home) for system, named in cases]))\n"
)


def asked(program: str, *arguments: str, declared: str | None = None) -> object:
    """What a fresh interpreter prints once the plugin is in: nothing of it reaches this one. Its
    environment is this one's **without the variable**, or with ``declared`` in it.

    **The environment is built here and is no argument of anything that can fail**: a traceback
    prints the arguments of the frame it ends in, and the environment of a machine is not for a
    log."""
    environment = {name: value for name, value in os.environ.items() if name != VARIABLE}
    if declared is not None:
        environment[VARIABLE] = declared
    ran = _run(program, arguments, environment)
    said, failed = ran.stdout, ran.returncode != 0
    del environment, ran
    assert not failed, "the interpreter with the plugin in ended badly"
    return json.loads(said)


def _run(
    program: str, arguments: tuple[str, ...], environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", program, *arguments],
        cwd=REPO,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def where_the_product_looks(system: str, named: dict[str, str]) -> str | None:
    """The folder of the browsers the product's own rule gives for ``system`` — what
    ``registry_folder`` looks into, without the browser's own folder."""
    found = registry_folder("chromium", named, system)
    return None if found is None else str(found.parent)


def test_without_the_variable_the_plugin_says_where_this_machine_s_browsers_are() -> None:
    """The trap: nothing set, and the suite pretending to be Linux looked in Linux's folder."""
    kept = {name: os.environ[name] for name in ("XDG_CACHE_HOME",) if name in os.environ}

    told = asked(TOLD)

    assert told == where_the_product_looks(REAL, kept)


def test_a_variable_that_is_there_is_left_as_it_is() -> None:
    declared = str(REPO / "a-folder-somebody-declared")

    told = asked(TOLD, declared=declared)

    assert told == declared


@pytest.mark.parametrize(
    ("system", "named"),
    [
        ("Darwin", {}),
        ("Linux", {}),
        ("Linux", {"XDG_CACHE_HOME": "/a/cache/of/the/test"}),
        ("Windows", {}),
    ],
)
def test_the_folder_is_the_one_the_product_looks_in_on_that_system(
    system: str, named: dict[str, str]
) -> None:
    """Derived, and held to the product's own rule: the day Playwright moves its folder the
    product's rule moves, and this says the plugin did not."""
    (found,) = asked(RULE, json.dumps([[system, named]]))  # type: ignore[misc]

    assert found == where_the_product_looks(system, named)


def test_where_the_product_has_no_rule_the_plugin_sets_nothing() -> None:
    """Not «not installed»: on a system the product does not know where to look, the variable
    stays as it was — absent."""
    assert where_the_product_looks("Windows", {}) is None
    (found,) = asked(RULE, json.dumps([["Windows", {}]]))  # type: ignore[misc]
    assert found is None
