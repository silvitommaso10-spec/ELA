"""**A proof script never launches a real process in a test that did not replace the launch**
(M13.17, decisions 62 and 68): the guard of ``tests/proof_launches.py``, which the fixture of
``tests/conftest.py`` puts in front of every launch of the suite.

The negative cases: ``base.run`` and ``base.started`` left in place, and the scripts' own launches —
``migrated()`` of ``prova_m13_12.py`` and of ``prova_m14_2.py``, which open the real database with
``uv run alembic current`` —, each refused before anything starts. And the other way: a launch
that does not come from a proof script still starts, and the scripts covered are every
``scripts/prova_*.py`` there is.

**Nothing here can reach the real world even with the guard broken** — the run of a mutant breaks
it: the scripts' ``ROOT`` is the test's folder, and the first ``uv`` on ``PATH`` is a fake one that
only leaves a mark there. What would have started is read from the mark.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests import proof_launches
from tests.composition.support import (  # noqa: F401 — it reads the scripts of the proofs
    _only_the_declared_environment,
)
from tests.docs.test_prova_eyes import loaded
from tests.proof_launches import PROOFS, SCRIPTS, LaunchFromAProof


def test_the_scripts_covered_are_every_proof_script_in_its_folder() -> None:
    found = {
        os.path.realpath(SCRIPTS / name)
        for name in os.listdir(SCRIPTS)
        if name.startswith("prova_")
    }

    assert {one for one in found if one.endswith(".py")} == PROOFS
    assert os.path.realpath(SCRIPTS / "prova_m13_17.py") in PROOFS


def test_the_refusal_is_not_an_exception_a_script_can_swallow() -> None:
    """A script's ``except Exception`` would turn the refusal into a step that merely failed."""
    assert issubclass(LaunchFromAProof, BaseException)
    assert not issubclass(LaunchFromAProof, Exception)


@pytest.fixture
def harmless(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A fake ``uv`` first on ``PATH``, which leaves the mark it returns and nothing else."""
    folder = tmp_path / "bin"
    folder.mkdir()
    mark = tmp_path / "uv-started"
    fake = folder / "uv"
    fake.write_text(f"#!/bin/sh\ntouch {mark}\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ.get('PATH', '')}")
    return mark


def test_a_line_of_the_guide_left_to_the_real_runner_is_refused_before_it_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, harmless: Path
) -> None:
    base = loaded(SCRIPTS / "prova_m6_3c.py")
    monkeypatch.setattr(base, "ROOT", tmp_path)
    made = tmp_path / "made"

    with pytest.raises(LaunchFromAProof, match="prova_m6_3c.py launched a real process"):
        base.run(f"touch {made}")
    with pytest.raises(LaunchFromAProof):
        base.run(f"touch {made}", 5)
    with pytest.raises(LaunchFromAProof):
        base.started(f"touch {made}")
    with pytest.raises(LaunchFromAProof):
        base.run("uv run ela status")

    assert not made.exists() and not harmless.exists(), "nothing started"


@pytest.mark.parametrize("script", ["prova_m13_12.py", "prova_m14_2.py"])
def test_a_script_s_own_launch_is_refused_too(
    script: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, harmless: Path
) -> None:
    """``migrated()`` would read the real ``.env`` and open the real database — here, with the guard
    broken, it would only start the fake ``uv``."""
    module = loaded(SCRIPTS / script)
    monkeypatch.setattr(module, "ROOT", tmp_path)

    with pytest.raises(LaunchFromAProof, match=script):
        module.migrated()

    assert not harmless.exists(), "nothing started"


def test_a_launch_that_does_not_come_from_a_proof_script_starts(tmp_path: Path) -> None:
    made = tmp_path / "made"

    subprocess.run(["touch", str(made)], check=True)

    assert made.exists()


@pytest.mark.launches_through_a_proof_script("the mark itself: a marked test is let through")
def test_a_marked_test_launches_through_a_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = loaded(SCRIPTS / "prova_m6_3c.py")
    monkeypatch.setattr(base, "ROOT", tmp_path)
    made = tmp_path / "made"

    done = base.run(f"touch {made}")

    assert done.returncode == 0 and made.exists()
    assert proof_launches.ALLOWED == "launches_through_a_proof_script"
