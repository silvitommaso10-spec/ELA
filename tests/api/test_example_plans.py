"""Every plan the guide and the scripts send passes the hand route's validation (M14.2, decision 8).

Since ADR 0058 the hand route refuses a step the executor would refuse — not exactly one capability
of the catalogue, no success condition, one outside its verifier's vocabulary — with a ``422``. A
plan of ``docs/examples/`` that the new check refused would fail in Tommaso's hands at the first
``ela task plan`` of a proof, so every one of them is **sent**: the files are found by a glob, not
by a list, and a plan added tomorrow is checked without anybody remembering to add it here.

The glob covers what the guide and the scripts send only if they send nothing else: the second
test reads every ``--file`` they write, and each is a file of ``docs/examples/`` or a copy the
guide makes of one with ``sed`` — which changes an argument, never a step's shape.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from httpx import AsyncClient

from ela.domain import TaskState

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "docs" / "examples"
PLANS = sorted(EXAMPLES.glob("*.json"))
SENDERS = (ROOT / "docs" / "GETTING_STARTED.md", *sorted((ROOT / "scripts").glob("*.py")))

FILE = re.compile(r"--file[ =]+([\w./~<>-]+\.json)")
COPY = re.compile(r"sed '[^']*' (docs/examples/[\w-]+\.json) > ([\w./-]+\.json)")


def test_the_glob_finds_the_plans() -> None:
    assert len(PLANS) >= 20, PLANS


@pytest.mark.parametrize("path", PLANS, ids=[path.name for path in PLANS])
async def test_the_example_passes_the_hand_route(client: AsyncClient, path: Path) -> None:
    task_id = (await client.post("/tasks", json={"text": path.stem})).json()["id"]

    response = await client.post(
        f"/tasks/{task_id}/plan", json=json.loads(path.read_text(encoding="utf-8"))
    )

    assert response.status_code == 200, response.text
    assert response.json()["state"] == TaskState.QUEUED.value


def sent() -> dict[str, str]:
    """Every plan file a sender names after ``--file``, with the example it comes from."""
    found: dict[str, str] = {}
    for sender in SENDERS:
        text = sender.read_text(encoding="utf-8")
        copies = dict((target, source) for source, target in COPY.findall(text))
        for name in FILE.findall(text):
            found[name] = copies.get(name, name)
    return found


def test_the_guide_and_the_scripts_send_only_the_examples_or_copies_of_them() -> None:
    plans = sent()

    assert plans, "the guide sends plans with --file: a pattern that finds none is broken"
    outside = {name: source for name, source in plans.items() if not source.startswith("docs/")}
    assert outside == {}
    missing = sorted(source for source in plans.values() if not (ROOT / source).is_file())
    assert missing == []
    assert {ROOT / source for source in plans.values()} <= set(PLANS)


def test_a_copy_the_guide_makes_is_found_with_its_source() -> None:
    assert sent()["/tmp/eco.json"] == "docs/examples/terminal-echo.json"
    assert sent()["/tmp/fs-overwrite.json"] == "docs/examples/fs-write.json"
