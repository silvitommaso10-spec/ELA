"""A node verifies what it did on its own machine, and says so in codes (M13.3, form B; ADR 0048).

The order of a capability whose verifier reads the machine carries the plan's success conditions;
the node looks the verifier up **before** its tool acts, runs it after, on a result that succeeded,
and puts the verdict in the envelope — conditions, codes, the name of an exception, never a
message. And the tool is the Core's own: it compares the plan's ``overwrite`` with the disk before
writing, so a yes to a question the disk contradicts is refused here, with nothing written.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ela.domain import CapabilityId, ExecutionStatus
from ela.node import envelope_of
from ela.node.runner import verdict_of
from ela.testing.fakes import FakeClock, FakeIdGenerator
from ela.tools import (
    FS_CONTENT_MATCHES,
    FS_FILE_EXISTS,
    FS_WRITE,
    OVERWRITE_MISMATCH,
    PATH_MISSING,
    FsReadVerifier,
    VerifierRegistry,
)
from tests.node.support import order, world
from tests.tools.support import allowed

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
SOON = NOW + timedelta(seconds=120)
CONDITIONS = [FS_FILE_EXISTS, FS_CONTENT_MATCHES]


def writing(
    body: str = "verbale\n", *, overwrite: bool = False, conditions: list[str] | None = CONDITIONS
) -> dict[str, Any]:
    """The order of an ``fs.write`` that the node verifies: seven keys, the seventh the plan's."""
    given = order(
        capability=str(FS_WRITE),
        expires_at=SOON,
        decision=allowed(FS_WRITE).model_dump(mode="json"),
        arguments={"path": "ELA/prova.md", "body": body, "overwrite": overwrite},
    )
    if conditions is not None:
        given["success_conditions"] = conditions
    return given


def rooted(tmp_path: Path) -> tuple[Any, Path]:
    root = tmp_path / "files"
    root.mkdir()
    return world(tmp_path / "state", fs_root=root), root


async def test_a_node_writes_on_its_root_verifies_there_and_sends_the_verdict(
    tmp_path: Path,
) -> None:
    built, root = rooted(tmp_path)

    envelope = await envelope_of(built, writing())

    assert envelope["status"] == "SUCCEEDED"
    assert (root / "ELA" / "prova.md").read_text(encoding="utf-8") == "verbale\n"
    assert envelope["verdict"] == {"conditions": CONDITIONS, "failed": [], "exception": None}


async def test_the_disk_that_contradicts_the_plan_is_refused_before_anything_is_written(
    tmp_path: Path,
) -> None:
    """Criterion 7, the first way: the plan declared a new file and one is there. The node's tool
    refuses with the code that names the fact, the file keeps its bytes, and no verdict is asked."""
    built, root = rooted(tmp_path)
    (root / "ELA").mkdir()
    (root / "ELA" / "prova.md").write_text("di prima\n", encoding="utf-8")

    envelope = await envelope_of(built, writing(overwrite=False))

    assert envelope["status"] == "FAILED"
    assert envelope["error"]["code"] == OVERWRITE_MISMATCH
    assert "was declared as a new file and something is there now" in envelope["error"]["message"]
    assert (root / "ELA" / "prova.md").read_text(encoding="utf-8") == "di prima\n"
    assert "verdict" not in envelope


async def test_and_the_other_way_an_overwrite_of_nothing_writes_nothing(tmp_path: Path) -> None:
    built, root = rooted(tmp_path)

    envelope = await envelope_of(built, writing(overwrite=True))

    assert envelope["error"]["code"] == OVERWRITE_MISMATCH
    assert not (root / "ELA" / "prova.md").exists()


async def test_an_order_it_cannot_verify_is_not_acted_on(tmp_path: Path) -> None:
    """A node with the tool and without the verifier cannot be built (``carried``): the world is
    taken apart here to make one, and the order's conditions find no verifier **before** the tool
    acts — nothing is written, and only the type's name travels."""
    built, root = rooted(tmp_path)
    blind = replace(built, verifiers=VerifierRegistry(()))

    envelope = await envelope_of(blind, writing())

    assert envelope == {"form": "exception", "exception": "VerifierNotFound"}
    assert not (root / "ELA").exists()


async def test_the_verdict_names_conditions_and_codes_and_never_a_message(tmp_path: Path) -> None:
    """A failure's message names the path, which is the user's content (§57): only the condition
    and the code travel."""
    verifier = FsReadVerifier(tmp_path)
    missing = allowed(CapabilityId("fs.read"))
    result = _read_result(missing)

    verdict = await verdict_of(verifier, (FS_FILE_EXISTS,), {"path": "segreto.md"}, result)

    assert verdict == {
        "conditions": [FS_FILE_EXISTS],
        "failed": [[FS_FILE_EXISTS, PATH_MISSING]],
        "exception": None,
    }
    assert "segreto" not in str(verdict)


async def test_a_verifier_that_raises_travels_as_the_name_of_its_type(tmp_path: Path) -> None:
    class Broken(FsReadVerifier):
        async def verify(self, *args: Any, **kwargs: Any) -> Any:
            raise OSError("segreto.md is on fire")

    verdict = await verdict_of(
        Broken(tmp_path), (FS_FILE_EXISTS,), {"path": "x"}, _read_result(allowed(FS_WRITE))
    )

    assert verdict == {"conditions": [FS_FILE_EXISTS], "failed": [], "exception": "OSError"}


def _read_result(decision: Any) -> Any:
    from ela.domain import ExecutionId, ExecutionResult

    return ExecutionResult(
        id=ExecutionId(FakeIdGenerator().new_uuid()),
        created_at=FakeClock().now(),
        capability_id=CapabilityId("fs.read"),
        status=ExecutionStatus.SUCCEEDED,
        tool_name="fs-read",
        decision_id=decision.id,
        output={"path": "segreto.md", "bytes": 0, "content": ""},
    )
