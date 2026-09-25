"""The ``powershell.exe`` of ELA starts without the ``PSModulePath`` it would inherit (M12.3d).

Measured by the Windows job of M13.3 (run 36151577468, 2026-09-25): under a PowerShell 7 shell,
Windows PowerShell 5.1 inherits PowerShell 7's ``PSModulePath`` and cannot load its own modules —
``Get-Acl``, ``Add-Type``, ``Get-CimInstance`` all fail —, so a node started from PowerShell 7
read its power source as ``UNKNOWN`` and its SAPI voice failed. The repair is where the child is
started: the environment it receives has everything the node's has, **but that one variable**, and
Windows PowerShell 5.1 computes its own default.

Proved here with a real child — a Python one, on every system — because what the child receives is
the fact; that ``powershell.exe`` then loads its modules is proved on the Windows job, under the
PowerShell 7 shell of the runner, by the two smoke tests that use these functions.
"""

from __future__ import annotations

import inspect
import sys

import pytest

from ela.composition.system import power_of_a_pc
from ela.infrastructure.machine.windows import (
    SapiSpeechCommand,
    power_status,
    spawn_powershell,
    spawn_powershell_with_input,
    without_module_path,
)

ASKS = (
    "import os, sys; "
    "sys.stdout.write(repr(sorted(k for k in os.environ if k.upper() == 'PSMODULEPATH')))"
)
"""A child that says which spelling of the variable it received, if any."""


@pytest.mark.parametrize("name", ["PSModulePath", "PSMODULEPATH", "psmodulepath"])
def test_the_variable_is_left_out_whatever_its_case(name: str) -> None:
    """Windows keeps the environment case-insensitive and ``os.environ`` uppercases its keys: every
    spelling is the same variable, and none of them passes."""
    assert without_module_path({name: r"C:\Program Files\PowerShell\7\Modules", "PATH": "p"}) == {
        "PATH": "p"
    }


def test_everything_else_passes_as_it_is() -> None:
    environment = {"PATH": "p", "SystemRoot": r"C:\Windows", "USERPROFILE": r"C:\Users\tu"}

    assert without_module_path(environment) == environment


async def test_the_child_of_the_power_reading_does_not_receive_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PSModulePath", r"C:\Program Files\PowerShell\7\Modules")

    code, output = await spawn_powershell([sys.executable, "-c", ASKS], 30.0)

    assert (code, output) == (0, "[]")


async def test_the_child_of_the_voice_does_not_receive_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PSModulePath", r"C:\Program Files\PowerShell\7\Modules")

    code, output = await spawn_powershell_with_input([sys.executable, "-c", ASKS], b"", 30.0)

    assert (code, output) == (0, "[]")


def test_every_powershell_of_elas_starts_through_them() -> None:
    """The power reading of the adapter and of the composition, and the voice: the defaults are the
    launchers of this module, so production cannot start ``powershell.exe`` the old way."""
    assert inspect.signature(power_status).parameters["run"].default is spawn_powershell
    assert inspect.signature(power_of_a_pc).parameters["run"].default is spawn_powershell
    assert (
        inspect.signature(SapiSpeechCommand).parameters["runner"].default
        is spawn_powershell_with_input
    )
