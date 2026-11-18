"""A proof never asks the eye about a screen whose command failed, and a creation says what happened
(M13.17, decision 18; the second point M13.15's proof put in its account).

The fact, from the first run of 2026-11-18 at step 9 (``docs/milestones/M13.15.md``, «I punti in
conto dalla prova», point 2): the ``schermo`` printed «ela: policy.would_not_start: vault.no_entry»
and the script asked the eye «è ciò che vuoi approvare?» all the same; the answer was yes; then
``crea`` wrote «FALLITO: l'anteprima ha creato una policy», when no policy had been born and the
preview had ended in an error.

**The rules.** (a) A ``schermo`` whose command ends in an error — the exit code says so, not a word
of the output — fails the step with the reason read from the output, and the eye that follows is not
asked: the proof stops there. (b) ``crea`` tells three outcomes apart and says one: the preview
ended in an error, with its code, and no policy was born; the preview created a policy, and there is
one more live policy; the output does not say «not created», without an error.
"""

from __future__ import annotations

import io
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.composition.support import _only_the_declared_environment  # noqa: F401 — the fixture
from tests.docs.test_prova_m13_15 import script

PREVIEW = (
    "uv run ela policy create browser.login --scope news.ycombinator.com --entry <id della voce> "
    "--days 1 --uses 2"
)
"""The ``schermo`` and the ``crea`` of step 9 of section 34, as the guide writes them."""
SHOWN = "HIGH\nsigns in to these sites with these entries of your vault\n"
"""What a preview prints on stdout: the screen's, never the file's."""
ERROR = "ela: policy.would_not_start: vault.no_entry"
"""What step 9 of the first run of 2026-11-18 printed, and the exit of an ``ela`` that refused."""


class Api:
    """The live policies, one answer after the other: before the preview, after it."""

    def __init__(self, *answers: list[dict[str, Any]]) -> None:
        self.answers = list(answers)

    def get(self, path: str) -> dict[str, Any]:
        policies = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return {"policies": policies}


def a_proof(tmp_path: Path, api: Api, asked: list[str]) -> Any:
    module = script()
    report = module.Report(io.StringIO())

    def ask(question: str) -> str:
        asked.append(question)
        return "s"

    proof = module.Proof(api, report, ask, root=tmp_path)
    proof.current = 9
    return proof


