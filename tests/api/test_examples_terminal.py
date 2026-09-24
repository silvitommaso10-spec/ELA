"""The six plans of M13.2 are plans ELA really runs, on real programs (ADR 0047).

Sent byte for byte, like every example (``test_examples.py``), to an ELA whose
``ELA_TERMINAL_PROGRAMS`` is the line ``GETTING_STARTED.md`` §16 tells the reader to write — without
``usr/bin/whoami``, which is the program nobody declared. The children are real: ``/bin/echo``
prints, ``/usr/bin/seq`` prints more than the ceiling, ``/usr/bin/env`` shows what a child
receives. ``/usr/bin/time`` may be missing on a runner's image, and the test that needs it says so
with a ``skipif`` read from the filesystem (ADR 0031 §6) — a missing entry does not stop ELA
(Domanda 3), which is why the others still run there.

Three facts no example shows are asserted here on real children too, with plans written in the
test: what a program prints on stderr and the folder it starts from never reach the audit, and a
child with no ``cwd`` starts from the scope's folder.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from ela.composition.settings import Settings
from ela.domain import TaskState
from ela.tools.terminal import PROGRAM, RUNS
from tests.composition.support import declare

EXAMPLES = Path(__file__).resolve().parents[2] / "docs" / "examples"
GUIDE = EXAMPLES.parent / "GETTING_STARTED.md"
DECLARED = ["bin/echo", "usr/bin/seq", "usr/bin/time", "usr/bin/printf", "usr/bin/env"]
"""The line of the guide, step 2 of §16 — read from it by the last test of this file."""
MARKER = "girasole-7431"


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    """The ELA of the guide's §16: the programs declared, a short timeout, the scope's folder."""
    declare(
        monkeypatch,
        tmp_path,
        ELA_TERMINAL_PROGRAMS=json.dumps(DECLARED),
        ELA_TERMINAL_TIMEOUT_SECONDS="3",
    )
    loaded = Settings.load()
    (loaded.filesystem.root / "ELA").mkdir()
    return loaded


def plan(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))
    return loaded


async def asked(client: AsyncClient, name: str, text: str) -> dict[str, Any]:
    task_id = (await client.post("/tasks", json={"text": text})).json()["id"]
    planned = await client.post(f"/tasks/{task_id}/plan", json=plan(name))
    assert planned.status_code == 200, planned.text
    await client.post(f"/tasks/{task_id}/run")
    waiting = (await client.get("/approvals")).json()
    assert len(waiting) == 1, waiting
    question: dict[str, Any] = waiting[0]
    question["task_id"] = task_id
    return question


async def answered(client: AsyncClient, question: dict[str, Any]) -> dict[str, Any]:
    await client.post(f"/tasks/{question['task_id']}/approve", json={"approval_id": question["id"]})
    run: dict[str, Any] = (await client.post(f"/tasks/{question['task_id']}/run")).json()
    return run


async def outcome(client: AsyncClient, task_id: str) -> dict[str, Any]:
    results = (await client.get(f"/tasks/{task_id}/results")).json()
    final: dict[str, Any] = results[-1]
    return final


def scope_of(settings: Settings) -> str:
    return str(settings.filesystem.root.resolve() / "ELA")


async def test_the_echo_is_asked_about_with_what_will_really_run(
    client: AsyncClient, settings: Settings
) -> None:
    """Decision 12: the program in full and the file it leads to, the folder, every argument, the
    timeout and the expected code — facts read from the machine, not from the plan."""
    question = await asked(client, "terminal-echo.json", "far girare echo")

    assert question["capability_id"] == "terminal.run"
    assert question["risk"] == "HIGH"
    assert question["target"] == "/bin/echo"
    assert question["label"] == PROGRAM
    assert question["runs"] == os.path.realpath("/bin/echo")
    assert question["arguments"] == ["la parola di prova è", MARKER]
    assert question["folder"] == scope_of(settings)
    assert question["timeout_seconds"] == 3
    assert question["expect_exit"] == 0
    assert question["does"] == RUNS


async def test_the_echo_prints_in_the_result_and_its_words_never_reach_the_audit(
    client: AsyncClient,
) -> None:
    """Criterion 12: the marker is in the result and nowhere in the trail; the program is."""
    question = await asked(client, "terminal-echo.json", "far girare echo")

    run = await answered(client, question)

    assert run["task"]["state"] == TaskState.COMPLETED.value, run
    result = await outcome(client, question["task_id"])
    assert result["output"]["stdout"]["head"] == f"la parola di prova è {MARKER}\n"
    assert result["output"]["exit_code"] == 0
    trail = json.dumps((await client.get("/audit")).json())
    assert MARKER not in trail
    assert "bin/echo" in trail


async def test_the_echo_spends_its_yes_and_the_audit_carries_its_numbers(
    client: AsyncClient,
) -> None:
    """«La ripresa»: the HIGH grant is spent before the action for the terminal too (criterion
    20); and the numbers of the command are the only thing of it the audit holds (criterion 12)."""
    question = await asked(client, "terminal-echo.json", "far girare echo")
    await answered(client, question)

    task_id = question["task_id"]
    results = (await client.get(f"/tasks/{task_id}/results")).json()
    events = (await client.get("/audit", params={"task_id": task_id})).json()
    (granted,) = [e for e in events if e["event_type"] == "AUTHORIZATION_GRANTED"]
    (executed,) = [e for e in events if e["event_type"] == "TOOL_EXECUTED"]
    printed = len(f"la parola di prova è {MARKER}\n".encode())

    assert [r["status"] for r in results] == ["STARTED", "SUCCEEDED"]
    assert [r["authorization_id"] for r in results] == [granted["authorization_id"]] * 2
    assert executed["authorization_id"] == granted["authorization_id"]
    assert executed["payload"]["uses"] == 1
    assert executed["payload"]["numbers"] == {
        "argument_count": 2,
        "exit_code": 0,
        "signal": None,
        "stdout.shown": printed,
        "stdout.total": printed,
        "stderr.shown": 0,
        "stderr.total": 0,
    }


async def test_a_program_nobody_declared_is_denied_before_anybody_is_asked(
    client: AsyncClient,
) -> None:
    """Criterion 2: ``DENIED`` with ``Rule.SCOPE``, no approval, nothing run."""
    task_id = (await client.post("/tasks", json={"text": "chi sono"})).json()["id"]
    await client.post(f"/tasks/{task_id}/plan", json=plan("terminal-not-declared.json"))

    run = (await client.post(f"/tasks/{task_id}/run")).json()

    assert run["task"]["state"] == TaskState.DENIED.value, run
    assert (await client.get("/approvals")).json() == []
    assert (await client.get(f"/tasks/{task_id}/results")).json() == []
    events = (await client.get("/audit")).json()
    decided = [e for e in events if e["event_type"] == "PERMISSION_DECIDED"][-1]
    assert decided["payload"]["rule"] == "SCOPE"
    assert "usr/bin/whoami" in decided["payload"]["reason"]


async def test_an_output_longer_than_the_ceiling_keeps_its_head_and_its_tail(
    client: AsyncClient,
) -> None:
    """Criterion 3, on a real ``seq``: 588 895 bytes, and the result says where it cut."""
    question = await asked(client, "terminal-long-output.json", "contare")
    run = await answered(client, question)

    assert run["task"]["state"] == TaskState.COMPLETED.value, run
    stdout = (await outcome(client, question["task_id"]))["output"]["stdout"]
    assert stdout["total"] == 588895
    assert stdout["head"].startswith("1\n2\n3\n")
    assert stdout["tail"].endswith("99999\n100000\n")
    assert stdout["shown"] <= 65536
    assert stdout["missing"] == stdout["total"] - stdout["shown"]
    assert stdout["cut_after"] == len(stdout["head"].encode())


@pytest.mark.skipif(not Path("/usr/bin/time").exists(), reason="/usr/bin/time is not here")
async def test_a_program_that_does_not_end_is_stopped_with_its_grandchild(
    client: AsyncClient,
) -> None:
    """Criterion 10 on the plan of the guide: ``time`` is the child, ``sleep`` the grandchild."""
    before = sleeping()
    question = await asked(client, "terminal-timeout.json", "dormire")
    run = await answered(client, question)

    assert run["task"]["state"] == TaskState.FAILED.value, run
    result = await outcome(client, question["task_id"])
    assert result["error"]["code"] == "terminal.timeout"
    assert result["output"]["ended"] == "stopped_by_ela"
    assert sleeping() <= before, "the grandchild outlived the answer"


def sleeping() -> set[int]:
    """The processes whose whole command line is the grandchild of the plan — the ``pgrep`` the
    guide tells the reader to run. No other test of the suite starts ``/bin/sleep 600``."""
    found = subprocess.run(
        ["pgrep", "-f", "-x", "/bin/sleep 600"], capture_output=True, text=True, check=False
    )
    return {int(pid) for pid in found.stdout.split()}


async def test_a_control_sequence_is_kept_in_the_result_as_the_program_printed_it(
    client: AsyncClient,
) -> None:
    """What the surfaces do with it is theirs (decision 13): the result keeps what was printed."""
    question = await asked(client, "terminal-escape.json", "rosso")
    run = await answered(client, question)

    assert run["task"]["state"] == TaskState.COMPLETED.value, run
    head = (await outcome(client, question["task_id"]))["output"]["stdout"]["head"]
    assert "\x1b[31mROSSO\x1b[0m" in head


async def test_a_child_receives_the_closed_environment_whatever_the_core_has(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 4 on the plan of the guide: a variable exported where ELA runs does not arrive."""
    monkeypatch.setenv("ELA_API_TOKEN_DI_PROVA", "non-deve-arrivare")

    question = await asked(client, "terminal-env.json", "l'ambiente")
    run = await answered(client, question)

    assert run["task"]["state"] == TaskState.COMPLETED.value, run
    head = (await outcome(client, question["task_id"]))["output"]["stdout"]["head"]
    names = sorted(line.partition("=")[0] for line in head.splitlines())
    assert names == ["HOME", "LANG", "PATH", "TMPDIR"]


