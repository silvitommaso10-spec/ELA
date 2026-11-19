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

from tests.composition.support import _only_the_declared_environment  # noqa: F401 — the fixture

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
DECLARED = ("LOOKS", "SHOWS")


def proofs() -> list[Path]:
    """Every script of a proof, found in its folder."""
    return sorted(SCRIPTS.glob("prova_*.py"))


@contextmanager
def _siblings() -> Iterator[None]:
    """The scripts import their siblings by name: the folder on the path while one is loaded, and
    ``sys.modules`` as it was afterwards. **The siblings another test left in ``sys.modules`` are
    hidden during the load** (the make check of M13.17 at ``0612dba``): a script that found an old
    ``prova_m13_15`` would share it, with another ``prova_m6_3c`` than its own, and a patch of its
    ``base`` would not reach the screen of the old one."""
    before = dict(sys.modules)
    for name in [one for one in before if one.startswith("prova_")]:
        del sys.modules[name]
    sys.path.insert(0, str(SCRIPTS))
    try:
        yield
    finally:
        sys.path.remove(str(SCRIPTS))
        for name in set(sys.modules) - set(before):
            del sys.modules[name]
        sys.modules.update({name: one for name, one in before.items() if name.startswith("prova_")})


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


# ----------------------------------------------------------------------------------------
# Rule (a) of M13.17 for every section (decision 18 (d) of its starting block): a screen whose
# command ended in an error stops the proof, and the eye is not asked
# ----------------------------------------------------------------------------------------

REFUSED = "ela: policy.would_not_start: vault.no_entry"
"""What step 9 of the first run of M13.15's proof printed, on 2026-11-18."""
SHOWN = "what the screen shows, and the file never"


def screens() -> list[Path]:
    """Every script whose vocabulary has a ``schermo``, derived from its ``KINDS``."""
    return [path for path in proofs() if "schermo" in loaded(path).KINDS]


def walker(module: ModuleType) -> Any:
    """The ``a_block`` the script walks with: its own, or — for a script that has none — the one of
    the script its ``Proof`` comes from."""
    if hasattr(module, "a_block"):
        return module.a_block
    held = module.Proof.__module__
    (owner,) = [one for one in vars(module).values() if getattr(one, "__name__", None) == held]
    return owner.a_block


class _Proof:
    """What a block reads of a proof, and nothing that answers for a live ELA: the report, the eye,
    the folders of the masks."""

    def __init__(self, report: Any, asked: list[str], tmp_path: Path) -> None:
        self.report = report
        self.asked = asked
        self.root = tmp_path
        self.home = tmp_path
        self.entry = None
        self.current = 1

    def ask(self, question: str) -> str:
        self.asked.append(question)
        return "s"

    def __getattr__(self, name: str) -> None:
        """A field a script's proof has and this one does not — a login, a plan —: none given."""
        return None


@pytest.mark.parametrize("path", screens(), ids=lambda path: path.stem)
def test_a_screen_that_ends_in_an_error_stops_the_proof_and_the_eye_is_not_asked(
    path: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import inspect
    import io
    import subprocess
    import typing

    module = loaded(path)
    reader = module.base

    def refusing(line: str, limit: float | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(line, 1, SHOWN + "\n", REFUSED + "\n")

    monkeypatch.setattr(reader, "run", refusing)
    a_block = walker(module)
    turn = typing.get_type_hints(a_block)["turn"]()
    asked: list[str] = []
    proof = _Proof(reader.Report(io.StringIO()), asked, tmp_path)
    extra = [lambda text: text] * (len(inspect.signature(a_block).parameters) - 4)

    with pytest.raises(reader.Stop):
        for block in (
            reader.Block(1, "schermo", "uv run ela status"),
            reader.Block(1, "occhio", "E?"),
        ):
            a_block(1, block, turn, proof, *extra)

    written = "\n".join(proof.report.lines)
    assert asked == [], f"{path.name}: the eye was asked about a screen that shows an error"
    assert proof.report.failures == 1
    assert REFUSED in written
    assert SHOWN not in written, f"{path.name}: what the screen shows reached the file"


def test_the_rule_finds_a_screen_that_does_not_look_at_the_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The negative case: without the look at the exit, a screen that ended in an error leaves the
    eye to be asked — what the rule above says no script does."""
    import io
    import subprocess

    module = loaded(SCRIPTS / "prova_m14_6b.py")
    reader = module.base
    monkeypatch.setattr(
        reader, "run", lambda line, limit=None: subprocess.CompletedProcess(line, 1, "", REFUSED)
    )
    monkeypatch.setattr(reader, "screen_failed", lambda *args: None)
    asked: list[str] = []
    proof = _Proof(reader.Report(io.StringIO()), asked, tmp_path)
    turn = module.Turn()

    for block in (reader.Block(1, "schermo", "uv run ela status"), reader.Block(1, "occhio", "E?")):
        module.a_block(1, block, turn, proof)

    assert asked == ["[1] E? (s/n) "]