def printing(code: int, out: str = "", err: str = "") -> Any:
    def run(line: str, limit: float | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(line, code, out, err)

    return run


def test_a_screen_whose_command_failed_fails_the_step_and_asks_the_eye_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = script()
    monkeypatch.setattr(module.base, "run", printing(1, out=SHOWN, err=ERROR + "\n"))
    asked: list[str] = []
    proof = a_proof(tmp_path, Api([]), asked)
    turn = module.guided.Turn()
    blocks = (
        module.base.Block(9, "schermo", PREVIEW),
        module.base.Block(
            9, "occhio", "Qui sopra, sullo schermo, l'anteprima. È ciò che vuoi approvare?"
        ),
    )

    with pytest.raises(module.base.Stop):
        for block in blocks:
            module.a_block(9, block, turn, proof, lambda _: "")

    written = "\n".join(proof.report.lines)
    assert asked == [], "the eye was asked about a screen that shows an error"
    assert proof.report.failures == 1
    assert "policy.would_not_start: vault.no_entry" in written
    assert "signs in to these sites" not in written, "what the screen shows stays off the file"


def test_the_exit_code_decides_and_not_a_word_of_the_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Decision 18 (a): «lo dice il codice d'uscita, non una parola dell'uscita». A preview that
    exits 0 and prints a line that starts with «ela:» is the eye's to judge; one that exits 1 and
    prints nothing ELA would write is FALLITO all the same."""
    module = script()
    asked: list[str] = []
    monkeypatch.setattr(module.base, "run", printing(0, out=SHOWN + "ela: a word, not an error\n"))
    calm = a_proof(tmp_path, Api([]), asked)
    turn = module.guided.Turn()
    module.a_block(9, module.base.Block(9, "schermo", PREVIEW), turn, calm, lambda _: "")
    module.a_block(
        9, module.base.Block(9, "occhio", "È ciò che vuoi approvare?"), turn, calm, lambda _: ""
    )

    assert len(asked) == 1 and calm.report.failures == 0

    monkeypatch.setattr(module.base, "run", printing(1, out="", err="Traceback: boom\n"))
    broken = a_proof(tmp_path, Api([]), asked)
    with pytest.raises(module.base.Stop):
        module.a_block(
            9, module.base.Block(9, "schermo", PREVIEW), module.guided.Turn(), broken, lambda _: ""
        )

    assert len(asked) == 1 and broken.report.failures == 1


def test_a_screen_whose_command_succeeded_is_left_to_the_eye(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The case that does not change: a preview that printed and exited 0 is the eye's to judge."""
    module = script()
    monkeypatch.setattr(module.base, "run", printing(0, out="HIGH\nnot created\n"))
    asked: list[str] = []
    proof = a_proof(tmp_path, Api([]), asked)
    turn = module.guided.Turn()

    module.a_block(9, module.base.Block(9, "schermo", PREVIEW), turn, proof, lambda _: "")
    module.a_block(
        9, module.base.Block(9, "occhio", "È ciò che vuoi approvare?"), turn, proof, lambda _: ""
    )

    assert len(asked) == 1 and proof.report.failures == 0


def test_a_preview_that_ended_in_an_error_says_so_and_that_no_policy_was_born(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The first run of 2026-11-18 at step 9: the creation said «l'anteprima ha creato una policy»
    of a preview that had ended in ``vault.no_entry``."""
    module = script()
    monkeypatch.setattr(module.base, "run", printing(1, err=ERROR + "\n"))
    asked: list[str] = []
    proof = a_proof(tmp_path, Api([], []), asked)

    with pytest.raises(module.base.Stop):
        module.a_block(
            9, module.base.Block(9, "crea", PREVIEW), module.guided.Turn(), proof, lambda _: ""
        )

    written = "\n".join(proof.report.lines)
    assert asked == [], "nobody is asked to create a policy after a preview that failed"
    assert "ha creato una policy" not in written, written
    assert "policy.would_not_start: vault.no_entry" in written
    assert "nessuna policy è nata" in written


def test_an_output_without_not_created_and_without_an_error_says_just_that(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = script()
    monkeypatch.setattr(module.base, "run", printing(0, out="something else\n"))
    proof = a_proof(tmp_path, Api([], []), [])

    with pytest.raises(module.base.Stop):
        module.a_block(
            9, module.base.Block(9, "crea", PREVIEW), module.guided.Turn(), proof, lambda _: ""
        )

    written = "\n".join(proof.report.lines)
    assert "ha creato una policy" not in written, written
    assert "not created" in written


def test_a_preview_that_created_a_policy_says_so(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The case that keeps its words: one more live policy after a preview."""
    module = script()
    monkeypatch.setattr(module.base, "run", printing(0, out="not created\n"))
    born = [{"id": "p-1", "short": "p1", "state": "LIVE"}]
    proof = a_proof(tmp_path, Api([], born), [])

    with pytest.raises(module.base.Stop):
        module.a_block(
            9, module.base.Block(9, "crea", PREVIEW), module.guided.Turn(), proof, lambda _: ""
        )

    assert "l'anteprima ha creato una policy" in "\n".join(proof.report.lines)


def test_a_preview_that_exits_with_an_error_without_saying_ela_is_still_an_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The exit code decides for ``crea`` too: «not created» on stdout, an exit of 1, no policy."""
    module = script()
    monkeypatch.setattr(module.base, "run", printing(1, out="not created\n", err="boom\n"))
    asked: list[str] = []
    proof = a_proof(tmp_path, Api([], []), asked)

    with pytest.raises(module.base.Stop):
        module.a_block(
            9, module.base.Block(9, "crea", PREVIEW), module.guided.Turn(), proof, lambda _: ""
        )

    written = "\n".join(proof.report.lines)
    assert asked == [] and "ha creato una policy" not in written
    assert "nessuna policy è nata" in written


def test_an_eye_that_finds_a_screen_ended_in_an_error_asks_nothing(tmp_path: Path) -> None:
    """The second line (decision 18 (c)): a script that caught the ``Stop`` of the screen would
    still find the mark on the turn, and the eye would not be asked."""
    module = script()
    asked: list[str] = []
    proof = a_proof(tmp_path, Api([]), asked)
    turn = module.guided.Turn(failed_screen=ERROR)

    with pytest.raises(module.base.Stop):
        module.a_block(9, module.base.Block(9, "occhio", "È ciò che vuoi?"), turn, proof, str)

    assert asked == []
