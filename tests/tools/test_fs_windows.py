"""The bytes of ``fs.*`` on a real NTFS, and the root of a node that is a junction (M13.3).

Found by the rereading of the implementation, before the manual test: on Windows ``os.open``
without ``O_BINARY`` opens a file in **text mode**, and a read turns ``\\r\\n`` into ``\\n`` and
stops at the first ``0x1A``. The tool and its verifier would share the translation, and the node's
verifier would agree with the tool on bytes the disk does not hold — the false positive of ADR 0038
§14, on the machine M13.3 sends ``fs.*`` to. Red on the Windows job before the repair (run
36162668652): the read, the verifier and the junction root; the write was already right, and its
test stays as the guard of the flag it carries. Declared with its
``skipif`` (ADR 0031 §6) and named on the Windows job's line (form J): a Mac cannot build it.

It imports nothing of ``tests/tools/test_verifiers.py``: that module reads ``os.geteuid`` while it
is collected, and Windows has none — the first run of this file died there, before any test ran.
"""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path

import pytest

from ela.composition.settings import refuse_the_root
from ela.domain import ExecutionStatus
from ela.testing.fakes import FakeClock, FakeIdGenerator
from ela.tools import FS_CONTENT_MATCHES, FS_WRITE, FsReadTool, FsWriteTool, FsWriteVerifier
from tests.domain.examples import EXECUTION_RESULT
from tests.tools.support import allowed

pytestmark = pytest.mark.skipif(platform.system() != "Windows", reason="NTFS is Windows's")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "files" / "ELA").mkdir(parents=True)
    return tmp_path / "files"


async def test_a_write_puts_on_the_disk_exactly_the_bytes_of_the_body(root: Path) -> None:
    tool = FsWriteTool(root, FakeClock(), FakeIdGenerator())

    result = await tool.execute(
        allowed(FS_WRITE), {"path": "ELA/a.md", "body": "a\nb\n", "overwrite": False}
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert (root / "ELA" / "a.md").read_bytes() == b"a\nb\n"


async def test_a_read_returns_exactly_the_bytes_on_the_disk(root: Path) -> None:
    (root / "ELA" / "b.md").write_bytes(b"a\r\nb\x1ac")
    tool = FsReadTool(root, FakeClock(), FakeIdGenerator())

    result = await tool.execute(allowed(tool.capability_id), {"path": "ELA/b.md"})

    assert result.output["content"] == "a\r\nb\x1ac"


async def test_the_verifier_sees_a_carriage_return_the_body_does_not_have(root: Path) -> None:
    (root / "ELA" / "c.md").write_bytes(b"a\r\nb\r\n")

    failures = await FsWriteVerifier(root).verify(
        (FS_CONTENT_MATCHES,),
        {"path": "ELA/c.md", "body": "a\nb\n", "overwrite": True},
        EXECUTION_RESULT.model_copy(
            update={
                "capability_id": FS_WRITE,
                "status": ExecutionStatus.SUCCEEDED,
                "error": None,
                "output": {},
            }
        ),
    )

    assert [failure.code for failure in failures] == ["fs.content_mismatch"]


def test_a_root_that_is_a_junction_stops_the_node_like_a_symbolic_link(tmp_path: Path) -> None:
    (tmp_path / "real").mkdir()
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(tmp_path / "alias"), str(tmp_path / "real")],
        check=True,
        capture_output=True,
    )

    with pytest.raises(ValueError, match="link"):
        refuse_the_root(tmp_path / "alias", {})