def test_the_programs_of_the_plans_are_the_line_the_guide_tells_you_to_write() -> None:
    """The fixture declares what §16 says, and every plan but one names a declared program."""
    guide = GUIDE.read_text(encoding="utf-8")
    line = f"ELA_TERMINAL_PROGRAMS={json.dumps(DECLARED, separators=(',', ':'))}"

    assert line in guide
    for path in sorted(EXAMPLES.glob("terminal-*.json")):
        (step,) = plan(path.name)["steps"]
        declared = step["arguments"]["program"] in DECLARED
        assert declared is (path.name != "terminal-not-declared.json"), path.name
        assert "terminal.exit_code_matches" in step["success_conditions"], path.name
        assert not step["arguments"]["program"].startswith("/"), "relative to /, as the scope"


def written(program: str, args: list[str], **more: Any) -> dict[str, Any]:
    """A plan of one command, written here: the examples are the guide's, and these facts are not
    in the guide. The code is not a condition, so a program that fails still completes."""
    return {
        "goal": "un comando",
        "steps": [
            {
                "id": "e7a3c915-2b64-4d08-9f71-0000000000ee",
                "goal": "un comando scritto dal test",
                "required_capabilities": ["terminal.run"],
                "arguments": {"program": program, "args": args, "purpose": "il test", **more},
                "risk": "HIGH",
                "expected_result": "finisce",
                "success_conditions": ["terminal.program_unchanged", "terminal.output_whole"],
                "requires_authorization": True,
            }
        ],
    }


