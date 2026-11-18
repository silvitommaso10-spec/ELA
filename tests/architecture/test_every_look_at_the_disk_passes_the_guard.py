"""Every look at, read of and write to a file under ``ELA_FS_ROOT`` passes **one guard**, and every
tool and verifier that looks there says so (M13.17, ADR 0074; decision 12 of its starting block).

The guard (:mod:`ela.tools.disk`) is what gives a wait on the disk its limit, and keeps the Core
answering while a disk does not. **A look that went around it would hold the whole Core** for as
long as the disk keeps silent — what a window of macOS asking for a permission, or a file the
system fetches from elsewhere, can make it.

**A closed world, derived and not listed.** The tools and verifiers are those of the registries
the composition builds — the Core's and a node's —, and the ones under the root are those that
declare :attr:`~ela.tools.base.Tool.under_the_root`; each of them has a case here, or the rule
speaks. The members are derived from the ports — :class:`~ela.ports.ToolPort` and
:class:`~ela.ports.VerifierPort` —: each one the class overrides is called, or exempt here with its
reason. **What is asserted, for every call**: the guard was used, and **no call of the operating
system on a path under the root was made outside the guard's thread** — a watch on ``os`` that
counts the calls of the loop's thread, leaving out what the fakes of the test do on their own (the
fake browser writes the file a site would send).
"""

from __future__ import annotations

import contextlib
import inspect
import os
import sys
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from ela.domain import (
    AuthorizationId,
    CapabilityId,
    DecisionId,
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    PermissionDecision,
    PermissionOutcome,
    RiskLevel,
)
from ela.ports import Field, ToolPort, VerifierPort
from ela.testing.fakes import (
    FakeAccountBrowser,
    FakeAuditLog,
    FakeBrowser,
    FakeClock,
    FakeIdGenerator,
    FakeListening,
    FakeModelRouter,
    FakePage,
    FakeProbe,
    FakeProviderRegistry,
    FakeScreenCapture,
    FakeSpeech,
    FakeStop,
    FakeTaskPages,
    FakeTextRecognition,
)
from ela.tools import (
    CaptureSettings,
    CaptureStore,
    node_tools,
    node_verifiers,
    production_tools,
    production_verifiers,
)
from ela.tools.base import PLACE_UNSEEN, Tool, any_moment
from ela.tools.browser import Browsing
from ela.tools.disk import Disk
from tests.permissions.catalogue_calls import CALLS
from tests.tools.browsers import SECONDS, a_door
from tests.tools.guided import GATEWAY, a_room, a_session
from tests.tools.terminals import a_launcher, a_terminal

NOW = datetime(2026, 11, 18, 10, 0, tzinfo=UTC)
SITE = "httpbin.org"
PROGRAM = "bin/sh"
WATCHED = (
    "stat",
    "lstat",
    "open",
    "mkdir",
    "replace",
    "link",
    "unlink",
    "chmod",
    "listdir",
    "scandir",
    "readlink",
    "rmdir",
)
"""The calls of ``os`` that look at, read or write a path: ``pathlib`` reaches the disk through
them, and so does ``os.path``."""

EXEMPT: Mapping[str, str] = {
    "asserted": "says what the plan asserts about a disk ELA has not looked at (ADR 0048 §8)",
    "worst_case": "says what a call spends: no disk",
}
"""The members of the ports a tool may define without the disk, each with its reason."""


class Counting(Disk):
    """The guard, counting the works handed to it."""

    def __init__(self) -> None:
        super().__init__(limit=10.0)
        self.works = 0

    async def run[T](self, work: Callable[[Any], T], what: str) -> T:
        self.works += 1
        return await super().run(work, what)


def decision(capability_id: CapabilityId) -> PermissionDecision:
    """A decision on a policy: the road that reads once and spends no question."""
    return PermissionDecision(
        id=DecisionId(FakeIdGenerator().new_uuid()),
        created_at=NOW,
        capability_id=capability_id,
        risk=RiskLevel.HIGH,
        outcome=PermissionOutcome.ALLOWED,
        reason="allowed for this test",
        expires_at=NOW.replace(hour=11),
        authorization_id=AuthorizationId(FakeIdGenerator().new_uuid()),
    )


