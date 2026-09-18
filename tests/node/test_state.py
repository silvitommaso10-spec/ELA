"""What a node keeps on disk, and how (M12.3 dec. B; criteria 3, 4, 8; ADR 0037 §7; M12.4 dec. B).

Three properties, and each one is a thing that has gone wrong somewhere before: a secret that is
world-readable for an instant, a secret that is printed, and an identity silently replaced.

**Two ways of protecting it, one writer** (M12.4 dec. B). ``BITS`` narrows the file with
``fchmod`` before its first byte; ``ACL`` leaves the protection to the directory that already
holds it, which on Windows is the protected ACL ``mkdir(0o700)`` applies. The properties that are
not about permissions hold in both modes, so those tests run in both — and ``BITS`` is declared
where it cannot run, because Windows has neither ``os.fchmod`` (before 3.13) nor ``O_NOFOLLOW``.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from ela.composition.node import PermissionMode
from ela.node import NodeIdentity, read_identity, write_identity
from ela.node.state import DIRECTORY_MODE, STATE_FILE, STATE_MODE

SECRET = "tanto-lungo-quanto-un-token-urlsafe-di-32-byte"  # pragma: allowlist secret
IDENTITY = NodeIdentity(device_id="9f0d2a6e-0000-4000-8000-000000000001", secret=SECRET)

POSIX_WRITER = pytest.mark.skipif(
    os.name == "nt", reason="the BITS writer is POSIX's: Windows has no fchmod and no O_NOFOLLOW"
)


@pytest.fixture(
    params=[pytest.param(PermissionMode.BITS, marks=POSIX_WRITER), PermissionMode.ACL],
    ids=lambda mode: mode.name,
)
def mode(request: pytest.FixtureRequest) -> PermissionMode:
    """Both writers, for every property that is not about the permissions themselves."""
    chosen: PermissionMode = request.param
    return chosen


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits: Windows has no 0o600")
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
        write_identity(tmp_path / "state", IDENTITY, PermissionMode.BITS)
    finally:
        os.umask(was)

    written = tmp_path / "state" / STATE_FILE
    assert stat.S_IMODE(written.stat().st_mode) == STATE_MODE
    assert stat.S_IMODE((tmp_path / "state").stat().st_mode) == DIRECTORY_MODE


def test_the_acl_writer_needs_no_fchmod_and_the_bits_writer_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M12.4 criterion 6: ``os.fchmod`` taken away, which is what Windows on 3.12 is.

    **The one monkeypatch of dec. H, and why here.** The absence of a function of the standard
    library is what Windows *is*, and it cannot be declared by parameter without handing the writer
    a fake ``os`` module — which would prove the fake. ``raising=False`` because on Windows there is
    nothing to take away.

    ``ACL`` writes, and keeps ``O_EXCL``: a second enrollment over the file refuses. ``BITS``, in
    the same process, stops on the missing function — which is the ``AttributeError`` P1 saw on the
    PC at ``state.py:99``, 23 times (M12.4, §«Gli esiti»).
    """
    monkeypatch.delattr(os, "fchmod", raising=False)

    write_identity(tmp_path / "acl", IDENTITY, PermissionMode.ACL)

    assert read_identity(tmp_path / "acl") == IDENTITY
    with pytest.raises(FileExistsError):
        write_identity(
            tmp_path / "acl", NodeIdentity(device_id="x", secret="y"), PermissionMode.ACL
        )
    with pytest.raises(AttributeError):
        write_identity(tmp_path / "bits", IDENTITY, PermissionMode.BITS)


def test_a_second_enrollment_refuses_rather_than_replacing_an_identity(
    tmp_path: Path, mode: PermissionMode
) -> None:
    """Criterion 3, the other half. ``O_EXCL`` is the whole point and not a precaution.

    Overwriting would throw away an identity the Core still has a row for — leaving a node nobody
    can revoke, because nobody can name it.
    """
    write_identity(tmp_path, IDENTITY, mode)

    with pytest.raises(FileExistsError):
        write_identity(tmp_path, NodeIdentity(device_id="another", secret="another"), mode)

    assert read_identity(tmp_path) == IDENTITY


def test_what_was_written_is_what_comes_back(tmp_path: Path, mode: PermissionMode) -> None:
    write_identity(tmp_path, IDENTITY, mode)

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


def test_the_file_holds_two_fields_and_the_revision_is_not_one(
    tmp_path: Path, mode: PermissionMode
) -> None:
    """Dec. B: what the Core minted once and never changes. The revision is a fact of the Core's
    row, and a copy of it here would be a cache nobody resynchronises (dec. L)."""
    write_identity(tmp_path, IDENTITY, mode)

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

    Written with ``ACL``, which runs on every system: what is under test is the file's name and
    place, and the two writers give it the same ones.
    """
    repo = Path(__file__).resolve().parents[2]
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text(
        (repo / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8"
    )
    write_identity(tmp_path / "inside", IDENTITY, PermissionMode.ACL)

    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    assert f"inside/{STATE_FILE}" in listed
