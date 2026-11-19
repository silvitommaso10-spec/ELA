"""**The places of ELA's are refused at every use** — the first line and the only one since the root
may hold them (M13.17, ADR 0074; decision 8 (ii) and (iii) of its starting block, answer 38 of the
review of its SPEC).

**A closed world, derived.** The tools and verifiers are those of the registries the composition
builds — the Core's and a node's — that declare ``under_the_root``; the members are those of the
ports. Each one, on **a root of proof that holds the places** — a database, a ``.env``, ELA's
home, its source tree, its Python, under the folder the scope opens —, refuses a target that
touches a place:

- a target that **is** a place, or **lies inside** one: ``path.ela_s_own``, for every member;
- a target that **holds** a place: ``path.ela_s_own`` for whoever looks at a folder — the birth of
  a policy (``prospect_place``) —; for whoever looks at a file it is a folder, and the
  classification, which comes first, answers ``path.is_directory``; **for the folder a command
  starts from it is no refusal** (answer 38: the folder is not a boundary);

under a yes and under a policy, before the question and before the spend — and **nothing on the
disk changes**. The members that look at no disk are exempt with their reason.
"""

from __future__ import annotations

import contextlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from ela.domain import ApprovalId, CapabilityId
from ela.ports import ToolPort, VerifierPort
from ela.testing.fakes import FakeStop
from ela.tools.base import Tool
from ela.tools.fs import ELA_S_OWN
from ela.tools.paths import PATH_IS_DIRECTORY
from tests.architecture.test_every_look_at_the_disk_passes_the_guard import (
    EXEMPT,
    OUTPUTS,
    PROGRAM,
    SITE,
    Counting,
    a_result,
    decision,
    members,
    registries,
)

FOLDER = "ELA"
"""The folder the scope of the tests opens: the places are under it, so every tool reaches them."""
FILES = {"the database": "ela.db", "the .env ELA read": ".env"}
FOLDERS = {
    "ELA's home": ".ela",
    "ELA's own source tree": "sorgenti",
    "the Python environment ELA runs in (sys.prefix)": ".venv",
}


def a_root_with_the_places(tmp_path: Path) -> tuple[Path, dict[str, Path]]:
    """The precondition (decision 8 (iii)): a root of proof that really holds the places."""
    root = tmp_path / "files"
    under = root / FOLDER
    under.mkdir(parents=True)
    places: dict[str, Path] = {}
    for what, name in FILES.items():
        (under / name).write_text("of ELA's\n", encoding="utf-8")
        places[what] = (under / name).resolve()
    for what, name in FOLDERS.items():
        (under / name).mkdir()
        (under / name / "dentro.txt").write_text("of ELA's\n", encoding="utf-8")
        places[what] = (under / name).resolve()
    (under / "contiene").mkdir()
    (under / "contiene" / ".ela").mkdir()
    places["a place inside a folder"] = (under / "contiene" / ".ela").resolve()
    return root, places


def the_disk(root: Path) -> dict[str, bytes | None]:
    """Everything under the root, and its bytes: what must not change."""
    return {
        str(path.relative_to(root)): path.read_bytes() if path.is_file() else None
        for path in sorted(root.rglob("*"))
    }


DIRECTIONS = {
    "is": f"{FOLDER}/ela.db",
    "inside": f"{FOLDER}/.ela/dentro.txt",
    "holds": f"{FOLDER}/contiene",
}
"""A target that is a place, one inside a place, and one that holds a place."""


def expected(tool: ToolPort, member: str, direction: str) -> str | None:
    """The code each member must give for each direction, or ``None`` for no refusal."""
    if direction != "holds":
        return ELA_S_OWN
    if member == "prospect_place":
        return ELA_S_OWN
    if str(tool.capability_id) == "terminal.run":
        return None
    return PATH_IS_DIRECTORY


def arguments_for(tool: ToolPort, target: str) -> dict[str, Any]:
    capability = str(tool.capability_id)
    exists = Path(target).name in {"ela.db"}
    if capability == "fs.read":
        return {"path": target, "purpose": "la prova"}
    if capability == "fs.write":
        return {"path": target, "body": "x", "overwrite": exists, "purpose": "la prova"}
    if capability == "terminal.run":
        return {"program": PROGRAM, "args": [], "cwd": target.removeprefix(f"{FOLDER}/")}
    if capability.startswith("browser.download"):
        return {"site": SITE, "path": "/x", "file": target, "overwrite": exists, "purpose": "p"}
    return {
        "site": SITE,
        "path": "/forms/post",
        "file": target,
        "file_field": "#file",
        "expect_text": "ok",
        "purpose": "p",
    }


async def called(tool: ToolPort, member: str, target: str, road: str) -> str | None:
    """The code the member answers with, for ``target``: a refusal's, a failure's, or ``None``."""
    if member == "prospect_place":
        values = (SITE,) if "browser" in str(tool.capability_id) else ()
        seen = await tool.prospect_place(target, values)
        return None if seen.refusal is None else seen.refusal.code
    arguments = arguments_for(tool, target)
    if member in {"prospect", "prospect_covered"}:
        seen = await getattr(tool, member)(arguments)
        return None if seen.refusal is None else seen.refusal.code
    allowed = decision(tool.capability_id)
    if road == "a yes":
        allowed = allowed.model_copy(update={"approval_id": ApprovalId(allowed.id)})
    result = await tool.execute(allowed, arguments, FakeStop())
    return None if result.error is None else result.error.code


