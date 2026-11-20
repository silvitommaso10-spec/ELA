"""``scripts/misura_m13_11.py`` on a real Windows: what only Windows answers, read as the script
reads it (SPEC of M13.11, «Test previsti — dello script», the last line).

On the line of the job ``node-windows`` — no Smart App Control there, and no browser —: the
registry, ``Get-MpComputerStatus``, ``Get-AuthenticodeSignature``, ``Win32_Process``, ``Get-Acl``,
the two PowerShells of B3, and the adapters of today built on Windows (A3.0). **They assert only
that the script reads them**: what they say on Tommaso's PC is the measure's, not the job's. Every
launch the script does here is named with ``script_may``, its program and its arguments exact —
the scripts of PowerShell are constants, and what they read goes on stdin — (M13.17b; criterion 5
of the SPEC's first part). Everything else of the script is tested on fakes, in
``tests/scripts/test_misura_m13_11.py``.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

from tests import machines
from tests.script_fences import Named
from tests.scripts.test_misura_m13_11 import script

pytestmark = machines.needs(
    machines.WINDOWS, why="winreg, PowerShell and Win32_Process are Windows's"
)

STATUSES = frozenset(
    {
        "Valid",
        "UnknownError",
        "NotSigned",
        "HashMismatch",
        "NotTrusted",
        "NotSupportedFileFormat",
        "Incompatible",
    }
)
"""The values of ``SignatureStatus`` that ``Get-AuthenticodeSignature`` gives."""
READING = (
    "Windows read through powershell.exe as ELA starts its own: a constant script, reading only"
)


def powershell(script_text: str) -> tuple[str, ...]:
    """The launch of ``powershell.exe`` the script does to run ``script_text``, exactly."""
    measure = script()
    return (
        measure.POWERSHELL,
        "-NoProfile",
        "-NonInteractive",
        "-EncodedCommand",
        measure.encoded(script_text),
    )


def test_the_registry_answers_the_smart_app_control_or_says_why_not() -> None:
    found = script().Pc().registry_sac()
    assert isinstance(found, int | script().Failure), found


def test_get_mpcomputerstatus_is_read_or_says_why_not(script_may: Named) -> None:
    script_may.launch(*powershell(script().DEFENDER_SAC), why=READING)
    found = script().Pc().defender_sac()
    assert isinstance(found, str | script().Failure), found


def test_win32_process_knows_this_process_and_its_parent(script_may: Named) -> None:
    script_may.launch(*powershell(script().PROCESSES), why=READING)
    table = script().Pc().processes()

    assert not isinstance(table, script().Failure), table
    parent, name = table[os.getpid()]
    assert parent == os.getppid()
    assert name.lower().endswith(".exe")


def test_the_signature_the_size_and_the_digest_of_a_file_are_read(script_may: Named) -> None:
    script_may.launch(*powershell(script().FILE_FACTS), why=READING)
    path = Path(sys.executable)
    facts = script().Pc().file_facts([path])

    assert not isinstance(facts, script().Failure), facts
    read = facts[path]
    assert read.status in STATUSES, read
    assert read.size == path.stat().st_size
    assert read.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_dacl_of_a_folder_made_with_mkdir_0700_is_read_as_protected(
    script_may: Named, tmp_path: Path
) -> None:
    script_may.launch(*powershell(script().READ_SDDL), why=READING)
    folder = tmp_path / "a4-modo"
    folder.mkdir(mode=0o700)
    descriptor = script().Pc().sddl(folder)

    assert not isinstance(descriptor, script().Failure), descriptor
    assert script().protected(descriptor), script().dacl_shown(descriptor)


def test_the_check_of_the_folder_of_the_profile_answers_on_windows(tmp_path: Path) -> None:
    folder = tmp_path / "a4-modo"
    folder.mkdir(mode=0o700)
    mode, said = script().Pc().folder_check(folder)
    assert len(mode) == 4 and said


def test_the_adapters_of_today_answer_what_difference_7_reads(tmp_path: Path) -> None:
    answers = script().Pc().adapters_installed(tmp_path / "ms-playwright")
    assert answers == script().EXPECTED_ADAPTERS
    assert "PLAYWRIGHT_BROWSERS_PATH" not in os.environ


def test_the_line_of_the_shape_of_a_key_goes_through_each_powershell_and_is_read(
    script_may: Named, tmp_path: Path
) -> None:
    measure = script()
    shells = {name: where for name, where in measure.Pc().shells().items() if where is not None}
    assert "powershell.exe" in shells, shells
    first, second = tmp_path / "primo.py", tmp_path / "secondo.py"
    first.write_text(measure.FIRST, encoding="utf-8")
    second.write_text(measure.SECOND, encoding="utf-8")
    launches = {}
    for name, where in shells.items():
        out = tmp_path / f"tubo-{Path(name).stem}.bin"
        argv = measure.pipe_argv(str(where), sys.executable, str(first), str(second), str(out))
        script_may.launch(
            *argv, why="B3: two programs of the test's in place of bw and ELA, never a real key"
        )
        launches[name] = (argv, out)

    for name, (argv, out) in launches.items():
        ran = measure.Pc().run(argv, env=measure.without_module_path(os.environ), timeout=120.0)
        piped = measure.read_pipe(out.read_bytes() if out.exists() else None)
        assert ran.code == 0, (name, ran.err)
        assert piped.intact, (name, piped)