def registries(tmp_path: Path, disk: Disk) -> tuple[list[ToolPort], list[VerifierPort]]:
    """The Core's registries, as the composition builds them, with a site declared and the files
    of the calls there; and a node's, on the same root."""
    root = tmp_path / "files"
    (root / "ELA").mkdir(parents=True)
    for name in ("a.md", "prova.txt"):
        (root / "ELA" / name).write_text("una riga")
    browsing = Browsing(sites=(SITE,))
    page = FakePage(download=b"what the site sent", fields={"#file": Field("file", "")})
    captures = CaptureStore(CaptureSettings(capture_dir=tmp_path / "captures"))
    core = production_tools(
        root=tmp_path,
        clock=FakeClock(NOW),
        ids=FakeIdGenerator(),
        router=FakeModelRouter(),
        providers=FakeProviderRegistry(),
        captures=captures,
        screen=FakeScreenCapture(),
        probe=FakeProbe(),
        recognition=FakeTextRecognition(),
        languages=("it-IT",),
        listening=FakeListening(),
        listen_enabled=False,
        speech=FakeSpeech(),
        voice="Alice",
        voice_enabled=False,
        speech_online=FakeSpeech(),
        voice_id=None,
        model="m",
        fs_root=root,
        terminal=a_terminal(root, PROGRAM),
        launcher=a_launcher(),
        browsing=browsing,
        browser=FakeBrowser(page),
        gestures=a_room(),
        sessions=a_session(),
        gateway=GATEWAY,
        accounts=FakeAccountBrowser(page),
        vault=a_door(),
        not_now=any_moment,
        pages=FakeTaskPages(),
        protected={},
        disk=disk,
    )
    verifiers = production_verifiers(
        root=tmp_path,
        router=FakeModelRouter(),
        captures=captures,
        fs_root=root,
        programs=a_terminal(root).programs,
        browser=FakeBrowser(page),
        browser_seconds=SECONDS,
        gestures=a_room(),
        sessions=a_session(),
        audit=FakeAuditLog(),
        accounts=FakeAccountBrowser(page),
        disk=disk,
    )
    node = node_tools(
        clock=FakeClock(NOW),
        ids=FakeIdGenerator(),
        router=FakeModelRouter(),
        providers=FakeProviderRegistry(),
        speech=FakeSpeech(),
        voice="Alice",
        voice_enabled=False,
        speech_online=FakeSpeech(),
        voice_id=None,
        model="m",
        fs_root=root,
        protected={},
        disk=disk,
    )
    return (
        [*core.tools(), *node.tools()],
        [*verifiers.verifiers(), *node_verifiers(root, disk).verifiers()],
    )


def under_the_root(found: list[Any]) -> list[Any]:
    return [one for one in found if one.under_the_root]


def members(port: type) -> list[str]:
    """The asynchronous members of ``port``, as the port declares them: every one a tool can look
    at the disk in. Derived, never listed."""
    return sorted(
        name
        for name, member in inspect.getmembers(port)
        if not name.startswith("_") and inspect.iscoroutinefunction(member)
    )


@contextmanager
def watched(root: Path) -> Iterator[list[str]]:
    """Every call of ``os`` on a path under ``root`` made outside the guard's thread, and not by a
    fake of the test: what the rule wants empty."""
    outside: list[str] = []
    real = {name: getattr(os, name) for name in WATCHED if hasattr(os, name)}
    under = str(root.resolve())

    def wrapped(name: str) -> Callable[..., Any]:
        def call(*args: Any, **kwargs: Any) -> Any:
            path = args[0] if args else None
            if (
                isinstance(path, str | os.PathLike)
                and os.fspath(path).startswith(under)
                and not threading.current_thread().name.startswith("ela-disk")
                and not _from_a_fake()
            ):
                outside.append(f"os.{name}({os.fspath(path)!r})")
            return real[name](*args, **kwargs)

        return call

    for name in real:
        setattr(os, name, wrapped(name))
    try:
        yield outside
    finally:
        for name, function in real.items():
            setattr(os, name, function)


def _from_a_fake() -> bool:
    frame = sys._getframe(2)  # noqa: SLF001 — the caller of the watched call
    while frame is not None:
        name = frame.f_code.co_filename
        if f"{os.sep}ela{os.sep}testing{os.sep}" in name:
            return True
        frame = frame.f_back
    return False


def a_result(capability: CapabilityId, output: Mapping[str, Any]) -> ExecutionResult:
    return ExecutionResult(
        id=ExecutionId(FakeIdGenerator().new_uuid()),
        created_at=NOW,
        capability_id=capability,
        status=ExecutionStatus.SUCCEEDED,
        output=dict(output),
    )


OUTPUTS: Mapping[str, Mapping[str, Any]] = {
    "fs.read": {"path": "ELA/a.md", "bytes": 8, "content": "una riga"},
    "fs.write": {"path": "ELA/a.md", "bytes": 8, "overwrote": False},
    "browser.download": {"gestures": 1, "file": "ELA/prova.png", "size": 3, "digest": "0" * 64},
    "browser.download_as_you": {"gestures": 1, "file": "ELA/prova.png", "size": 3, "digest": "0"},
}
"""What a verifier is handed with the call: an output of the tool's shape."""


