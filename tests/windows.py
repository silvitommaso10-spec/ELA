"""The tests reserved to Windows that the ``node-windows`` job does not collect, each with why.

M13.3, form J (ADR 0048, which pays ADR 0047 §17). A test reserved to Windows runs nowhere else,
so a file the job does not name is a defence that does not exist on any runner. Every such file is
**either** named on the job's ``pytest`` line in ``.github/workflows/ci.yml`` **or** written here
with the reason, and ``tests/docs/test_adr_terminal.py`` fails for a file that is in neither — and
for an entry here that is no longer reserved to Windows.

A reason is a fact of the runner measured or read, never a wish: the job's first run is the
measurement (M13.3, Rischi).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

OUTSIDE_THE_WINDOWS_JOB: Final[Mapping[str, str]] = {
    "tests/infrastructure/machine/test_sapi_smoke.py": "a CI runner has no speakers",
    "tests/infrastructure/machine/test_acl_smoke.py": (
        "measured on the job's first run (36151577468, 2026-09-25): the job's shell is PowerShell "
        "7, and the powershell.exe 5.1 the test starts to read the SDDL inherits its PSModulePath "
        "and cannot load Microsoft.PowerShell.Security ('Get-Acl ... could not be loaded')"
    ),
    "tests/infrastructure/machine/test_power_smoke.py": (
        "measured on the same run: power_status answered None — the powershell.exe 5.1 it starts "
        "inherits the PSModulePath of the job's PowerShell 7, the cause the ACL smoke names"
    ),
}
