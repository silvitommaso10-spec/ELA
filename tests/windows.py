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
}
"""The two smokes of the ACL and of the power source stood here from M13.3's first run
(36151577468) until M12.3d: their ``powershell.exe`` inherited the PSModulePath of the job's
PowerShell 7 and could not load its modules. That was a defect of ELA, not of the runner, and
M12.3d repaired it; the two are back on the job's line, under the same shell."""
