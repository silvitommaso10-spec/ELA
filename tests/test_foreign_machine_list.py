"""The binaries ``tests/foreign_machine.py`` hides are the ones ELA names (M13.1b, point d).

``make check-linux`` pretends to be the other half of the CI matrix, and part of the pretence is
that Apple's binaries are absent. The list was written by hand and drifted: it hid
``/usr/bin/screencapture``, which does not exist on a Mac, while ELA uses
``/usr/sbin/screencapture``, which stayed visible. Nothing noticed, because nothing asked — the
list is compared here with the absolute POSIX paths ``ela.infrastructure.machine`` exports, in
both directions.

**The plugin is read, never imported.** It replaces ``platform.system`` and ``os.access`` at import
time, for the whole process, with no way back: a test that imported it would turn every worker
that collected it into the foreign machine, and ``make check`` would quietly stop being this Mac.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import ela.infrastructure.machine as machine

PLUGIN: Final = Path(__file__).resolve().parent / "foreign_machine.py"


def hidden_by_the_plugin(source: str) -> frozenset[str]:
    """The literal ``APPLE_BINARIES = frozenset({...})`` of the plugin, evaluated as a literal."""
    for node in ast.parse(source).body:
        if (
            isinstance(node, ast.Assign)
            and [target.id for target in node.targets if isinstance(target, ast.Name)]
            == ["APPLE_BINARIES"]
            and isinstance(node.value, ast.Call)
        ):
            return frozenset(ast.literal_eval(node.value.args[0]))
    raise AssertionError("tests/foreign_machine.py no longer assigns APPLE_BINARIES literally")


def named_by_ela() -> frozenset[str]:
    """Every absolute POSIX path ``ela.infrastructure.machine`` exports.

    POSIX, because the same module exports ``POWERSHELL``, a Windows path the foreign machine — a
    Linux runner — has no reason to hide.
    """
    return frozenset(
        value
        for name in machine.__all__
        if isinstance(value := getattr(machine, name), str) and value.startswith("/")
    )


def mismatches(hidden: frozenset[str], named: frozenset[str]) -> list[str]:
    return [
        *(f"ELA names {path} and the foreign machine does not hide it" for path in named - hidden),
        *(f"the foreign machine hides {path} and ELA never names it" for path in hidden - named),
    ]


def test_the_foreign_machine_hides_exactly_what_ela_names() -> None:
    problems = mismatches(hidden_by_the_plugin(PLUGIN.read_text(encoding="utf-8")), named_by_ela())
    assert not problems, problems


def test_ela_names_a_binary_to_hide_at_all() -> None:
    """A comparison between two empty sets would pass and say nothing."""
    assert named_by_ela()
    assert all(not path.startswith("C:") for path in named_by_ela())


def test_a_drift_either_way_is_detected() -> None:
    """The two directions, on the defect M13.1b found: the path in the wrong folder."""
    named = frozenset({"/usr/sbin/screencapture", "/usr/bin/say"})
    drifted = frozenset({"/usr/bin/screencapture", "/usr/bin/say"})

    assert mismatches(drifted, named) == [
        "ELA names /usr/sbin/screencapture and the foreign machine does not hide it",
        "the foreign machine hides /usr/bin/screencapture and ELA never names it",
    ]
    assert mismatches(named, named) == []
