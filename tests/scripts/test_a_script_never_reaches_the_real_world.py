"""**A script of ``scripts/`` never reaches the real world in a test that did not replace it**
(M13.17b): the fences of ``tests/script_fences.py`` — a launch, a connection, the resolution of a
name —, installed once per process by ``tests/conftest.py``, for every script of ``scripts/`` and
not by the prefix of its name.

**Nothing here can reach the real world even with the fences broken** — the run of a mutant
breaks them: a launch finds a fake program first on ``PATH``, in a folder of the test **outside
pytest's temporary folder** (answer 35: one inside it would be let through as derived); a
connection finds a listener the test started **in a child process** — another process, as a
provider and the real ELA are —, which leaves a mark and closes; no name of a real site is
resolved. What would have happened is read from the mark.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"

LISTENER = """
import pathlib, socket, sys
mark = pathlib.Path(sys.argv[1])
listening = socket.socket()
listening.bind(("127.0.0.1", 0))
listening.listen()
print(listening.getsockname()[1], flush=True)
while True:
    connection, _ = listening.accept()
    mark.write_text("arrived", encoding="utf-8")
    connection.close()
"""
"""A listener of another process: whatever connects leaves the mark, and is closed at once."""


def loaded(name: str) -> ModuleType:
    """A script of ``scripts/``, loaded from its file, as its own tests load it."""
    spec = importlib.util.spec_from_file_location(f"_fences_{name}", SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def outside_pytest(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A folder of the test **outside** ``getbasetemp()`` — and the precondition said, not
    assumed (answer 35 (a))."""
    folder = Path(tempfile.mkdtemp(prefix="ela-finto-"))
    base = tmp_path_factory.getbasetemp().resolve()
    assert not folder.resolve().is_relative_to(base), "the fake must lie outside pytest's folder"
    return folder


@pytest.fixture
def a_fake_ps(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    folder = outside_pytest(tmp_path_factory)
    mark = tmp_path / "ps-started"
    fake = folder / "ps"
    fake.write_text(f"#!/bin/sh\ntouch {mark}\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ.get('PATH', '')}")
    yield mark
    shutil.rmtree(folder, ignore_errors=True)


@pytest.fixture(scope="module")
def a_listener_of_another_process(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[int, Path]]:
    mark = tmp_path_factory.mktemp("listener") / "arrived"
    child = subprocess.Popen(  # noqa: S603 — this interpreter, and the listener above
        [sys.executable, "-c", LISTENER, str(mark)], stdout=subprocess.PIPE, text=True
    )
    try:
        assert child.stdout is not None
        yield int(child.stdout.readline()), mark
    finally:
        child.kill()
        child.wait()


def caught(what: Callable[[], Any]) -> BaseException | None:
    """``what()``, and what it raised — a refusal is a ``BaseException``."""
    try:
        what()
    except BaseException as raised:  # noqa: BLE001 — the refusal is one on purpose
        return raised
    return None


# ----------------------------------------------------------------------------------------
# Decision 8 (a): a launch of a script that is not a proof
# ----------------------------------------------------------------------------------------


def test_a_launch_of_a_measure_s_script_is_refused_before_it_starts(a_fake_ps: Path) -> None:
    """``descendants()`` of ``misura_m14_3.py`` launches ``ps`` by name: the fake is first on
    ``PATH``."""
    measure = loaded("misura_m14_3")

    refusal = caught(lambda: measure.descendants(os.getpid()))

    assert not a_fake_ps.exists(), "the script of a measure started a program in a test"
    assert type(refusal).__name__ == "LaunchFromAScript"


# ----------------------------------------------------------------------------------------
# Decision 8 (b): a call to a provider, from a fixture of a module
# ----------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def the_gateway_from_a_module_fixture(
    a_listener_of_another_process: tuple[int, Path],
) -> tuple[BaseException | None, Path]:
    """``gateway()`` of ``misura_m14_3.py`` forwards to its upstream — here the listener of
    another process, as the provider is —, called while a fixture of a module is set up: before
    any fixture of a function."""
    from starlette.requests import Request

    port, mark = a_listener_of_another_process
    measure = loaded("misura_m14_3")
    upstream = f"http://127.0.0.1:{port}"
    world = measure.World(token="t" * 43, key="k" * 40, upstream=upstream, browser=None)
    body = json.dumps({"model": "claude-haiku-4-5", "max_tokens": 10, "messages": []}).encode()

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/messages",
            "query_string": b"",
            "headers": [(b"x-api-key", world.token.encode())],
        },
        receive,
    )
    return caught(lambda: asyncio.run(measure.gateway(world, request))), mark


def test_a_call_to_a_provider_from_a_module_fixture_is_refused(
    the_gateway_from_a_module_fixture: tuple[BaseException | None, Path],
) -> None:
    refusal, mark = the_gateway_from_a_module_fixture

    assert not mark.exists(), "the script of a measure reached a listener from a module fixture"
    assert type(refusal).__name__ == "ConnectionFromAScript"


# ----------------------------------------------------------------------------------------
# Decision 8 (c): a connection with urllib from a script
# ----------------------------------------------------------------------------------------


def test_a_connection_of_urllib_from_a_script_is_refused(
    a_listener_of_another_process: tuple[int, Path],
) -> None:
    """``answers()`` of ``prova_m13_1c_m13_1d_m9_6.py`` opens a site with ``urllib``: here the
    listener of another process, by its address — no name is resolved."""
    from tests.docs.test_prova_eyes import loaded as a_proof  # its siblings hidden while it loads

    port, mark = a_listener_of_another_process
    mark.unlink(missing_ok=True)
    proof = a_proof(SCRIPTS / "prova_m13_1c_m13_1d_m9_6.py")

    refusal = caught(lambda: proof.answers(f"127.0.0.1:{port}"))

    assert not mark.exists(), "the script of a proof reached a listener of another process"
    assert type(refusal).__name__ == "ConnectionFromAScript"
