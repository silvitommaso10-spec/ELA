"""The ACL a Windows node's secret really gets, read on the machine that applies it (M12.4 dec. B).

Criterion 9. Declared with its ``skipif`` (ADR 0031 §6): on every other runner there is no ACL to
read, and ``tests/node/test_state.py`` already proves the writer that relies on it. What only a PC
can say is whether the directory ``build_node`` makes first carries the protected ACL that
``os.mkdir(path, 0o700)`` applies from 3.12.4 on — CPython's own SDDL,
``D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)(A;OICI;FA;;;OW)`` — and whether the secret inherits it.

**The SDDL, not the text of ``icacls``**, which is translated: on the PC of P2 it wrote «DIRITTI
PROPRIETARIO» for OWNER RIGHTS. Read through ``powershell.exe``'s ``Get-Acl`` in a child, with the
path on stdin, so nothing of Windows is loaded into this process (rule 32's reason, in a test).

**And the negative case, on the same machine**: a directory born as the parent of a
``mkdir(parents=True)`` — the road a node took until M12.3b, P2's variant «oggi» — has an ACL that
is not that one. Without it, a predicate that answered yes to everything would pass here.
"""

from __future__ import annotations

import platform
import re
import subprocess
from pathlib import Path

import pytest

from ela.composition import build_node
from ela.infrastructure.machine.windows import POWERSHELL, encoded
from ela.node import join_or_read
from ela.node.state import STATE_FILE
from ela.testing.fakes import FakePower, FakeSpeech
from tests.node.support import config, replies, status

READ_SDDL = """$ProgressPreference = 'SilentlyContinue'
$ErrorActionPreference = 'Stop'
try {
  $ms = New-Object System.IO.MemoryStream
  [Console]::OpenStandardInput().CopyTo($ms)
  $path = [System.Text.Encoding]::UTF8.GetString($ms.ToArray())
  [Console]::Out.WriteLine((Get-Acl -LiteralPath $path).Sddl)
} catch {
  [Console]::Error.WriteLine($_.Exception.Message)
  exit 1
}
"""

PROTECTED = frozenset({"(A;OICI;FA;;;SY)", "(A;OICI;FA;;;BA)", "(A;OICI;FA;;;OW)"})
"""The three entries of the ACL ``mkdir(0o700)`` applies: SYSTEM, Administrators, OWNER RIGHTS."""

INHERITED = frozenset({"(A;ID;FA;;;SY)", "(A;ID;FA;;;BA)", "(A;ID;FA;;;OW)"})
"""The same three on a file inside it, each marked as inherited."""

BORN = {
    "device_id": "0b1d3c5e-0000-4000-8000-000000000009",
    "secret": "un-segreto-abbastanza-lungo-da-sembrare-vero",  # pragma: allowlist secret
    "revision": 1,
}


def dacl(path: Path) -> tuple[str, list[str]]:
    """The DACL's flags — ``P``: *protected*, nothing inherited from above — and its entries."""
    done = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded(READ_SDDL)],
        input=str(path).encode("utf-8"),
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", errors="replace")
    sddl = done.stdout.decode("utf-8").strip()
    body = sddl.partition("D:")[2].partition("S:")[0]
    flags = body.partition("(")[0]
    return flags, re.findall(r"\([^)]*\)", body)


def protected(path: Path) -> bool:
    flags, entries = dacl(path)
    return "P" in flags and len(entries) == len(PROTECTED) and set(entries) == PROTECTED


@pytest.mark.skipif(platform.system() != "Windows", reason="an ACL is Windows's")
async def test_the_secret_sits_under_the_protected_acl_on_the_road_a_node_takes(
    tmp_path: Path,
) -> None:
    state = tmp_path / "a-pc-with-no-core" / ".ela"
    built = build_node(
        config(state), speech=FakeSpeech(), speech_online=FakeSpeech(), power=FakePower()
    )

    await join_or_read(built, code="un-codice", transport=replies(status(201, BORN)).transport())

    assert protected(state)
    _, entries = dacl(state / STATE_FILE)
    assert len(entries) == len(INHERITED)
    assert set(entries) == INHERITED


@pytest.mark.skipif(platform.system() != "Windows", reason="an ACL is Windows's")
def test_a_directory_born_as_a_parent_does_not_carry_it(tmp_path: Path) -> None:
    today = tmp_path / "today"
    (today / "speech").mkdir(mode=0o700, parents=True)

    assert protected(today / "speech")
    assert not protected(today)
