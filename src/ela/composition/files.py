"""What is open, said and shown (M13.17, ADR 0074; decision 7 of its starting block, answers 37
and 41 of the review of its SPEC).

**At the start-up** ELA says the root, every folder the scope opens as the disk names it, the
folder a command of the terminal starts from, and which places of ELA's lie under the root — with
the sentence that no read and no write of ``fs.*`` or of a file of the browser reaches them. Two
entries that are the same, or one inside the other, are said, and ELA starts.

**At any moment** ``ela diagnostics`` and ``GET /diagnostics`` show the same, and the scope every
capability declares. **They read the state of ELA, not the world**: :class:`OpenFolders` is built
once, at the start-up, from what the settings resolved; nothing here looks at the disk again.

The sentence says ``fs.*`` and the files of the browser and **not «ELA»**: a program the terminal
launches reaches those places, because the folder a command starts from is not a boundary (ADR
0047 §6; the SPEC's C2-bis).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from ela.composition.errors import ConfigurationError
from ela.permissions import PolicyState, short_id, shown_of, state_of
from ela.ports import AuthorizationStore, CapabilityRegistryPort
from ela.tools.paths import within

__all__ = [
    "NEVER_REACHED",
    "OpenFolder",
    "OpenFolders",
    "open_folders",
    "refuse_the_moved_policies",
    "said_at_start",
]

NEVER_REACHED: Final = (
    "Inside the root, and never read or written by fs.read, fs.write or a file of the browser "
    "— a program of the terminal reaches them:"
)


@dataclass(frozen=True, slots=True)
class OpenFolder:
    """One entry of ``ELA_FS_SCOPE``, as written, and the folder it is on this disk."""

    entry: str
    folder: Path


@dataclass(frozen=True, slots=True)
class OpenFolders:
    """What the scope opens, resolved at the start-up: the state ``ela diagnostics`` reads."""

    root: Path
    folders: tuple[OpenFolder, ...]
    commands_from: Path
    """The first folder of the list: where a command of the terminal starts (answer 41)."""
    inside: tuple[tuple[str, Path], ...]
    """ELA's places that lie under the root, each with its name: refused at every use."""
    overlaps: tuple[str, ...]
    """Two entries that are one, or one inside another: said, and ELA starts (decision 4)."""


def open_folders(root: Path, scope: Sequence[str], own: Mapping[str, Path]) -> OpenFolders:
    """The folders of ``scope`` under ``root``, the places of ``own`` under it, and the overlaps
    — resolved once, at the start-up, after the settings looked at every folder."""
    resolved = root.resolve()
    folders = tuple(OpenFolder(entry, (resolved / entry).resolve()) for entry in scope)
    inside = tuple((what, place) for what, place in own.items() if within(place, resolved))
    return OpenFolders(
        root=resolved,
        folders=folders,
        commands_from=folders[0].folder,
        inside=inside,
        overlaps=_overlaps(folders),
    )


def _overlaps(folders: tuple[OpenFolder, ...]) -> tuple[str, ...]:
    said: list[str] = []
    for n, one in enumerate(folders):
        for other in folders[n + 1 :]:
            if one.folder == other.folder:
                said.append(
                    f"{other.entry!r} is {one.entry!r} written twice: it opens nothing more"
                )
            elif within(other.folder, one.folder):
                said.append(f"{other.entry!r} is inside {one.entry!r}: it opens nothing more")
            elif within(one.folder, other.folder):
                said.append(f"{one.entry!r} is inside {other.entry!r}: it opens nothing more")
    return tuple(said)


def said_at_start(view: OpenFolders) -> list[str]:
    """What ``ela serve`` says before it serves: the root, the folders, the terminal's, the places
    of ELA's under the root, and the overlaps — lines a person reads."""
    width = max(len(one.entry) for one in view.folders)
    lines = [f"ela: the folders fs.read and fs.write may touch, under {view.root}:"]
    lines += [f"  {one.entry.ljust(width)}  {one.folder}" for one in view.folders]
    lines.append(f"ela: a command of the terminal starts from {view.commands_from}, or under it.")
    lines += [f"ela: {sentence}" for sentence in view.overlaps]
    if view.inside:
        lines.append(f"ela: {NEVER_REACHED}")
        lines += [f"  {what}: {place}" for what, place in view.inside]
    return lines


async def refuse_the_moved_policies(
    store: AuthorizationStore,
    capabilities: CapabilityRegistryPort,
    root: Path,
    scope: Sequence[str],
    now: datetime,
) -> None:
    """**A live policy of a file whose folder, today, is somewhere else stops ELA** (M13.17, ADR
    0074; answer 48 of the review of its SPEC).

    The entries of a policy are written relative to the root, and resolved on the root of now: a
    root moved — from Documents to the home — would make every policy of a file cover another
    folder than the one its preview showed. At the start-up, after the configuration and before
    serving, for every live policy of a capability whose scope is ``ELA_FS_SCOPE`` that carries
    what its birth showed (:func:`~ela.permissions.shown_of`): if one of its folders resolves
    elsewhere now, ELA does not start, and the sentence names the policy, where the folder was,
    where it would be, and the road. **Exact and not a belief**: the root is read only at the
    start-up. An ended policy does not count; a live one born before M13.15, without what its birth
    showed, cannot be judged and is declared (ADR 0074). No predicate of the Guardian.
    """
    for spec in capabilities.specs():
        if spec.policy_terms is None or tuple(spec.scope) != tuple(scope):
            continue
        for grant in await store.for_capability(spec.id):
            if grant.approval_id is not None:
                continue
            uses = await store.uses(grant.id)
            if state_of(grant, now, uses=uses) is not PolicyState.LIVE:
                continue
            shown = shown_of(grant)
            if shown is None:
                continue
            for entry, was in zip(grant.scope, shown[0], strict=False):
                if was is None:
                    continue
                would = (root / entry).resolve()
                if within(would, Path(was)) and within(Path(was), would):
                    continue
                short = short_id(grant.id)
                raise ConfigurationError(
                    f"ela: policy {short} of {spec.id} was born on {was} for {entry!r}, and with "
                    f"ELA_FS_ROOT={root} it would cover {would}. Put ELA_FS_ROOT back, revoke the "
                    f"policy (uv run ela policy revoke {short}), then change the root again "
                    "(M13.17)."
                )
