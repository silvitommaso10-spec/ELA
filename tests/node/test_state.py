"""What a node keeps on disk, and how (M12.3 dec. B; criteria 3, 4, 8; ADR 0037 §7).

Three properties, and each one is a thing that has gone wrong somewhere before: a secret that is
world-readable for an instant, a secret that is printed, and an identity silently replaced.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from ela.node import NodeIdentity, read_identity, write_identity
from ela.node.state import DIRECTORY_MODE, STATE_FILE, STATE_MODE

SECRET = "tanto-lungo-quanto-un-token-urlsafe-di-32-byte"  # pragma: allowlist secret
IDENTITY = NodeIdentity(device_id="9f0d2a6e-0000-4000-8000-000000000001", secret=SECRET)


def test_the_secret_is_0o600_from_the_first_byte_even_under_a_permissive_umask(
    tmp_path: Path,
) -> None:
    """Criterion 3. The mode is exact *before* a byte is written, which is what ``fchmod`` on the
    descriptor buys and a ``chmod`` afterwards does not.

    The ``umask`` is the test: a creation mode can only be narrowed by it, so a file written and
    then narrowed carries the process umask for an instant — the bug ADR 0037 §7 records ``ela
    init`` having had. With ``0o000`` a missing ``fchmod`` shows up as ``0o666``.
    """
    was = os.umask(0o000)
    try:
        write_identity(tmp_path / "state", IDENTITY)
    finally:
        os.umask(was)

    written = tmp_path / "state" / STATE_FILE
    assert stat.S_IMODE(written.stat().st_mode) == STATE_MODE
    assert stat.S_IMODE((tmp_path / "state").stat().st_mode) == DIRECTORY_MODE


def test_a_second_enrollment_refuses_rather_than_replacing_an_identity(tmp_path: Path) -> None:
    """Criterion 3, the other half. ``O_EXCL`` is the whole point and not a precaution.

    Overwriting would throw away an identity the Core still has a row for — leaving a node nobody
    can revoke, because nobody can name it.
    """
    write_identity(tmp_path, IDENTITY)

    with pytest.raises(FileExistsError):
        write_identity(tmp_path, NodeIdentity(device_id="another", secret="another"))

    assert read_identity(tmp_path) == IDENTITY


def test_what_was_written_is_what_comes_back(tmp_path: Path) -> None:
    write_identity(tmp_path, IDENTITY)

    read = read_identity(tmp_path)

    assert read is not None
    assert read.device_id == IDENTITY.device_id
    assert read.secret == SECRET
    assert read.bearer == f"{IDENTITY.device_id}.{SECRET}"


def test_a_machine_that_never_enrolled_reads_nothing_rather_than_failing(tmp_path: Path) -> None:
    """``None`` and not an exception: a first run is not an error, and it is the command above
    that knows whether a ``--join`` was offered to fix it."""
    assert read_identity(tmp_path) is None


def test_the_secret_is_not_in_the_repr_because_tracebacks_are_printed() -> None:
    """Criterion 4, at the one place a secret escapes without anybody deciding to print it."""
    shown = repr(IDENTITY)

    assert SECRET not in shown
    assert IDENTITY.device_id in shown
    assert SECRET not in f"{IDENTITY}"


def test_the_file_holds_two_fields_and_the_revision_is_not_one(tmp_path: Path) -> None:
    """Dec. B: what the Core minted once and never changes. The revision is a fact of the Core's
    row, and a copy of it here would be a cache nobody resynchronises (dec. L)."""
    write_identity(tmp_path, IDENTITY)

    kept = json.loads((tmp_path / STATE_FILE).read_text(encoding="utf-8"))

    assert set(kept) == {"device_id", "secret"}


def test_the_state_file_is_outside_the_tree_and_git_would_take_it_if_it_were_not(
    tmp_path: Path,
) -> None:
    """Criterion 8, on the shape of ``tests/security/test_no_secrets.py``.

    The defence is **where the file is**, not ``.gitignore``: the only secret-ish lines there are
    ``.env``, ``.env.*`` and ``!.env.example``, so a file called something else *inside* the tree
    would be taken. This writes one inside a tree carrying the repository's own ``.gitignore`` and
    shows that git would add it — which is why the real one lives beside the database instead.
    """
    repo = Path(__file__).resolve().parents[2]
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text(
        (repo / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8"
    )
    write_identity(tmp_path / "inside", IDENTITY)

    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    assert f"inside/{STATE_FILE}" in listed
