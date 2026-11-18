"""A root that holds a place of ELA's is admitted at the start-up, and **every use refuses the
place** (M13.17, ADR 0074; decision 8 (iv) of its starting block).

What the tests that used to say «a root that holds a place of ELA's is refused» say now, in both
directions: the start-up admits the root, and a read and a write of ``fs.*`` — built with the list
the composition derives — refuse the place, ``path.ela_s_own``, naming it, before any question.
Nothing is read and nothing is written.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ela.testing.fakes import FakeClock, FakeIdGenerator
from ela.tools import FsReadTool, FsWriteTool
from ela.tools.fs import ELA_S_OWN

PROBE = "probe.txt"
"""A file put inside a place that is a folder, so that a read has a file to be refused."""


async def every_use_refuses(
    root: Path, protected: Mapping[str, Path], place: Path, what: str
) -> None:
    """A read and a write of the place — the place itself when it is a file, a file inside it when
    it is a folder — are refused with ``path.ela_s_own``, naming ``what``; nothing changes on the
    disk."""
    root, place = root.resolve(), place.absolute()
    clock, ids = FakeClock(), FakeIdGenerator()
    reader = FsReadTool(root, clock, ids, protected=protected)
    writer = FsWriteTool(root, clock, ids, protected=protected)
    if place.is_file():
        read, write = place, place
    else:
        place.mkdir(parents=True, exist_ok=True)
        (place / PROBE).write_text("of ELA's\n", encoding="utf-8")
        read, write = place / PROBE, place / "nuovo.md"
    before = {path: path.read_bytes() for path in (read, write) if path.is_file()}

    looked = await reader.prospect({"path": _under(root, read), "purpose": "la prova"})
    wrote = await writer.prospect(
        {
            "path": _under(root, write),
            "body": "x",
            "overwrite": write.is_file(),
            "purpose": "la prova",
        }
    )

    for seen in (looked, wrote):
        assert seen.refusal is not None, f"{place} was not refused"
        assert seen.refusal.code == ELA_S_OWN, seen.refusal
        assert what in seen.refusal.message, seen.refusal.message
    assert {path: path.read_bytes() for path in (read, write) if path.is_file()} == before


def _under(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root).as_posix()
