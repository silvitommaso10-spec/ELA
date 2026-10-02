"""The guide's §22, steps 2–6, run by the script of the branch on an ELA in this process.

``scripts/prova_m13_1c_m13_1d_m9_6.py`` runs §22 on the Mac against the real ELA; here **the same
script** — its ``a_step``, its comparison and its three checks of its own — runs the same lines
against an ELA built by ``build``, with the browser of ``ela.testing`` set to what the real sites do
and a voice configured. The one thing replaced is how a line reaches ``ela``: through Typer in this
process instead of a shell. So what §22 expects is what the CLI prints, and a line of the guide
that the CLI no longer prints stops the suite here, not on the Mac.

Steps 7 and 8 are not run: one speaks, the other opens a page, and both ask Tommaso's eye.
"""

from __future__ import annotations

import asyncio
import importlib.util
import io
import shlex
import subprocess
import sys
from functools import cache
from pathlib import Path
from types import ModuleType

import pytest
from typer.testing import CliRunner

from ela.cli.app import app as ela_app
from ela.testing.fakes import FakePage
from tests.api.reasons import World, opened

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prova_m13_1c_m13_1d_m9_6.py"
CONFIGURED = "a-voice-of-my-own"
RUN_HERE = (2, 3, 4, 5, 6)
LEFT = FakePage(status=None, left="https://example.org/")
"""What httpbin.org does for the plan of step 3: the page goes to a site nobody declared."""


@cache
def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("prova_m13_1c_m13_1d_m9_6", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def in_this_process(line: str) -> subprocess.CompletedProcess[str]:
    """``uv run ela …`` through Typer, the plans read from the repository and not from ``cwd``."""
    words = shlex.split(line)
    assert words[:3] == ["uv", "run", "ela"], line
    arguments = [
        str(ROOT / word) if word.startswith("docs/examples/") else word for word in words[3:]
    ]
    result = CliRunner().invoke(ela_app, arguments)
    return subprocess.CompletedProcess(words, result.exit_code, result.stdout, result.stderr)


def never_asked(question: str) -> str:
    raise AssertionError(f"steps 2–6 ask nothing of the eye, and this asked {question!r}")


async def ran(w: World, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Steps 2–6 of §22 through the script, and the lines its report wrote."""
    module = script()
    monkeypatch.setattr(module.base, "run", in_this_process)
    text = module.GUIDE.read_text(encoding="utf-8")
    todo = module.base.steps(module.base.blocks(text, module.HEADING))
    report = module.base.Report(io.StringIO())
    proof = module.Proof(None, report, never_asked, module.the_guides_question(text), CONFIGURED)

    def walk() -> None:
        for number in RUN_HERE:
            if number == 3:
                w.browser.page = LEFT
            module.a_step(number, todo[number], proof)

    # ``a_step`` is synchronous and the CLI reaches the application on this loop: off the loop.
    await asyncio.to_thread(walk)
    assert report.lines, "the script said nothing"
    return list(report.lines)


async def test_steps_2_to_6_pass_with_what_the_cli_prints(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with opened(monkeypatch, tmp_path, ELA_ELEVENLABS_VOICE_ID=CONFIGURED) as w:
        lines = await ran(w, monkeypatch)

    failed = [line for line in lines if "FALLITO" in line]
    assert not failed, "\n".join(lines)
    passed = [line for line in lines if "PASSATO" in line]
    for step in (2, 3, 4):
        assert any(
            line.startswith(f"[{step}] PASSATO: le corse dicono la stessa ragione")
            for line in passed
        ), step
    assert "[4] PASSATO: la domanda del task ha la forma del blocco di §6" in passed
    assert "[6] PASSATO: «uv run ela voice» esce con 0" in passed
    assert "[5] PASSATO: l'uscita è quella attesa" in passed
