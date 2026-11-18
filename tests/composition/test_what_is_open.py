"""What the scope opens is said at the start-up and shown at any moment, and a root moved under a
live policy of a file stops ELA (M13.17, ADR 0074; decision 7 of its starting block, answers 37,
40, 41 and 48 of the review of its SPEC).

- **Said and shown**: the root, every folder as written and as the disk names it, the folder of
  the terminal — the first —, ELA's places under the root, the overlaps; and ``ela diagnostics``
  with the scope every capability declares, derived from the catalogue, and the standing waits of
  the guard. The state of ELA: built once, never a new look.
- **A moved root**: a live policy of a file whose folder resolves elsewhere now stops ELA, with
  the policy, where it was, where it would be, and the road; an ended one, one born before M13.15
  and a yes do not count.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from ela.composition import ConfigurationError
from ela.composition.files import (
    NEVER_REACHED,
    open_folders,
    refuse_the_moved_policies,
    said_at_start,
)
from ela.domain import ApprovalId, Authorization, AuthorizationId, CapabilityId, StepId, TaskId
from ela.permissions import production_catalogue, short_id, shown_at_birth
from ela.testing.fakes import FakeAuthorizationStore
from tests.domain.examples import NOW
from tests.permissions.policy_support import policy_for

WRITE = CapabilityId("fs.write")


def a_folder(*parts: Path | str) -> Path:
    made = Path(*parts)
    made.mkdir(parents=True, exist_ok=True)
    return made


# ----------------------------------------------------------------------------------------
# What is open (decision 7, answer 41)
# ----------------------------------------------------------------------------------------


def test_the_open_folders_are_resolved_once_with_the_terminal_s_first(tmp_path: Path) -> None:
    root = a_folder(tmp_path, "casa")
    for name in ("Documents", "Desktop", "Documents/ELA"):
        a_folder(root, name)
    house = a_folder(root, ".ela")

    view = open_folders(
        root,
        ("Documents", "Desktop", "Documents/ELA", "Desktop"),
        {"ELA's home": house.resolve(), "elsewhere": a_folder(tmp_path, "altrove").resolve()},
    )

    assert view.root == root.resolve()
    assert [one.entry for one in view.folders] == [
        "Documents",
        "Desktop",
        "Documents/ELA",
        "Desktop",
    ]
    assert view.commands_from == (root / "Documents").resolve()
    assert view.inside == (("ELA's home", house.resolve()),), "only what lies under the root"
    assert view.overlaps == (
        "'Documents/ELA' is inside 'Documents': it opens nothing more",
        "'Desktop' is 'Desktop' written twice: it opens nothing more",
    )


def test_the_start_up_says_the_folders_the_terminal_s_and_ela_s_places(tmp_path: Path) -> None:
    root = a_folder(tmp_path, "casa")
    a_folder(root, "Documents")
    house = a_folder(root, ".ela")

    lines = said_at_start(open_folders(root, ("Documents",), {"ELA's home": house.resolve()}))

    assert lines == [
        f"ela: the folders fs.read and fs.write may touch, under {root.resolve()}:",
        f"  Documents  {(root / 'Documents').resolve()}",
        f"ela: a command of the terminal starts from {(root / 'Documents').resolve()}, "
        "or under it.",
        f"ela: {NEVER_REACHED}",
        f"  ELA's home: {house.resolve()}",
    ]
    assert "a program of the terminal reaches them" in NEVER_REACHED


# ----------------------------------------------------------------------------------------
# A root moved under a live policy of a file (answer 48)
# ----------------------------------------------------------------------------------------

CATALOGUE = production_catalogue(fs_scope=("ELA",))


def born_on(folder: Path, **changes: object) -> object:
    spec = CATALOGUE.get(WRITE)
    return shown_at_birth(
        policy_for(spec, scope=("ELA/policy",), **changes),
        resolved=[str(folder.resolve())],
        values=[],
    )


async def test_a_live_policy_whose_folder_is_elsewhere_now_stops_ela(tmp_path: Path) -> None:
    before, after = a_folder(tmp_path, "Documents"), a_folder(tmp_path, "casa")
    a_folder(before, "ELA", "policy")
    a_folder(after, "ELA", "policy")
    store, policy = FakeAuthorizationStore(), born_on(before / "ELA" / "policy")
    await store.grant(policy)  # type: ignore[arg-type]
    now = policy.created_at + timedelta(hours=1)  # type: ignore[attr-defined]

    with pytest.raises(ConfigurationError) as stopped:
        await refuse_the_moved_policies(store, CATALOGUE, after, ("ELA",), now)

    said = str(stopped.value)
    assert f"policy {short_id(policy.id)} of fs.write was born on" in said  # type: ignore[attr-defined]
    assert str((before / "ELA" / "policy").resolve()) in said
    assert str((after / "ELA" / "policy").resolve()) in said
    assert "Put ELA_FS_ROOT back, revoke the policy" in said


async def test_a_policy_on_the_same_folder_an_ended_one_an_old_one_and_a_yes_do_not_stop_it(
    tmp_path: Path,
) -> None:
    before, after = a_folder(tmp_path, "Documents"), a_folder(tmp_path, "casa")
    a_folder(before, "ELA", "policy")
    same = born_on(before / "ELA" / "policy", tail=901)
    ended = born_on(after / "ELA" / "policy", tail=902, revoked_at=NOW)
    old = policy_for(CATALOGUE.get(WRITE), scope=("ELA/policy",), tail=903)
    # A yes is not a policy: whatever its metadata says, it is never judged here.
    yes = shown_at_birth(
        Authorization(
            id=AuthorizationId(UUID(int=904)),
            created_at=NOW,
            capability_id=WRITE,
            scope=("ELA/policy",),
            granted_by="tommaso",
            task_id=TaskId(UUID(int=1)),
            step_id=StepId(UUID(int=2)),
            approval_id=ApprovalId(UUID(int=3)),
            expires_at=NOW + timedelta(days=1),
            max_uses=1,
        ),
        resolved=[str((after / "ELA" / "policy").resolve())],
        values=[],
    )
    store = FakeAuthorizationStore()
    for one in (same, ended, old, yes):
        await store.grant(one)  # type: ignore[arg-type]
    now = same.created_at + timedelta(hours=1)  # type: ignore[attr-defined]

    await refuse_the_moved_policies(store, CATALOGUE, before, ("ELA",), now)


def test_an_entry_inside_a_later_one_is_said_and_no_place_of_ela_s_is_not_listed(
    tmp_path: Path,
) -> None:
    root = a_folder(tmp_path, "casa")
    a_folder(root, "Documents", "ELA")

    view = open_folders(root, ("Documents/ELA", "Documents"), {})
    lines = said_at_start(view)

    assert view.overlaps == ("'Documents/ELA' is inside 'Documents': it opens nothing more",)
    assert not any(NEVER_REACHED in line for line in lines)


async def test_a_folder_the_birth_did_not_resolve_is_not_judged(tmp_path: Path) -> None:
    """A place a birth showed as ``None`` — no folder there then — has nothing to compare."""
    store, spec = FakeAuthorizationStore(), CATALOGUE.get(WRITE)
    policy = shown_at_birth(policy_for(spec, scope=("ELA/policy",)), resolved=[None], values=[])
    await store.grant(policy)

    await refuse_the_moved_policies(
        store, CATALOGUE, a_folder(tmp_path, "x"), ("ELA",), policy.created_at
    )


def test_a_database_that_is_not_a_file_has_no_journal_among_ela_s_places(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from ela.composition import Settings
    from tests.composition.support import declare

    declare(monkeypatch, tmp_path)
    settings = Settings.load()
    moved = settings.model_copy(
        update={
            "persistence": settings.persistence.model_copy(update={"db_url": "sqlite:///:memory:"})
        }
    )

    assert not any("journal" in what for what in moved.ela_s_own())


async def test_the_start_up_refuses_a_moved_policy_before_it_serves(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The check runs in ``build``: an ELA with a live policy of a file born on another folder does
    not start, and says which."""
    from ela.composition import Settings, build
    from ela.testing.fakes import FakePower
    from tests.composition.support import create_schema, declare

    declare(monkeypatch, tmp_path)
    settings = Settings.load()
    await create_schema(settings.persistence.db_url)
    first = await build(settings, power=FakePower())
    elsewhere = a_folder(tmp_path, "altrove", "ELA", "policy")
    policy = born_on(elsewhere, created_at=datetime.now(UTC) - timedelta(minutes=5))
    try:
        await first.authorizations.grant(policy)  # type: ignore[arg-type]
    finally:
        await first.aclose()

    with pytest.raises(ConfigurationError, match=f"policy {short_id(policy.id)}"):  # type: ignore[attr-defined]
        await build(settings, power=FakePower())