ROADS = pytest.mark.parametrize("road", ["a yes", "a policy"])


@ROADS
@pytest.mark.parametrize("direction", list(DIRECTIONS))
async def test_every_member_of_a_tool_under_the_root_refuses_ela_s_places(
    tmp_path: Path, direction: str, road: str
) -> None:
    root, places = a_root_with_the_places(tmp_path / "derived")
    found, _ = registries(tmp_path / "derived", Counting(), places)
    wrong: list[str] = []
    worlds = 0
    for place, name in [(n, one.name) for n, one in enumerate(found) if one.under_the_root]:
        for member in [one for one in members(ToolPort) if one not in EXEMPT]:
            worlds += 1
            world = tmp_path / str(worlds)
            root, places = a_root_with_the_places(world)
            tools, _ = registries(world, Counting(), places)
            (tool,) = [one for one in tools[place : place + 1] if one.name == name]
            if member == "prospect_place" and type(tool).prospect_place is Tool.prospect_place:
                continue  # the default refuses every place, looking at none (the guard's test)
            target = DIRECTIONS[direction]
            if member == "prospect_place":
                target = target.rsplit("/", 1)[0] if direction != "holds" else target
                target = f"{FOLDER}/.ela" if direction == "is" else target
                target = f"{FOLDER}/.ela/dentro" if direction == "inside" else target
            if member == "prospect_place" and direction == "inside":
                (root / FOLDER / ".ela" / "dentro").mkdir(exist_ok=True)
            if str(tool.capability_id) == "terminal.run" and direction != "holds":
                target = f"{FOLDER}/.ela" if direction == "is" else f"{FOLDER}/.ela/sotto"
                (root / FOLDER / ".ela" / "sotto").mkdir(exist_ok=True)
            before = the_disk(root)
            code: str | None = "raised"
            with contextlib.suppress(Exception):
                code = await called(tool, member, target, road)
            want = expected(tool, member, direction)
            if want is None and code == ELA_S_OWN or want is not None and code != want:
                wrong.append(f"{tool.name}.{member} on {target}: {code}, not {want}")
            if want is not None and want not in tool.error_codes:
                wrong.append(f"{tool.name}: {want} is not among the codes it declares")
            if the_disk(root) != before:
                wrong.append(f"{tool.name}.{member} on {target}: the disk changed")

    assert wrong == []


@pytest.mark.parametrize("direction", ["is", "inside"])
async def test_every_verifier_under_the_root_refuses_ela_s_places(
    tmp_path: Path, direction: str
) -> None:
    root, places = a_root_with_the_places(tmp_path)
    _, verifiers = registries(tmp_path, Counting(), places)
    wrong: list[str] = []
    for verifier in [one for one in verifiers if one.under_the_root]:
        capability = str(verifier.capability_id)
        target = DIRECTIONS[direction]
        arguments: Mapping[str, Any] = (
            {"path": target, "body": "of ELA's\n", "purpose": "p"}
            if capability.startswith("fs.")
            else {"file": target, "site": SITE, "path": "/x", "overwrite": False}
        )
        before = the_disk(root)
        failures = await verifier.verify(
            tuple(verifier.conditions),
            arguments,
            a_result(verifier.capability_id, OUTPUTS[capability]),
        )
        codes = {one.code for one in failures}
        if codes != {ELA_S_OWN} or ELA_S_OWN not in verifier.failure_codes:
            wrong.append(f"{verifier.name} on {target}: {sorted(codes)}")
        if the_disk(root) != before:
            wrong.append(f"{verifier.name}: the disk changed")

    assert wrong == []


def test_the_members_and_the_exemptions_are_the_ports(tmp_path: Path) -> None:
    """The members called are the port's, derived; and a verifier has one, ``verify``."""
    assert set(EXEMPT) <= set(members(ToolPort))
    assert members(VerifierPort) == ["verify"]
    tools, verifiers = registries(tmp_path, Counting(), a_root_with_the_places(tmp_path)[1])
    assert {str(one.capability_id) for one in tools if one.under_the_root} == {
        "fs.read",
        "fs.write",
        "terminal.run",
        "browser.download",
        "browser.download_as_you",
        "browser.upload",
        "browser.upload_as_you",
    }
    assert {str(one.capability_id) for one in verifiers if one.under_the_root} == {
        "fs.read",
        "fs.write",
        "browser.download",
        "browser.download_as_you",
    }


def test_a_tool_that_says_it_is_not_under_the_root_is_handed_no_root(tmp_path: Path) -> None:
    """The contrary of the closed world: a tool of the registries that declares ``False`` is not
    one the composition hands ``ELA_FS_ROOT`` — so none can step out of the world in silence.
    ``workspace.write_note`` has a root of its own, the workspace, which is a place of ELA's."""
    root = (tmp_path / "files").resolve()
    tools, _ = registries(tmp_path, Counting(), {})
    for tool in [one for one in tools if not one.under_the_root]:
        held = [getattr(tool, name, None) for name in ("root", "_root")]
        assert root not in [Path(one).resolve() for one in held if one is not None], tool.name
    assert CapabilityId("workspace.write_note") in {one.capability_id for one in tools}
