"""``ela diagnostics`` prints the block ``files`` (M13.17, ADR 0074; decision 7): the root, the
folders as written and as the disk names them, the folder of the terminal, ELA's places under the
root when there are some, the overlaps when there are some, and the standing waits."""

from __future__ import annotations

from ela.cli.system import _files


def test_the_block_prints_the_places_and_the_overlaps_only_when_there_are_some() -> None:
    bare = {
        "root": "/Users/you",
        "folders": [{"entry": "Documents", "folder": "/Users/you/Documents"}],
        "commands_from": "/Users/you/Documents",
        "inside": [],
        "overlaps": [],
        "waiting": 0,
    }
    full = {
        **bare,
        "inside": [{"what": "ELA's home", "place": "/Users/you/.ela"}],
        "overlaps": ["'Documents/ELA' is inside 'Documents': it opens nothing more"],
        "waiting": 2,
    }

    assert _files(bare) == [
        ("files root", "/Users/you"),
        ("files open", {"Documents": "/Users/you/Documents"}),
        ("commands start from", "/Users/you/Documents"),
        ("disk waits standing", 0),
    ]
    assert _files(full)[3:] == [
        ("never read or written by fs.*", {"ELA's home": "/Users/you/.ela"}),
        ("files overlapping", ["'Documents/ELA' is inside 'Documents': it opens nothing more"]),
        ("disk waits standing", 2),
    ]