def test_every_tool_and_verifier_under_the_root_has_a_case_and_the_composition_s_guard(
    tmp_path: Path,
) -> None:
    disk = Counting()
    tools, verifiers = registries(tmp_path, disk)
    found = under_the_root(tools) + under_the_root(verifiers)

    assert {str(one.capability_id) for one in under_the_root(tools)} <= set(CALLS)
    assert {str(one.capability_id) for one in under_the_root(verifiers)} <= set(OUTPUTS)
    assert [one.name for one in found if getattr(one, "disk", None) is not disk] == []


async def test_every_member_of_a_tool_under_the_root_looks_at_the_disk_through_the_guard(
    tmp_path: Path,
) -> None:
    missed: list[str] = []
    found, _ = registries(tmp_path / "derived", Counting())
    worlds = 0
    for place, name in _where(found):
        for member in [one for one in members(ToolPort) if one not in EXEMPT]:
            # A world of its own for every call: a fake left busy by one is no world for the next.
            worlds += 1
            disk = Counting()
            tools, _ = registries(tmp_path / str(worlds), disk)
            root = tmp_path / str(worlds) / "files"
            (tool,) = [one for one in tools[place : place + 1] if one.name == name]
            arguments = dict(CALLS[str(tool.capability_id)])
            if str(tool.capability_id) == "terminal.run":
                arguments["program"] = PROGRAM
            if member == "prospect_place" and type(tool).prospect_place is Tool.prospect_place:
                # The default refuses a place without looking at one (ADR 0068 §6): its answer.
                refused = (await tool.prospect_place("ELA")).refusal
                assert refused is not None and refused.code == PLACE_UNSEEN, tool.name
                continue
            # A fake may refuse after the disk: what is asserted is the disk.
            with watched(root) as outside, contextlib.suppress(Exception):
                await _called(tool, member, arguments)
            if outside or disk.works == 0:
                missed.append(f"{tool.name}.{member}: {outside or 'the guard was not used'}")

    assert missed == []


def _where(tools: list[ToolPort]) -> list[tuple[int, str]]:
    """Where each tool under the root stands in the registries, and its name."""
    return [(n, one.name) for n, one in enumerate(tools) if one.under_the_root]


async def _called(tool: ToolPort, member: str, arguments: Mapping[str, Any]) -> object:
    if member == "prospect_place":
        values = (SITE,) if "browser" in str(tool.capability_id) else ()
        return await tool.prospect_place("ELA", values)
    if member in {"prospect", "prospect_covered"}:
        return await getattr(tool, member)(arguments)
    if member == "execute":
        return await tool.execute(decision(tool.capability_id), arguments, FakeStop())
    raise AssertionError(f"{member} has no call here and no exemption: add one, with its reason")


def test_the_members_are_the_port_s_and_the_exemptions_are_members() -> None:
    """A member added to the port makes the rule speak; an exemption of a member the port has no
    more is taken away."""
    assert {"execute", "prospect", "prospect_covered", "prospect_place"} <= set(members(ToolPort))
    assert set(EXEMPT) <= set(members(ToolPort))
    assert members(VerifierPort) == ["verify"]


async def test_every_verifier_under_the_root_reads_the_disk_through_the_guard(
    tmp_path: Path,
) -> None:
    disk = Counting()
    _, verifiers = registries(tmp_path, disk)
    root = tmp_path / "files"
    (root / "ELA" / "prova.png").write_bytes(b"abc")
    missed: list[str] = []
    for verifier in under_the_root(verifiers):
        capability = str(verifier.capability_id)
        before = disk.works
        with watched(root) as outside:
            await verifier.verify(
                tuple(verifier.conditions),
                CALLS[capability],
                a_result(verifier.capability_id, OUTPUTS[capability]),
            )
        if outside or disk.works == before:
            missed.append(f"{verifier.name}: {outside or 'the guard was not used'}")

    assert missed == []


def test_the_watch_sees_a_look_made_outside_the_guard(tmp_path: Path) -> None:
    """The negative case: a look on the loop's thread is counted, one in the guard's is not."""
    root = tmp_path / "files"
    (root / "ELA").mkdir(parents=True)
    with watched(root) as outside:
        (root / "ELA").is_dir()

    assert len(outside) == 1 and outside[0].startswith("os.stat(")


@pytest.mark.parametrize("flag", [True, False])
def test_a_class_that_does_not_say_is_refused_and_one_that_says_is_counted(flag: bool) -> None:
    """The closed world is derived from the declaration: a tool under the root is one that says
    so, and the registry refuses one that says nothing (:class:`~ela.tools.SilentRootError`)."""
    from ela.testing.fakes import FakeTool
    from ela.tools import SilentRootError, ToolRegistry

    tool = FakeTool(CapabilityId("core.echo"), FakeClock(NOW), FakeIdGenerator())
    tool.under_the_root = flag
    assert under_the_root([tool]) == ([tool] if flag else [])
    del tool.under_the_root
    with pytest.raises(SilentRootError):
        ToolRegistry((tool,))