async def ran(client: AsyncClient, body: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    task_id = (await client.post("/tasks", json={"text": "un comando"})).json()["id"]
    assert (await client.post(f"/tasks/{task_id}/plan", json=body)).status_code == 200
    await client.post(f"/tasks/{task_id}/run")
    (question,) = (await client.get("/approvals")).json()
    question["task_id"] = task_id
    run = await answered(client, question)
    assert run["task"]["state"] == TaskState.COMPLETED.value, run
    return task_id, await outcome(client, task_id)


async def test_what_a_program_says_on_stderr_and_where_it_started_never_reach_the_audit(
    client: AsyncClient, settings: Settings
) -> None:
    """Criterion 12, the two halves the echo does not show: ``seq`` refuses the marker **on
    stderr**, from a folder whose name is a second marker, and neither is anywhere in the trail."""
    folder = "cartella-girasole-9127"
    (settings.filesystem.root / "ELA" / folder).mkdir()

    _, result = await ran(client, written("usr/bin/seq", [MARKER], cwd=folder))

    assert MARKER in result["output"]["stderr"]["head"], "the precondition: it is on stderr"
    trail = json.dumps((await client.get("/audit")).json())
    assert MARKER not in trail
    assert folder not in trail


async def test_a_child_with_no_folder_starts_from_the_scope_and_never_from_ela_s(
    client: AsyncClient, settings: Settings
) -> None:
    """Criterion 9 on a real child reached through the tool: ``env`` runs ``/bin/pwd``, which
    asks the kernel — the closed environment has no ``PWD`` to repeat."""
    _, result = await ran(client, written("usr/bin/env", ["/bin/pwd"]))

    printed = result["output"]["stdout"]["head"].strip()
    assert printed == scope_of(settings)
    assert printed != str(Path.cwd().resolve())
