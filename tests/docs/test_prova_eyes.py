"""**Before every question to Tommaso's eye, a block of the same step has put in front of him what
the question asks about** (M13.10b; decisions 77 and 79 of M13.10, answers 17 of the review of the
SPECs of the branch ``m13.13-i-file-dal-browser``).

The proof of M13.10 of 2026-10-29 asked about «the model's answer, in the file», and neither the
file nor the screen had carried it: no test could see it, because the text of an ``occhio`` is a
free question. What a machine can see is the shape: which kinds of block ask the eye, which put
something in front of it, and whether one of the second comes before each of the first in its step.

**Which kinds do what is declared by each script, never listed here**: every ``scripts/prova_*.py``
— found in its folder — declares ``LOOKS`` and ``SHOWS``, in the same form, a kind and its reason.
A ``SHOWS`` that claims more than its kind puts in front is a judgement no test sees: its reason is
written beside it, for the review to read.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
DECLARED = ("LOOKS", "SHOWS")


def proofs() -> list[Path]:
    """Every script of a proof, found in its folder."""
    return sorted(SCRIPTS.glob("prova_*.py"))


@contextmanager
def _siblings() -> Iterator[None]:
    """The scripts import their siblings by name: the folder on the path while one is loaded, and
    ``sys.modules`` as it was afterwards."""
    before = dict(sys.modules)
    sys.path.insert(0, str(SCRIPTS))
    try:
        yield
    finally:
        sys.path.remove(str(SCRIPTS))
        for name in set(sys.modules) - set(before):
            del sys.modules[name]


def loaded(path: Path) -> ModuleType:
    with _siblings():
        spec = importlib.util.spec_from_file_location(f"_eyes_{path.stem}", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module  # a dataclass of the script asks for its module
        spec.loader.exec_module(module)
        return module


def base() -> ModuleType:
    return loaded(SCRIPTS / "prova_m6_3c.py")


def unshown(
    steps: Mapping[int, Sequence[Any]], looks: Sequence[str], shows: Sequence[str]
) -> list[str]:
    """Every block of a kind that asks the eye with no block before it, in its step, of a kind
    that shows — named by its step, its kind and the beginning of its question."""
    found: list[str] = []
    for number, blocks in steps.items():
        seen: list[str] = []
        for block in blocks:
            if block.kind in looks and not set(seen) & set(shows):
                found.append(f"{number}.{block.kind}: {block.lines[0][:60]}")
            seen.append(block.kind)
    return found


@pytest.mark.parametrize("path", proofs(), ids=lambda path: path.stem)
def test_every_proof_declares_what_asks_the_eye_and_what_shows_it_in_the_same_form(
    path: Path,
) -> None:
    module = loaded(path)
    for name in DECLARED:
        declared = getattr(module, name, None)
        assert isinstance(declared, Mapping), f"{path.name} declares no {name}"
        assert declared, f"{path.name}: {name} is empty"
        for kind, why in declared.items():
            assert kind in module.KINDS, f"{path.name}: {name} names {kind!r}, not a kind of it"
            assert isinstance(why, str) and why.strip(), f"{path.name}: {kind!r} has no reason"


@pytest.mark.parametrize("path", proofs(), ids=lambda path: path.stem)
def test_before_every_question_to_the_eye_a_block_of_its_step_shows_what_it_asks(
    path: Path,
) -> None:
    module, reader = loaded(path), base()
    steps = reader.steps(reader.blocks(reader.GUIDE.read_text(encoding="utf-8"), module.HEADING))

    assert unshown(steps, tuple(module.LOOKS), tuple(module.SHOWS)) == []


SECTION = """## 99. Una sezione di questo test

### 1. Il passo

<!-- prova: 1.comando -->
```
uv run ela status
```

<!-- prova: 1.occhio -->
```
Che cosa ha detto?
```

<!-- prova: 1.schermo -->
```
uv run ela status
```

<!-- prova: 1.occhio -->
```
Qui sopra, sullo schermo, che cosa dice?
```
"""


def test_a_question_with_nothing_shown_before_it_in_its_step_is_named() -> None:
    """The negative case: the first ``occhio`` has only a ``comando`` before it, which this
    section does not declare as showing; the second has the ``schermo``."""
    reader = base()
    steps = reader.steps(reader.blocks(SECTION, "## 99. "))

    assert unshown(steps, ("occhio",), ("schermo",)) == ["1.occhio: Che cosa ha detto?"]


def test_a_block_shown_in_another_step_does_not_count() -> None:
    reader = base()
    two = SECTION.replace("### 1. Il passo", "### 1. Il passo") + SECTION.split("### 1. Il passo")[
        1
    ].replace("1.", "2.")
    steps = reader.steps(reader.blocks(two, "## 99. "))

    assert unshown(steps, ("occhio",), ("schermo",)) == [
        "1.occhio: Che cosa ha detto?",
        "2.occhio: Che cosa ha detto?",
    ]
